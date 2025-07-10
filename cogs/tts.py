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

    # --- Las funciones de base de datos se han eliminado de aquí ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        
        # Usamos el gestor de DB
        active_channel_row = await db.fetchone("SELECT text_channel_id FROM tts_active_channels WHERE guild_id = ?", (message.guild.id,))
        active_channel_id = active_channel_row['text_channel_id'] if active_channel_row else None
        
        if not active_channel_id or message.channel.id != active_channel_id: return
        
        music_cog = self.bot.get_cog("Música")
        if not music_cog or (music_cog.get_guild_state(message.guild.id).current_song is not None): return
        
        vc = message.guild.voice_client
        if not vc or not vc.is_connected() or vc.is_playing(): return
        if not message.author.voice or message.author.voice.channel != vc.channel: return
        
        # Usamos el gestor de DB
        lang_row = await db.fetchone("SELECT lang FROM tts_guild_settings WHERE guild_id = ?", (message.guild.id,))
        lang_code = lang_row['lang'] if lang_row else 'es'
        
        text_to_speak = message.clean_content
        if not text_to_speak: return
        
        try:
            tts_file = f"tts_{message.guild.id}_{message.author.id}.mp3"
            
            def save_tts():
                tts = gTTS(text=text_to_speak, lang=lang_code, slow=False)
                tts.save(tts_file)
            await self.bot.loop.run_in_executor(None, save_tts)

            source = discord.FFmpegPCMAudio(tts_file)
            vc.play(source, after=lambda e: os.remove(tts_file) if os.path.exists(tts_file) else None)
        except Exception as e:
            print(f"Error en TTS automático: {e}")

    @commands.hybrid_command(name='setup_tts', description="Configura el bot para leer mensajes en este canal.")
    @commands.has_permissions(manage_guild=True)
    async def setup_tts(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("Debes estar en un canal de voz para usar este comando.", ephemeral=True)
        music_cog = self.bot.get_cog("Música")
        if not music_cog: return await ctx.send("Error interno: no se pudo encontrar el cog de música.", ephemeral=True)
        
        channel = ctx.author.voice.channel
        if not (vc := await music_cog.ensure_voice_client(channel)):
            return await ctx.send("❌ No pude conectarme a tu canal de voz.", ephemeral=True)

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
