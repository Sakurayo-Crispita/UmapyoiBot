import discord
from discord.ext import commands
import sqlite3
import asyncio
import os
from gtts import gTTS

class TTSCog(commands.Cog, name="Texto a Voz"):
    """Comandos para que el bot hable y lea tus mensajes."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn = bot.db_conn
        self.cursor = self.conn.cursor()
        self.db_lock = bot.db_lock
        self.setup_tts_database()

    def setup_tts_database(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS tts_guild_settings (guild_id INTEGER PRIMARY KEY, lang TEXT NOT NULL DEFAULT 'es')''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS tts_active_channels (guild_id INTEGER PRIMARY KEY, text_channel_id INTEGER NOT NULL)''')
        self.conn.commit()
    
    # --- FUNCIONES SÍNCRONAS PARA LA BASE DE DATOS ---

    def _get_guild_lang_sync(self, guild_id: int) -> str:
        self.cursor.execute("SELECT lang FROM tts_guild_settings WHERE guild_id = ?", (guild_id,))
        result = self.cursor.fetchone()
        return result['lang'] if result else 'es'

    def _set_guild_lang_sync(self, guild_id: int, lang: str):
        self.cursor.execute("REPLACE INTO tts_guild_settings (guild_id, lang) VALUES (?, ?)", (guild_id, lang))
        self.conn.commit()

    def _set_active_channel_sync(self, guild_id: int, text_channel_id: int):
        self.cursor.execute("REPLACE INTO tts_active_channels (guild_id, text_channel_id) VALUES (?, ?)", (guild_id, text_channel_id))
        self.conn.commit()

    def _get_active_channel_sync(self, guild_id: int) -> int | None:
        self.cursor.execute("SELECT text_channel_id FROM tts_active_channels WHERE guild_id = ?", (guild_id,))
        result = self.cursor.fetchone()
        return result['text_channel_id'] if result else None

    # --- FUNCIONES ASÍNCRONAS (WRAPPERS) ---

    async def get_guild_lang(self, guild_id: int) -> str:
        async with self.db_lock:
            return await asyncio.to_thread(self._get_guild_lang_sync, guild_id)

    async def set_guild_lang(self, guild_id: int, lang: str):
        async with self.db_lock:
            await asyncio.to_thread(self._set_guild_lang_sync, guild_id, lang)

    async def set_active_channel(self, guild_id: int, text_channel_id: int):
        async with self.db_lock:
            await asyncio.to_thread(self._set_active_channel_sync, guild_id, text_channel_id)

    async def get_active_channel(self, guild_id: int) -> int | None:
        async with self.db_lock:
            return await asyncio.to_thread(self._get_active_channel_sync, guild_id)

    # --- LÓGICA Y COMANDOS ---
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        
        active_channel_id = await self.get_active_channel(message.guild.id)
        if not active_channel_id or message.channel.id != active_channel_id: return
        
        music_cog = self.bot.get_cog("Música")
        if not music_cog or (music_cog.get_guild_state(message.guild.id).current_song is not None): return
        
        vc = message.guild.voice_client
        if not vc or not vc.is_connected() or vc.is_playing(): return
        if not message.author.voice or message.author.voice.channel != vc.channel: return
        
        lang_code = await self.get_guild_lang(message.guild.id)
        text_to_speak = message.clean_content
        if not text_to_speak: return
        
        try:
            tts_file = f"tts_{message.guild.id}_{message.author.id}.mp3"
            
            # gTTS también puede ser bloqueante, así que lo movemos a un hilo
            def save_tts():
                tts = gTTS(text=text_to_speak, lang=lang_code, slow=False)
                tts.save(tts_file)
            await asyncio.to_thread(save_tts)

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

        await self.set_active_channel(ctx.guild.id, ctx.channel.id)
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
        await self.set_guild_lang(ctx.guild.id, idioma.value)
        await ctx.send(f"✅ El idioma de TTS ha sido establecido a **{idioma.name}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(TTSCog(bot))