import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import datetime
import random
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import aiohttp
import re
import sqlite3
import lyricsgenius
from enum import Enum
from dotenv import load_dotenv
from gtts import gTTS
from typing import Literal, Optional
import io

# --- CONFIGURACIÓN DE APIS Y CONSTANTES ---
load_dotenv()
GENIUS_API_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

DB_FILE = "bot_data.db"
CREAM_COLOR = discord.Color.from_str("#F0EAD6")

# --- CONFIGURACIÓN DEL BOT ---
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -ar 48000 -ac 2 -b:a 192k'
}
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'noplaylist': True,
    'cookiefile': 'cookies.txt',
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
}

# --- CLASE DE BOT PERSONALIZADA PARA MANEJAR DB ---
class UmapyoiBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db_conn: Optional[sqlite3.Connection] = None
        self.db_lock = asyncio.Lock()

    async def setup_hook(self):
        # Conectar a la base de datos y configurar para devolver filas tipo diccionario
        self.db_conn = sqlite3.connect(DB_FILE, timeout=10)
        self.db_conn.row_factory = sqlite3.Row
        print("Conexión a la base de datos establecida.")

        print('-----------------------------------------')
        print("Cargando Cogs...")
        await self.add_cog(MusicCog(self))
        await self.add_cog(UtilityCog(self))
        await self.add_cog(FunCog(self))
        # Pasar la conexión y el lock a los cogs que usan la DB
        await self.add_cog(EconomyCog(self, self.db_conn, self.db_lock))
        await self.add_cog(LevelingCog(self, self.db_conn, self.db_lock))
        await self.add_cog(TTSCog(self, self.db_conn, self.db_lock))
        await self.add_cog(ServerConfigCog(self, self.db_conn, self.db_lock))
        await self.add_cog(GamblingCog(self, self.db_conn, self.db_lock))
        print("Cogs cargados.")
        print("-----------------------------------------")
        print("Sincronizando comandos slash...")
        await self.tree.sync()
        print("¡Comandos sincronizados!")

    async def close(self):
        if self.db_conn:
            self.db_conn.close()
            print("Conexión a la base de datos cerrada.")
        await super().close()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.members = True

bot = UmapyoiBot(command_prefix='!', intents=intents, case_insensitive=True, help_command=None)


# --- CLASES DE ESTADO Y VISTAS DE LA INTERFAZ ---
class LoopState(Enum):
    OFF = 0
    SONG = 1
    QUEUE = 2

class GuildState:
    def __init__(self, guild_id: int):
        self.id = guild_id
        self.queue: list[dict] = []
        self.current_song: dict | None = None
        self.loop_state: LoopState = LoopState.OFF
        self.volume: float = 0.5
        self.history: list[dict] = []
        self.autoplay: bool = False
        self.active_panel: discord.Message | None = None

class HelpSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        options = [discord.SelectOption(label="Inicio", description="Vuelve al panel principal de ayuda.", emoji="🏠")]
        if bot.cogs:
            for cog_name, cog in bot.cogs.items():
                options.append(discord.SelectOption(label=cog_name, description=getattr(cog, "description", "Sin descripción."), emoji="➡️"))
        super().__init__(placeholder="Selecciona una categoría para ver los comandos...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_cog_name = self.values[0]
        embed = discord.Embed(title=f"📜 Ayuda de Umapyoi", color=CREAM_COLOR)
        if selected_cog_name == "Inicio":
            embed.description = "**🚀 Cómo empezar a escuchar música**\n`/play <nombre de la canción o enlace>`\n\n**❓ ¿Qué es Umapyoi?**\nUn bot de nueva generación con música, juegos, economía y mucho más. ¡Todo en uno!\n\n**🎛️ Categorías de Comandos:**"
            embed.set_image(url="https://i.imgur.com/WwexK3G.png")
            embed.set_footer(text="Gracias por elegir a Umapyoi ✨")
        else:
            cog = self.bot.get_cog(selected_cog_name)
            if cog:
                embed.title = f"Comandos de: {selected_cog_name}"
                description = ""
                for cmd in cog.get_commands():
                    if isinstance(cmd, commands.HybridCommand) and cmd.name != 'help':
                        description += f"**`/{cmd.name}`** - {cmd.description}\n"
                embed.description = description
        await interaction.response.edit_message(embed=embed)

class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=180)
        self.add_item(HelpSelect(bot))

class MusicPanelView(discord.ui.View):
    """Vista de panel de música independiente del contexto original."""
    def __init__(self, music_cog: "MusicCog"):
        super().__init__(timeout=None)
        self.music_cog = music_cog
        # Al crear la vista, nos aseguramos que los botones tengan el estilo correcto desde el principio
        # (Aunque el panel se crea con una interacción, es una buena práctica)
        # self._update_button_styles(None) # Esto no es necesario si el panel se crea después de la primera canción

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice or not interaction.guild.voice_client or interaction.user.voice.channel != interaction.guild.voice_client.channel:
            await interaction.response.send_message("Debes estar en el mismo canal de voz que yo para usar los botones.", ephemeral=True, delete_after=10)
            return False
        return True

    def _update_button_styles(self, interaction: discord.Interaction):
        """Prepara los estilos de los botones antes de enviar la actualización."""
        state = self.music_cog.get_guild_state(interaction.guild.id)

        # Actualizar botón de Loop
        loop_button: discord.ui.Button = discord.utils.get(self.children, custom_id='loop_button')
        if loop_button:
            if state.loop_state == LoopState.OFF: loop_button.style, loop_button.label, loop_button.emoji = discord.ButtonStyle.secondary, "Loop", "🔁"
            elif state.loop_state == LoopState.SONG: loop_button.style, loop_button.label, loop_button.emoji = discord.ButtonStyle.success, "Loop Song", "🔂"
            else: loop_button.style, loop_button.label, loop_button.emoji = discord.ButtonStyle.success, "Loop Queue", "🔁"

        # Actualizar botón de Autoplay
        autoplay_button: discord.ui.Button = discord.utils.get(self.children, custom_id='autoplay_button')
        if autoplay_button:
            autoplay_button.style = discord.ButtonStyle.success if state.autoplay else discord.ButtonStyle.secondary

        # Actualizar botón de Pausa/Reanudar
        pause_button: discord.ui.Button = discord.utils.get(self.children, custom_id='pause_resume_button')
        if pause_button and interaction.guild.voice_client:
            if interaction.guild.voice_client.is_paused(): pause_button.label, pause_button.emoji = "Reanudar", "▶️"
            else: pause_button.label, pause_button.emoji = "Pausa", "⏸️"

    async def _execute_command(self, interaction: discord.Interaction, command_name: str):
        """Función auxiliar para ejecutar comandos que no necesitan actualización de panel."""
        command = self.music_cog.bot.get_command(command_name)
        if not command: return await interaction.response.send_message("Error interno.", ephemeral=True, delete_after=5)

        ctx = await self.music_cog.bot.get_context(interaction.message)
        ctx.author = interaction.user
        ctx.interaction = interaction
        await command.callback(self.music_cog, ctx)

    # --- BOTONES ---

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="⏪", row=0, custom_id="previous_button")
    async def previous_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._execute_command(interaction, 'previous')

    @discord.ui.button(label="Pausa", style=discord.ButtonStyle.secondary, emoji="⏸️", row=0, custom_id="pause_resume_button")
    async def pause_resume_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        # El comando 'pause' envía su propia respuesta, así que lo ejecutamos
        await self._execute_command(interaction, 'pause')
        # Luego, actualizamos el panel para que el botón cambie de 'Pausa' a 'Reanudar'
        self._update_button_styles(interaction)
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="Saltar", style=discord.ButtonStyle.primary, emoji="⏭️", row=0, custom_id="skip_button")
    async def skip_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._execute_command(interaction, 'skip')

    @discord.ui.button(label="Barajar", style=discord.ButtonStyle.secondary, emoji="🔀", row=1, custom_id="shuffle_button")
    async def shuffle_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._execute_command(interaction, 'shuffle')

    @discord.ui.button(label="Loop", style=discord.ButtonStyle.secondary, emoji="🔁", row=1, custom_id="loop_button")
    async def loop_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        # Lógica del loop directamente aquí
        state = self.music_cog.get_guild_state(interaction.guild.id)
        if state.loop_state == LoopState.OFF:
            state.loop_state, msg = LoopState.SONG, 'Bucle de canción activado.'
        elif state.loop_state == LoopState.SONG:
            state.loop_state, msg = LoopState.QUEUE, 'Bucle de cola activado.'
        else:
            state.loop_state, msg = LoopState.OFF, 'Bucle desactivado.'
        
        # Actualizar la apariencia y responder
        self._update_button_styles(interaction)
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"🔁 {msg}", ephemeral=True, delete_after=5)

    @discord.ui.button(label="Autoplay", style=discord.ButtonStyle.secondary, emoji="🔄", row=1, custom_id="autoplay_button")
    async def autoplay_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        # Lógica del autoplay directamente aquí
        state = self.music_cog.get_guild_state(interaction.guild.id)
        state.autoplay = not state.autoplay
        status = "activado" if state.autoplay else "desactivado"

        # Actualizar la apariencia y responder
        self._update_button_styles(interaction)
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"🔄 Autoplay **{status}**.", ephemeral=True, delete_after=5)

    @discord.ui.button(label="Sonando", style=discord.ButtonStyle.primary, emoji="🎵", row=2, custom_id="nowplaying_button")
    async def nowplaying_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._execute_command(interaction, 'nowplaying')

    @discord.ui.button(label="Cola", style=discord.ButtonStyle.primary, emoji="🎶", row=2, custom_id="queue_button")
    async def queue_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._execute_command(interaction, 'queue')

    @discord.ui.button(label="Letra", style=discord.ButtonStyle.primary, emoji="🎤", row=2, custom_id="lyrics_button")
    async def lyrics_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._execute_command(interaction, 'lyrics')

    @discord.ui.button(label="Detener", style=discord.ButtonStyle.danger, emoji="⏹️", row=3, custom_id="stop_button")
    async def stop_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._execute_command(interaction, 'stop')

    @discord.ui.button(label="Desconectar", style=discord.ButtonStyle.danger, emoji="👋", row=3, custom_id="leave_button")
    async def leave_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._execute_command(interaction, 'leave')

