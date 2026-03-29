import discord
from discord.ext import commands
import os
from gtts import gTTS
from typing import Optional

# Importamos el gestor de base de datos
from utils import database_manager as db

class TTSCog(commands.Cog, name="Texto a Voz"):
    """Comandos para que el bot hable y lea tus mensajes."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context):
        """Check global para este Cog."""
        if not ctx.guild: return True
        settings = await db.get_cached_server_settings(ctx.guild.id)
        if settings and not settings.get('tts_enabled', 1):
            await ctx.send("❌ El módulo de **Texto a Voz** está desactivado. Un administrador debe habilitarlo en el dashboard.", ephemeral=True)
            return False
        return True

    # --- Las funciones de base de datos se han eliminado de aquí ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        
        # USAMOS CACHÉ GLOBAL DE SETTINGS
        settings = await db.get_cached_server_settings(message.guild.id)
        if not settings or not settings.get('tts_enabled', 1): return
        
        if message.channel.id != settings.get('tts_channel_id'): # Asumimos que guardaremos tts_channel_id en server_settings
            # Fallback legacy check
            active_channel_row = await db.fetchone("SELECT text_channel_id FROM tts_active_channels WHERE guild_id = ?", (message.guild.id,))
            if not active_channel_row or message.channel.id != active_channel_row['text_channel_id']: return
        
        vc = message.guild.voice_client
        if not vc or not vc.is_connected() or vc.is_playing(): return
        if not message.author.voice or message.author.voice.channel != vc.channel: return
        
        # Idioma desde tabla settings (preferido) o tabla legacy
        lang_code = settings.get('tts_lang', 'es') if settings else 'es'
        if not settings or 'tts_lang' not in settings:
            lang_row = await db.fetchone("SELECT lang FROM tts_guild_settings WHERE guild_id = ?", (message.guild.id,))
            if lang_row: lang_code = lang_row['lang']
        
        text_to_speak = message.clean_content
        if not text_to_speak: return
        
        try:
            # Archivo único por servidor para evitar choques en el mismo canal
            tts_file = f"tts_{message.guild.id}.mp3"
            
            def save_tts():
                tts = gTTS(text=text_to_speak, lang=lang_code, slow=False)
                tts.save(tts_file)
            await self.bot.loop.run_in_executor(None, save_tts)

            def cleanup(error):
                if os.path.exists(tts_file):
                    try: os.remove(tts_file)
                    except: pass

            source = discord.FFmpegPCMAudio(tts_file)
            vc.play(source, after=cleanup)
        except Exception as e:
            print(f"Error en TTS automático: {e}")

    @commands.hybrid_command(name='setup_tts', description="Configura el bot para leer mensajes en este canal.")
    @commands.has_permissions(manage_guild=True)
    async def setup_tts(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("Debes estar en un canal de voz para usar este comando.", ephemeral=True)
        channel = ctx.author.voice.channel
        vc = ctx.guild.voice_client
        if not vc:
            try:
                vc = await channel.connect()
            except Exception as e:
                return await ctx.send(f"❌ No pude conectarme a tu canal de voz: {e}", ephemeral=True)

        # Usamos el gestor de DB
        await db.execute("REPLACE INTO tts_active_channels (guild_id, text_channel_id) VALUES (?, ?)", (ctx.guild.id, ctx.channel.id))
        await ctx.send(f"✅ ¡Perfecto! A partir de ahora leeré los mensajes enviados en {ctx.channel.mention} (mientras no haya música).")

    @commands.hybrid_command(name='set_language_tts', description="Establece el idioma de TTS para el servidor.")
    @commands.has_permissions(manage_guild=True)
    @discord.app_commands.choices(idioma=[
        discord.app_commands.Choice(name="Español", value="es"),
        discord.app_commands.Choice(name="Inglés (EE.UU.)", value="en"),
        discord.app_commands.Choice(name="Japonés", value="ja"),
        discord.app_commands.Choice(name="Italiano", value="it"),
        discord.app_commands.Choice(name="Francés", value="fr"),
    ])
    async def set_language_tts(self, ctx: commands.Context, idioma: discord.app_commands.Choice[str]):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        # Usamos el gestor de DB
        await db.execute("REPLACE INTO tts_guild_settings (guild_id, lang) VALUES (?, ?)", (ctx.guild.id, idioma.value))
        await ctx.send(f"✅ El idioma de TTS ha sido establecido a **{idioma.name}**.")

async def setup(bot: commands.Bot):
    await bot.add_cog(TTSCog(bot))
