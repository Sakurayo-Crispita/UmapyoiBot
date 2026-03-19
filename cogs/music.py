import discord
from discord.ext import commands
import yt_dlp
import asyncio
import datetime
import random
import lyricsgenius
from enum import Enum
import re
import os
from utils import constants
from utils import database_manager as db

# --- CLASES AUXILIARES DE MÚSICA ---
class LoopState(Enum):
    OFF = 0; SONG = 1; QUEUE = 2

def format_duration(seconds: int) -> str:
    """Invierte segundos a un formato amigable (ej: 4m 20s)."""
    if not seconds: return "Desconocido"
    if seconds >= 3600:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m {seconds % 60}s"
    return f"{seconds // 60}m {seconds % 60}s"

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

class MusicPanelView(discord.ui.View):
    def __init__(self, music_cog: "MusicCog"):
        super().__init__(timeout=None)
        self.music_cog = music_cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice or not interaction.guild.voice_client or interaction.user.voice.channel != interaction.guild.voice_client.channel:
            await interaction.response.send_message("Debes estar en el mismo canal de voz que yo para usar los botones.", ephemeral=True, delete_after=10)
            return False
        return True

    def _update_button_styles(self, interaction: discord.Interaction):
        state = self.music_cog.get_guild_state(interaction.guild.id)
        
        # Actualizar botón de Bucle
        loop_button = discord.utils.get(self.children, custom_id='loop_button')
        if loop_button:
            if state.loop_state == LoopState.OFF:
                loop_button.style, loop_button.emoji = discord.ButtonStyle.secondary, "🔁"
            elif state.loop_state == LoopState.SONG:
                loop_button.style, loop_button.emoji = discord.ButtonStyle.success, "🔂"
            else:
                loop_button.style, loop_button.emoji = discord.ButtonStyle.success, "🔁"
        
        # Actualizar botón de Autoplay
        autoplay_button = discord.utils.get(self.children, custom_id='autoplay_button')
        if autoplay_button:
            autoplay_button.style = discord.ButtonStyle.success if state.autoplay else discord.ButtonStyle.secondary
        
        # Actualizar botón de Pausa/Reanudar
        pause_button = discord.utils.get(self.children, custom_id='pause_resume_button')
        if pause_button and interaction.guild.voice_client:
            if interaction.guild.voice_client.is_paused():
                pause_button.emoji, pause_button.style = "▶️", discord.ButtonStyle.success
            else:
                pause_button.emoji, pause_button.style = "⏸️", discord.ButtonStyle.secondary

    async def _execute_command(self, interaction: discord.Interaction, command_name: str):
        command = self.music_cog.bot.get_command(command_name)
        if not command: return await interaction.response.send_message(" Error interno.", ephemeral=True, delete_after=5)
        ctx = await self.music_cog.bot.get_context(interaction.message)
        ctx.author = interaction.user; ctx.interaction = interaction
        await command.callback(self.music_cog, ctx)

    # FILA 0: CONTROLES DE REPRODUCCIÓN
    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="⏮️", row=0, custom_id="previous_button")
    async def previous_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'previous')
    
    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="⏸️", row=0, custom_id="pause_resume_button")
    async def pause_resume_button(self, i: discord.Interaction, b: discord.ui.Button):
        vc = i.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()): return await i.response.send_message("No hay nada para pausar o reanudar.", ephemeral=True, delete_after=10)
        if vc.is_paused(): vc.resume(); msg = "▶️ Canción reanudada."
        else: vc.pause(); msg = "⏸️ Canción pausada."
        self._update_button_styles(i); await i.response.edit_message(view=self); await i.followup.send(msg, ephemeral=True, delete_after=10)
    
    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="⏭️", row=0, custom_id="skip_button")
    async def skip_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'skip')

    # FILA 1: MODOS Y AJUSTES
    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="🔀", row=1, custom_id="shuffle_button")
    async def shuffle_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'shuffle')
    
    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="🔁", row=1, custom_id="loop_button")
    async def loop_button(self, i: discord.Interaction, _: discord.ui.Button):
        state = self.music_cog.get_guild_state(i.guild.id)
        if state.loop_state == LoopState.OFF: state.loop_state, msg = LoopState.SONG, 'Bucle de canción activado.'
        elif state.loop_state == LoopState.SONG: state.loop_state, msg = LoopState.QUEUE, 'Bucle de cola activado.'
        else: state.loop_state, msg = LoopState.OFF, 'Bucle desactivado.'
        self._update_button_styles(i); await i.response.edit_message(view=self); await i.followup.send(f"🔁 {msg}", ephemeral=True, delete_after=5)
    
    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="🔄", row=1, custom_id="autoplay_button")
    async def autoplay_button(self, i: discord.Interaction, _: discord.ui.Button):
        state = self.music_cog.get_guild_state(i.guild.id); state.autoplay = not state.autoplay
        status = "activado" if state.autoplay else "desactivado"
        self._update_button_styles(i); await i.response.edit_message(view=self); await i.followup.send(f"🔄 Autoplay **{status}**.", ephemeral=True, delete_after=5)

    # FILA 2: UTILIDADES
    @discord.ui.button(label="Cola", style=discord.ButtonStyle.secondary, emoji="📜", row=2, custom_id="queue_button")
    async def queue_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'queue')
    
    @discord.ui.button(label="Letra", style=discord.ButtonStyle.secondary, emoji="🎤", row=2, custom_id="lyrics_button")
    async def lyrics_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'lyrics')

    # FILA 3: GESTIÓN Y SALIDA
    @discord.ui.button(label="Detener", style=discord.ButtonStyle.danger, emoji="⏹️", row=3, custom_id="stop_button")
    async def stop_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'stop')
    
    @discord.ui.button(label="Salir", style=discord.ButtonStyle.danger, emoji="🚪", row=3, custom_id="leave_button")
    async def leave_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'leave')