# --- COG DE MÚSICA ---
class MusicCog(commands.Cog, name="Música"):
    """Comandos para reproducir música de alta calidad."""
    def __init__(self, bot: UmapyoiBot):
        self.bot = bot
        self.guild_states: dict[int, GuildState] = {}
        self.genius = lyricsgenius.Genius(GENIUS_API_TOKEN) if GENIUS_API_TOKEN else None
        self.voice_locks: dict[int, asyncio.Lock] = {}

    def get_guild_state(self, guild_id: int) -> GuildState:
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = GuildState(guild_id)
        return self.guild_states[guild_id]

    def get_voice_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self.voice_locks:
            self.voice_locks[guild_id] = asyncio.Lock()
        return self.voice_locks[guild_id]

    async def ensure_voice_client(self, channel: discord.VoiceChannel) -> discord.VoiceClient | None:
        lock = self.get_voice_lock(channel.guild.id)
        async with lock:
            vc = channel.guild.voice_client
            if not vc:
                try:
                    return await asyncio.wait_for(channel.connect(), timeout=15.0)
                except Exception as e:
                    print(f"Error al conectar a canal de voz: {e}")
                    return None
            if vc.channel != channel:
                await vc.move_to(channel)
            return vc

    async def send_response(self, ctx: commands.Context | discord.Interaction, content: str = None, embed: discord.Embed = None, ephemeral: bool = False, view: discord.ui.View = discord.utils.MISSING):
        """Helper para responder a un Contexto o una Interacción (versión corregida)."""
        interaction = ctx.interaction if isinstance(ctx, commands.Context) else ctx
        
        # Elige el método de respuesta correcto basado en el tipo de contexto.
        if interaction:
            # Si es una interacción (slash command o botón)
            if interaction.response.is_done():
                # Si ya se ha respondido (ej. con defer()), usamos followup
                await interaction.followup.send(content, embed=embed, ephemeral=ephemeral, view=view)
            else:
                # Si es la primera respuesta, usamos send_message
                await interaction.response.send_message(content, embed=embed, ephemeral=ephemeral, view=view)
        elif isinstance(ctx, commands.Context):
            # Si es un comando de prefijo, simplemente enviamos al canal
            await ctx.send(content, embed=embed, view=view)

    async def send_music_panel(self, ctx: commands.Context, song: dict):
        state = self.get_guild_state(ctx.guild.id)
        if state.active_panel:
            try: await state.active_panel.delete()
            except (discord.NotFound, discord.HTTPException): pass

        embed = discord.Embed(title="🎵 Reproduciendo Ahora 🎵", color=CREAM_COLOR)
        embed.description = f"**[{song.get('title', 'Título Desconocido')}]({song.get('webpage_url', '#')})**"
        embed.add_field(name="Pedido por", value=song['requester'].mention, inline=True)
        if duration := song.get('duration'):
            embed.add_field(name="Duración", value=str(datetime.timedelta(seconds=duration)), inline=True)
        if thumbnail_url := song.get('thumbnail'):
            embed.set_thumbnail(url=thumbnail_url)

        view = MusicPanelView(self)
        try:
            # Aseguramos que el panel se envíe al canal correcto (texto o interacción)
            target_channel = ctx.channel or (ctx.interaction and ctx.interaction.channel)
            if target_channel:
                state.active_panel = await target_channel.send(embed=embed, view=view)
        except Exception as e:
            print(f"Error al enviar panel de música: {e}")

    def play_next_song(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if state.current_song:
            if state.loop_state == LoopState.SONG: state.queue.insert(0, state.current_song)
            elif state.loop_state == LoopState.QUEUE: state.queue.append(state.current_song)
            state.history.append(state.current_song)
            if len(state.history) > 20: state.history.pop(0)

        if not state.queue:
            state.current_song = None
            if state.autoplay and state.history:
                last_song_title = state.history[-1]['title']
                self.bot.loop.create_task(self.play.callback(self, ctx, search_query=f"{last_song_title} mix"))
            else:
                self.bot.loop.create_task(self.disconnect_after_inactivity(ctx))
            return

        state.current_song = state.queue.pop(0)
        vc = ctx.guild.voice_client
        if isinstance(vc, discord.VoiceClient) and vc.is_connected():
            try:
                source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(state.current_song['url'], **FFMPEG_OPTIONS), volume=state.volume)
                vc.play(source, after=lambda e: self.handle_after_play(ctx, e))
                self.bot.loop.create_task(self.send_music_panel(ctx, state.current_song))
            except Exception as e:
                print(f"Error al reproducir: {e}")
                target_channel = ctx.channel or (ctx.interaction and ctx.interaction.channel)
                if target_channel:
                    self.bot.loop.create_task(target_channel.send('❌ Error al reproducir. Saltando.'))
                self.play_next_song(ctx)

    def handle_after_play(self, ctx: commands.Context, error: Exception | None):
        if error: print(f'Error after play: {error}')
        self.bot.loop.call_soon_threadsafe(self.play_next_song, ctx)

    async def disconnect_after_inactivity(self, ctx: commands.Context):
        await asyncio.sleep(120)
        lock = self.get_voice_lock(ctx.guild.id)
        async with lock:
            vc = ctx.guild.voice_client
            state = self.get_guild_state(ctx.guild.id)
            # Solo desconectar si no hay canción, ni en la cola, ni está pausado
            if vc and not vc.is_playing() and not vc.is_paused() and not state.queue:
                if state.active_panel:
                    try: await state.active_panel.delete()
                    except (discord.NotFound, discord.HTTPException): pass
                    state.active_panel = None
                await vc.disconnect()
                target_channel = ctx.channel or (ctx.interaction and ctx.interaction.channel)
                if target_channel:
                    await target_channel.send("👋 ¡Adiós! Desconectado por inactividad.")

    @commands.hybrid_command(name='join', description="Hace que el bot se una a tu canal de voz.")
    async def join(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await self.send_response(ctx, "Debes estar en un canal de voz para que pueda unirme.", ephemeral=True)
        channel = ctx.author.voice.channel
        vc = await self.ensure_voice_client(channel)
        if vc:
            await self.send_response(ctx, f"👋 ¡Hola! Me he unido a **{channel.name}**.", ephemeral=True)
        else:
            await self.send_response(ctx, "❌ No pude conectarme al canal de voz.", ephemeral=True)

    @commands.hybrid_command(name='leave', description="Desconecta el bot del canal de voz.")
    async def leave(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc:
            return await self.send_response(ctx, "No estoy en ningún canal de voz.", ephemeral=True)

        state = self.get_guild_state(ctx.guild.id)
        state.queue.clear()
        state.current_song = None
        state.autoplay = False
        state.loop_state = LoopState.OFF
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        if state.active_panel:
            try: await state.active_panel.delete()
            except (discord.NotFound, discord.HTTPException): pass
            state.active_panel = None

        await vc.disconnect()
        await self.send_response(ctx, "👋 ¡Adiós! Me he desconectado.", ephemeral=True)


    @commands.hybrid_command(name='play', aliases=['p'], description="Reproduce una canción o playlist.")
    async def play(self, ctx: commands.Context, *, search_query: str):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await self.send_response(ctx, "Debes estar en un canal de voz.", ephemeral=True)

        if ctx.interaction:
            await ctx.interaction.response.defer()

        channel = ctx.author.voice.channel
        vc = await self.ensure_voice_client(channel)
        if not vc:
            return await self.send_response(ctx, "❌ No pude conectarme al canal de voz.", ephemeral=True)

        if ctx.interaction:
            msg = await ctx.interaction.followup.send(f'🔎 Procesando: "**{search_query}**"...')
        else:
            msg = await ctx.send(f'🔎 Procesando: "**{search_query}**"...')

        state = self.get_guild_state(ctx.guild.id)
        try:
            # --- INICIO DE LA CORRECCIÓN ---
            # Determinar si la entrada es una URL o una búsqueda de texto
            is_url = re.match(r'https?://', search_query)
            search_term = search_query if is_url else f"ytsearch:{search_query}"
            # --- FIN DE LA CORRECCIÓN ---

            loop = self.bot.loop or asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                # Usar el término de búsqueda corregido
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(search_term, download=False))

            # Si es una URL y no una búsqueda de playlist, la info puede no estar en 'entries'
            if is_url and 'entries' not in info:
                 entries = [info]
            else:
                 entries = info.get('entries', [])

            if not entries:
                return await msg.edit(content="❌ No encontré nada con esa búsqueda.")
            
            songs_to_add = entries

            added_count = 0
            for entry in songs_to_add:
                if entry and entry.get('url'):
                    song_data = {
                        'title': entry.get('title', 'Título desconocido'),
                        'url': entry.get('url'),
                        'webpage_url': entry.get('webpage_url'),
                        'thumbnail': entry.get('thumbnail'),
                        'duration': entry.get('duration'),
                        'requester': ctx.author
                    }
                    state.queue.append(song_data)
                    added_count += 1

            if added_count > 0:
                playlist_msg = "de la playlist " if len(songs_to_add) > 1 and is_url else ""
                await msg.edit(content=f'✅ ¡Añadido{"s" if added_count > 1 else ""} {added_count} canci{"ón" if added_count == 1 else "ones"} {playlist_msg}a la cola!')
            else:
                await msg.edit(content="❌ No se pudieron procesar las canciones.")

            if not vc.is_playing() and not state.current_song:
                self.play_next_song(ctx)
        except Exception as e:
            await msg.edit(content=f'❌ Ocurrió un error al procesar tu solicitud: {e}')
            print(f"Error en Play: {e}")

    @commands.hybrid_command(name='skip', description="Salta la canción actual.")
    async def skip(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await self.send_response(ctx, "⏭️ Canción saltada.", ephemeral=True)
        else:
            await self.send_response(ctx, "No hay nada que saltar.", ephemeral=True)

    @commands.hybrid_command(name='stop', description="Detiene la reproducción y limpia la cola.")
    async def stop(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        vc = ctx.guild.voice_client
        if vc:
            state.queue.clear()
            state.current_song = None
            state.autoplay = False
            state.loop_state = LoopState.OFF
            vc.stop()
            if state.active_panel:
                try: await state.active_panel.delete()
                except (discord.NotFound, discord.HTTPException): pass
                state.active_panel = None
        await self.send_response(ctx, "⏹️ Reproducción detenida y cola limpiada.", ephemeral=True)

    @commands.hybrid_command(name='pause', description="Pausa o reanuda la canción actual.")
    async def pause(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
             return await self.send_response(ctx, "No hay nada para pausar o reanudar.", ephemeral=True)
        if vc.is_paused():
            vc.resume()
            await self.send_response(ctx, "▶️ Canción reanudada.", ephemeral=True)
        else:
            vc.pause()
            await self.send_response(ctx, "⏸️ Canción pausada.", ephemeral=True)

    @commands.hybrid_command(name='queue', aliases=['q'], description="Muestra la cola de canciones.")
    async def queue(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if not state.current_song and not state.queue:
            return await self.send_response(ctx, "La cola está vacía.", ephemeral=True)
        embed = discord.Embed(title="🎵 Cola de Música 🎵", color=CREAM_COLOR)
        if state.current_song:
            embed.add_field(name="Reproduciendo ahora", value=f"**[{state.current_song['title']}]({state.current_song.get('webpage_url', '#')})**", inline=False)
        if state.queue:
            next_songs = [f"`{i+1}.` {s['title']}" for i, s in enumerate(state.queue[:10])]
            embed.add_field(name="A continuación:", value="\n".join(next_songs), inline=False)
        if len(state.queue) > 10:
            embed.set_footer(text=f"Y {len(state.queue) - 10} más...")
        await self.send_response(ctx, embed=embed, ephemeral=True)

    @commands.hybrid_command(name='nowplaying', aliases=['np'], description="Muestra la canción que está sonando.")
    async def nowplaying(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if not state.current_song:
            return await self.send_response(ctx, "No hay ninguna canción reproduciéndose.", ephemeral=True)
        song = state.current_song
        embed = discord.Embed(title="🎵 Sonando Ahora", description=f"**[{song['title']}]({song.get('webpage_url', '#')})**", color=CREAM_COLOR)
        embed.set_footer(text=f"Pedida por: {song['requester'].display_name}")
        if song.get('thumbnail'):
            embed.set_thumbnail(url=song['thumbnail'])
        await self.send_response(ctx, embed=embed, ephemeral=True)

    @commands.hybrid_command(name='lyrics', description="Busca la letra de la canción actual.")
    async def lyrics(self, ctx: commands.Context):
        if not self.genius:
            return await self.send_response(ctx, "❌ La función de letras no está configurada.", ephemeral=True)
        state = self.get_guild_state(ctx.guild.id)
        if not state.current_song:
            return await self.send_response(ctx, "No hay ninguna canción reproduciéndose.", ephemeral=True)

        if ctx.interaction: await ctx.defer(ephemeral=True)
        song_title = re.sub(r'\(.*?lyric.*?\)|\[.*?video.*?\]', '', state.current_song['title'], flags=re.IGNORECASE).strip()
        try:
            song = await asyncio.to_thread(self.genius.search_song, song_title)
            if song and song.lyrics:
                lyrics_text = song.lyrics
                if len(lyrics_text) > 4000: lyrics_text = lyrics_text[:3997] + "..."
                embed = discord.Embed(title=f"🎤 Letra de: {song.title}", description=lyrics_text, color=CREAM_COLOR)
                embed.set_footer(text=f"Artista: {song.artist}")
                await self.send_response(ctx, embed=embed, ephemeral=True)
            else:
                await self.send_response(ctx, "❌ No se encontraron letras para esta canción.", ephemeral=True)
        except Exception as e:
            await self.send_response(ctx, f"❌ Ocurrió un error al buscar la letra: {e}", ephemeral=True)

    @commands.hybrid_command(name='shuffle', description="Mezcla la cola de canciones actual.")
    async def shuffle(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if not state.queue:
            return await self.send_response(ctx, "La cola está vacía, no hay nada que barajar.", ephemeral=True)
        random.shuffle(state.queue)
        await self.send_response(ctx, "🔀 ¡La cola ha sido barajada!", ephemeral=True)

    @commands.hybrid_command(name='previous', description="Reproduce la canción anterior del historial.")
    async def previous(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if len(state.history) < 2: # Necesita al menos la actual y una anterior
            return await self.send_response(ctx, "No hay historial suficiente para reproducir la canción anterior.", ephemeral=True)

        # Mover la canción actual de vuelta a la cola
        if state.current_song:
            state.queue.insert(0, state.current_song)

        # La última canción en el historial es la actual, la penúltima es la que queremos
        state.queue.insert(0, state.history[-2])
        # Quitar las dos últimas del historial para evitar duplicados al reproducir
        state.history = state.history[:-2]

        vc = ctx.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
             vc.stop() # Esto activará play_next_song, que reproducirá la canción que acabamos de insertar
        else:
             self.play_next_song(ctx) # Si no estaba sonando nada, iniciar la reproducción

        await self.send_response(ctx, "⏪ Reproduciendo la canción anterior.", ephemeral=True)

    @commands.hybrid_command(name='loop', description="Activa o desactiva la repetición (canción/cola).")
    async def loop(self, ctx: commands.Context):
        message = self._toggle_loop(ctx.guild.id)
        await self.send_response(ctx, message, ephemeral=True)

    @commands.hybrid_command(name='autoplay', description="Activa o desactiva el autoplay de canciones.")
    async def autoplay(self, ctx: commands.Context):
        message = self._toggle_autoplay(ctx.guild.id)
        await self.send_response(ctx, message, ephemeral=True)

# --- COG DE NIVELES ---
class LevelingCog(commands.Cog, name="Niveles"):
    """Comandos para ver tu nivel y competir en el ranking de XP."""
    def __init__(self, bot: UmapyoiBot, conn: sqlite3.Connection, lock: asyncio.Lock):
        self.bot = bot
        self.conn = conn
        self.cursor = self.conn.cursor()
        self.db_lock = lock
        self.setup_database()

    def setup_database(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS levels (
                guild_id INTEGER, user_id INTEGER,
                level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS role_rewards (
                guild_id INTEGER, level INTEGER, role_id INTEGER,
                PRIMARY KEY (guild_id, level)
            )
        ''')
        self.conn.commit()

    async def get_user_level(self, guild_id: int, user_id: int):
        async with self.db_lock:
            self.cursor.execute("SELECT level, xp FROM levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
            result = self.cursor.fetchone()
            if result:
                return result['level'], result['xp']
            else:
                self.cursor.execute("INSERT INTO levels (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
                self.conn.commit()
                return 1, 0

    async def update_user_xp(self, guild_id: int, user_id: int, level: int, xp: int):
        async with self.db_lock:
            self.cursor.execute("UPDATE levels SET level = ?, xp = ? WHERE guild_id = ? AND user_id = ?", (level, xp, guild_id, user_id))
            self.conn.commit()

    async def check_role_rewards(self, member: discord.Member, new_level: int):
        guild_id = member.guild.id
        async with self.db_lock:
            self.cursor.execute("SELECT role_id FROM role_rewards WHERE guild_id = ? AND level = ?", (guild_id, new_level))
            result = self.cursor.fetchone()
        if result:
            role_id = result['role_id']
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role)
                    return role
                except discord.Forbidden:
                    print(f"No tengo permisos para dar el rol {role.name} en el servidor {member.guild.name}")
        return None

    async def process_xp(self, message: discord.Message):
        """Otorga XP a los usuarios por cada mensaje que envían."""
        if message.author.bot or not message.guild:
            return

        guild_id = message.guild.id
        user_id = message.author.id
        level, xp = await self.get_user_level(guild_id, user_id)
        xp_to_add = random.randint(15, 25)
        new_xp = xp + xp_to_add
        xp_needed = 5 * (level ** 2) + 50 * level + 100

        if new_xp >= xp_needed:
            new_level = level + 1
            xp_leftover = new_xp - xp_needed
            await self.update_user_xp(guild_id, user_id, new_level, xp_leftover)
            reward_role = await self.check_role_rewards(message.author, new_level)
            level_up_message = f"🎉 ¡Felicidades {message.author.mention}, has subido al **nivel {new_level}**!"
            if reward_role:
                level_up_message += f"\n🎁 ¡Has ganado el rol {reward_role.mention} como recompensa!"
            try:
                await message.channel.send(level_up_message)
            except discord.Forbidden:
                pass
        else:
            await self.update_user_xp(guild_id, user_id, level, new_xp)

    @commands.hybrid_command(name='rank', description="Muestra tu nivel y XP en este servidor.")
    async def rank(self, ctx: commands.Context, miembro: discord.Member | None = None):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        await ctx.defer()
        target_user = miembro or ctx.author
        level, xp = await self.get_user_level(ctx.guild.id, target_user.id)
        xp_needed = 5 * (level ** 2) + 50 * level + 100
        progress = int((xp / xp_needed) * 20) if xp_needed > 0 else 0
        progress_bar = '🟩' * progress + '⬛' * (20 - progress)
        embed = discord.Embed(title=f"Estadísticas de Nivel de {target_user.display_name}", description=f"Mostrando el rango para el servidor **{ctx.guild.name}**", color=target_user.color)
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.add_field(name="Nivel", value=f"**{level}**", inline=True)
        embed.add_field(name="XP", value=f"**{xp} / {xp_needed}**", inline=True)
        embed.add_field(name="Progreso", value=f"`{progress_bar}`", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='levelboard', aliases=['lb_level'], description="Muestra a los usuarios con más nivel en este servidor.")
    async def levelboard(self, ctx: commands.Context):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        await ctx.defer()
        async with self.db_lock:
            self.cursor.execute("SELECT user_id, level, xp FROM levels WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10", (ctx.guild.id,))
            top_users = self.cursor.fetchall()

        if not top_users: return await ctx.send("Nadie tiene nivel en este servidor todavía. ¡Empieza a chatear para ganar XP!")
        embed = discord.Embed(title=f"🏆 Ranking de Niveles de {ctx.guild.name} 🏆", color=discord.Color.gold())
        description = ""
        for i, user_row in enumerate(top_users):
            try:
                user = await self.bot.fetch_user(user_row['user_id'])
                user_name = user.display_name
            except discord.NotFound:
                user_name = f"Usuario Desconocido ({user_row['user_id']})"
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`{i+1}.`"
            description += f"{rank} **{user_name}**: Nivel {user_row['level']} ({user_row['xp']} XP)\n"
        embed.description = description
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='set_level_role', description="Asigna un rol como recompensa por alcanzar un nivel.")
    @commands.has_permissions(administrator=True)
    async def set_level_role(self, ctx: commands.Context, nivel: int, rol: discord.Role):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        async with self.db_lock:
            self.cursor.execute("REPLACE INTO role_rewards (guild_id, level, role_id) VALUES (?, ?, ?)", (ctx.guild.id, nivel, rol.id))
            self.conn.commit()
        await ctx.send(f"✅ ¡Perfecto! El rol {rol.mention} se dará como recompensa al alcanzar el **nivel {nivel}**.")

    @commands.hybrid_command(name='remove_level_role', description="Elimina la recompensa de rol de un nivel.")
    @commands.has_permissions(administrator=True)
    async def remove_level_role(self, ctx: commands.Context, nivel: int):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        async with self.db_lock:
            self.cursor.execute("DELETE FROM role_rewards WHERE guild_id = ? AND level = ?", (ctx.guild.id, nivel))
            self.conn.commit()
        await ctx.send(f"🗑️ Se ha eliminado la recompensa de rol para el **nivel {nivel}**.")

    @commands.hybrid_command(name='list_level_roles', description="Muestra todas las recompensas de roles configuradas.")
    async def list_level_roles(self, ctx: commands.Context):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        await ctx.defer()
        async with self.db_lock:
            self.cursor.execute("SELECT level, role_id FROM role_rewards WHERE guild_id = ? ORDER BY level ASC", (ctx.guild.id,))
            rewards = self.cursor.fetchall()
        if not rewards: return await ctx.send("No hay recompensas de roles configuradas en este servidor.")
        embed = discord.Embed(title=f"🎁 Recompensas de Roles de {ctx.guild.name}", color=CREAM_COLOR)
        description = ""
        for reward in rewards:
            role = ctx.guild.get_role(reward['role_id'])
            description += f"**Nivel {reward['level']}** → {role.mention if role else 'Rol no encontrado'}\n"
        embed.description = description
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='reset_level', description="Reinicia el nivel de un usuario.")
    @commands.has_permissions(administrator=True)
    async def reset_level(self, ctx: commands.Context, miembro: discord.Member):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        await self.update_user_xp(ctx.guild.id, miembro.id, 1, 0)
        await ctx.send(f"🔄 El nivel de {miembro.mention} ha sido reiniciado.")

    @commands.hybrid_command(name='give_xp', description="Otorga XP a un usuario.")
    @commands.has_permissions(administrator=True)
    async def give_xp(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        level, xp = await self.get_user_level(ctx.guild.id, miembro.id)
        await self.update_user_xp(ctx.guild.id, miembro.id, level, xp + cantidad)
        await ctx.send(f"✨ Se han añadido **{cantidad} XP** a {miembro.mention}.")

# --- COG DE TEXTO A VOZ (TTS) ---
class TTSCog(commands.Cog, name="Texto a Voz"):
    """Comandos para que el bot hable y lea tus mensajes."""
    def __init__(self, bot: UmapyoiBot, conn: sqlite3.Connection, lock: asyncio.Lock):
        self.bot = bot
        self.conn = conn
        self.cursor = self.conn.cursor()
        self.db_lock = lock
        self.setup_tts_database()

    def setup_tts_database(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS tts_guild_settings (guild_id INTEGER PRIMARY KEY, lang TEXT NOT NULL DEFAULT 'es')''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS tts_active_channels (guild_id INTEGER PRIMARY KEY, text_channel_id INTEGER NOT NULL)''')
        self.conn.commit()

    async def get_guild_lang(self, guild_id: int) -> str:
        async with self.db_lock:
            self.cursor.execute("SELECT lang FROM tts_guild_settings WHERE guild_id = ?", (guild_id,))
            result = self.cursor.fetchone()
        return result['lang'] if result else 'es'

    async def set_guild_lang(self, guild_id: int, lang: str):
        async with self.db_lock:
            self.cursor.execute("REPLACE INTO tts_guild_settings (guild_id, lang) VALUES (?, ?)", (guild_id, lang))
            self.conn.commit()

    async def set_active_channel(self, guild_id: int, text_channel_id: int):
        async with self.db_lock:
            self.cursor.execute("REPLACE INTO tts_active_channels (guild_id, text_channel_id) VALUES (?, ?)", (guild_id, text_channel_id))
            self.conn.commit()

    async def get_active_channel(self, guild_id: int) -> int | None:
        async with self.db_lock:
            self.cursor.execute("SELECT text_channel_id FROM tts_active_channels WHERE guild_id = ?", (guild_id,))
            result = self.cursor.fetchone()
        return result['text_channel_id'] if result else None

    async def clear_guild_setup(self, guild_id: int):
        async with self.db_lock:
            self.cursor.execute("DELETE FROM tts_active_channels WHERE guild_id = ?", (guild_id,))
            self.conn.commit()

    async def is_guild_setup(self, guild_id: int) -> bool:
        return await self.get_active_channel(guild_id) is not None

    async def process_tts_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        active_channel_id = await self.get_active_channel(message.guild.id)
        if not active_channel_id or message.channel.id != active_channel_id:
            return

        music_cog = self.bot.get_cog("Música")
        if not music_cog or (music_cog.get_guild_state(message.guild.id).current_song is not None):
            return

        vc = message.guild.voice_client
        if not vc or not vc.is_connected() or vc.is_playing():
            return

        if not message.author.voice or message.author.voice.channel != vc.channel:
            return

        lang_code = await self.get_guild_lang(message.guild.id)
        text_to_speak = message.clean_content
        if not text_to_speak: return

        try:
            loop = asyncio.get_event_loop()
            tts_file = f"tts_{message.guild.id}_{message.author.id}.mp3"

            def save_tts():
                tts = gTTS(text=text_to_speak, lang=lang_code, slow=False)
                tts.save(tts_file)

            await loop.run_in_executor(None, save_tts)
            source = discord.FFmpegPCMAudio(tts_file)

            def after_playing(e):
                if e: print(f'TTS Error: {e}')
                try: os.remove(tts_file)
                except OSError as e: print(f"TTS File Error: {e}")

            vc.play(source, after=after_playing)
        except Exception as e:
            print(f"Error en TTS automático: {e}")

    @commands.hybrid_command(name='setup', description="Configura el bot para leer mensajes en este canal.")
    @commands.has_permissions(manage_guild=True)
    async def setup(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("Debes estar en un canal de voz para usar este comando.", ephemeral=True)

        music_cog = self.bot.get_cog("Música")
        if not music_cog:
            return await ctx.send("Error interno: no se pudo encontrar el cog de música.", ephemeral=True)

        channel = ctx.author.voice.channel
        vc = await music_cog.ensure_voice_client(channel)
        if not vc:
            return await ctx.send("❌ No pude conectarme a tu canal de voz.", ephemeral=True)

        await self.set_active_channel(ctx.guild.id, ctx.channel.id)
        await ctx.send(f"✅ ¡Perfecto! A partir de ahora leeré los mensajes enviados en {ctx.channel.mention} (mientras no haya música).")


    @commands.hybrid_command(name='set_language', description="[Admin] Establece el idioma de TTS para el servidor.")
    @commands.has_permissions(manage_guild=True)
    @discord.app_commands.choices(idioma=[
        discord.app_commands.Choice(name="Español", value="es"),
        discord.app_commands.Choice(name="Inglés (EE.UU.)", value="en"),
        discord.app_commands.Choice(name="Japonés", value="ja"),
        discord.app_commands.Choice(name="Italiano", value="it"),
        discord.app_commands.Choice(name="Francés", value="fr"),
    ])
    async def set_language(self, ctx: commands.Context, idioma: discord.app_commands.Choice[str]):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        await self.set_guild_lang(ctx.guild.id, idioma.value)
        await ctx.send(f"✅ El idioma por defecto del servidor para TTS ha sido establecido a **{idioma.name}**.")

# --- COG DE CONFIGURACIÓN DEL SERVIDOR ---

class WelcomeConfigModal(discord.ui.Modal, title='Configuración de Bienvenida'):
    def __init__(self, cog, default_message, default_banner):
        super().__init__()
        self.server_config_cog = cog
        self.add_item(discord.ui.TextInput(label="Mensaje de Bienvenida", style=discord.TextStyle.long, placeholder="Usa {user.mention}, {user.name}, {server.name}, {member.count}", default=default_message, required=True))
        self.add_item(discord.ui.TextInput(label="URL del Banner de Bienvenida", placeholder="https://i.imgur.com/WwexK3G.png", default=default_banner, required=False))
    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        await self.server_config_cog.save_setting(guild_id, 'welcome_message', self.children[0].value)
        await self.server_config_cog.save_setting(guild_id, 'welcome_banner_url', self.children[1].value or self.server_config_cog.DEFAULT_WELCOME_BANNER)
        await interaction.response.send_message("✅ Configuración de bienvenida guardada.", ephemeral=True)

class GoodbyeConfigModal(discord.ui.Modal, title='Configuración de Despedida'):
    def __init__(self, cog, default_message, default_banner):
        super().__init__()
        self.server_config_cog = cog
        self.add_item(discord.ui.TextInput(label="Mensaje de Despedida", style=discord.TextStyle.long, placeholder="Usa {user.name}, {server.name}, {member.count}", default=default_message, required=True))
        self.add_item(discord.ui.TextInput(label="URL del Banner de Despedida", placeholder="https://i.imgur.com/WwexK3G.png", default=default_banner, required=False))
    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        await self.server_config_cog.save_setting(guild_id, 'goodbye_message', self.children[0].value)
        await self.server_config_cog.save_setting(guild_id, 'goodbye_banner_url', self.children[1].value or self.server_config_cog.DEFAULT_GOODBYE_BANNER)
        await interaction.response.send_message("✅ Configuración de despedida guardada.", ephemeral=True)

class ReactionRoleModal(discord.ui.Modal, title="Crear Rol por Reacción"):
    def __init__(self, cog):
        super().__init__()
        self.server_config_cog = cog
        self.add_item(discord.ui.TextInput(label="ID del Mensaje", placeholder="Copia aquí el ID del mensaje al que reaccionar", required=True))
        self.add_item(discord.ui.TextInput(label="Emoji", placeholder="Pega el emoji a usar (ej. ✅)", required=True))
        self.add_item(discord.ui.TextInput(label="ID del Rol", placeholder="Copia aquí el ID del rol a asignar", required=True))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            message_id = int(self.children[0].value)
            emoji = self.children[1].value
            role_id = int(self.children[2].value)
        except ValueError:
            return await interaction.response.send_message("❌ ID de Mensaje o ID de Rol no son números válidos.", ephemeral=True)

        try:
            await self.server_config_cog.add_reaction_role(interaction.guild.id, message_id, emoji, role_id)
            # Asegurarse que el canal de interacción existe antes de usarlo
            channel = interaction.channel
            if isinstance(channel, (discord.TextChannel, discord.ForumChannel, discord.Thread)):
                message = await channel.fetch_message(message_id)
                await message.add_reaction(emoji)
                await interaction.response.send_message("✅ Rol por reacción creado con éxito.", ephemeral=True)
            else:
                await interaction.response.send_message("✅ Rol por reacción guardado, pero no pude añadir la reacción. Asegúrate de estar en el canal correcto.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error al crear el rol por reacción: {e}", ephemeral=True)

class ServerConfigCog(commands.Cog, name="Configuración del Servidor"):
    """Comandos para que los administradores configuren el bot en el servidor."""

    DEFAULT_WELCOME_MESSAGE = "¡Bienvenido a {server.name}, {user.mention}! 🎉"
    DEFAULT_WELCOME_BANNER = "https://i.imgur.com/WwexK3G.png"
    DEFAULT_GOODBYE_MESSAGE = "{user.name} ha dejado el nido. ¡Hasta la próxima! 😢"
    DEFAULT_GOODBYE_BANNER = "https://i.imgur.com/WwexK3G.png"
    TEMP_CHANNEL_PREFIX = "Sala de "

    def __init__(self, bot: UmapyoiBot, conn: sqlite3.Connection, lock: asyncio.Lock):
        self.bot = bot
        self.conn = conn
        self.cursor = self.conn.cursor()
        self.db_lock = lock
        self.setup_database()

    def setup_database(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_settings (
                guild_id INTEGER PRIMARY KEY,
                welcome_channel_id INTEGER,
                goodbye_channel_id INTEGER,
                log_channel_id INTEGER,
                autorole_id INTEGER,
                welcome_message TEXT,
                welcome_banner_url TEXT,
                goodbye_message TEXT,
                goodbye_banner_url TEXT,
                automod_anti_invite INTEGER DEFAULT 1,
                automod_banned_words TEXT,
                temp_channel_creator_id INTEGER,
                leveling_enabled INTEGER DEFAULT 1
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS reaction_roles (
                guild_id INTEGER, message_id INTEGER, emoji TEXT, role_id INTEGER,
                PRIMARY KEY (guild_id, message_id, emoji)
            )
        ''')
        self.conn.commit()

    async def get_settings(self, guild_id: int) -> Optional[sqlite3.Row]:
        async with self.db_lock:
            self.cursor.execute("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
            res = self.cursor.fetchone()
        return res

    async def save_setting(self, guild_id: int, key: str, value):
        async with self.db_lock:
            self.cursor.execute("INSERT OR IGNORE INTO server_settings (guild_id) VALUES (?)", (guild_id,))
            self.cursor.execute(f"UPDATE server_settings SET {key} = ? WHERE guild_id = ?", (value, guild_id))
            self.conn.commit()

    async def add_reaction_role(self, guild_id, message_id, emoji, role_id):
        async with self.db_lock:
            self.cursor.execute("REPLACE INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)", (guild_id, message_id, emoji, role_id))
            self.conn.commit()

    @commands.hybrid_command(name='setwelcomechannel', description="Establece el canal para los mensajes de bienvenida.")
    @commands.has_permissions(manage_guild=True)
    async def set_welcome_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        await self.save_setting(ctx.guild.id, 'welcome_channel_id', canal.id)
        await ctx.send(f"✅ Canal de bienvenida establecido en {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name='setgoodbyechannel', description="Establece el canal para los mensajes de despedida.")
    @commands.has_permissions(manage_guild=True)
    async def set_goodbye_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        await self.save_setting(ctx.guild.id, 'goodbye_channel_id', canal.id)
        await ctx.send(f"✅ Canal de despedida establecido en {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name='setlogchannel', description="Establece el canal para el registro de moderación.")
    @commands.has_permissions(manage_guild=True)
    async def set_log_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        await self.save_setting(ctx.guild.id, 'log_channel_id', canal.id)
        await ctx.send(f"✅ Canal de logs establecido en {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name='setautorole', description="Establece un rol para asignar a nuevos miembros.")
    @commands.has_permissions(manage_guild=True)
    async def set_autorole(self, ctx: commands.Context, rol: discord.Role):
        await self.save_setting(ctx.guild.id, 'autorole_id', rol.id)
        await ctx.send(f"✅ El rol {rol.mention} se asignará automáticamente a los nuevos miembros.", ephemeral=True)

    @commands.hybrid_command(name='configwelcome', description="Personaliza el mensaje y banner de bienvenida.")
    @commands.has_permissions(manage_guild=True)
    async def config_welcome(self, ctx: commands.Context):
        settings = await self.get_settings(ctx.guild.id)
        msg = (settings['welcome_message'] if settings and settings['welcome_message'] else self.DEFAULT_WELCOME_MESSAGE)
        banner = (settings['welcome_banner_url'] if settings and settings['welcome_banner_url'] else self.DEFAULT_WELCOME_BANNER)
        await ctx.interaction.response.send_modal(WelcomeConfigModal(self, msg, banner))

    @commands.hybrid_command(name='configgoodbye', description="Personaliza el mensaje y banner de despedida.")
    @commands.has_permissions(manage_guild=True)
    async def config_goodbye(self, ctx: commands.Context):
        settings = await self.get_settings(ctx.guild.id)
        msg = (settings['goodbye_message'] if settings and settings['goodbye_message'] else self.DEFAULT_GOODBYE_MESSAGE)
        banner = (settings['goodbye_banner_url'] if settings and settings['goodbye_banner_url'] else self.DEFAULT_GOODBYE_BANNER)
        await ctx.interaction.response.send_modal(GoodbyeConfigModal(self, msg, banner))

    @commands.hybrid_command(name='createreactionrole', description="Crea un nuevo rol por reacción.")
    @commands.has_permissions(manage_guild=True)
    async def create_reaction_role(self, ctx: commands.Context):
        await ctx.interaction.response.send_modal(ReactionRoleModal(self))

    # --- INICIO DE LA CORRECCIÓN DE PERMISOS ---
    @commands.hybrid_group(name="automod", description="Configura las opciones de auto-moderación.")
    @commands.has_permissions(manage_guild=True) # Permiso para el grupo principal
    async def automod(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Comando de automod inválido. Usa `/automod anti-invites` o `/automod badwords`.", ephemeral=True)

    @automod.command(name="anti_invites", description="Activa o desactiva el borrado de invitaciones de Discord.")
    @commands.has_permissions(manage_guild=True) # Permiso para el sub-comando
    async def anti_invites(self, ctx: commands.Context, estado: Literal['on', 'off']):
        is_on = 1 if estado == 'on' else 0
        await self.save_setting(ctx.guild.id, 'automod_anti_invite', is_on)
        await ctx.send(f"✅ El filtro anti-invitaciones ha sido **{estado}**.", ephemeral=True)

    @automod.group(name="badwords", description="Gestiona la lista de palabras prohibidas.")
    @commands.has_permissions(manage_guild=True) # Permiso para el sub-grupo
    async def badwords(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Comando de badwords inválido. Usa `/automod badwords add/remove/list`.", ephemeral=True)

    @badwords.command(name="add", description="Añade una palabra a la lista de palabras prohibidas.")
    @commands.has_permissions(manage_guild=True) # Permiso para el comando final
    async def badwords_add(self, ctx: commands.Context, palabra: str):
        settings = await self.get_settings(ctx.guild.id)
        current_words_str = (settings['automod_banned_words'] if settings and settings['automod_banned_words'] else "")
        word_list = [word.strip() for word in current_words_str.split(',') if word.strip()]

        if palabra.lower() not in word_list:
            word_list.append(palabra.lower())
            new_words_str = ",".join(word_list)
            await self.save_setting(ctx.guild.id, 'automod_banned_words', new_words_str)
            await ctx.send(f"✅ La palabra `{palabra}` ha sido añadida a la lista de palabras prohibidas.", ephemeral=True)
        else:
            await ctx.send(f"⚠️ La palabra `{palabra}` ya estaba en la lista.", ephemeral=True)

    @badwords.command(name="remove", description="Quita una palabra de la lista de prohibidas.")
    @commands.has_permissions(manage_guild=True) # Permiso para el comando final
    async def badwords_remove(self, ctx: commands.Context, palabra: str):
        settings = await self.get_settings(ctx.guild.id)
        current_words_str = (settings['automod_banned_words'] if settings and settings['automod_banned_words'] else "")
        word_list = [word.strip() for word in current_words_str.split(',') if word.strip()]

        if palabra.lower() in word_list:
            word_list.remove(palabra.lower())
            new_words_str = ",".join(word_list)
            await self.save_setting(ctx.guild.id, 'automod_banned_words', new_words_str)
            await ctx.send(f"✅ La palabra `{palabra}` ha sido eliminada de la lista.", ephemeral=True)
        else:
            await ctx.send(f"⚠️ La palabra `{palabra}` no se encontró en la lista.", ephemeral=True)

    @badwords.command(name="list", description="Muestra la lista de palabras prohibidas.")
    @commands.has_permissions(manage_guild=True) # Permiso para el comando final
    async def badwords_list(self, ctx: commands.Context):
        settings = await self.get_settings(ctx.guild.id)
        words = (settings['automod_banned_words'] if settings and settings['automod_banned_words'] else "La lista está vacía.")
        await ctx.send(f"**Lista de palabras prohibidas:**\n`{words}`", ephemeral=True)
    # --- FIN DE LA CORRECCIÓN DE PERMISOS ---

    @commands.hybrid_command(name='setcreatorchannel', description="Establece el canal de voz para crear salas temporales.")
    @commands.has_permissions(manage_guild=True)
    async def set_creator_channel(self, ctx: commands.Context, canal: discord.VoiceChannel):
        await self.save_setting(ctx.guild.id, 'temp_channel_creator_id', canal.id)
        await ctx.send(f"✅ ¡Perfecto! Ahora, quien se una a **{canal.name}** creará su propia sala de voz.", ephemeral=True)

    @commands.hybrid_command(name='removecreatorchannel', description="Desactiva la creación de salas de voz temporales.")
    @commands.has_permissions(manage_guild=True)
    async def remove_creator_channel(self, ctx: commands.Context):
        await self.save_setting(ctx.guild.id, 'temp_channel_creator_id', None)
        await ctx.send("✅ La función de crear salas de voz temporales ha sido desactivada.", ephemeral=True)

    @commands.hybrid_command(name='levels', description="Activa o desactiva el sistema de niveles en el servidor.")
    @commands.has_permissions(manage_guild=True)
    async def toggle_leveling(self, ctx: commands.Context, estado: Literal['on', 'off']):
        is_on = 1 if estado == 'on' else 0
        await self.save_setting(ctx.guild.id, 'leveling_enabled', is_on)
        status_text = "activado" if is_on else "desactivado"
        await ctx.send(f"✅ El sistema de niveles ha sido **{status_text}** en este servidor.", ephemeral=True)


    async def log_event(self, guild_id, embed):
        settings = await self.get_settings(guild_id)
        if settings and settings["log_channel_id"]:
            if log_channel := self.bot.get_channel(settings["log_channel_id"]):
                try: await log_channel.send(embed=embed)
                except discord.Forbidden: pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild_id = member.guild.id
        settings = await self.get_settings(guild_id)
        if not settings: return
        
        creator_channel_id = settings["temp_channel_creator_id"]

        if after.channel and after.channel.id == creator_channel_id:
            try:
                overwrites = {
                    member.guild.default_role: discord.PermissionOverwrite(view_channel=True),
                    member: discord.PermissionOverwrite(view_channel=True, manage_channels=True, manage_permissions=True, move_members=True, mute_members=True, deafen_members=True)
                }
                temp_channel = await member.guild.create_voice_channel(
                    name=f"{self.TEMP_CHANNEL_PREFIX}{member.display_name}",
                    category=after.channel.category,
                    overwrites=overwrites,
                    reason=f"Canal temporal creado por {member.display_name}"
                )
                await member.move_to(temp_channel)
            except Exception as e:
                print(f"No se pudo crear el canal temporal: {e}")

        if before.channel and before.channel.name.startswith(self.TEMP_CHANNEL_PREFIX):
            await asyncio.sleep(1)
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Canal temporal vacío.")
                except Exception as e:
                    print(f"No se pudo borrar el canal temporal: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = await self.get_settings(member.guild.id)
        if not settings: return

        if channel_id := settings["welcome_channel_id"]:
            if channel := self.bot.get_channel(channel_id):
                message_format = settings["welcome_message"] or self.DEFAULT_WELCOME_MESSAGE
                message = message_format.format(user=member, server=member.guild, member_count=member.guild.member_count)
                banner_url = settings["welcome_banner_url"] or self.DEFAULT_WELCOME_BANNER
                embed = discord.Embed(description=message, color=discord.Color.green())
                embed.set_author(name=f"¡Bienvenido a {member.guild.name}!", icon_url=member.display_avatar.url)
                if banner_url: embed.set_image(url=banner_url)
                embed.set_footer(text=f"Ahora somos {member.guild.member_count} miembros.")
                try: await channel.send(embed=embed)
                except discord.Forbidden: pass

        if role_id := settings["autorole_id"]:
            if role := member.guild.get_role(role_id):
                try: await member.add_roles(role, reason="Autorol al unirse")
                except discord.Forbidden: pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        settings = await self.get_settings(member.guild.id)
        if settings and (channel_id := settings["goodbye_channel_id"]):
            if channel := self.bot.get_channel(channel_id):
                message_format = settings["goodbye_message"] or self.DEFAULT_GOODBYE_MESSAGE
                message = message_format.format(user=member, server=member.guild, member_count=member.guild.member_count)
                banner_url = settings["goodbye_banner_url"] or self.DEFAULT_GOODBYE_BANNER
                embed = discord.Embed(description=message, color=discord.Color.red())
                embed.set_author(name=f"Adiós, {member.display_name}", icon_url=member.display_avatar.url)
                if banner_url: embed.set_image(url=banner_url)
                embed.set_footer(text=f"Ahora somos {member.guild.member_count} miembros.")
                try: await channel.send(embed=embed)
                except discord.Forbidden: pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        embed = discord.Embed(description=f"**Mensaje de {message.author.mention} borrado en {message.channel.mention}**\n{message.content or '*(Contenido no disponible)*'}", color=discord.Color.orange(), timestamp=datetime.datetime.now())
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        await self.log_event(message.guild.id, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content: return
        embed = discord.Embed(description=f"**{before.author.mention} editó un mensaje en {before.channel.mention}** [Ir al mensaje]({after.jump_url})", color=discord.Color.blue(), timestamp=datetime.datetime.now())
        embed.add_field(name="Antes", value=before.content[:1024] or "*(Vacío)*", inline=False)
        embed.add_field(name="Después", value=after.content[:1024] or "*(Vacío)*", inline=False)
        embed.set_author(name=before.author.display_name, icon_url=before.author.display_avatar.url)
        await self.log_event(before.guild.id, embed)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member and payload.member.bot: return
        async with self.db_lock:
            self.cursor.execute("SELECT role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?", (payload.guild_id, payload.message_id, str(payload.emoji)))
            result = self.cursor.fetchone()
        if result:
            guild = self.bot.get_guild(payload.guild_id)
            if guild and payload.member:
                role = guild.get_role(result['role_id'])
                if role:
                    try: await payload.member.add_roles(role, reason="Rol por reacción")
                    except discord.Forbidden: pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        async with self.db_lock:
            self.cursor.execute("SELECT role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?", (payload.guild_id, payload.message_id, str(payload.emoji)))
            result = self.cursor.fetchone()
        if result:
            guild = self.bot.get_guild(payload.guild_id)
            if guild:
                member = guild.get_member(payload.user_id)
                if member:
                    role = guild.get_role(result['role_id'])
                    if role:
                        try: await member.remove_roles(role, reason="Rol por reacción")
                        except discord.Forbidden: pass

# --- COG DE UTILIDAD ---
class UtilityCog(commands.Cog, name="Utilidad"):
    """Comandos útiles y de información."""
    def __init__(self, bot: UmapyoiBot): self.bot = bot

    @commands.hybrid_command(name='help', description="Muestra el panel de ayuda interactivo.")
    async def help(self, ctx: commands.Context):
        embed = discord.Embed(title="📜 Ayuda de Umapyoi", color=CREAM_COLOR)
        embed.description = "**🚀 Cómo empezar a escuchar música**\n`/play <nombre de la canción o enlace>`\n\n**❓ ¿Qué es Umapyoi?**\nUn bot de nueva generación con música, juegos, economía y mucho más. ¡Todo en uno!\n\n**🎛️ Categorías de Comandos:**"
        embed.set_image(url="https://i.imgur.com/WwexK3G.png")
        embed.set_footer(text="Gracias por elegir a Umapyoi ✨")
        view = HelpView(self.bot)
        await ctx.send(embed=embed, view=view)
        
    # --- COMANDO ANNOUNCE OCULTO ---
    @commands.command(name='announce', hidden=True)
    @commands.is_owner()
    async def announce(self, ctx: commands.Context, *, mensaje: str):
        """Envía un anuncio a todos los servidores donde está el bot."""
        await ctx.typing()

        embed = discord.Embed(
            title="📢 Anuncio del Bot",
            description=mensaje,
            color=CREAM_COLOR,
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text=f"Enviado por el desarrollador de Umapyoi")

        successful_sends = 0
        failed_sends = 0

        for guild in self.bot.guilds:
            target_channel = None
            if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
                target_channel = guild.system_channel
            else:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        target_channel = channel
                        break
            
            if target_channel:
                try:
                    await target_channel.send(embed=embed)
                    successful_sends += 1
                except Exception as e:
                    print(f"No se pudo enviar anuncio a '{guild.name}' (ID: {guild.id}). Error: {e}")
                    failed_sends += 1
            else:
                print(f"No se encontró un canal válido en '{guild.name}' (ID: {guild.id}).")
                failed_sends += 1

        response_message = f"✅ Anuncio enviado con éxito a **{successful_sends} servidores**.\n❌ Falló en **{failed_sends} servidores**."
        await ctx.send(response_message)

    @announce.error
    async def announce_error(self, ctx: commands.Context, error: commands.CommandError):
        """Manejador de errores local y exclusivo para el comando 'announce'."""
        root_error = getattr(error, 'original', error)

        if isinstance(root_error, commands.MissingRequiredArgument):
            await ctx.send("⚠️ ¡Oye! Olvidaste incluir el mensaje que quieres anunciar.\n**Uso correcto:** `!announce <tu mensaje aquí>`", delete_after=15)
            return

        if isinstance(root_error, commands.NotOwner):
            await ctx.send("❌ Este comando es solo para el dueño del bot.", delete_after=10)
            return

        print(f"Ocurrió un error inesperado en el comando 'announce': {root_error}")
        await ctx.send("❌ Hubo un problema técnico al intentar ejecutar el comando de anuncio.", delete_after=10)
        return

    # --- COMANDO SERVERLIST OCULTO ---
    @commands.command(name='serverlist', hidden=True)
    @commands.is_owner()
    async def serverlist(self, ctx: commands.Context):
        """Envía al dueño una lista de los servidores donde está el bot."""
        await ctx.typing()

        server_list_str = f"Lista de Servidores de Umapyoi ({len(self.bot.guilds)} en total):\n"
        server_list_str += "=============================================\n\n"
        
        for i, guild in enumerate(self.bot.guilds):
            server_list_str += f"{i+1}. {guild.name}\n"
            server_list_str += f"   ID: {guild.id}\n"
            server_list_str += f"   Miembros: {guild.member_count}\n\n"

        file_buffer = io.StringIO(server_list_str)
        file_to_send = discord.File(fp=file_buffer, filename="lista_de_servidores.txt")

        try:
            await ctx.author.send("Aquí tienes la lista de servidores donde estoy:", file=file_to_send)
            if ctx.guild:
                await ctx.send("✅ Te he enviado la lista de servidores por mensaje directo.", delete_after=10)
        except discord.Forbidden:
            await ctx.send("No pude enviarte la lista por DM. Aquí la tienes:", file=file_to_send)

    @commands.hybrid_command(name='contacto', description="Muestra la información de contacto del creador.")
    async def contacto(self, ctx: commands.Context):
        creador_discord = "sakurayo_crispy"
        embed = discord.Embed(title="📞 Contacto", description=f"Puedes contactar a mi creador a través de Discord.", color=CREAM_COLOR)
        embed.add_field(name="Creador", value=f"👑 {creador_discord}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='serverhelp', description="Obtén el enlace al servidor de ayuda oficial.")
    async def serverhelp(self, ctx: commands.Context):
        enlace_servidor = "https://discord.gg/fwNeZsGkSj"
        embed = discord.Embed(title="💬 Servidor de Ayuda", description=f"¿Necesitas ayuda o quieres sugerir algo? ¡Únete a nuestro servidor oficial!", color=CREAM_COLOR)
        embed.add_field(name="Enlace de Invitación", value=f"[Haz clic aquí para unirte]({enlace_servidor})")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='ping', description="Muestra la latencia del bot.")
    async def ping(self, ctx: commands.Context):
        await ctx.send(f'🏓 ¡Pong! La latencia es de **{round(self.bot.latency * 1000)}ms**.', ephemeral=True)

    @commands.hybrid_command(name='avatar', description="Muestra el avatar de un usuario en grande.")
    async def avatar(self, ctx: commands.Context, miembro: discord.Member | None = None):
        miembro = miembro or ctx.author
        embed = discord.Embed(title=f"Avatar de {miembro.display_name}", color=miembro.color).set_image(url=miembro.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='userinfo', description="Muestra información sobre un usuario.")
    async def userinfo(self, ctx: commands.Context, miembro: discord.Member | None = None):
        miembro = miembro or ctx.author
        embed = discord.Embed(title=f"Información de {miembro.display_name}", color=miembro.color).set_thumbnail(url=miembro.display_avatar.url)
        embed.add_field(name="ID", value=miembro.id, inline=False)
        embed.add_field(name="Cuenta Creada", value=f"<t:{int(miembro.created_at.timestamp())}:D>", inline=True)
        if miembro.joined_at:
            embed.add_field(name="Se Unió al Servidor", value=f"<t:{int(miembro.joined_at.timestamp())}:D>", inline=True)
        roles = [role.mention for role in miembro.roles[1:]]
        if roles:
            roles_str = ", ".join(roles)
            if len(roles_str) > 1024: roles_str = roles_str[:1020] + "..."
            embed.add_field(name=f"Roles ({len(roles)})", value=roles_str, inline=False)
        else:
            embed.add_field(name="Roles (0)", value="Ninguno", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='serverinfo', description="Muestra información sobre este servidor.")
    async def serverinfo(self, ctx: commands.Context):
        server = ctx.guild
        if not server: return
        embed = discord.Embed(title=f"Información de {server.name}", color=CREAM_COLOR)
        if server.icon: embed.set_thumbnail(url=server.icon.url)
        if server.owner: embed.add_field(name="👑 Propietario", value=server.owner.mention, inline=True)
        embed.add_field(name="👥 Miembros", value=str(server.member_count), inline=True)
        embed.add_field(name="📅 Creado el", value=f"<t:{int(server.created_at.timestamp())}:D>", inline=True)
        embed.add_field(name="💬 Canales", value=f"{len(server.text_channels)} de texto | {len(server.voice_channels)} de voz", inline=False)
        embed.add_field(name="✨ Nivel de Boost", value=f"Nivel {server.premium_tier} ({server.premium_subscription_count} boosts)", inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='say', description="Hace que el bot repita tu mensaje.")
    @commands.has_permissions(manage_messages=True)
    async def say(self, ctx: commands.Context, *, mensaje: str):
        if ctx.interaction:
            await ctx.interaction.response.send_message("Mensaje enviado.", ephemeral=True)
            await ctx.channel.send(mensaje)
        else:
            await ctx.message.delete()
            await ctx.send(mensaje)

# --- COG DE JUEGOS ---
class FunCog(commands.Cog, name="Juegos e IA"):
    """Comandos interactivos y divertidos para pasar el rato."""
    def __init__(self, bot: UmapyoiBot):
        self.bot = bot
        self.game_in_progress: dict[int, bool] = {}

    @commands.hybrid_command(name='pregunta', description="Hazme cualquier pregunta y usaré mi IA para responder.")
    async def pregunta(self, ctx: commands.Context, *, pregunta: str):
        await ctx.defer()
        if not GEMINI_API_KEY:
            return await ctx.send("❌ La función de IA no está configurada (falta GEMINI_API_KEY).")
        API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": pregunta}]}]}
        headers = {"Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(API_URL, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        respuesta_ia = data['candidates'][0]['content']['parts'][0]['text']
                    else:
                        error_details = await response.text()
                        print(f"Error de la API de Gemini: {response.status} - {error_details}")
                        respuesta_ia = f"Error al contactar la API de Gemini. Código: {response.status}"
        except Exception as e:
            respuesta_ia = f"Ocurrió un error inesperado: {e}"
        embed = discord.Embed(title="🤔 Pregunta para Umapyoi", description=f"**Tú preguntaste:**\n{pregunta}", color=discord.Color.gold())
        embed.add_field(name="💡 Mi Respuesta:", value=respuesta_ia)
        await ctx.send(embed=embed)

    def process_wanted_image(self, template_bytes: bytes, avatar_bytes: bytes) -> BytesIO:
        template = Image.open(BytesIO(template_bytes)).convert("RGBA")
        avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
        avatar_size = (833, 820); paste_position = (96, 445)
        avatar = avatar.resize(avatar_size)
        template.paste(avatar, paste_position, avatar)
        final_buffer = BytesIO()
        template.save(final_buffer, format="PNG")
        final_buffer.seek(0)
        return final_buffer

    @commands.hybrid_command(name='wanted', description="Crea un cartel de 'Se Busca' para un usuario.")
    async def wanted(self, ctx: commands.Context, miembro: discord.Member | None = None):
        await ctx.defer()
        miembro = miembro or ctx.author
        try:
            wanted_template_url = "https://i.imgur.com/wNvXv8i.jpeg"
            headers = {'User-Agent': 'Mozilla/5.0'}
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(wanted_template_url) as resp:
                    if resp.status != 200: return await ctx.send(f"❌ No pude descargar la plantilla. Estado: {resp.status}")
                    template_bytes = await resp.read()
                async with session.get(miembro.display_avatar.url) as resp:
                    if resp.status != 200: return await ctx.send("❌ No pude descargar el avatar.")
                    avatar_bytes = await resp.read()
            loop = asyncio.get_event_loop()
            buffer = await loop.run_in_executor(None, self.process_wanted_image, template_bytes, avatar_bytes)
            file = discord.File(buffer, filename="wanted.png")
            await ctx.send(file=file)
        except Exception as e:
            print(f"Error en /wanted: {e}")
            await ctx.send(f"❌ No pude crear el cartel. Error: {e}")

    @commands.hybrid_command(name='ppt', description="Juega Piedra, Papel o Tijera contra mí.")
    async def ppt(self, ctx: commands.Context, eleccion: Literal['piedra', 'papel', 'tijera']):
        opciones = ['piedra', 'papel', 'tijera']
        eleccion_usuario = eleccion.lower()
        eleccion_bot = random.choice(opciones)
        if eleccion_usuario == eleccion_bot:
            resultado = f"¡Empate! Ambos elegimos **{eleccion_bot}**."
        elif (eleccion_usuario == 'piedra' and eleccion_bot == 'tijera') or \
             (eleccion_usuario == 'papel' and eleccion_bot == 'piedra') or \
             (eleccion_usuario == 'tijera' and eleccion_bot == 'papel'):
            resultado = f"¡Ganaste! Yo elegí **{eleccion_bot}**."
        else:
            resultado = f"¡Perdiste! Yo elegí **{eleccion_bot}**."
        await ctx.send(f"Tú elegiste **{eleccion_usuario}**. {resultado}")
                    
    @commands.hybrid_command(name='anime', description="Busca información detallada sobre un anime.")
    async def anime(self, ctx: commands.Context, *, nombre: str):
        await ctx.defer()
        API_URL = f"https://api.jikan.moe/v4/anime?q={nombre.replace(' ', '%20')}&limit=1"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL) as response:
                    if response.status == 200:
                        data = await response.json()
                        if not data['data']:
                            return await ctx.send(f"❌ No encontré ningún anime llamado `{nombre}`.", ephemeral=True)

                        anime_data = data['data'][0]
                        synopsis = anime_data.get('synopsis', 'No hay sinopsis disponible.')
                        if len(synopsis) > 1000:
                            synopsis = synopsis[:1000] + "..."

                        embed = discord.Embed(
                            title=anime_data.get('title', 'N/A'),
                            url=anime_data.get('url', ''),
                            description=synopsis,
                            color=discord.Color.blue()
                        )

                        if image_url := anime_data.get('images', {}).get('jpg', {}).get('large_image_url'):
                            embed.set_thumbnail(url=image_url)

                        embed.add_field(name="Puntuación", value=f"⭐ {anime_data.get('score', 'N/A')}", inline=True)
                        embed.add_field(name="Episodios", value=anime_data.get('episodes', 'N/A'), inline=True)
                        embed.add_field(name="Estado", value=anime_data.get('status', 'N/A'), inline=True)

                        genres = [genre['name'] for genre in anime_data.get('genres', [])]
                        if genres:
                            embed.add_field(name="Géneros", value=", ".join(genres), inline=False)

                        embed.set_footer(text=f"Fuente: MyAnimeList | ID: {anime_data.get('mal_id')}")

                        await ctx.send(embed=embed)
                    else:
                        await ctx.send(f"❌ Hubo un error con la API (Código: {response.status}). Inténtalo de nuevo más tarde.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Ocurrió un error inesperado: {e}", ephemeral=True)


# --- COG DE ECONOMÍA ---
class EconomyCog(commands.Cog, name="Economía"):
    """Gana Umapesos, compite y sé el más rico del servidor."""
    def __init__(self, bot: UmapyoiBot, conn: sqlite3.Connection, lock: asyncio.Lock):
        self.bot = bot
        self.conn = conn
        self.cursor = self.conn.cursor()
        self.db_lock = lock
        self.setup_database()

    def setup_database(self):
        self.cursor.execute('CREATE TABLE IF NOT EXISTS balances (user_id INTEGER PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0)')
        self.conn.commit()

    async def get_balance(self, user_id: int) -> int:
        async with self.db_lock:
            self.cursor.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
            result = self.cursor.fetchone()
            if result:
                return result['balance']
            else:
                self.cursor.execute("INSERT INTO balances (user_id, balance) VALUES (?, ?)", (user_id, 0))
                self.conn.commit()
                return 0

    async def update_balance(self, user_id: int, amount: int):
        async with self.db_lock:
            # Usamos una sola transacción para leer y escribir
            self.cursor.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
            result = self.cursor.fetchone()
            current_balance = result['balance'] if result else 0
            new_balance = current_balance + amount
            self.cursor.execute("REPLACE INTO balances (user_id, balance) VALUES (?, ?)", (user_id, new_balance))
            self.conn.commit()
            return new_balance

    @commands.hybrid_command(name='daily', description="Reclama tu recompensa diaria de Umapesos.")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx: commands.Context):
        await ctx.defer()
        amount = random.randint(100, 500)
        await self.update_balance(ctx.author.id, amount)
        embed = discord.Embed(title="💸 Recompensa Diaria", description=f"¡Felicidades, {ctx.author.mention}! Has reclamado **{amount} Umapesos**.", color=discord.Color.gold())
        await ctx.send(embed=embed)

    @daily.error
    async def daily_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            m, s = divmod(error.retry_after, 60)
            h, m = divmod(m, 60)
            await ctx.send(f"Ya reclamaste tu recompensa. Vuelve en **{int(h)}h {int(m)}m**.", ephemeral=True)
        else:
            await ctx.send(f"Ocurrió un error: {error}", ephemeral=True)
            raise error

    @commands.hybrid_command(name='balance', aliases=['bal'], description="Muestra cuántos Umapesos tienes.")
    async def balance(self, ctx: commands.Context, miembro: discord.Member | None = None):
        await ctx.defer(ephemeral=True)
        target_user = miembro or ctx.author
        balance = await self.get_balance(target_user.id)
        embed = discord.Embed(title=f"💰 Balance de {target_user.display_name}", description=f"Tiene **{balance} Umapesos**.", color=CREAM_COLOR)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='leaderboard', aliases=['lb'], description="Muestra a los usuarios más ricos.")
    async def leaderboard(self, ctx: commands.Context):
        await ctx.defer()
        async with self.db_lock:
            self.cursor.execute("SELECT user_id, balance FROM balances ORDER BY balance DESC LIMIT 10")
            top_users = self.cursor.fetchall()
        if not top_users: return await ctx.send("Nadie tiene Umapesos todavía.")
        embed = discord.Embed(title="🏆 Ranking de Umapesos 🏆", color=discord.Color.gold())
        description = ""
        for i, user_row in enumerate(top_users):
            try:
                user = await self.bot.fetch_user(user_row['user_id'])
                user_name = user.display_name
            except discord.NotFound:
                user_name = f"Usuario Desconocido ({user_row['user_id']})"
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`{i+1}.`"
            description += f"{rank} **{user_name}**: {user_row['balance']} Umapesos\n"
        embed.description = description
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='give', description="Transfiere Umapesos a otro usuario.")
    async def give(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        await ctx.defer()
        sender_id, receiver_id = ctx.author.id, miembro.id
        if sender_id == receiver_id: return await ctx.send("No puedes darte dinero a ti mismo.", ephemeral=True)
        if cantidad <= 0: return await ctx.send("La cantidad debe ser positiva.", ephemeral=True)

        sender_balance = await self.get_balance(sender_id)
        if sender_balance < cantidad: return await ctx.send(f"No tienes suficientes Umapesos. Tu balance: **{sender_balance}**.", ephemeral=True)
        # Realizar ambas transacciones
        await self.update_balance(sender_id, -cantidad)
        await self.update_balance(receiver_id, cantidad)

        embed = discord.Embed(title="💸 Transferencia Realizada", description=f"{ctx.author.mention} le ha transferido **{cantidad} Umapesos** a {miembro.mention}.", color=CREAM_COLOR)
        await ctx.send(embed=embed)

# --- COG DE JUEGOS Y APUESTAS ---
class BlackJackView(discord.ui.View):
    def __init__(self, cog: 'GamblingCog', ctx: commands.Context, bet: int):
        super().__init__(timeout=120.0)
        self.cog = cog
        # No necesitamos guardar todo el contexto, solo el autor para los checks
        self.author = ctx.author
        self.bet = bet
        self.player_hand = [self.cog.deal_card(), self.cog.deal_card()]
        self.dealer_hand = [self.cog.deal_card(), self.cog.deal_card()]
        # El atributo self.message se asignará automáticamente cuando se envíe la vista.
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Comprueba si el usuario que interactúa es el autor original del comando
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("No puedes interactuar con el juego de otra persona.", ephemeral=True, delete_after=10)
            return False
        return True

    async def on_timeout(self):
        # Cuando se acaba el tiempo, desactivamos los botones
        for item in self.children:
            item.disabled = True
        
        timeout_embed = self.create_embed()
        timeout_embed.description = "⌛ El juego ha terminado por inactividad."
        
        # --- INICIO DE LA CORRECCIÓN ---
        # Usamos self.message.edit() que es el método correcto para editar
        # el mensaje al que está adjunta esta vista.
        if self.message:
            try:
                await self.message.edit(embed=timeout_embed, view=self)
            except discord.NotFound:
                pass # El mensaje original fue borrado, no hay nada que hacer.
        # --- FIN DE LA CORRECCIÓN ---

    def update_buttons(self):
        player_score = self.cog.calculate_score(self.player_hand)
        if player_score >= 21:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

    @discord.ui.button(label="Pedir Carta", style=discord.ButtonStyle.success, emoji="➕")
    async def hit(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.player_hand.append(self.cog.deal_card())
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
        if self.cog.calculate_score(self.player_hand) >= 21:
            # Pasamos la interacción para que el final del juego pueda responder.
            await self.cog.end_blackjack_game(interaction, self)

    @discord.ui.button(label="Plantarse", style=discord.ButtonStyle.danger, emoji="🛑")
    async def stand(self, interaction: discord.Interaction, _: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        await self.cog.end_blackjack_game(interaction, self)

    def create_embed(self, show_dealer_card=False):
        player_score = self.cog.calculate_score(self.player_hand)
        dealer_score = self.cog.calculate_score(self.dealer_hand)

        embed = discord.Embed(title="🃏 Blackjack", color=CREAM_COLOR)
        embed.add_field(name=f"Tu Mano ({player_score})", value=" ".join(self.player_hand), inline=False)

        if show_dealer_card:
            embed.add_field(name=f"Mano del Bot ({dealer_score})", value=" ".join(self.dealer_hand), inline=False)
        else:
            embed.add_field(name="Mano del Bot (?)", value=f"{self.dealer_hand[0]} ❔", inline=False)

        embed.set_footer(text=f"Apuesta: {self.bet} Umapesos")
        return embed
    
class GamblingCog(commands.Cog, name="Juegos de Apuestas"):
    """Juegos para apostar tus Umapesos y probar tu suerte."""
    def __init__(self, bot: UmapyoiBot, conn: sqlite3.Connection, lock: asyncio.Lock):
        self.bot = bot
        self.conn = conn
        self.db_lock = lock
        self.cards = ['🇦', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟', '🇯', '🇶', '🇰']
        self.card_values = {'🇦': 11, '2️⃣': 2, '3️⃣': 3, '4️⃣': 4, '5️⃣': 5, '6️⃣': 6, '7️⃣': 7, '8️⃣': 8, '9️⃣': 9, '🔟': 10, '🇯': 10, '🇶': 10, '🇰': 10}

    def get_economy_cog(self) -> Optional[EconomyCog]:
        return self.bot.get_cog("Economía")

    def deal_card(self):
        return random.choice(self.cards)

    def calculate_score(self, hand):
        score = sum(self.card_values[card] for card in hand)
        aces = hand.count('🇦')
        while score > 21 and aces:
            score -= 10
            aces -= 1
        return score

    async def end_blackjack_game(self, interaction: discord.Interaction, view: BlackJackView):
        player_score = self.calculate_score(view.player_hand)

        while self.calculate_score(view.dealer_hand) < 17:
            view.dealer_hand.append(self.deal_card())
        dealer_score = self.calculate_score(view.dealer_hand)

        economy_cog = self.get_economy_cog()
        if not economy_cog: return

        result_message = ""
        if player_score > 21:
            result_message = f"Te pasaste de 21. ¡Perdiste **{view.bet}** Umapesos!"
            await economy_cog.update_balance(interaction.user.id, -view.bet)
        elif dealer_score > 21 or player_score > dealer_score:
            result_message = f"¡Ganaste! Recibes **{view.bet * 2}** Umapesos."
            await economy_cog.update_balance(interaction.user.id, view.bet)
        elif player_score < dealer_score:
            result_message = f"El bot gana. ¡Perdiste **{view.bet}** Umapesos!"
            await economy_cog.update_balance(interaction.user.id, -view.bet)
        else:
            result_message = "¡Es un empate! Recuperas tu apuesta."

        final_embed = view.create_embed(show_dealer_card=True)
        final_embed.description = result_message
        await interaction.edit_original_response(embed=final_embed, view=view)

    @commands.hybrid_command(name='blackjack', description="Juega una partida de Blackjack apostando Umapesos.")
    async def blackjack(self, ctx: commands.Context, apuesta: int):
        economy_cog = self.get_economy_cog()
        if not economy_cog: return await ctx.send("El sistema de economía no está disponible.", ephemeral=True)

        balance = await economy_cog.get_balance(ctx.author.id)
        if apuesta <= 0: return await ctx.send("La apuesta debe ser mayor que cero.", ephemeral=True)
        if balance < apuesta: return await ctx.send(f"No tienes suficientes Umapesos para esa apuesta. Tu balance: **{balance}**", ephemeral=True)

        view = BlackJackView(self, ctx, apuesta)
        await ctx.send(embed=view.create_embed(), view=view)

    @commands.hybrid_command(name='tragamonedas', aliases=['slots'], description="Prueba tu suerte en la máquina tragamonedas.")
    async def slots(self, ctx: commands.Context, apuesta: int):
        economy_cog = self.get_economy_cog()
        if not economy_cog: return await ctx.send("El sistema de economía no está disponible.", ephemeral=True)

        await ctx.defer()
        balance = await economy_cog.get_balance(ctx.author.id)
        if apuesta <= 0: return await ctx.send("La apuesta debe ser mayor que cero.", ephemeral=True)
        if balance < apuesta: return await ctx.send(f"No tienes suficientes Umapesos. Tu balance: **{balance}**", ephemeral=True)

        emojis = ["🍒", "🔔", "🍋", "⭐", "💎", "🍀"]
        reels = [random.choice(emojis) for _ in range(3)]
        result_text = f"**[ {reels[0]} | {reels[1]} | {reels[2]} ]**"

        winnings = 0
        if reels[0] == reels[1] == reels[2]:
            winnings = apuesta * 10
            result_text += f"\n\n**¡JACKPOT!** ¡Ganaste **{winnings}** Umapesos!"
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            winnings = apuesta * 2
            result_text += f"\n\n¡Dos iguales! ¡Ganaste **{winnings}** Umapesos!"
        else:
            result_text += "\n\n¡Mala suerte! Perdiste tu apuesta."

        # El cambio neto es la ganancia menos la apuesta inicial
        net_change = winnings - apuesta
        new_balance = await economy_cog.update_balance(ctx.author.id, net_change)

        embed = discord.Embed(title="🎰 Tragamonedas 🎰", description=result_text, color=CREAM_COLOR)
        embed.set_footer(text=f"Apostaste {apuesta} Umapesos. Tu nuevo balance: {new_balance}")
        await ctx.send(embed=embed)

# --- EVENTOS Y EJECUCIÓN DEL BOT ---
@bot.event
async def on_ready():
    print(f'¡Umapyoi está en línea! Conectado como {bot.user}')
    await bot.change_presence(activity=discord.Game(name="Música y Juegos | /help"))


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    config_cog: Optional[ServerConfigCog] = bot.get_cog("Configuración del Servidor")
    level_cog: Optional[LevelingCog] = bot.get_cog("Niveles")
    tts_cog: Optional[TTSCog] = bot.get_cog("Texto a Voz")

    if config_cog and not message.author.guild_permissions.manage_messages:
        settings = await config_cog.get_settings(message.guild.id)
        if settings:
            if settings["automod_anti_invite"] and ("discord.gg/" in message.content or "discord.com/invite/" in message.content):
                await message.delete()
                await message.channel.send(f"⚠️ {message.author.mention}, no se permiten invitaciones en este servidor.", delete_after=10)
                return

            banned_words_str = settings["automod_banned_words"] or ""
            if banned_words_str:
                # --- INICIO DE LAS LÍNEAS DE DEPURACIÓN ---
                print("--- INICIANDO CHEQUEO DE AUTOMOD ---")
                print(f"Mensaje original: '{message.content}'")
                print(f"Palabras prohibidas desde la DB: '{banned_words_str}'")
                
                banned_words_set = {word.strip().lower() for word in banned_words_str.split(',') if word.strip()}
                print(f"Set de palabras procesadas: {banned_words_set}")

                pattern = r'\b(' + '|'.join(re.escape(word) for word in banned_words_set) + r')\b'
                print(f"Patrón Regex generado: {pattern}")
                
                match = re.search(pattern, message.content, re.IGNORECASE)
                print(f"Resultado de la búsqueda Regex: {match}")
                # --- FIN DE LAS LÍNEAS DE DEPURACIÓN ---

                if match:
                    try:
                        print("¡Palabra prohibida encontrada! Borrando mensaje...")
                        await message.delete()
                        await message.channel.send(f"⚠️ {message.author.mention}, tu mensaje contiene una palabra no permitida.", delete_after=10)
                        print("Mensaje borrado y notificación enviada.")
                    except discord.Forbidden:
                        print(f"Error: No tengo permiso para borrar mensajes en el servidor '{message.guild.name}'.")
                    except Exception as e:
                        print(f"Error inesperado al borrar el mensaje: {e}")
                    return

    await bot.process_commands(message)
    ctx = await bot.get_context(message)
    if ctx.valid:
        return

    if bot.user.mentioned_in(message) and not message.mention_everyone and not message.reference:
        await message.channel.send(f'¡Hola, {message.author.mention}! Usa `/help` para ver todos mis comandos. ✨')
        return

    if config_cog and level_cog:
        settings = await config_cog.get_settings(message.guild.id)
        if settings and settings["leveling_enabled"]:
            await level_cog.process_xp(message)

    if tts_cog:
        await tts_cog.process_tts_message(message)

# --- REEMPLAZA LA FUNCIÓN on_guild_join ANTERIOR CON ESTA ---
@bot.event
async def on_guild_join(guild: discord.Guild):
    """
    Se activa cuando el bot se une a un nuevo servidor.
    Envía un mensaje de bienvenida por DM al dueño del servidor.
    Si falla, lo envía a un canal público como alternativa.
    """
    print(f"¡Me he unido a un nuevo servidor: {guild.name} (ID: {guild.id})!")

    # 1. Recopilar la información y crear el embed (esto no cambia).
    creador_discord = "sakurayo_crispy"
    enlace_servidor = "https://discord.gg/fwNeZsGkSj"
    bot_summary = "Un bot de nueva generación con música, juegos, economía y mucho más. ¡Todo en uno!"

    embed = discord.Embed(
        title=f"👋 ¡Gracias por añadir a Umapyoi a tu servidor '{guild.name}'!",
        description="¡Hola! Estoy aquí para llenar tu servidor de música, juegos y diversión. Aquí tienes una guía rápida para empezar:",
        color=CREAM_COLOR
    )

    if bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    embed.add_field(
        name="1️⃣ Configuración Importante: ¡Permisos!",
        value="Para que mis funciones de moderación (como borrar mensajes con palabras prohibidas) funcionen, **necesito que me des un rol con permisos de Administrador**.",
        inline=False
    )
    embed.add_field(name="2️⃣ ¿Qué hago?", value=bot_summary, inline=False)
    embed.add_field(name="3️⃣ Lista de Comandos", value="Puedes ver todos mis comandos usando el menú interactivo que aparece al escribir `/help`.", inline=False)
    embed.add_field(name="🔗 Servidor de Soporte", value=f"¿Necesitas ayuda o quieres sugerir algo? [¡Únete aquí!]({enlace_servidor})", inline=True)
    embed.add_field(name="👑 Creador", value=creador_discord, inline=True)
    embed.set_footer(text="¡Espero que disfrutes usando Umapyoi!")

    # 2. Intentar enviar el mensaje por DM al dueño del servidor.
    try:
        if guild.owner:
            await guild.owner.send(embed=embed)
            print(f"Mensaje de bienvenida enviado por DM al dueño de '{guild.name}'.")
            return  # Si se envía con éxito, terminamos la función aquí.
    except discord.Forbidden:
        print(f"No pude enviar el DM al dueño de '{guild.name}'. Intentando en un canal público.")
    except Exception as e:
        print(f"Ocurrió un error al intentar enviar el DM al dueño de '{guild.name}': {e}")

    # 3. Alternativa: Si el DM falla, buscar un canal público.
    target_channel = None
    if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
        target_channel = guild.system_channel
    else:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                target_channel = channel
                break
    
    if target_channel:
        try:
            await target_channel.send(embed=embed)
            print(f"Mensaje de bienvenida enviado al canal '{target_channel.name}' en el servidor '{guild.name}'.")
        except Exception as e:
            print(f"Error al enviar el mensaje de bienvenida en el canal público de '{guild.name}': {e}")
    else:
        print(f"Fallo total: No se pudo encontrar ningún canal para enviar el mensaje de bienvenida en '{guild.name}'.")

@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Espera {round(error.retry_after, 1)} segundos.", ephemeral=True)
        return
    elif isinstance(error, commands.CommandNotFound):
        return # Ignorar comandos no encontrados
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes los permisos necesarios para usar este comando.", ephemeral=True)
        return
    elif isinstance(error, commands.BotMissingPermissions):
        # Convierte la lista de permisos faltantes en un texto legible
        permisos_faltantes = ", ".join(perm.replace('_', ' ').capitalize() for perm in error.missing_permissions)
        # Envía el mensaje de error específico al canal
        await ctx.send(f"⚠️ No puedo ejecutar esa acción porque me faltan los siguientes permisos: **{permisos_faltantes}**", ephemeral=True)
        return
    elif isinstance(error, commands.errors.HybridCommandError):
        original = error.original
        if isinstance(original, discord.errors.InteractionResponded):
            print("Ignorando error 'Interaction has already been responded to.'")
            return
        if isinstance(original, discord.errors.NotFound) and original.code in [10062, 10008]:
             print("Ignorando error 'Unknown Interaction' o 'Unknown Message'. La interacción probablemente expiró.")
             return
    
    # Loguear el error para depuración
    command_name = ctx.command.name if ctx.command else "Comando desconocido"
    print(f"Error no manejado en '{command_name}':")
    # Imprimir el traceback completo para una mejor depuración
    import traceback
    traceback.print_exception(type(error), error, error.__traceback__)

    # Intentar enviar un mensaje de error genérico al usuario
    error_message = "Ocurrió un error inesperado al ejecutar el comando. El desarrollador ha sido notificado."
    try:
        if ctx.interaction:
            if not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(error_message, ephemeral=True)
            else:
                await ctx.interaction.followup.send(error_message, ephemeral=True)
        else:
            await ctx.send(error_message)
    except discord.errors.HTTPException as e:
        print(f"No se pudo enviar el mensaje de error al usuario: {e}")

def main():
    if not DISCORD_TOKEN:
        print("¡ERROR! No se encontró el DISCORD_TOKEN en el archivo .env o en los Secrets.")
        return
    if not GENIUS_API_TOKEN:
        print("¡ADVERTENCIA! No se encontró el GENIUS_ACCESS_TOKEN. El comando /lyrics no funcionará.")
    if not GEMINI_API_KEY:
        print("¡ADVERTENCIA! No se encontró la GEMINI_API_KEY. El comando /pregunta no funcionará.")

    try:
        bot.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        print("\n¡ERROR! El token de Discord proporcionado no es válido.")
    except Exception as e:
        print(f"\nOcurrió un error crítico al iniciar el bot: {e}")

if __name__ == "__main__":
    main()