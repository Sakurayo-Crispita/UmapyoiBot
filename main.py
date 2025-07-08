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
from typing import Literal

# --- CONFIGURACIÓN DE APIS Y CONSTANTES ---
load_dotenv()
GENIUS_API_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Usar un solo archivo para toda la base de datos
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
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents, case_insensitive=True, help_command=None)

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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice or not interaction.guild.voice_client or interaction.user.voice.channel != interaction.guild.voice_client.channel:
            await interaction.response.send_message("Debes estar en el mismo canal de voz que yo para usar los botones.", ephemeral=True)
            return False
        return True

    async def update_panel(self, interaction: discord.Interaction):
        """Actualiza los botones del panel y edita el mensaje."""
        state = self.music_cog.get_guild_state(interaction.guild.id)
        
        loop_button = discord.utils.get(self.children, custom_id='loop_button')
        if loop_button:
            if state.loop_state == LoopState.OFF: loop_button.style, loop_button.label, loop_button.emoji = discord.ButtonStyle.secondary, "Loop", "🔁"
            elif state.loop_state == LoopState.SONG: loop_button.style, loop_button.label, loop_button.emoji = discord.ButtonStyle.success, "Loop Song", "🔂"
            elif state.loop_state == LoopState.QUEUE: loop_button.style, loop_button.label, loop_button.emoji = discord.ButtonStyle.success, "Loop Queue", "🔁"

        autoplay_button = discord.utils.get(self.children, custom_id='autoplay_button')
        if autoplay_button:
            autoplay_button.style = discord.ButtonStyle.success if state.autoplay else discord.ButtonStyle.secondary
        
        pause_button = discord.utils.get(self.children, custom_id='pause_resume_button')
        if pause_button and interaction.guild.voice_client:
            if interaction.guild.voice_client.is_paused(): pause_button.label, pause_button.emoji = "Reanudar", "▶️"
            else: pause_button.label, pause_button.emoji = "Pausa", "⏸️"

        try:
            await interaction.message.edit(view=self)
        except discord.NotFound:
            pass # El mensaje ya fue borrado

    async def _execute_command(self, interaction: discord.Interaction, command_name: str):
        """Función auxiliar para ejecutar un comando desde un botón."""
        command = self.music_cog.bot.get_command(command_name)
        if command:
            ctx = await self.music_cog.bot.get_context(interaction)
            # Silenciamos la respuesta del botón para que solo la respuesta del comando sea visible.
            await interaction.response.defer()
            await command.callback(self.music_cog, ctx)

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="⏪", row=0, custom_id="previous_button")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_command(interaction, 'previous')

    @discord.ui.button(label="Pausa", style=discord.ButtonStyle.secondary, emoji="⏸️", row=0, custom_id="pause_resume_button")
    async def pause_resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_command(interaction, 'pause')
        await self.update_panel(interaction) # Actualizamos el panel después

    @discord.ui.button(label="Saltar", style=discord.ButtonStyle.primary, emoji="⏭️", row=0, custom_id="skip_button")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_command(interaction, 'skip')

    @discord.ui.button(label="Barajar", style=discord.ButtonStyle.secondary, emoji="🔀", row=1, custom_id="shuffle_button")
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_command(interaction, 'shuffle')

    @discord.ui.button(label="Loop", style=discord.ButtonStyle.secondary, emoji="🔁", row=1, custom_id="loop_button")
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_command(interaction, 'loop')
        await self.update_panel(interaction)

    @discord.ui.button(label="Autoplay", style=discord.ButtonStyle.secondary, emoji="🔄", row=1, custom_id="autoplay_button")
    async def autoplay_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_command(interaction, 'autoplay')
        await self.update_panel(interaction)

    @discord.ui.button(label="Sonando", style=discord.ButtonStyle.primary, emoji="🎵", row=2, custom_id="nowplaying_button")
    async def nowplaying_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_command(interaction, 'nowplaying')

    @discord.ui.button(label="Cola", style=discord.ButtonStyle.primary, emoji="🎶", row=2, custom_id="queue_button")
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_command(interaction, 'queue')

    @discord.ui.button(label="Letra", style=discord.ButtonStyle.primary, emoji="🎤", row=2, custom_id="lyrics_button")
    async def lyrics_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_command(interaction, 'lyrics')

    @discord.ui.button(label="Detener", style=discord.ButtonStyle.danger, emoji="⏹️", row=3, custom_id="stop_button")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_command(interaction, 'stop')

    @discord.ui.button(label="Desconectar", style=discord.ButtonStyle.danger, emoji="👋", row=3, custom_id="leave_button")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_command(interaction, 'leave')
        
