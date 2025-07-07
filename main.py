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
        embed = discord.Embed(title=f"📜 Ayuda de Umapyoi", color=discord.Color.purple())
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
    """La vista definitiva con un diseño de botones ordenado y profesional."""
    def __init__(self, music_cog: "MusicCog", ctx: commands.Context):
        super().__init__(timeout=None)
        self.music_cog = music_cog
        self.ctx = ctx
        self.update_loop_button_style()
        self.update_autoplay_button_style()

    def update_loop_button_style(self):
        state = self.music_cog.get_guild_state(self.ctx.guild.id)
        loop_button = discord.utils.get(self.children, custom_id='loop_button')
        if not loop_button: return

        if state.loop_state == LoopState.OFF:
            loop_button.style = discord.ButtonStyle.secondary
            loop_button.label = "Loop"
            loop_button.emoji = "🔁"
        elif state.loop_state == LoopState.SONG:
            loop_button.style = discord.ButtonStyle.success
            loop_button.label = "Loop Song"
            loop_button.emoji = "🔂"
        elif state.loop_state == LoopState.QUEUE:
            loop_button.style = discord.ButtonStyle.success
            loop_button.label = "Loop Queue"
            loop_button.emoji = "🔁"

    def update_autoplay_button_style(self):
        state = self.music_cog.get_guild_state(self.ctx.guild.id)
        autoplay_button = discord.utils.get(self.children, custom_id='autoplay_button')
        if not autoplay_button: return

        if state.autoplay:
            autoplay_button.style = discord.ButtonStyle.success
        else:
            autoplay_button.style = discord.ButtonStyle.secondary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice or not interaction.guild.voice_client or interaction.user.voice.channel != interaction.guild.voice_client.channel:
            await interaction.response.send_message("Debes estar en el mismo canal de voz que yo para usar los botones.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="⏪", row=0, custom_id="previous_button")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.previous.callback(self.music_cog, self.ctx)
        await interaction.response.defer()

    @discord.ui.button(label="Pausa", style=discord.ButtonStyle.secondary, emoji="⏸️", row=0, custom_id="pause_resume_button")
    async def pause_resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc.is_paused():
            await self.music_cog.resume.callback(self.music_cog, self.ctx)
            button.label = "Pausa"; button.emoji = "⏸️"
        else:
            await self.music_cog.pause.callback(self.music_cog, self.ctx)
            button.label = "Reanudar"; button.emoji = "▶️"
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Saltar", style=discord.ButtonStyle.primary, emoji="⏭️", row=0, custom_id="skip_button")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.skip.callback(self.music_cog, self.ctx)
        await interaction.response.defer()

    @discord.ui.button(label="Barajar", style=discord.ButtonStyle.secondary, emoji="🔀", row=1, custom_id="shuffle_button")
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.shuffle.callback(self.music_cog, self.ctx)
        await interaction.response.defer()

    @discord.ui.button(label="Loop", style=discord.ButtonStyle.secondary, emoji="🔁", row=1, custom_id="loop_button")
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.music_cog.get_guild_state(interaction.guild.id)
        if state.loop_state == LoopState.OFF:
            state.loop_state = LoopState.SONG
            msg = 'Bucle de canción activado.'
        elif state.loop_state == LoopState.SONG:
            state.loop_state = LoopState.QUEUE
            msg = 'Bucle de cola activado.'
        else:
            state.loop_state = LoopState.OFF
            msg = 'Bucle desactivado.'
        self.update_loop_button_style()
        await interaction.response.send_message(f"🔁 {msg}", ephemeral=True, delete_after=5)
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Autoplay", style=discord.ButtonStyle.secondary, emoji="🔄", row=1, custom_id="autoplay_button")
    async def autoplay_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.music_cog.get_guild_state(interaction.guild.id)
        state.autoplay = not state.autoplay
        status = "activado" if state.autoplay else "desactivado"
        self.update_autoplay_button_style()
        await interaction.response.send_message(f"🔄 Autoplay **{status}**.", ephemeral=True, delete_after=5)
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Sonando", style=discord.ButtonStyle.primary, emoji="🎵", row=2, custom_id="nowplaying_button")
    async def nowplaying_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.nowplaying.callback(self.music_cog, self.ctx)
        await interaction.response.defer()

    @discord.ui.button(label="Cola", style=discord.ButtonStyle.primary, emoji="🎶", row=2, custom_id="queue_button")
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.queue_info.callback(self.music_cog, self.ctx)
        await interaction.response.defer()

    @discord.ui.button(label="Letra", style=discord.ButtonStyle.primary, emoji="🎤", row=2, custom_id="lyrics_button")
    async def lyrics_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.lyrics.callback(self.music_cog, self.ctx)
        await interaction.response.defer()

    @discord.ui.button(label="Detener", style=discord.ButtonStyle.danger, emoji="⏹️", row=3, custom_id="stop_button")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.stop.callback(self.music_cog, self.ctx)
        await interaction.response.defer()

    @discord.ui.button(label="Desconectar", style=discord.ButtonStyle.danger, emoji="👋", row=3, custom_id="leave_button")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.leave.callback(self.music_cog, self.ctx)
        await interaction.response.defer()

# --- COG DE MÚSICA ---
class MusicCog(commands.Cog, name="Música"):
    """Comandos para reproducir música de alta calidad."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_states: dict[int, GuildState] = {}
        self.genius = lyricsgenius.Genius(GENIUS_API_TOKEN) if GENIUS_API_TOKEN else None

    def get_guild_state(self, guild_id: int) -> GuildState:
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = GuildState(guild_id)
        return self.guild_states[guild_id]

    async def send_music_panel(self, ctx: commands.Context, song: dict):
        state = self.get_guild_state(ctx.guild.id)
        if state.active_panel:
            try: await state.active_panel.delete()
            except (discord.NotFound, discord.HTTPException): pass

        embed = discord.Embed(title="🎵 Reproduciendo Ahora 🎵", color=discord.Color.blue())
        embed.description = f"**[{song['title']}]({song.get('webpage_url', '#')})**"
        embed.add_field(name="Pedido por", value=song['requester'].mention, inline=True)
        if 'duration' in song and song['duration']:
            embed.add_field(name="Duración", value=str(datetime.timedelta(seconds=song['duration'])), inline=True)
        if 'thumbnail' in song:
            embed.set_thumbnail(url=song['thumbnail'])
        view = MusicPanelView(self, ctx)
        state.active_panel = await ctx.send(embed=embed, view=view)

    def play_next_song(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if state.current_song:
            if state.loop_state == LoopState.SONG:
                state.queue.insert(0, state.current_song)
            elif state.loop_state == LoopState.QUEUE:
                state.queue.append(state.current_song)
            state.history.append(state.current_song)
            if len(state.history) > 20:
                state.history.pop(0)

        if not state.queue:
            state.current_song = None
            if state.autoplay and state.history:
                last_song_title = state.history[-1]['title']
                self.bot.loop.create_task(self.start_autoplay(ctx, last_song_title))
            else:
                self.bot.loop.create_task(self.disconnect_after_inactivity(ctx))
            return

        state.current_song = state.queue.pop(0)
        vc = ctx.guild.voice_client
        if isinstance(vc, discord.VoiceClient) and vc.is_connected():
            try:
                source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(state.current_song['url'], **FFMPEG_OPTIONS),
                    volume=state.volume
                )
                vc.play(source, after=lambda e: self.handle_after_play(ctx, e))
                self.bot.loop.create_task(self.send_music_panel(ctx, state.current_song))
            except Exception as e:
                print(f"Error al reproducir: {e}")
                self.bot.loop.create_task(ctx.channel.send(f'❌ Error al reproducir. Saltando.'))
                self.play_next_song(ctx)

    def handle_after_play(self, ctx: commands.Context, error: Exception | None):
        if error:
            print(f'Error after play: {error}')
        self.bot.loop.call_soon_threadsafe(self.play_next_song, ctx)

    async def disconnect_after_inactivity(self, ctx: commands.Context):
        await asyncio.sleep(120)
        state = self.get_guild_state(ctx.guild.id)
        vc = ctx.guild.voice_client
        if vc and not vc.is_playing() and not vc.is_paused():
            fun_cog = self.bot.get_cog("Juegos e IA")
            if not fun_cog or not fun_cog.game_in_progress.get(ctx.guild.id, False):
                if state.active_panel:
                    try: await state.active_panel.delete()
                    except (discord.NotFound, discord.HTTPException): pass
                    state.active_panel = None
                await vc.disconnect()
                await ctx.channel.send("👋 ¡Adiós! Desconectado por inactividad.")

    async def send_response(self, ctx: commands.Context, content: str = None, embed: discord.Embed = None, ephemeral: bool = False, view: discord.ui.View = None):
        if ctx.interaction:
            if ctx.interaction.response.is_done():
                return await ctx.interaction.followup.send(content, embed=embed, ephemeral=ephemeral, view=view)
            else:
                return await ctx.interaction.response.send_message(content, embed=embed, ephemeral=ephemeral, view=view)
        else:
            return await ctx.send(content, embed=embed, view=view)

    async def start_autoplay(self, ctx: commands.Context, last_song_title: str):
        await ctx.channel.send("🎶 Autoplay activado: buscando canciones similares...")
        await self.play.callback(self, ctx, search_query=f"{last_song_title} mix")

    @commands.hybrid_command(name='join', description="Hace que el bot se una a tu canal de voz.")
    async def join(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await self.send_response(ctx, "Debes estar en un canal de voz para que pueda unirme.", ephemeral=True)
        channel = ctx.author.voice.channel
        if ctx.guild.voice_client:
            await ctx.guild.voice_client.move_to(channel)
        else:
            await channel.connect()
        await self.send_response(ctx, f"👋 ¡Hola! Me he unido a **{channel.name}**.", ephemeral=True)

    @commands.hybrid_command(name='play', aliases=['p'], description="Reproduce una canción o playlist.")
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def play(self, ctx: commands.Context, *, search_query: str):
        if ctx.interaction:
            await ctx.defer(ephemeral=False)
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await self.send_response(ctx, "Debes estar en un canal de voz.", ephemeral=True)
        
        channel = ctx.author.voice.channel
        vc = ctx.guild.voice_client
        if not vc:
            vc = await channel.connect()
        elif vc.channel != channel:
            await vc.move_to(channel)

        msg = await self.send_response(ctx, f'🔎 Procesando: "**{search_query}**"...')
        state = self.get_guild_state(ctx.guild.id)

        from urllib.parse import urlparse, parse_qs
        final_query = search_query
        ydl_opts = YDL_OPTIONS.copy()

        if "youtube.com" in search_query or "youtu.be" in search_query:
            parsed_url = urlparse(search_query)
            query_params = parse_qs(parsed_url.query)
            if 'v' in query_params:
                final_query = f"https://www.youtube.com/watch?v={query_params['v'][0]}"
                ydl_opts['noplaylist'] = True
            elif 'list' in query_params:
                ydl_opts['noplaylist'] = False

        try:
            loop = self.bot.loop or asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(final_query, download=False))
            
            entries = info.get('entries', [info]) if info else []
            if not entries:
                return await msg.edit(content="❌ No encontré nada.")
            
            for entry in entries:
                if entry and entry.get('url'):
                    song = {
                        'title': entry.get('title', 'Título desconocido'),
                        'url': entry.get('url'),
                        'webpage_url': entry.get('webpage_url'),
                        'thumbnail': entry.get('thumbnail'),
                        'duration': entry.get('duration'),
                        'requester': ctx.author
                    }
                    state.queue.append(song)
            
            num_songs = len(entries)
            await msg.edit(content=f'✅ ¡Añadido{"s" if num_songs > 1 else ""} {num_songs} canci{"ón" if num_songs == 1 else "ones"} a la cola!')
            
            if not state.current_song:
                self.play_next_song(ctx)
        except Exception as e:
            error_msg = str(e)
            if 'DRM' in error_msg or 'not DRM protected' in error_msg:
                await msg.edit(content="❌ No puedo reproducir contenido de **Spotify** u otras plataformas con protección DRM.\nPor favor, intenta con un enlace de **YouTube**.")
            else:
                await msg.edit(content=f'❌ Ocurrió un error: {error_msg}')

    @commands.hybrid_command(name='stop', description="Detiene la música y vacía la cola.")
    async def stop(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if vc := ctx.guild.voice_client:
            state.queue.clear()
            state.current_song = None
            vc.stop()
            await self.send_response(ctx, "⏹️ Música detenida.")
            if state.active_panel:
                try: await state.active_panel.delete()
                except (discord.NotFound, discord.HTTPException): pass
                state.active_panel = None
        else:
            await self.send_response(ctx, "No hay nada que detener.", ephemeral=True)

    @commands.hybrid_command(name='skip', aliases=['s'], description="Salta a la siguiente canción.")
    async def skip(self, ctx: commands.Context):
        if (vc := ctx.guild.voice_client) and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await self.send_response(ctx, "⏭️ Canción saltada.", ephemeral=True)
        else:
            await self.send_response(ctx, "No hay nada que saltar.", ephemeral=True)

    @commands.hybrid_command(name='pause', description="Pausa la canción actual.")
    async def pause(self, ctx: commands.Context):
        if (vc := ctx.guild.voice_client) and vc.is_playing():
            vc.pause()
            await self.send_response(ctx, "⏸️ Canción pausada.", ephemeral=True)
        else:
            await self.send_response(ctx, "No hay música sonando para pausar.", ephemeral=True)

    @commands.hybrid_command(name='resume', aliases=['r'], description="Reanuda la música.")
    async def resume(self, ctx: commands.Context):
        if (vc := ctx.guild.voice_client) and vc.is_paused():
            vc.resume()
            await self.send_response(ctx, "▶️ Música reanudada.", ephemeral=True)
        else:
            await self.send_response(ctx, "La música no está pausada.", ephemeral=True)

    @commands.hybrid_command(name='queue', aliases=['q'], description="Muestra la cola de canciones.")
    async def queue_info(self, ctx: commands.Context):
        if ctx.interaction: await ctx.defer(ephemeral=False)
        state = self.get_guild_state(ctx.guild.id)
        if not state.current_song and not state.queue:
            return await self.send_response(ctx, "La cola está vacía.")
        embed = discord.Embed(title="🎵 Cola de Música 🎵", color=discord.Color.blue())
        if state.current_song:
            embed.add_field(name="Reproduciendo ahora", value=f"**{state.current_song['title']}**", inline=False)
        if state.queue:
            next_songs = [f"`{i+1}.` {s['title']}" for i, s in enumerate(state.queue[:10])]
            embed.add_field(name="A continuación:", value="\n".join(next_songs), inline=False)
        if len(state.queue) > 10:
            embed.set_footer(text=f"Y {len(state.queue) - 10} más...")
        await self.send_response(ctx, embed=embed)

    @commands.hybrid_command(name='nowplaying', aliases=['np'], description="Muestra la canción que está sonando.")
    async def nowplaying(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if not state.current_song:
            return await self.send_response(ctx, "No hay ninguna canción reproduciéndose.", ephemeral=True)
        song = state.current_song
        embed = discord.Embed(title="🎵 Sonando Ahora", description=f"**[{song['title']}]({song.get('webpage_url', '#')})**", color=discord.Color.green())
        embed.set_footer(text=f"Pedida por: {song['requester'].display_name}")
        if song.get('thumbnail'):
            embed.set_thumbnail(url=song['thumbnail'])
        await self.send_response(ctx, embed=embed)

    @commands.hybrid_command(name='volume', description="Ajusta el volumen (0-100).")
    async def volume(self, ctx: commands.Context, volume: int):
        state = self.get_guild_state(ctx.guild.id)
        if not (vc := ctx.guild.voice_client):
            return await self.send_response(ctx, "No estoy en un canal de voz.", ephemeral=True)
        if not 0 <= volume <= 100:
            return await self.send_response(ctx, "El volumen debe estar entre 0 y 100.", ephemeral=True)
        state.volume = volume / 100
        if vc.source:
            vc.source.volume = state.volume
        await self.send_response(ctx, f"🔊 Volumen ajustado al **{volume}%**.")

    @commands.hybrid_command(name='loop', description="Activa el modo bucle (song, queue, off).")
    async def loop(self, ctx: commands.Context, mode: Literal['song', 'queue', 'off']):
        state = self.get_guild_state(ctx.guild.id)
        mode = mode.lower()
        if mode == 'off':
            state.loop_state = LoopState.OFF
            await self.send_response(ctx, "🔁 Bucle desactivado.")
        elif mode == 'song':
            state.loop_state = LoopState.SONG
            await self.send_response(ctx, "🔂 Bucle de canción activado.")
        elif mode == 'queue':
            state.loop_state = LoopState.QUEUE
            await self.send_response(ctx, "🔁 Bucle de cola activado.")

    @commands.hybrid_command(name='autoplay', description="Activa o desactiva la reproducción automática.")
    async def autoplay(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        state.autoplay = not state.autoplay
        status = "activado" if state.autoplay else "desactivado"
        await self.send_response(ctx, f"🔄 Autoplay **{status}**.")

    @commands.hybrid_command(name='shuffle', description="Baraja la cola de canciones.")
    async def shuffle(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if not state.queue:
            return await self.send_response(ctx, "La cola está vacía.", ephemeral=True)
        random.shuffle(state.queue)
        await self.send_response(ctx, "🔀 ¡La cola ha sido barajada!")

    @commands.hybrid_command(name='remove', description="Elimina una canción de la cola por su posición.")
    async def remove(self, ctx: commands.Context, posicion: int):
        state = self.get_guild_state(ctx.guild.id)
        if not 1 <= posicion <= len(state.queue):
            return await self.send_response(ctx, "Posición inválida.", ephemeral=True)
        removed_song = state.queue.pop(posicion - 1)
        await self.send_response(ctx, f"🗑️ Se ha eliminado **{removed_song['title']}** de la cola.")

    @commands.hybrid_command(name='move', description="Mueve una canción a una nueva posición en la cola.")
    async def move(self, ctx: commands.Context, cancion: int, posicion: int):
        state = self.get_guild_state(ctx.guild.id)
        if not (1 <= cancion <= len(state.queue) and 1 <= posicion <= len(state.queue)):
            return await self.send_response(ctx, "Posición inválida.", ephemeral=True)
        song_to_move = state.queue.pop(cancion - 1)
        state.queue.insert(posicion - 1, song_to_move)
        await self.send_response(ctx, f"✅ Se ha movido **{song_to_move['title']}** a la posición {posicion}.")

    @commands.hybrid_command(name='skipto', description="Salta a una canción específica en la cola.")
    async def skipto(self, ctx: commands.Context, posicion: int):
        state = self.get_guild_state(ctx.guild.id)
        if not 1 <= posicion <= len(state.queue):
            return await self.send_response(ctx, "Posición inválida.", ephemeral=True)
        state.queue = state.queue[posicion - 1:]
        if (vc := ctx.guild.voice_client) and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        await self.send_response(ctx, f"⏭️ Saltando a la canción en la posición {posicion}.")

    @commands.hybrid_command(name='lyrics', aliases=['letras'], description="Muestra la letra de la canción actual.")
    async def lyrics(self, ctx: commands.Context):
        if not self.genius:
            return await self.send_response(ctx, "❌ La función de letras no está configurada (falta API key de Genius).")
        state = self.get_guild_state(ctx.guild.id)
        if not state.current_song:
            return await self.send_response(ctx, "No hay ninguna canción reproduciéndose.", ephemeral=True)
        if ctx.interaction: await ctx.defer()
        song_title = state.current_song['title']
        try:
            song = await asyncio.to_thread(self.genius.search_song, song_title)
            if song and song.lyrics:
                lyrics_text = song.lyrics
                if len(lyrics_text) > 4000:
                    lyrics_text = lyrics_text[:3997] + "..."
                embed = discord.Embed(title=f"🎤 Letra de: {song.title}", description=lyrics_text, color=discord.Color.purple())
                embed.set_footer(text=f"Artista: {song.artist}")
                await self.send_response(ctx, embed=embed)
            else:
                await self.send_response(ctx, "❌ No se encontraron letras para esta canción.")
        except Exception as e:
            await self.send_response(ctx, f"❌ Ocurrió un error al buscar la letra: {e}")

    @commands.hybrid_command(name='clearqueue', description="Limpia toda la cola de canciones.")
    async def clearqueue(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        state.queue.clear()
        await self.send_response(ctx, "🧹 La cola ha sido vaciada.")

    @commands.hybrid_command(name='previous', description="Reproduce la canción anterior.")
    async def previous(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if not state.history:
            return await self.send_response(ctx, "No hay historial de canciones.", ephemeral=True)
        if state.current_song:
            state.queue.insert(0, state.current_song)
        last_song = state.history.pop()
        state.queue.insert(0, last_song)
        if (vc := ctx.guild.voice_client) and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        else:
            self.play_next_song(ctx)
        await self.send_response(ctx, "⏪ Reproduciendo la canción anterior.")

    @commands.hybrid_command(name='leave', aliases=['disconnect'], description="Desconecta el bot del canal de voz.")
    async def leave(self, ctx: commands.Context):
        if ctx.guild.voice_client:
            await self.stop.callback(self, ctx) # Llama a stop para limpiar todo
            await ctx.guild.voice_client.disconnect()
        else:
            await self.send_response(ctx, "No estoy en ningún canal de voz.", ephemeral=True)

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
        embed = discord.Embed(title=f"🎁 Recompensas de Roles de {ctx.guild.name}", color=discord.Color.blue())
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
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS tts_user_settings (guild_id INTEGER, user_id INTEGER, lang TEXT, is_active INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))''')
        self.conn.commit()

    def get_guild_lang(self, guild_id: int) -> str:
        self.cursor.execute("SELECT lang FROM tts_guild_settings WHERE guild_id = ?", (guild_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 'es'

    def get_user_tts_settings(self, guild_id: int, user_id: int):
        self.cursor.execute("SELECT lang, is_active FROM tts_user_settings WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        result = self.cursor.fetchone()
        if result: return result[0], bool(result[1])
        return None, False

    def set_user_lang(self, guild_id: int, user_id: int, lang: str):
        self.cursor.execute("INSERT OR IGNORE INTO tts_user_settings (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
        self.cursor.execute("UPDATE tts_user_settings SET lang = ? WHERE guild_id = ? AND user_id = ?", (lang, guild_id, user_id))
        self.conn.commit()

    def set_guild_lang(self, guild_id: int, lang: str):
        self.cursor.execute("REPLACE INTO tts_guild_settings (guild_id, lang) VALUES (?, ?)", (guild_id, lang))
        self.conn.commit()

    def set_user_tts_status(self, guild_id: int, user_id: int, is_active: bool):
        self.cursor.execute("INSERT OR IGNORE INTO tts_user_settings (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
        self.cursor.execute("UPDATE tts_user_settings SET is_active = ? WHERE guild_id = ? AND user_id = ?", (int(is_active), guild_id, user_id))
        self.conn.commit()

    async def process_tts_message(self, message: discord.Message):
        user_lang, is_active = self.get_user_tts_settings(message.guild.id, message.author.id)
        if not is_active or not message.author.voice: return
        
        vc = message.guild.voice_client
        if vc and vc.is_playing(): return

        channel = message.author.voice.channel
        if not vc:
            vc = await channel.connect()
        elif vc.channel != channel:
            await vc.move_to(channel)

        lang_code = user_lang or self.get_guild_lang(message.guild.id)
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
                # Ya no se llama a la función de desconexión aquí

            vc.play(source, after=after_playing)
        except Exception as e:
            print(f"Error en TTS automático: {e}")

    @commands.hybrid_command(name='tts', description="Activa o desactiva la lectura automática de tus mensajes.")
    async def tts_toggle(self, ctx: commands.Context, modo: Literal['on', 'off']):
        if not ctx.guild: return await ctx.send("Este comando solo funciona en servidores.", ephemeral=True)
        is_active = (modo.lower() == 'on')
        self.set_user_tts_status(ctx.guild.id, ctx.author.id, is_active)
        status_text = "activado" if is_active else "desactivado"
        await ctx.send(f"🎤 ¡Modo de lectura automática **{status_text}** para ti!", ephemeral=True)

    @commands.hybrid_command(name='set_my_language', description="Elige tu idioma personal para la lectura de mensajes.")
    @discord.app_commands.choices(idioma=[
        discord.app_commands.Choice(name="Español", value="es"),
        discord.app_commands.Choice(name="Inglés (EE.UU.)", value="en"),
        discord.app_commands.Choice(name="Japonés", value="ja"),
        discord.app_commands.Choice(name="Italiano", value="it"),
        discord.app_commands.Choice(name="Francés", value="fr"),
    ])
    async def set_my_language(self, ctx: commands.Context, idioma: discord.app_commands.Choice[str]):
        if not ctx.guild: return await ctx.send("Este comando solo funciona en servidores.", ephemeral=True)
        self.set_user_lang(ctx.guild.id, ctx.author.id, idioma.value)
        await ctx.send(f"✅ Tu idioma para la lectura de mensajes ha sido establecido a **{idioma.name}**.", ephemeral=True)

    @commands.hybrid_command(name='set_server_language', description="[Admin] Establece el idioma de TTS por defecto para el servidor.")
    @commands.has_permissions(administrator=True)
    @discord.app_commands.choices(idioma=[
        discord.app_commands.Choice(name="Español", value="es"),
        discord.app_commands.Choice(name="Inglés (EE.UU.)", value="en"),
        discord.app_commands.Choice(name="Japonés", value="ja"),
        discord.app_commands.Choice(name="Italiano", value="it"),
        discord.app_commands.Choice(name="Francés", value="fr"),
    ])
    async def set_server_language(self, ctx: commands.Context, idioma: discord.app_commands.Choice[str]):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        self.set_guild_lang(ctx.guild.id, idioma.value)
        await ctx.send(f"✅ El idioma por defecto del servidor para TTS ha sido establecido a **{idioma.name}**.")

# --- COG DE UTILIDAD ---
class UtilityCog(commands.Cog, name="Utilidad"):
    """Comandos útiles y de información."""
    def __init__(self, bot: commands.Bot): self.bot = bot
    
    @commands.hybrid_command(name='help', description="Muestra el panel de ayuda interactivo.")
    async def help(self, ctx: commands.Context):
        embed = discord.Embed(title="📜 Ayuda de Umapyoi", color=discord.Color.purple())
        embed.description = "**🚀 Cómo empezar a escuchar música**\n`/play <nombre de la canción o enlace>`\n\n**❓ ¿Qué es Umapyoi?**\nUn bot de nueva generación con música, juegos, economía y mucho más. ¡Todo en uno!\n\n**🎛️ Categorías de Comandos:**"
        embed.set_image(url="https://i.imgur.com/WwexK3G.png")
        embed.set_footer(text="Gracias por elegir a Umapyoi ✨")
        view = HelpView(self.bot)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name='contacto', description="Muestra la información de contacto del creador.")
    async def contacto(self, ctx: commands.Context):
        creador_discord = "sakurayo_crispy"
        embed = discord.Embed(title="📞 Contacto", description=f"Puedes contactar a mi creador a través de Discord.", color=discord.Color.green())
        embed.add_field(name="Creador", value=f"👑 {creador_discord}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='serverhelp', description="Obtén el enlace al servidor de ayuda oficial.")
    async def serverhelp(self, ctx: commands.Context):
        enlace_servidor = "https://discord.gg/fwNeZsGkSj"
        embed = discord.Embed(title="💬 Servidor de Ayuda", description=f"¿Necesitas ayuda o quieres sugerir algo? ¡Únete a nuestro servidor oficial!", color=discord.Color.blurple())
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
        embed = discord.Embed(title=f"Información de {server.name}", color=discord.Color.blue())
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
        vc = ctx.guild.voice_client
        if vc and vc.is_playing(): return await ctx.send("No puedo iniciar un juego mientras reproduzco música.")
        channel = ctx.author.voice.channel
        if not vc: vc = await channel.connect()
        elif vc.channel != channel: await vc.move_to(channel)

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
            music_cog = self.bot.get_cog('Música')
            if not vc.is_playing() and not (music_cog and music_cog.get_guild_state(ctx.guild.id).current_song):
                await vc.disconnect()

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
        embed = discord.Embed(title=f"💰 Balance de {target_user.display_name}", description=f"Tienes **{balance} Umapesos**.", color=discord.Color.green())
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
        embed = discord.Embed(title="💸 Transferencia Realizada", description=f"{ctx.author.mention} le ha transferido **{cantidad} Umapesos** a {miembro.mention}.", color=discord.Color.blue())
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
    print("Cogs cargados.")
    print("-----------------------------------------")
    print("Sincronizando comandos slash...")
    await bot.tree.sync()
    print("¡Comandos sincronizados!")
    await bot.change_presence(activity=discord.Game(name="Música y Juegos | /help"))

@bot.event
async def on_message(message: discord.Message):
    # Ignorar mensajes de bots y mensajes privados
    if message.author.bot or not message.guild:
        return

    # Procesar comandos primero
    await bot.process_commands(message)

    # Si el mensaje es un comando, no procesar XP ni TTS
    if message.content.startswith(bot.command_prefix):
        return

    # Distribuir el mensaje a los cogs relevantes
    level_cog = bot.get_cog("Niveles")
    if level_cog:
        await level_cog.process_xp(message)

    tts_cog = bot.get_cog("Texto a Voz")
    if tts_cog:
        await tts_cog.process_tts_message(message)

@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Espera {round(error.retry_after, 1)} segundos.", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes los permisos necesarios para usar este comando.", ephemeral=True)
    else:
        command_name = ctx.command.name if ctx.command else "Ninguno"
        print(f"Error no manejado en '{command_name}': {error}")
        # Opcional: enviar un mensaje de error genérico al usuario
        try:
            await ctx.send(f"Ocurrió un error inesperado al ejecutar el comando. Ya se ha notificado al desarrollador.", ephemeral=True)
        except discord.errors.InteractionResponded:
            await ctx.followup.send(f"Ocurrió un error inesperado al ejecutar el comando. Ya se ha notificado al desarrollador.", ephemeral=True)


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