class MusicCog(commands.Cog, name="Música"):
    """Comandos para reproducir música de alta calidad."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_states: dict[int, GuildState] = {}
        if bot.GENIUS_API_TOKEN: self.genius = lyricsgenius.Genius(bot.GENIUS_API_TOKEN, verbose=False, remove_section_headers=True)
        else: self.genius = None
        self.voice_locks: dict[int, asyncio.Lock] = {}

    async def cog_check(self, ctx: commands.Context):
        """Check global para este Cog."""
        if not ctx.guild: return True
        settings = await db.get_cached_server_settings(ctx.guild.id)
        if settings and not settings.get('music_enabled', 1):
            await ctx.send("❌ El módulo de **Música** está desactivado. Un administrador debe habilitarlo en el dashboard.", ephemeral=True)
            return False
        return True

    def get_guild_state(self, guild_id: int) -> GuildState:
        if guild_id not in self.guild_states: self.guild_states[guild_id] = GuildState(guild_id)
        return self.guild_states[guild_id]

    def get_voice_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self.voice_locks: self.voice_locks[guild_id] = asyncio.Lock()
        return self.voice_locks[guild_id]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Limpia el panel y el estado si el bot es desconectado o se queda solo."""
        if member.id == self.bot.user.id:
            if before.channel and not after.channel: # Bot desconectado
                state = self.get_guild_state(member.guild.id)
                state.queue.clear(); state.current_song = None; state.autoplay = False
                if state.active_panel:
                    try: await state.active_panel.delete()
                    except: pass
                    state.active_panel = None
        
        # Opcional: Desconexión si el bot se queda solo (ahorro de recursos)
        elif before.channel and not after.channel:
            vc = member.guild.voice_client
            if vc and vc.channel == before.channel and len(before.channel.members) == 1: # Solo el bot
                await asyncio.sleep(30) # Esperar un poco por si alguien vuelve
                if len(before.channel.members) == 1:
                    state = self.get_guild_state(member.guild.id)
                    if state.active_panel:
                        try: await state.active_panel.delete()
                        except: pass
                        state.active_panel = None
                    await vc.disconnect()

    async def ensure_voice_client(self, channel: discord.VoiceChannel) -> discord.VoiceClient | None:
        async with self.get_voice_lock(channel.guild.id):
            vc = channel.guild.voice_client
            if not vc:
                try: 
                    return await asyncio.wait_for(channel.connect(reconnect=True, timeout=20.0), timeout=25.0)
                except asyncio.TimeoutError:
                    print(f"⌛ Tiempo de espera agotado al conectar a voz en {channel.guild.name}")
                    return None
                except Exception as e: 
                    print(f"❌ Error al conectar a voz: {e}")
                    return None
            if vc.channel != channel: 
                try:
                    await vc.move_to(channel)
                except Exception as e:
                    print(f"❌ Error al mover canal de voz: {e}")
            return vc

    async def send_response(self, ctx: commands.Context | discord.Interaction, content: str = None, embed: discord.Embed = None, ephemeral: bool = False, view: discord.ui.View = discord.utils.MISSING):
        interaction = ctx.interaction if isinstance(ctx, commands.Context) else ctx
        if interaction:
            if interaction.response.is_done(): await interaction.followup.send(content, embed=embed, ephemeral=ephemeral, view=view)
            else: await interaction.response.send_message(content, embed=embed, ephemeral=ephemeral, view=view)
        elif isinstance(ctx, commands.Context): await ctx.send(content, embed=embed, view=view)

    async def send_music_panel(self, ctx: commands.Context, song: dict):
        state = self.get_guild_state(ctx.guild.id)
        if state.active_panel:
            try: await state.active_panel.delete()
            except: pass
        
        embed = discord.Embed(title="✨ MESA DE MEZCLAS UMAPYOI", color=self.bot.CREAM_COLOR)
        
        info_song = f"🎵 **Canción:** [{song.get('title', 'Título Desconocido')}]({song.get('webpage_url', '#')})\n"
        info_song += f"👤 **Solicitante:** {song['requester'].mention}\n"
        info_song += f"🕒 **Duración:** `{format_duration(song.get('duration', 0))}`\n"
        info_song += f"🎤 **Artista:** `{song.get('uploader', 'Desconocido')}`\n"
        info_song += f"🔊 **Volumen:** `{int(state.volume * 100)}%`"
        
        embed.description = info_song
        
        if thumbnail := song.get('thumbnail'):
            embed.set_thumbnail(url=thumbnail)
            
        embed.set_footer(text="Umapyoi Music • Usa los botones para controlar", icon_url=self.bot.user.display_avatar.url)
        
        view = MusicPanelView(self)
        try:
            if channel := ctx.channel or (ctx.interaction and ctx.interaction.channel):
                state.active_panel = await channel.send(embed=embed, view=view)
        except Exception as e: print(f"Error enviando panel: {e}")

    def play_next_song(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if state.current_song:
            if state.loop_state == LoopState.SONG: state.queue.insert(0, state.current_song)
            elif state.loop_state == LoopState.QUEUE: state.queue.append(state.current_song)
            state.history.append(state.current_song)
            if len(state.history) > 20: state.history.pop(0)
        if not state.queue:
            state.current_song = None
            if state.autoplay and state.history: self.bot.loop.create_task(self.play.callback(self, ctx, search_query=f"{state.history[-1]['title']} mix"))
            else: self.bot.loop.create_task(self.disconnect_after_inactivity(ctx))
            return
        state.current_song = state.queue.pop(0)
        vc = ctx.guild.voice_client
        if isinstance(vc, discord.VoiceClient) and vc.is_connected():
            try:
                source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(state.current_song['url'], **self.bot.FFMPEG_OPTIONS), volume=state.volume)
                vc.play(source, after=lambda e: self.handle_after_play(ctx, e))
                self.bot.loop.create_task(self.send_music_panel(ctx, state.current_song))
            except Exception as e:
                print(f"Error al reproducir: {e}")
                if channel := (ctx.channel or (ctx.interaction and ctx.interaction.channel)): self.bot.loop.create_task(channel.send('❌ Error al reproducir, saltando...'))
                self.play_next_song(ctx)

    def handle_after_play(self, ctx: commands.Context, error: Exception | None):
        if error:
            print(f'Error after play: {error}')
            state = self.get_guild_state(ctx.guild.id)
            failed_song_title = state.current_song.get('title', 'la canción') if state.current_song else 'la canción'
            state.current_song = None
            if channel := (ctx.channel or (ctx.interaction and ctx.interaction.channel)):
                self.bot.loop.create_task(channel.send(f"❌ Error al reproducir '{failed_song_title}'. Saltando."))
        self.bot.loop.call_soon_threadsafe(self.play_next_song, ctx)

    async def disconnect_after_inactivity(self, ctx: commands.Context):
        if channel := (ctx.channel or (ctx.interaction and ctx.interaction.channel)):
            try: await channel.send("🎵 La cola ha terminado. Me desconectaré en 2 minutos si no se añaden más canciones.", delete_after=115)
            except: pass
        await asyncio.sleep(120)
        async with self.get_voice_lock(ctx.guild.id):
            vc = ctx.guild.voice_client
            state = self.get_guild_state(ctx.guild.id)
            if vc and not vc.is_playing() and not vc.is_paused() and not state.queue:
                if state.active_panel:
                    try:
                        embed = state.active_panel.embeds[0]; embed.title = "⏹️ Reproducción Finalizada"; embed.description = "La cola de canciones ha terminado."
                        await state.active_panel.edit(embed=embed, view=None)
                    except: pass
                    state.active_panel = None
                await vc.disconnect()
                if channel:
                    try: await channel.send("👋 ¡Adiós! Desconectado por inactividad.")
                    except: pass

    @commands.hybrid_command(name='join', description="Hace que el bot se una a tu canal de voz.")
    async def join(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel: 
            return await self.send_response(ctx, "Debes estar en un canal de voz.", ephemeral=True)
        
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
            
        channel = ctx.author.voice.channel
        vc = await self.ensure_voice_client(channel)
        
        if vc: 
            emoji = getattr(constants, 'EMOJI_CHECK', '✅')
            await self.send_response(ctx, f"{emoji} ¡Hola! Me he unido a **{channel.name}**.", ephemeral=True)
        else: 
            emoji = getattr(constants, 'EMOJI_ERROR', '❌')
            await self.send_response(ctx, f"{emoji} No pude conectarme al canal de voz. Revisa mis permisos o intenta cambiar la región del canal.", ephemeral=True)

    @commands.hybrid_command(name='leave', description="Desconecta el bot del canal de voz.")
    async def leave(self, ctx: commands.Context):
        if not (vc := ctx.guild.voice_client): return await self.send_response(ctx, "No estoy en ningún canal de voz.", ephemeral=True)
        state = self.get_guild_state(ctx.guild.id); state.queue.clear(); state.current_song = None; state.autoplay = False; state.loop_state = LoopState.OFF
        if vc.is_playing() or vc.is_paused(): vc.stop()
        if state.active_panel:
            try: await state.active_panel.delete()
            except: pass
            state.active_panel = None
        await vc.disconnect()
        emoji = getattr(constants, 'EMOJI_LEAVE', '🚪')
        await self.send_response(ctx, f"{emoji} ¡Adiós! Me he desconectado.", ephemeral=True)

    @commands.hybrid_command(name='play', aliases=['p'], description="Reproduce una canción o playlist.")
    async def play(self, ctx: commands.Context, *, search_query: str):
        if not ctx.author.voice or not ctx.author.voice.channel: return await self.send_response(ctx, "Debes estar en un canal de voz.", ephemeral=True)
        if ctx.interaction: await ctx.interaction.response.defer()
        channel = ctx.author.voice.channel
        if not (vc := await self.ensure_voice_client(channel)): return await self.send_response(ctx, "❌ No pude conectarme al canal de voz.", ephemeral=True)
        msg = await ctx.send(f'🔎 Procesando: "**{search_query}**"...')
        state = self.get_guild_state(ctx.guild.id)
        try:
            is_url = re.match(r'https?://', search_query)
            search_term = search_query if is_url else f"ytsearch:{search_query}"
            with yt_dlp.YoutubeDL(self.bot.YDL_OPTIONS) as ydl: info = await asyncio.to_thread(ydl.extract_info, search_term, download=False)
            entries = [info] if is_url and 'entries' not in info else info.get('entries', [])
            if not entries: return await msg.edit(content="❌ No encontré nada con esa búsqueda.")
            added_count = 0
            for entry in entries:
                if entry and entry.get('url'):
                    state.queue.append({
                        'title': entry.get('title', 'Título desconocido'),
                        'url': entry.get('url'),
                        'webpage_url': entry.get('webpage_url'),
                        'thumbnail': entry.get('thumbnail'),
                        'duration': entry.get('duration'),
                        'uploader': entry.get('uploader', 'Artista desconocido'),
                        'requester': ctx.author
                    })
                    added_count += 1
            if added_count > 0:
                # --- NUEVO DISEÑO DE RESPUESTA PREMIUM ---
                embed = discord.Embed(color=self.bot.CREAM_COLOR)
                
                # Buscamos el emoji personalizado en las constantes o usamos uno por defecto
                emoji_queue = getattr(constants, 'EMOJI_QUEUE', '✅')
                
                if added_count == 1:
                    song = entries[0]
                    embed.set_author(name="Canción Añadida a la Cola #1", icon_url=ctx.author.display_avatar.url)
                    # Formato estilizado: [Título] [Duración]
                    duration = format_duration(song.get('duration', 0))
                    embed.description = f"**[{song.get('title', 'Desconocido')}]({song.get('webpage_url', '#')})** `[{duration}]`"
                else:
                    embed.set_author(name=f"Añadidas {added_count} canciones", icon_url=ctx.author.display_avatar.url)
                    embed.description = f"Se han añadido {added_count} pistas a la cola con éxito."
                
                await msg.edit(content=None, embed=embed)
            else: 
                await msg.edit(content="❌ No se pudieron procesar las canciones.")
            
            if not vc.is_playing() and not state.current_song: self.play_next_song(ctx)
        except Exception as e: await msg.edit(content=f'❌ Ocurrió un error: {e}'); print(f"Error en Play: {e}")

    @commands.hybrid_command(name='skip', description="Salta la canción actual.")
    async def skip(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        if (vc := ctx.guild.voice_client) and (vc.is_playing() or vc.is_paused()):
            vc.stop(); await self.send_response(ctx, "⏭️ Canción saltada.", ephemeral=True)
        else: await self.send_response(ctx, "No hay nada que saltar.", ephemeral=True)

    @commands.hybrid_command(name='stop', description="Detiene la reproducción y limpia la cola.")
    async def stop(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        state = self.get_guild_state(ctx.guild.id); state.queue.clear(); state.current_song=None; state.autoplay=False; state.loop_state=LoopState.OFF
        if (vc := ctx.guild.voice_client) and (vc.is_playing() or vc.is_paused()): vc.stop()
        if state.active_panel:
            try: await state.active_panel.edit(content="⏹️ La reproducción ha sido detenida.", embed=None, view=None)
            except: pass
            state.active_panel = None
        await self.send_response(ctx, "⏹️ Reproducción detenida y cola limpiada.", ephemeral=True)

    @commands.hybrid_command(name='pause', description="Pausa o reanuda la canción actual.")
    async def pause(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        vc = ctx.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()): return await self.send_response(ctx, "No hay nada que pausar o reanudar.", ephemeral=True)
        if vc.is_paused(): vc.resume(); await self.send_response(ctx, "▶️ Canción reanudada.", ephemeral=True)
        else: vc.pause(); await self.send_response(ctx, "⏸️ Canción pausada.", ephemeral=True)

    @commands.hybrid_command(name='queue', aliases=['q'], description="Muestra la cola de canciones.")
    async def queue(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        state = self.get_guild_state(ctx.guild.id)
        if not state.current_song and not state.queue: return await self.send_response(ctx, "La cola está vacía.", ephemeral=True)
        embed = discord.Embed(title="🎵 Cola de Música 🎵", color=self.bot.CREAM_COLOR)
        if state.current_song: embed.add_field(name="Reproduciendo ahora", value=f"**[{state.current_song['title']}]({state.current_song.get('webpage_url', '#')})**", inline=False)
        if state.queue:
            next_songs = "\n".join([f"`{i+1}.` {s['title']}" for i, s in enumerate(state.queue[:10])])
            embed.add_field(name="A continuación:", value=next_songs, inline=False)
        if len(state.queue) > 10: embed.set_footer(text=f"Y {len(state.queue) - 10} más...")
        await self.send_response(ctx, embed=embed, ephemeral=True)

    @commands.hybrid_command(name='nowplaying', aliases=['np'], description="Muestra la canción que está sonando.")
    async def nowplaying(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        state = self.get_guild_state(ctx.guild.id)
        if not state.current_song: return await self.send_response(ctx, "No hay ninguna canción reproduciéndose.", ephemeral=True)
        song = state.current_song
        embed = discord.Embed(title="🎵 Sonando Ahora", description=f"**[{song['title']}]({song.get('webpage_url', '#')})**", color=self.bot.CREAM_COLOR)
        embed.set_footer(text=f"Pedida por: {song['requester'].display_name}")
        if song.get('thumbnail'): embed.set_thumbnail(url=song['thumbnail'])
        await self.send_response(ctx, embed=embed, ephemeral=True)

    @commands.hybrid_command(name='lyrics', description="Busca la letra de la canción actual.")
    async def lyrics(self, ctx: commands.Context):
        if not self.genius: return await self.send_response(ctx, "❌ La función de letras no está configurada.", ephemeral=True)
        state = self.get_guild_state(ctx.guild.id)
        if not state.current_song: return await self.send_response(ctx, "No hay ninguna canción reproduciéndose.", ephemeral=True)
        await ctx.defer(ephemeral=True)
        
        # Limpiar el título de basura común de YouTube
        raw_title = state.current_song['title']
        clean_title = re.sub(r'(?i)(\(|\[).*?(letra|lyric|video|audio|official|oficial|live|en vivo).*?(\)|\])', '', raw_title)
        clean_title = re.sub(r'(?i)(official video|video oficial|audio oficial|official audio|con letra)', '', clean_title)
        
        # Separar artista y canción si hay un guion
        if '-' in clean_title:
            parts = clean_title.split('-', 1)
            artist = parts[0].strip()
            title = parts[1].strip()
        else:
            artist = ""
            title = clean_title.strip()
            
        try:
            song = await asyncio.to_thread(self.genius.search_song, title, artist)
            if song and song.lyrics:
                lyrics = song.lyrics[:3996] + "..." if len(song.lyrics) > 4000 else song.lyrics
                embed = discord.Embed(title=f"🎤 Letra de: {song.title}", description=lyrics, color=self.bot.CREAM_COLOR)
                embed.set_footer(text=f"Artista: {song.artist}")
                await self.send_response(ctx, embed=embed, ephemeral=True)
            else: await self.send_response(ctx, f"❌ No se encontraron letras para: **{title}**", ephemeral=True)
        except Exception as e: await self.send_response(ctx, f"❌ Ocurrió un error al buscar la letra: {e}", ephemeral=True)

    @commands.hybrid_command(name='shuffle', description="Mezcla la cola de canciones actual.")
    async def shuffle(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if not state.queue: return await self.send_response(ctx, "La cola está vacía.", ephemeral=True)
        random.shuffle(state.queue); await self.send_response(ctx, "🔀 ¡La cola ha sido barajada!", ephemeral=True)

    @commands.hybrid_command(name='previous', description="Reproduce la canción anterior del historial.")
    async def previous(self, ctx: commands.Context):
        state = self.get_guild_state(ctx.guild.id)
        if len(state.history) < 2: return await self.send_response(ctx, "No hay historial suficiente.", ephemeral=True)
        if state.current_song: state.queue.insert(0, state.current_song)
        state.queue.insert(0, state.history[-2]); state.history = state.history[:-2]
        if (vc := ctx.guild.voice_client) and (vc.is_playing() or vc.is_paused()): vc.stop()
        else: self.play_next_song(ctx)
        await self.send_response(ctx, "⏪ Reproduciendo la canción anterior.", ephemeral=True)
    
    @commands.hybrid_command(name='volume', aliases=['vol'], description="Ajusta el volumen del reproductor (0-100%).")
    async def volume(self, ctx: commands.Context, new_volume: commands.Range[int, 0, 100]):
        if not (vc := ctx.guild.voice_client): return await self.send_response(ctx, "No estoy en un canal de voz.", ephemeral=True)
        state = self.get_guild_state(ctx.guild.id)
        state.volume = new_volume / 100.0
        if vc.source: vc.source.volume = state.volume
        await self.send_response(ctx, f"🔊 Volumen ajustado a **{new_volume}%**.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))