# --- COG DE MÚSICA ---
class MusicCog(commands.Cog, name="Música"):
    """Comandos para reproducir música de alta calidad."""
    def __init__(self, bot: commands.Bot):
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

    async def send_response(self, ctx: commands.Context | discord.Interaction, content: str = None, embed: discord.Embed = None, ephemeral: bool = False, view: discord.ui.View = None):
        """Helper para responder a un Contexto o una Interacción."""
        interaction = ctx.interaction if isinstance(ctx, commands.Context) else ctx
        
        # Si es una interacción y ya fue respondida (o diferida), usa followup.
        if interaction and interaction.response.is_done():
            await interaction.followup.send(content, embed=embed, ephemeral=ephemeral, view=view)
        # Si es una interacción y no ha sido respondida, usa send_message.
        elif interaction:
            await interaction.response.send_message(content, embed=embed, ephemeral=ephemeral, view=view)
        # Si es un comando de prefijo (sin interacción), usa ctx.send.
        elif isinstance(ctx, commands.Context):
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
            state.active_panel = await ctx.channel.send(embed=embed, view=view)
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
                self.bot.loop.create_task(ctx.channel.send('❌ Error al reproducir. Saltando.'))
                self.play_next_song(ctx)

    def handle_after_play(self, ctx: commands.Context, error: Exception | None):
        if error: print(f'Error after play: {error}')
        self.bot.loop.call_soon_threadsafe(self.play_next_song, ctx)

    async def disconnect_after_inactivity(self, ctx: commands.Context):
        await asyncio.sleep(120)
        lock = self.get_voice_lock(ctx.guild.id)
        async with lock:
            vc = ctx.guild.voice_client
            if vc and not vc.is_playing() and not vc.is_paused():
                state = self.get_guild_state(ctx.guild.id)
                if state.active_panel:
                    try: await state.active_panel.delete()
                    except (discord.NotFound, discord.HTTPException): pass
                    state.active_panel = None
                await vc.disconnect()
                await ctx.channel.send("👋 ¡Adiós! Desconectado por inactividad.")

    # --- COMANDOS RESTAURADOS ---

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

        if ctx.interaction: await ctx.defer()
        
        channel = ctx.author.voice.channel
        vc = await self.ensure_voice_client(channel)
        if not vc: return await self.send_response(ctx, "❌ No pude conectarme al canal de voz.", ephemeral=True)

        if ctx.interaction:
            msg = await ctx.interaction.followup.send(f'🔎 Procesando: "**{search_query}**"...')
        else:
            msg = await ctx.send(f'🔎 Procesando: "**{search_query}**"...')
        
        state = self.get_guild_state(ctx.guild.id)
        try:
            loop = self.bot.loop or asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch:{search_query}", download=False))
            
            entries = info.get('entries', [])
            if not entries: return await msg.edit(content="❌ No encontré nada con esa búsqueda.")
            
            # Si no es una playlist, toma solo el primer resultado
            is_playlist = 'playlist' in info.get('extractor', '')
            songs_to_add = entries if is_playlist else [entries[0]]

            for entry in songs_to_add:
                if entry and entry.get('url'):
                    state.queue.append({'title': entry.get('title', 'Título desconocido'), 'url': entry.get('url'), 'webpage_url': entry.get('webpage_url'), 'thumbnail': entry.get('thumbnail'), 'duration': entry.get('duration'), 'requester': ctx.author})
            
            num_songs = len(songs_to_add)
            await msg.edit(content=f'✅ ¡Añadido{"s" if num_songs > 1 else ""} {num_songs} canci{"ón" if num_songs == 1 else "ones"} a la cola!')
            
            if not vc.is_playing() and not state.current_song:
                self.play_next_song(ctx)
        except Exception as e:
            await msg.edit(content=f'❌ Ocurrió un error al buscar la canción: {e}')

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
        song_title = state.current_song['title']
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
        if not state.history:
            return await self.send_response(ctx, "No hay historial de canciones.", ephemeral=True)
        
        if state.current_song: state.queue.insert(0, state.current_song)
        state.queue.insert(0, state.history.pop())
        
        vc = ctx.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()): vc.stop()
        else: self.play_next_song(ctx)
            
        await self.send_response(ctx, "⏪ Reproduciendo la canción anterior.", ephemeral=True)

    @commands.hybrid_command(name='loop', description="Activa o desactiva la repetición (canción/cola).")
    async def loop(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if state.loop_state == LoopState.OFF:
            state.loop_state, msg = LoopState.SONG, 'Bucle de canción activado.'
        elif state.loop_state == LoopState.SONG:
            state.loop_state, msg = LoopState.QUEUE, 'Bucle de cola activado.'
        else:
            state.loop_state, msg = LoopState.OFF, 'Bucle desactivado.'
        await self.send_response(ctx, f"🔁 {msg}", ephemeral=True)

    @commands.hybrid_command(name='autoplay', description="Activa o desactiva el autoplay de canciones.")
    async def autoplay(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        state.autoplay = not state.autoplay
        status = "activado" if state.autoplay else "desactivado"
        await self.send_response(ctx, f"🔄 Autoplay **{status}**.", ephemeral=True)

# --- COG DE NIVELES ---
class LevelingCog(commands.Cog, name="Niveles"):
    """Comandos para ver tu nivel y competir en el ranking de XP."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn = sqlite3.connect(DB_FILE)
        self.cursor = self.conn.cursor()
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

    def get_user_level(self, guild_id: int, user_id: int):
        self.cursor.execute("SELECT level, xp FROM levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        result = self.cursor.fetchone()
        if result:
            return result
        else:
            self.cursor.execute("INSERT INTO levels (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
            self.conn.commit()
            return 1, 0

    def update_user_xp(self, guild_id: int, user_id: int, level: int, xp: int):
        self.cursor.execute("UPDATE levels SET level = ?, xp = ? WHERE guild_id = ? AND user_id = ?", (level, xp, guild_id, user_id))
        self.conn.commit()

    async def check_role_rewards(self, member: discord.Member, new_level: int):
        guild_id = member.guild.id
        self.cursor.execute("SELECT role_id FROM role_rewards WHERE guild_id = ? AND level = ?", (guild_id, new_level))
        result = self.cursor.fetchone()
        if result:
            role_id = result[0]
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
        guild_id = message.guild.id
        user_id = message.author.id
        level, xp = self.get_user_level(guild_id, user_id)
        xp_to_add = random.randint(15, 25)
        new_xp = xp + xp_to_add
        xp_needed = 5 * (level ** 2) + 50 * level + 100
        if new_xp >= xp_needed:
            new_level = level + 1
            xp_leftover = new_xp - xp_needed
            self.update_user_xp(guild_id, user_id, new_level, xp_leftover)
            reward_role = await self.check_role_rewards(message.author, new_level)
            level_up_message = f"🎉 ¡Felicidades {message.author.mention}, has subido al **nivel {new_level}**!"
            if reward_role:
                level_up_message += f"\n🎁 ¡Has ganado el rol {reward_role.mention} como recompensa!"
            try:
                await message.channel.send(level_up_message)
            except discord.Forbidden:
                pass
        else:
            self.update_user_xp(guild_id, user_id, level, new_xp)

    @commands.hybrid_command(name='rank', description="Muestra tu nivel y XP en este servidor.")
    async def rank(self, ctx: commands.Context, miembro: discord.Member | None = None):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        await ctx.defer()
        target_user = miembro or ctx.author
        level, xp = self.get_user_level(ctx.guild.id, target_user.id)
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
        self.cursor.execute("SELECT user_id, level, xp FROM levels WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10", (ctx.guild.id,))
        top_users = self.cursor.fetchall()
        if not top_users: return await ctx.send("Nadie tiene nivel en este servidor todavía. ¡Empieza a chatear para ganar XP!")
        embed = discord.Embed(title=f"🏆 Ranking de Niveles de {ctx.guild.name} 🏆", color=discord.Color.gold())
        description = ""
        for i, (user_id, level, xp) in enumerate(top_users):
            try:
                user = await self.bot.fetch_user(user_id)
                user_name = user.display_name
            except discord.NotFound:
                user_name = f"Usuario Desconocido ({user_id})"
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`{i+1}.`"
            description += f"{rank} **{user_name}**: Nivel {level} ({xp} XP)\n"
        embed.description = description
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='set_level_role', description="Asigna un rol como recompensa por alcanzar un nivel.")
    @commands.has_permissions(administrator=True)
    async def set_level_role(self, ctx: commands.Context, nivel: int, rol: discord.Role):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        self.cursor.execute("REPLACE INTO role_rewards (guild_id, level, role_id) VALUES (?, ?, ?)", (ctx.guild.id, nivel, rol.id))
        self.conn.commit()
        await ctx.send(f"✅ ¡Perfecto! El rol {rol.mention} se dará como recompensa al alcanzar el **nivel {nivel}**.")

    @commands.hybrid_command(name='remove_level_role', description="Elimina la recompensa de rol de un nivel.")
    @commands.has_permissions(administrator=True)
    async def remove_level_role(self, ctx: commands.Context, nivel: int):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        self.cursor.execute("DELETE FROM role_rewards WHERE guild_id = ? AND level = ?", (ctx.guild.id, nivel))
        self.conn.commit()
        await ctx.send(f"🗑️ Se ha eliminado la recompensa de rol para el **nivel {nivel}**.")

    @commands.hybrid_command(name='list_level_roles', description="Muestra todas las recompensas de roles configuradas.")
    async def list_level_roles(self, ctx: commands.Context):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        await ctx.defer()
        self.cursor.execute("SELECT level, role_id FROM role_rewards WHERE guild_id = ? ORDER BY level ASC", (ctx.guild.id,))
        rewards = self.cursor.fetchall()
        if not rewards: return await ctx.send("No hay recompensas de roles configuradas en este servidor.")
        embed = discord.Embed(title=f"🎁 Recompensas de Roles de {ctx.guild.name}", color=CREAM_COLOR)
        description = ""
        for level, role_id in rewards:
            role = ctx.guild.get_role(role_id)
            description += f"**Nivel {level}** → {role.mention if role else 'Rol no encontrado'}\n"
        embed.description = description
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='reset_level', description="Reinicia el nivel de un usuario.")
    @commands.has_permissions(administrator=True)
    async def reset_level(self, ctx: commands.Context, miembro: discord.Member):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        self.update_user_xp(ctx.guild.id, miembro.id, 1, 0)
        await ctx.send(f"🔄 El nivel de {miembro.mention} ha sido reiniciado.")

    @commands.hybrid_command(name='give_xp', description="Otorga XP a un usuario.")
    @commands.has_permissions(administrator=True)
    async def give_xp(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        level, xp = self.get_user_level(ctx.guild.id, miembro.id)
        self.update_user_xp(ctx.guild.id, miembro.id, level, xp + cantidad)
        await ctx.send(f"✨ Se han añadido **{cantidad} XP** a {miembro.mention}.")

# --- COG DE TEXTO A VOZ (TTS) ---
class TTSCog(commands.Cog, name="Texto a Voz"):
    """Comandos para que el bot hable y lea tus mensajes."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn = sqlite3.connect(DB_FILE)
        self.cursor = self.conn.cursor()
        self.setup_tts_database()

    def setup_tts_database(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS tts_guild_settings (guild_id INTEGER PRIMARY KEY, lang TEXT NOT NULL DEFAULT 'es')''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS tts_active_channels (guild_id INTEGER PRIMARY KEY, text_channel_id INTEGER NOT NULL)''')
        self.conn.commit()

    def get_guild_lang(self, guild_id: int) -> str:
        self.cursor.execute("SELECT lang FROM tts_guild_settings WHERE guild_id = ?", (guild_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 'es'

    def set_guild_lang(self, guild_id: int, lang: str):
        self.cursor.execute("REPLACE INTO tts_guild_settings (guild_id, lang) VALUES (?, ?)", (guild_id, lang))
        self.conn.commit()

    def set_active_channel(self, guild_id: int, text_channel_id: int):
        self.cursor.execute("REPLACE INTO tts_active_channels (guild_id, text_channel_id) VALUES (?, ?)", (guild_id, text_channel_id))
        self.conn.commit()

    def get_active_channel(self, guild_id: int) -> int | None:
        self.cursor.execute("SELECT text_channel_id FROM tts_active_channels WHERE guild_id = ?", (guild_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def clear_guild_setup(self, guild_id: int):
        self.cursor.execute("DELETE FROM tts_active_channels WHERE guild_id = ?", (guild_id,))
        self.conn.commit()

    def is_guild_setup(self, guild_id: int) -> bool:
        return self.get_active_channel(guild_id) is not None

    async def process_tts_message(self, message: discord.Message):
        active_channel_id = self.get_active_channel(message.guild.id)
        if not active_channel_id or message.channel.id != active_channel_id:
            return

        music_cog = self.bot.get_cog("Música")
        if not music_cog: return

        vc = message.guild.voice_client
        if not vc or not vc.is_connected(): return
        
        if not message.author.voice or message.author.voice.channel != vc.channel:
            return

        if vc.is_playing(): return

        lang_code = self.get_guild_lang(message.guild.id)
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

        self.set_active_channel(ctx.guild.id, ctx.channel.id)
        await ctx.send(f"✅ ¡Perfecto! A partir de ahora leeré los mensajes enviados en {ctx.channel.mention}.")


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
        self.set_guild_lang(ctx.guild.id, idioma.value)
        await ctx.send(f"✅ El idioma por defecto del servidor para TTS ha sido establecido a **{idioma.name}**.")

# --- COG DE CONFIGURACIÓN DEL SERVIDOR (VERSIÓN COMPLETA) ---

# (Las clases de los Modales de configuración van aquí primero)
class WelcomeConfigModal(discord.ui.Modal, title='Configuración de Bienvenida'):
    def __init__(self, cog, default_message, default_banner):
        super().__init__()
        self.server_config_cog = cog
        self.add_item(discord.ui.TextInput(label="Mensaje de Bienvenida", style=discord.TextStyle.long, placeholder="Usa {user.mention}, {user.name}, {server.name}, {member.count}", default=default_message, required=True))
        self.add_item(discord.ui.TextInput(label="URL del Banner de Bienvenida", placeholder="https://i.imgur.com/WwexK3G.png", default=default_banner, required=False))
    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.server_config_cog.save_setting(guild_id, 'welcome_message', self.children[0].value)
        self.server_config_cog.save_setting(guild_id, 'welcome_banner_url', self.children[1].value or self.server_config_cog.DEFAULT_WELCOME_BANNER)
        await interaction.response.send_message("✅ Configuración de bienvenida guardada.", ephemeral=True)

class GoodbyeConfigModal(discord.ui.Modal, title='Configuración de Despedida'):
    def __init__(self, cog, default_message, default_banner):
        super().__init__()
        self.server_config_cog = cog
        self.add_item(discord.ui.TextInput(label="Mensaje de Despedida", style=discord.TextStyle.long, placeholder="Usa {user.name}, {server.name}, {member.count}", default=default_message, required=True))
        self.add_item(discord.ui.TextInput(label="URL del Banner de Despedida", placeholder="https://i.imgur.com/WwexK3G.png", default=default_banner, required=False))
    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.server_config_cog.save_setting(guild_id, 'goodbye_message', self.children[0].value)
        self.server_config_cog.save_setting(guild_id, 'goodbye_banner_url', self.children[1].value or self.server_config_cog.DEFAULT_GOODBYE_BANNER)
        await interaction.response.send_message("✅ Configuración de despedida guardada.", ephemeral=True)

class ReactionRoleModal(discord.ui.Modal, title="Crear Rol por Reacción"):
    def __init__(self, cog):
        super().__init__()
        self.server_config_cog = cog
        self.add_item(discord.ui.TextInput(label="ID del Mensaje", placeholder="Copia aquí el ID del mensaje al que reaccionar", required=True))
        self.add_item(discord.ui.TextInput(label="Emoji", placeholder="Pega el emoji a usar (ej. ✅)", required=True))
        self.add_item(discord.ui.TextInput(label="ID del Rol", placeholder="Copia aquí el ID del rol a asignar", required=True))
    
    async def on_submit(self, interaction: discord.Interaction):
        message_id = int(self.children[0].value)
        emoji = self.children[1].value
        role_id = int(self.children[2].value)
        
        try:
            self.server_config_cog.add_reaction_role(interaction.guild.id, message_id, emoji, role_id)
            message = await interaction.channel.fetch_message(message_id)
            await message.add_reaction(emoji)
            await interaction.response.send_message("✅ Rol por reacción creado con éxito.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error al crear el rol por reacción: {e}", ephemeral=True)

class ServerConfigCog(commands.Cog, name="Configuración del Servidor"):
    """Comandos para que los administradores configuren el bot en el servidor."""
    
    # --- Constantes y __init__ ---
    DEFAULT_WELCOME_MESSAGE = "¡Bienvenido a {server.name}, {user.mention}! 🎉"
    DEFAULT_WELCOME_BANNER = "https://i.imgur.com/WwexK3G.png" 
    DEFAULT_GOODBYE_MESSAGE = "{user.name} ha dejado el nido. ¡Hasta la próxima! 😢"
    DEFAULT_GOODBYE_BANNER = "https://i.imgur.com/WwexK3G.png"
    TEMP_CHANNEL_PREFIX = "Sala de " # Prefijo para identificar canales temporales

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn = sqlite3.connect(DB_FILE)
        self.cursor = self.conn.cursor()
        self.setup_database()

    def setup_database(self):
        # VERSIÓN CORREGIDA SIN LA COMA EXTRA AL FINAL
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

    def get_settings(self, guild_id: int):
        self.cursor.execute("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
        res = self.cursor.fetchone()
        return {
            "welcome_channel_id": res[1], "goodbye_channel_id": res[2], "log_channel_id": res[3],
            "autorole_id": res[4], "welcome_message": res[5], "welcome_banner_url": res[6],
            "goodbye_message": res[7], "goodbye_banner_url": res[8], "automod_anti_invite": res[9],
            "automod_banned_words": res[10], "temp_channel_creator_id": res[11], "leveling_enabled": res[12]
        } if res else {}

    def save_setting(self, guild_id: int, key: str, value):
        self.cursor.execute("INSERT OR IGNORE INTO server_settings (guild_id) VALUES (?)", (guild_id,))
        self.cursor.execute(f"UPDATE server_settings SET {key} = ? WHERE guild_id = ?", (value, guild_id))
        self.conn.commit()

    def add_reaction_role(self, guild_id, message_id, emoji, role_id):
        self.cursor.execute("REPLACE INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)", (guild_id, message_id, emoji, role_id))
        self.conn.commit()

    # --- Comandos de Configuración ---
    @commands.hybrid_command(name='setwelcomechannel', description="Establece el canal para los mensajes de bienvenida.")
    @commands.has_permissions(manage_guild=True)
    async def set_welcome_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        self.save_setting(ctx.guild.id, 'welcome_channel_id', canal.id)
        await ctx.send(f"✅ Canal de bienvenida establecido en {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name='setgoodbyechannel', description="Establece el canal para los mensajes de despedida.")
    @commands.has_permissions(manage_guild=True)
    async def set_goodbye_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        self.save_setting(ctx.guild.id, 'goodbye_channel_id', canal.id)
        await ctx.send(f"✅ Canal de despedida establecido en {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name='setlogchannel', description="Establece el canal para el registro de moderación.")
    @commands.has_permissions(manage_guild=True)
    async def set_log_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        self.save_setting(ctx.guild.id, 'log_channel_id', canal.id)
        await ctx.send(f"✅ Canal de logs establecido en {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name='setautorole', description="Establece un rol para asignar a nuevos miembros.")
    @commands.has_permissions(manage_guild=True)
    async def set_autorole(self, ctx: commands.Context, rol: discord.Role):
        self.save_setting(ctx.guild.id, 'autorole_id', rol.id)
        await ctx.send(f"✅ El rol {rol.mention} se asignará automáticamente a los nuevos miembros.", ephemeral=True)

    @commands.hybrid_command(name='configwelcome', description="Personaliza el mensaje y banner de bienvenida.")
    @commands.has_permissions(manage_guild=True)
    async def config_welcome(self, ctx: commands.Context):
        settings = self.get_settings(ctx.guild.id)
        await ctx.interaction.response.send_modal(WelcomeConfigModal(self, settings.get("welcome_message") or self.DEFAULT_WELCOME_MESSAGE, settings.get("welcome_banner_url") or self.DEFAULT_WELCOME_BANNER))

    @commands.hybrid_command(name='configgoodbye', description="Personaliza el mensaje y banner de despedida.")
    @commands.has_permissions(manage_guild=True)
    async def config_goodbye(self, ctx: commands.Context):
        settings = self.get_settings(ctx.guild.id)
        await ctx.interaction.response.send_modal(GoodbyeConfigModal(self, settings.get("goodbye_message") or self.DEFAULT_GOODBYE_MESSAGE, settings.get("goodbye_banner_url") or self.DEFAULT_GOODBYE_BANNER))

    @commands.hybrid_command(name='createreactionrole', description="Crea un nuevo rol por reacción.")
    @commands.has_permissions(manage_guild=True)
    async def create_reaction_role(self, ctx: commands.Context):
        await ctx.interaction.response.send_modal(ReactionRoleModal(self))

    @commands.hybrid_group(name="automod", description="Configura las opciones de auto-moderación.")
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Comando de automod inválido. Usa `/automod anti-invites` o `/automod badwords`.", ephemeral=True)

    @commands.hybrid_command(name='setcreatorchannel', description="Establece el canal de voz para crear salas temporales.")
    @commands.has_permissions(manage_guild=True)
    async def set_creator_channel(self, ctx: commands.Context, canal: discord.VoiceChannel):
        self.save_setting(ctx.guild.id, 'temp_channel_creator_id', canal.id)
        await ctx.send(f"✅ ¡Perfecto! Ahora, quien se una a **{canal.name}** creará su propia sala de voz.", ephemeral=True)

    @commands.hybrid_command(name='removecreatorchannel', description="Desactiva la creación de salas de voz temporales.")
    @commands.has_permissions(manage_guild=True)
    async def remove_creator_channel(self, ctx: commands.Context):
        # Establece el valor a NULL en la base de datos, desactivando la función
        self.save_setting(ctx.guild.id, 'temp_channel_creator_id', None)
        await ctx.send("✅ La función de crear salas de voz temporales ha sido desactivada.", ephemeral=True)

    # Dentro de ServerConfigCog
    @commands.hybrid_command(name='levels', description="Activa o desactiva el sistema de niveles en el servidor.")
    @commands.has_permissions(manage_guild=True)
    async def toggle_leveling(self, ctx: commands.Context, estado: Literal['on', 'off']):
        is_on = 1 if estado == 'on' else 0
        self.save_setting(ctx.guild.id, 'leveling_enabled', is_on)
        status_text = "activado" if is_on else "desactivado"
        await ctx.send(f"✅ El sistema de niveles ha sido **{status_text}** en este servidor.", ephemeral=True)


    @automod.command(name="anti_invites", description="Activa o desactiva el borrado de invitaciones de Discord.")
    async def anti_invites(self, ctx: commands.Context, estado: Literal['on', 'off']):
        is_on = 1 if estado == 'on' else 0
        self.save_setting(ctx.guild.id, 'automod_anti_invite', is_on)
        await ctx.send(f"✅ El filtro anti-invitaciones ha sido **{estado}**.", ephemeral=True)

    @automod.group(name="badwords", description="Gestiona la lista de palabras prohibidas.")
    async def badwords(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Comando de badwords inválido. Usa `/automod badwords add/remove/list`.", ephemeral=True)

    @badwords.command(name="add", description="Añade una palabra a la lista de palabras prohibidas.")
    async def badwords_add(self, ctx: commands.Context, palabra: str):
        settings = self.get_settings(ctx.guild.id)
        current_words_str = settings.get("automod_banned_words", "") or ""
        word_list = [word.strip() for word in current_words_str.split(',') if word.strip()]
        
        if palabra.lower() not in word_list:
            word_list.append(palabra.lower())
            new_words_str = ",".join(word_list)
            self.save_setting(ctx.guild.id, 'automod_banned_words', new_words_str)
            await ctx.send(f"✅ La palabra `{palabra}` ha sido añadida a la lista de palabras prohibidas.", ephemeral=True)
        else:
            await ctx.send(f"⚠️ La palabra `{palabra}` ya estaba en la lista.", ephemeral=True)

    @badwords.command(name="remove", description="Quita una palabra de la lista de prohibidas.")
    async def badwords_remove(self, ctx: commands.Context, palabra: str):
        settings = self.get_settings(ctx.guild.id)
        current_words_str = settings.get("automod_banned_words", "") or ""
        word_list = [word.strip() for word in current_words_str.split(',') if word.strip()]

        if palabra.lower() in word_list:
            word_list.remove(palabra.lower())
            new_words_str = ",".join(word_list)
            self.save_setting(ctx.guild.id, 'automod_banned_words', new_words_str)
            await ctx.send(f"✅ La palabra `{palabra}` ha sido eliminada de la lista.", ephemeral=True)
        else:
            await ctx.send(f"⚠️ La palabra `{palabra}` no se encontró en la lista.", ephemeral=True)

    @badwords.command(name="list", description="Muestra la lista de palabras prohibidas.")
    async def badwords_list(self, ctx: commands.Context):
        settings = self.get_settings(ctx.guild.id)
        words = settings.get("automod_banned_words", "La lista está vacía.")
        await ctx.send(f"**Lista de palabras prohibidas:**\n`{words}`", ephemeral=True)


    # --- Listeners (Eventos) ---
    async def log_event(self, guild_id, embed):
        settings = self.get_settings(guild_id)
        if settings and (log_channel_id := settings.get("log_channel_id")):
            if log_channel := self.bot.get_channel(log_channel_id):
                try: await log_channel.send(embed=embed)
                except discord.Forbidden: pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild_id = member.guild.id
        settings = self.get_settings(guild_id)
        creator_channel_id = settings.get("temp_channel_creator_id")

        # --- Lógica para CREAR un canal temporal ---
        # Si el usuario se une al canal creador
        if after.channel and after.channel.id == creator_channel_id:
            try:
                # Definir permisos para el creador del canal
                overwrites = {
                    member.guild.default_role: discord.PermissionOverwrite(view_channel=True),
                    member: discord.PermissionOverwrite(view_channel=True, manage_channels=True, manage_permissions=True, move_members=True, mute_members=True, deafen_members=True)
                }
                
                # Crear el nuevo canal de voz en la misma categoría que el canal creador
                temp_channel = await member.guild.create_voice_channel(
                    name=f"{self.TEMP_CHANNEL_PREFIX}{member.display_name}",
                    category=after.channel.category,
                    overwrites=overwrites,
                    reason=f"Canal temporal creado por {member.display_name}"
                )
                
                # Mover al miembro a su nuevo canal
                await member.move_to(temp_channel)
            except Exception as e:
                print(f"No se pudo crear el canal temporal: {e}")

        # --- Lógica para BORRAR un canal temporal ---
        # Si el usuario se va de un canal (y ese canal era temporal y ahora está vacío)
        if before.channel and before.channel.name.startswith(self.TEMP_CHANNEL_PREFIX):
            # Esperamos un segundo para evitar problemas de concurrencia
            await asyncio.sleep(1) 
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Canal temporal vacío.")
                except Exception as e:
                    print(f"No se pudo borrar el canal temporal: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = self.get_settings(member.guild.id)
        if not settings: return
        
        # Bienvenida
        if channel_id := settings.get("welcome_channel_id"):
            if channel := self.bot.get_channel(channel_id):
                message = (settings.get("welcome_message") or self.DEFAULT_WELCOME_MESSAGE).format(user=member, server=member.guild, member=member)
                banner_url = settings.get("welcome_banner_url") or self.DEFAULT_WELCOME_BANNER
                embed = discord.Embed(description=message, color=discord.Color.green())
                embed.set_author(name=f"¡Bienvenido a {member.guild.name}!", icon_url=member.display_avatar.url)
                if banner_url: embed.set_image(url=banner_url)
                embed.set_footer(text=f"Ahora somos {member.guild.member_count} miembros.")
                try: await channel.send(embed=embed)
                except discord.Forbidden: pass
        
        # Autorol
        if role_id := settings.get("autorole_id"):
            if role := member.guild.get_role(role_id):
                try: await member.add_roles(role, reason="Autorol al unirse")
                except discord.Forbidden: pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        settings = self.get_settings(member.guild.id)
        if settings and (channel_id := settings.get("goodbye_channel_id")):
            if channel := self.bot.get_channel(channel_id):
                message = (settings.get("goodbye_message") or self.DEFAULT_GOODBYE_MESSAGE).format(user=member, server=member.guild, member=member)
                banner_url = settings.get("goodbye_banner_url") or self.DEFAULT_GOODBYE_BANNER
                embed = discord.Embed(description=message, color=discord.Color.red())
                embed.set_author(name=f"Adiós, {member.display_name}", icon_url=member.display_avatar.url)
                if banner_url: embed.set_image(url=banner_url)
                embed.set_footer(text=f"Ahora somos {member.guild.member_count} miembros.")
                try: await channel.send(embed=embed)
                except discord.Forbidden: pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        embed = discord.Embed(description=f"**Mensaje de {message.author.mention} borrado en {message.channel.mention}**\n{message.content}", color=discord.Color.orange(), timestamp=datetime.datetime.now())
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        await self.log_event(message.guild.id, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content: return
        embed = discord.Embed(description=f"**{before.author.mention} editó un mensaje en {before.channel.mention}** [Ir al mensaje]({after.jump_url})", color=discord.Color.blue(), timestamp=datetime.datetime.now())
        embed.add_field(name="Antes", value=before.content[:1024], inline=False)
        embed.add_field(name="Después", value=after.content[:1024], inline=False)
        embed.set_author(name=before.author.display_name, icon_url=before.author.display_avatar.url)
        await self.log_event(before.guild.id, embed)
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member.bot: return
        self.cursor.execute("SELECT role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?", (payload.guild_id, payload.message_id, str(payload.emoji)))
        result = self.cursor.fetchone()
        if result:
            guild = self.bot.get_guild(payload.guild_id)
            role = guild.get_role(result[0])
            if role:
                try: await payload.member.add_roles(role, reason="Rol por reacción")
                except discord.Forbidden: pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        self.cursor.execute("SELECT role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?", (payload.guild_id, payload.message_id, str(payload.emoji)))
        result = self.cursor.fetchone()
        if result:
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            if member:
                role = guild.get_role(result[0])
                if role:
                    try: await member.remove_roles(role, reason="Rol por reacción")
                    except discord.Forbidden: pass
# --- COG DE UTILIDAD ---
class UtilityCog(commands.Cog, name="Utilidad"):
    """Comandos útiles y de información."""
    def __init__(self, bot: commands.Bot): self.bot = bot
    
    @commands.hybrid_command(name='help', description="Muestra el panel de ayuda interactivo.")
    async def help(self, ctx: commands.Context):
        embed = discord.Embed(title="📜 Ayuda de Umapyoi", color=CREAM_COLOR)
        embed.description = "**🚀 Cómo empezar a escuchar música**\n`/play <nombre de la canción o enlace>`\n\n**❓ ¿Qué es Umapyoi?**\nUn bot de nueva generación con música, juegos, economía y mucho más. ¡Todo en uno!\n\n**🎛️ Categorías de Comandos:**"
        embed.set_image(url="https://i.imgur.com/WwexK3G.png")
        embed.set_footer(text="Gracias por elegir a Umapyoi ✨")
        view = HelpView(self.bot)
        await ctx.send(embed=embed, view=view)

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
        embed.add_field(name="Cuenta Creada", value=miembro.created_at.strftime("%d/%m/%Y"), inline=True)
        if miembro.joined_at:
            embed.add_field(name="Se Unió al Servidor", value=miembro.joined_at.strftime("%d/%m/%Y"), inline=True)
        roles = [role.mention for role in miembro.roles[1:]]
        embed.add_field(name=f"Roles ({len(roles)})", value=", ".join(roles) if roles else "Ninguno", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='serverinfo', description="Muestra información sobre este servidor.")
    async def serverinfo(self, ctx: commands.Context):
        server = ctx.guild
        if not server: return
        embed = discord.Embed(title=f"Información de {server.name}", color=CREAM_COLOR)
        if server.icon: embed.set_thumbnail(url=server.icon.url)
        if server.owner: embed.add_field(name="👑 Propietario", value=server.owner.mention, inline=True)
        embed.add_field(name="👥 Miembros", value=server.member_count, inline=True)
        embed.add_field(name="📅 Creado el", value=server.created_at.strftime("%d/%m/%Y"), inline=True)
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
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.game_in_progress: dict[int, bool] = {}
        self.song_list = [{'url': 'https://www.youtube.com/watch?v=kJQP7kiw5Fk', 'answers': ['despacito']}]

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

    @commands.hybrid_command(name='adivina', description="Inicia un juego de 'Adivina la Canción'.")
    async def adivina(self, ctx: commands.Context):
        await ctx.defer()
        if self.game_in_progress.get(ctx.guild.id): return await ctx.send("Ya hay un juego en curso.")
        if not ctx.author.voice: return await ctx.send("Debes estar en un canal de voz.")
        
        channel = ctx.author.voice.channel
        music_cog = self.bot.get_cog("Música")
        if not music_cog: return # No debería pasar
        
        vc = await music_cog.ensure_voice_client(channel)
        if not vc: return await ctx.send("❌ No pude conectarme al canal de voz.")
        if vc.is_playing(): return await ctx.send("No puedo iniciar un juego mientras reproduzco música.")

        self.game_in_progress[ctx.guild.id] = True
        try:
            song_to_guess = random.choice(self.song_list)
            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(song_to_guess['url'], download=False))
            source = discord.FFmpegPCMAudio(info['url'], before_options=f'-ss {random.randint(30, 60)} -t 15', options='-vn')
            vc.play(source)
            await ctx.send("🎧 **¡Adivina la Canción!** Tienes 30 segundos...")

            def check(m):
                return m.channel == ctx.channel and any(re.sub(r'[^a-z0-9]', '', a) in re.sub(r'[^a-z0-9]', '', m.content.lower()) for a in song_to_guess['answers'])
            
            try:
                winner = await self.bot.wait_for('message', check=check, timeout=30.0)
                await ctx.send(f"🎉 ¡Correcto, {winner.author.mention}! La canción era **{info.get('title')}**.")
            except asyncio.TimeoutError:
                await ctx.send(f"⌛ ¡Se acabó el tiempo! La respuesta era **{info.get('title')}**.")
        except Exception as e:
            await ctx.send(f"❌ Hubo un problema al iniciar el juego: {e}")
        finally:
            if vc.is_playing(): vc.stop()
            self.game_in_progress[ctx.guild.id] = False
            await asyncio.sleep(5)
            if not vc.is_playing() and not (music_cog and music_cog.get_guild_state(ctx.guild.id).current_song):
                await vc.disconnect()
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
                        
                        # Crear el embed con la información
                        embed = discord.Embed(
                            title=anime_data.get('title', 'N/A'),
                            url=anime_data.get('url', ''),
                            description=anime_data.get('synopsis', 'No hay sinopsis disponible.')[:1000] + "...",
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
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn = sqlite3.connect(DB_FILE)
        self.cursor = self.conn.cursor()
        self.setup_database()

    def setup_database(self):
        self.cursor.execute('CREATE TABLE IF NOT EXISTS balances (user_id INTEGER PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0)')
        self.conn.commit()

    def get_balance(self, user_id: int) -> int:
        self.cursor.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        if result: return result[0]
        else:
            self.cursor.execute("INSERT INTO balances (user_id, balance) VALUES (?, ?)", (user_id, 0))
            self.conn.commit()
            return 0

    def update_balance(self, user_id: int, amount: int):
        new_balance = self.get_balance(user_id) + amount
        self.cursor.execute("UPDATE balances SET balance = ? WHERE user_id = ?", (new_balance, user_id))
        self.conn.commit()

    @commands.hybrid_command(name='daily', description="Reclama tu recompensa diaria de Umapesos.")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx: commands.Context):
        await ctx.defer()
        amount = random.randint(100, 500)
        self.update_balance(ctx.author.id, amount)
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

    @commands.hybrid_command(name='balance', aliases=['bal'], description="Muestra cuántos Umapesos tienes.")
    async def balance(self, ctx: commands.Context, miembro: discord.Member | None = None):
        await ctx.defer()
        target_user = miembro or ctx.author
        balance = self.get_balance(target_user.id)
        embed = discord.Embed(title=f"💰 Balance de {target_user.display_name}", description=f"Tienes **{balance} Umapesos**.", color=CREAM_COLOR)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='leaderboard', aliases=['lb'], description="Muestra a los usuarios más ricos.")
    async def leaderboard(self, ctx: commands.Context):
        await ctx.defer()
        self.cursor.execute("SELECT user_id, balance FROM balances ORDER BY balance DESC LIMIT 10")
        top_users = self.cursor.fetchall()
        if not top_users: return await ctx.send("Nadie tiene Umapesos todavía.")
        embed = discord.Embed(title="🏆 Ranking de Umapesos 🏆", color=discord.Color.gold())
        description = ""
        for i, (user_id, balance) in enumerate(top_users):
            try:
                user = await self.bot.fetch_user(user_id)
                user_name = user.display_name
            except discord.NotFound:
                user_name = f"Usuario Desconocido ({user_id})"
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`{i+1}.`"
            description += f"{rank} **{user_name}**: {balance} Umapesos\n"
        embed.description = description
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='give', description="Transfiere Umapesos a otro usuario.")
    async def give(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        await ctx.defer()
        sender_id, receiver_id = ctx.author.id, miembro.id
        if sender_id == receiver_id: return await ctx.send("No puedes darte dinero a ti mismo.", ephemeral=True)
        if cantidad <= 0: return await ctx.send("La cantidad debe ser positiva.", ephemeral=True)
        sender_balance = self.get_balance(sender_id)
        if sender_balance < cantidad: return await ctx.send(f"No tienes suficientes Umapesos. Tu balance: **{sender_balance}**.", ephemeral=True)
        self.update_balance(sender_id, -cantidad)
        self.update_balance(receiver_id, cantidad)
        embed = discord.Embed(title="💸 Transferencia Realizada", description=f"{ctx.author.mention} le ha transferido **{cantidad} Umapesos** a {miembro.mention}.", color=CREAM_COLOR)
        await ctx.send(embed=embed)

# --- COG DE JUEGOS Y APUESTAS ---

class BlackJackView(discord.ui.View):
    def __init__(self, cog, ctx, bet):
        super().__init__(timeout=120.0)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.player_hand = [self.cog.deal_card(), self.cog.deal_card()]
        self.dealer_hand = [self.cog.deal_card(), self.cog.deal_card()]
        self.update_buttons()

    def update_buttons(self):
        player_score = self.cog.calculate_score(self.player_hand)
        # Deshabilitar botones si el jugador se pasa de 21 o tiene Blackjack
        if player_score >= 21:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

    @discord.ui.button(label="Pedir Carta", style=discord.ButtonStyle.success, emoji="➕")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player_hand.append(self.cog.deal_card())
        player_score = self.cog.calculate_score(self.player_hand)
        
        if player_score >= 21:
            # El juego termina automáticamente si el jugador se pasa o llega a 21
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
            await self.cog.end_blackjack_game(self.ctx, self)
        else:
            # Si el juego continúa, solo actualiza el mensaje
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Plantarse", style=discord.ButtonStyle.danger, emoji="🛑")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Deshabilitar todos los botones una vez que el jugador se planta
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(embed=self.create_embed(show_dealer_card=True), view=self)
        await self.cog.end_blackjack_game(self.ctx, self)

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
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn = sqlite3.connect(DB_FILE)
        self.cursor = self.conn.cursor()
        self.cards = ['<:A:123456789>', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'] # Reemplaza el ID del emoji por uno real si tienes

    def get_economy_cog(self) -> EconomyCog:
        # Helper para obtener una instancia del EconomyCog
        return self.bot.get_cog("Economía")

    # --- Lógica de Blackjack ---
    def deal_card(self):
        return random.choice(self.cards)

    def calculate_score(self, hand):
        score = 0
        aces = 0
        for card in hand:
            if card.isdigit():
                score += int(card)
            elif card in ['J', 'Q', 'K']:
                score += 10
            elif card.startswith('<:A'): # As
                aces += 1
                score += 11
        while score > 21 and aces:
            score -= 10
            aces -= 1
        return score

    async def end_blackjack_game(self, ctx: commands.Context, view: BlackJackView):
        player_score = self.calculate_score(view.player_hand)
        
        # El bot pide cartas hasta llegar a 17 o más
        while self.calculate_score(view.dealer_hand) < 17:
            view.dealer_hand.append(self.deal_card())
            
        dealer_score = self.calculate_score(view.dealer_hand)
        
        # Actualizar el embed final para mostrar la mano completa del dealer
        final_embed = view.create_embed(show_dealer_card=True)
        
        economy_cog = self.get_economy_cog()
        result_message = ""
        
        if player_score > 21:
            result_message = f"Te pasaste de 21. ¡Perdiste **{view.bet}** Umapesos!"
            economy_cog.update_balance(ctx.author.id, -view.bet)
        elif dealer_score > 21 or player_score > dealer_score:
            result_message = f"¡Ganaste! Recibes **{view.bet}** Umapesos."
            economy_cog.update_balance(ctx.author.id, view.bet)
        elif player_score < dealer_score:
            result_message = f"El bot gana. ¡Perdiste **{view.bet}** Umapesos!"
            economy_cog.update_balance(ctx.author.id, -view.bet)
        else:
            result_message = "¡Es un empate! Recuperas tu apuesta."
        
        final_embed.description = result_message
        await ctx.interaction.edit_original_response(embed=final_embed, view=view)


    @commands.hybrid_command(name='blackjack', description="Juega una partida de Blackjack apostando Umapesos.")
    async def blackjack(self, ctx: commands.Context, apuesta: int):
        economy_cog = self.get_economy_cog()
        if not economy_cog: return await ctx.send("El sistema de economía no está disponible.", ephemeral=True)
        
        balance = economy_cog.get_balance(ctx.author.id)
        if apuesta <= 0: return await ctx.send("La apuesta debe ser mayor que cero.", ephemeral=True)
        if balance < apuesta: return await ctx.send(f"No tienes suficientes Umapesos para esa apuesta. Tu balance: **{balance}**", ephemeral=True)
        
        view = BlackJackView(self, ctx, apuesta)
        await ctx.send(embed=view.create_embed(), view=view)

    @commands.hybrid_command(name='tragamonedas', aliases=['slots'], description="Prueba tu suerte en la máquina tragamonedas.")
    async def slots(self, ctx: commands.Context, apuesta: int):
        economy_cog = self.get_economy_cog()
        if not economy_cog: return await ctx.send("El sistema de economía no está disponible.", ephemeral=True)

        balance = economy_cog.get_balance(ctx.author.id)
        if apuesta <= 0: return await ctx.send("La apuesta debe ser mayor que cero.", ephemeral=True)
        if balance < apuesta: return await ctx.send(f"No tienes suficientes Umapesos. Tu balance: **{balance}**", ephemeral=True)

        # Restar la apuesta inicial
        economy_cog.update_balance(ctx.author.id, -apuesta)

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
            result_text += "\n\n¡Mala suerte! No ganaste nada esta vez."

        if winnings > 0:
            economy_cog.update_balance(ctx.author.id, winnings)

        embed = discord.Embed(title="🎰 Tragamonedas 🎰", description=result_text, color=CREAM_COLOR)
        embed.set_footer(text=f"Apostaste {apuesta} Umapesos. Tu nuevo balance: {economy_cog.get_balance(ctx.author.id)}")
        await ctx.send(embed=embed)

# --- EVENTOS Y EJECUCIÓN DEL BOT ---
@bot.event
async def on_ready():
    print(f'¡Umapyoi está en línea! Conectado como {bot.user}')
    print('-----------------------------------------')
    print("Cargando Cogs...")
    await bot.add_cog(MusicCog(bot))
    await bot.add_cog(UtilityCog(bot))
    await bot.add_cog(FunCog(bot))
    await bot.add_cog(EconomyCog(bot))
    await bot.add_cog(LevelingCog(bot))
    await bot.add_cog(TTSCog(bot))
    await bot.add_cog(ServerConfigCog(bot))
    await bot.add_cog(GamblingCog(bot))
    print("Cogs cargados.")
    print("-----------------------------------------")
    print("Sincronizando comandos slash...")
    await bot.tree.sync()
    print("¡Comandos sincronizados!")
    await bot.change_presence(activity=discord.Game(name="Música y Juegos | /help"))

@bot.event
async def on_message(message: discord.Message):
    # 1. Ignorar bots y mensajes privados
    if message.author.bot or not message.guild:
        return

    # --- LÓGICA CORREGIDA ---

    # 2. Obtener los Cogs importantes al principio.
    config_cog = bot.get_cog("Configuración del Servidor")
    level_cog = bot.get_cog("Niveles")
    tts_cog = bot.get_cog("Texto a Voz")

    # 3. Lógica de Automod
    # No aplicar automod a moderadores
    if not message.author.guild_permissions.manage_messages and config_cog:
        settings = config_cog.get_settings(message.guild.id)
        # Filtro Anti-invites
        if settings.get("automod_anti_invite", 1) and ("discord.gg/" in message.content or "discord.com/invite/" in message.content):
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention}, no se permiten invitaciones en este servidor.", delete_after=10)
            return

        # Filtro de Palabras Prohibidas
        banned_words_str = settings.get("automod_banned_words", "") or ""
        if banned_words_str:
            banned_words = [word.strip() for word in banned_words_str.split(',')]
            if any(word in message.content.lower() for word in banned_words):
                await message.delete()
                await message.channel.send(f"⚠️ {message.author.mention}, tu mensaje contiene una palabra no permitida.", delete_after=10)
                return

    # 4. Procesar comandos
    await bot.process_commands(message)
    ctx = await bot.get_context(message)
    if ctx.valid:
        return

    # 5. Responder a menciones
    if bot.user.mentioned_in(message) and not message.mention_everyone and not message.reference:
        await message.channel.send(f'¡Hola, {message.author.mention}! Usa `/help` para ver todos mis comandos. ✨')
        return

    # 6. Procesar XP (si el sistema está activado)
    if config_cog and level_cog:
        settings = config_cog.get_settings(message.guild.id)
        if settings.get("leveling_enabled", 1):
            await level_cog.process_xp(message)

    # 7. Procesar TTS
    if tts_cog:
        await tts_cog.process_tts_message(message)

@bot.event
async def on_command_error(ctx: commands.Context, error):
    # Manejadores para errores comunes y esperados
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Espera {round(error.retry_after, 1)} segundos.", ephemeral=True)
        return
    elif isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes los permisos necesarios para usar este comando.", ephemeral=True)
        return

    # Loguear el error para depuración
    command_name = ctx.command.name if ctx.command else "Ninguno"
    print(f"Error no manejado en '{command_name}': {error}")

    # Ignorar errores de interacción que ya fueron manejados o expiraron
    if isinstance(error, commands.errors.HybridCommandError):
        original = error.original
        if isinstance(original, discord.errors.HTTPException) and original.code == 40060:
            print("Ignorando error 'Interaction has already been acknowledged.'")
            return
        if isinstance(original, discord.errors.NotFound) and original.code == 10062:
            print("Ignorando error 'Unknown Interaction.' La interacción probablemente expiró.")
            return

    # Intentar enviar un mensaje de error genérico al usuario de forma segura
    error_message = "Ocurrió un error inesperado al ejecutar el comando. Ya se ha notificado al desarrollador."
    try:
        # Para comandos de barra, la forma de responder depende de si ya se ha "diferido"
        if ctx.interaction:
            if ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(error_message, ephemeral=True)
            else:
                await ctx.interaction.response.send_message(error_message, ephemeral=True)
        # Para comandos de prefijo, simplemente se envía al canal
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
