import discord
from discord.ext import commands
import pomice
import asyncio
import re
import datetime
from enum import Enum
import random
import lyricsgenius
from utils import constants
from utils import database_manager as db

class LoopState(Enum):
    OFF = 0; SONG = 1; QUEUE = 2

def format_duration(milliseconds: int) -> str:
    if not milliseconds: return "Desconocido"
    seconds = milliseconds // 1000
    if seconds >= 3600:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m {seconds % 60}s"
    return f"{seconds // 60}m {seconds % 60}s"

class UmapyoiPlayer(pomice.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = pomice.Queue()
        self.loop_state: LoopState = LoopState.OFF
        self.autoplay: bool = False
        self.active_panel: discord.Message | None = None
        self.history = []

    async def play(self, track, *args, **kwargs):
        # Resolución de Spotify vía SoundCloud
        if hasattr(track, 'uri') and track.uri and 'spotify.com' in track.uri:
            query = f"scsearch:{track.title} {track.author}"
            try:
                results = await self.get_tracks(query)
                if results and not isinstance(results, pomice.Playlist):
                    sc_track = results[0]
                    sc_track.requester = getattr(track, 'requester', None)
                    track = sc_track
            except Exception:
                pass
                
        return await super().play(track, *args, **kwargs)

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
        player: UmapyoiPlayer = interaction.guild.voice_client
        if not player: return
        
        # Estado del bucle
        loop_button = discord.utils.get(self.children, custom_id='loop_button')
        if loop_button:
            if player.loop_state == LoopState.OFF:
                loop_button.style, loop_button.emoji = discord.ButtonStyle.secondary, "🔁"
            elif player.loop_state == LoopState.SONG:
                loop_button.style, loop_button.emoji = discord.ButtonStyle.success, "🔂"
            else:
                loop_button.style, loop_button.emoji = discord.ButtonStyle.success, "🔁"
        
        # Autoplay
        autoplay_button = discord.utils.get(self.children, custom_id='autoplay_button')
        if autoplay_button:
            autoplay_button.style = discord.ButtonStyle.success if player.autoplay else discord.ButtonStyle.secondary
        
        # Pausa/Reanudar
        pause_button = discord.utils.get(self.children, custom_id='pause_resume_button')
        if pause_button:
            if player.is_paused:
                pause_button.emoji, pause_button.style = "▶️", discord.ButtonStyle.success
            else:
                pause_button.emoji, pause_button.style = "⏸️", discord.ButtonStyle.secondary

    async def _execute_command(self, interaction: discord.Interaction, command_name: str):
        command = self.music_cog.bot.get_command(command_name)
        if not command: return await interaction.response.send_message("❌ Error interno.", ephemeral=True, delete_after=5)
        ctx = await self.music_cog.bot.get_context(interaction.message)
        ctx.author = interaction.user; ctx.interaction = interaction
        await command.callback(self.music_cog, ctx)

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="⏮️", row=0, custom_id="previous_button")
    async def previous_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'previous')
    
    @discord.ui.button(label="Pausa", style=discord.ButtonStyle.secondary, emoji="⏸️", row=0, custom_id="pause_resume_button")
    async def pause_resume_button(self, i: discord.Interaction, b: discord.ui.Button):
        player: UmapyoiPlayer = i.guild.voice_client
        if not player or not player.is_playing: return await i.response.send_message("No hay nada reproduciéndose.", ephemeral=True, delete_after=10)
        
        if player.is_paused:
            await player.set_pause(False)
            msg = "▶️ Canción reanudada."
            b.label, b.emoji = "Pausa", "⏸️"
        else:
            await player.set_pause(True)
            msg = "⏸️ Canción pausada."
            b.label, b.emoji = "Reanudar", "▶️"
            
        self._update_button_styles(i)
        await i.response.edit_message(view=self)
        await i.followup.send(msg, ephemeral=True, delete_after=10)
    
    @discord.ui.button(label="Siguiente", style=discord.ButtonStyle.secondary, emoji="⏭️", row=0, custom_id="skip_button")
    async def skip_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'skip')

    @discord.ui.button(label="Mezclar", style=discord.ButtonStyle.secondary, emoji="🔀", row=1, custom_id="shuffle_button")
    async def shuffle_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'shuffle')
    
    @discord.ui.button(label="Bucle", style=discord.ButtonStyle.secondary, emoji="🔁", row=1, custom_id="loop_button")
    async def loop_button(self, i: discord.Interaction, _: discord.ui.Button):
        player: UmapyoiPlayer = i.guild.voice_client
        if not player: return await i.response.send_message("❌ Sin reproductor.", ephemeral=True)
        
        if player.loop_state == LoopState.OFF: 
            player.loop_state, msg = LoopState.SONG, 'Bucle de canción activado.'
        elif player.loop_state == LoopState.SONG: 
            player.loop_state, msg = LoopState.QUEUE, 'Bucle de cola activado.'
        else: 
            player.loop_state, msg = LoopState.OFF, 'Bucle desactivado.'
            
        self._update_button_styles(i)
        await i.response.edit_message(view=self)
        await i.followup.send(f"🔁 {msg}", ephemeral=True, delete_after=5)
    
    @discord.ui.button(label="Mix Auto.", style=discord.ButtonStyle.secondary, emoji="🔄", row=1, custom_id="autoplay_button")
    async def autoplay_button(self, i: discord.Interaction, _: discord.ui.Button):
        player: UmapyoiPlayer = i.guild.voice_client
        if not player: return await i.response.send_message("❌ Sin reproductor.", ephemeral=True)
        
        player.autoplay = not player.autoplay
        status = "activado" if player.autoplay else "desactivado"
        self._update_button_styles(i)
        await i.response.edit_message(view=self)
        await i.followup.send(f"🔄 Autoplay **{status}**.", ephemeral=True, delete_after=5)

    @discord.ui.button(label="Cola", style=discord.ButtonStyle.secondary, emoji="📜", row=2, custom_id="queue_button")
    async def queue_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'queue')
    
    @discord.ui.button(label="Letra", style=discord.ButtonStyle.secondary, emoji="🎤", row=2, custom_id="lyrics_button")
    async def lyrics_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'lyrics')

    @discord.ui.button(label="Detener", style=discord.ButtonStyle.danger, emoji="⏹️", row=3, custom_id="stop_button")
    async def stop_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'stop')
    
    @discord.ui.button(label="Salir", style=discord.ButtonStyle.danger, emoji="🚪", row=3, custom_id="leave_button")
    async def leave_button(self, i: discord.Interaction, _: discord.ui.Button): await self._execute_command(i, 'leave')

class MusicCog(commands.Cog, name="Música"):
    """Comandos para reproducir música de alta calidad a través de Lavalink."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pomice = pomice.NodePool()
        if bot.GENIUS_API_TOKEN: self.genius = lyricsgenius.Genius(bot.GENIUS_API_TOKEN, verbose=False, remove_section_headers=True)
        else: self.genius = None
        self.voice_locks: dict[int, asyncio.Lock] = {}
        
        bot.loop.create_task(self.start_nodes())

    # Conexión de nodos Lavalink
    async def start_nodes(self):
        await self.bot.wait_until_ready()
        try:
            await self.pomice.create_node(
                bot=self.bot,
                host='127.0.0.1',
                port=2333,
                password='youshallnotpass',
                identifier='MAIN',
                spotify_client_id=getattr(constants, 'SPOTIFY_CLIENT_ID', None),
                spotify_client_secret=getattr(constants, 'SPOTIFY_CLIENT_SECRET', None)
            )
            print("🟢 Nodo Pomice (Lavalink) conectado exitosamente.")
        except Exception as e:
            print(f"🔴 Error al conectar el nodo Pomice: {e}")

    async def cog_check(self, ctx: commands.Context):
        if not ctx.guild: return True
        settings = await db.get_cached_server_settings(ctx.guild.id)
        if settings and not settings.get('music_enabled', 1):
            await ctx.send("❌ El módulo de **Música** está desactivado.", ephemeral=True)
            return False
        return True

    def get_voice_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self.voice_locks: self.voice_locks[guild_id] = asyncio.Lock()
        return self.voice_locks[guild_id]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id == self.bot.user.id and before.channel and not after.channel: # Desconexión bot
            player = getattr(before.channel.guild, 'voice_client', None)
            if not player:
                try:
                    node = self.pomice.get_node()
                    player = node.get_player(member.guild.id)
                except: pass
                
            if player:
                if getattr(player, 'active_panel', None):
                    try: await player.active_panel.delete()
                    except: pass
                
                bound_channel = getattr(player, 'bound_channel', None)
                if getattr(player, '_is_manually_destroyed', False) is False:
                    if bound_channel:
                        try: await bound_channel.send("🚪 Fui expulsado del canal de voz. He detenido la música y limpiado la cola.", delete_after=15)
                        except: pass
                
                try: await player.destroy()
                except: pass
        
        elif before.channel and not after.channel: # Salida de miembro
            vc = member.guild.voice_client
            if vc and vc.channel == before.channel and len(before.channel.members) == 1:
                await asyncio.sleep(30)
                if len(before.channel.members) == 1:
                    player: UmapyoiPlayer = vc
                    if player.active_panel:
                        try: await player.active_panel.delete()
                        except: pass
                    await player.destroy()

    @commands.Cog.listener()
    async def on_pomice_track_end(self, player: UmapyoiPlayer, track, reason):
        if reason == 'REPLACED': return
        
        if player.loop_state == LoopState.SONG:
            player.queue.put_at_front(track)
        elif player.loop_state == LoopState.QUEUE:
            player.queue.put(track)
            
        player.history.append(track)
        if len(player.history) > 20: player.history.pop(0)

        try:
            next_track = player.queue.get()
            await player.play(next_track)
        except pomice.QueueEmpty:
            if player.autoplay and player.history:
                try:
                    # Recomendación básica si es YouTube
                    results = await player.get_tracks(f"ytsearch:{player.history[-1].title} mix")
                    if results and not isinstance(results, pomice.Playlist):
                        await player.play(results[0])
                        return
                except: pass
            
            # Aviso de fin de cola y desconexión
            if player.active_panel and hasattr(player, 'bound_channel') and player.bound_channel:
                try:
                    embed = player.active_panel.embeds[0]
                    embed.title = "⏹️ Reproducción Finalizada"
                    embed.description = "La cola de canciones ha terminado."
                    await player.active_panel.edit(embed=embed, view=None)
                    await player.bound_channel.send("🎵 La cola ha terminado. Me desconectaré pronto si no hay actividad.", delete_after=60)
                except: pass
            
            self.bot.loop.create_task(self.disconnect_after_inactivity(player))

    @commands.Cog.listener()
    async def on_pomice_track_start(self, player: UmapyoiPlayer, track):
        if not hasattr(player, 'bound_channel') or not player.bound_channel: return
        
        if player.active_panel:
            try: await player.active_panel.delete()
            except: pass
            
        embed = discord.Embed(title="✨ MESA DE MEZCLAS UMAPYOI", color=self.bot.CREAM_COLOR)
        requester_mention = getattr(track.requester, "mention", "Alguien") if hasattr(track, 'requester') else "Desconocido"
        
        desc = f"🎵 **Canción:** [{track.title}]({constants.COMMANDS_PAGE_URL})\n"
        desc += f"👤 **Solicitante:** {requester_mention}\n"
        desc += f"🕒 **Duración:** `{format_duration(track.length)}`\n"
        desc += f"🎤 **Artista:** `{track.author}`\n"
        desc += f"🔊 **Volumen:** `{player.volume}%`"
        
        embed.description = desc
        if hasattr(track, 'thumbnail') and track.thumbnail: embed.set_thumbnail(url=track.thumbnail)
        embed.set_footer(text="Umapyoi Music • Usa los botones para controlar", icon_url=self.bot.user.display_avatar.url)
        
        try: player.active_panel = await player.bound_channel.send(embed=embed, view=MusicPanelView(self))
        except: pass

    async def disconnect_after_inactivity(self, player: UmapyoiPlayer):
        await asyncio.sleep(120)
        if hasattr(player, 'guild') and player.guild.voice_client:
            if not player.is_playing and not player.is_paused and player.queue.is_empty:
                await player.destroy()

    async def ensure_voice_client(self, ctx: commands.Context) -> UmapyoiPlayer | None:
        channel = ctx.author.voice.channel
        async with self.get_voice_lock(ctx.guild.id):
            player: UmapyoiPlayer = ctx.guild.voice_client
            if not player:
                try: 
                    player = await channel.connect(cls=UmapyoiPlayer)
                    player.bound_channel = ctx.channel or (ctx.interaction.channel if ctx.interaction else None)
                except Exception as e: 
                    print(f"❌ Error al conectar a voz (Pomice): {e}")
                    return None
            if player.channel != channel: 
                try: await player.move_to(channel)
                except: pass
            return player

    async def send_response(self, ctx: commands.Context | discord.Interaction, content: str = None, embed: discord.Embed = None, ephemeral: bool = False, view: discord.ui.View = discord.utils.MISSING):
        interaction = ctx.interaction if isinstance(ctx, commands.Context) else ctx
        if interaction:
            if interaction.response.is_done(): await interaction.followup.send(content, embed=embed, ephemeral=ephemeral, view=view)
            else: await interaction.response.send_message(content, embed=embed, ephemeral=ephemeral, view=view)
        elif isinstance(ctx, commands.Context): await ctx.send(content, embed=embed, view=view)

    @commands.hybrid_command(name='join', description="Hace que el bot se una a tu canal de voz.")
    async def join(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel: return await self.send_response(ctx, "Debes estar en un canal de voz.", ephemeral=True)
        if ctx.interaction: await ctx.interaction.response.defer(ephemeral=True)
        player = await self.ensure_voice_client(ctx)
        
        if player: 
            emoji = getattr(constants, 'EMOJI_CHECK', '✅')
            await self.send_response(ctx, f"{emoji} ¡Hola! Me he unido a **{ctx.author.voice.channel.name}** y estoy listo para poner música.", ephemeral=True)
        else: 
            emoji = getattr(constants, 'EMOJI_ERROR', '❌')
            await self.send_response(ctx, f"{emoji} No pude conectarme al canal de voz.", ephemeral=True)

    @commands.hybrid_command(name='leave', description="Desconecta el bot del canal de voz.")
    async def leave(self, ctx: commands.Context):
        player: UmapyoiPlayer = ctx.guild.voice_client
        if not player: return await self.send_response(ctx, "No estoy en ningún canal de voz.", ephemeral=True)
        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            return await self.send_response(ctx, "❌ Debes estar en mi canal de voz para desconectarme.", ephemeral=True)
        
        player._is_manually_destroyed = True
        if getattr(player, 'active_panel', None):
            try: await player.active_panel.delete()
            except: pass
            
        await player.destroy()
        emoji = getattr(constants, 'EMOJI_LEAVE', '🚪')
        await self.send_response(ctx, f"{emoji} ¡Adiós! Me he desconectado.", ephemeral=True)

    @commands.hybrid_command(name='play', aliases=['p'], description="Reproduce una canción o playlist.")
    async def play(self, ctx: commands.Context, *, search_query: str):
        if not ctx.author.voice or not ctx.author.voice.channel: return await self.send_response(ctx, "Debes estar en un canal de voz.", ephemeral=True)
        if ctx.interaction: await ctx.interaction.response.defer()
        
        player = await self.ensure_voice_client(ctx)
        if not player: return await self.send_response(ctx, "❌ No pude conectarme al canal de voz.", ephemeral=True)
        
        # Actualizar canal de enlace
        player.bound_channel = ctx.channel or (ctx.interaction.channel if ctx.interaction else None)
        
        if not search_query.startswith(('http://', 'https://', 'ytsearch:', 'scsearch:', 'spsearch:')):
            search_query = f"scsearch:{search_query}"
            
        display_query = search_query.replace("scsearch:", "").replace("ytsearch:", "").replace("spsearch:", "")
        msg = await ctx.send(f'🔎 Buscando: "**{display_query}**"...')
        
        try:
            results = await player.get_tracks(query=search_query, ctx=ctx)
            
            if not results:
                return await msg.edit(content="❌ No encontré nada con esa búsqueda.")

            if isinstance(results, pomice.Playlist):
                for track in results.tracks: player.queue.put(track)
                emoji_queue = getattr(constants, 'EMOJI_QUEUE', '✅')
                embed = discord.Embed(
                    color=self.bot.CREAM_COLOR,
                    description=f"{emoji_queue} Se añadieron **{len(results.tracks)}** canciones de la playlist **{results.name}** a la cola."
                )
                await msg.edit(content=None, embed=embed)
            else:
                track = results[0]
                player.queue.put(track)
                
                embed = discord.Embed(color=self.bot.CREAM_COLOR)
                emoji_queue = getattr(constants, 'EMOJI_QUEUE', '✅')
                duration = format_duration(track.length)
                
                if player.is_playing:
                    embed.set_author(name=f"Añadida a la cola (Posición #{len(player.queue)})", icon_url=ctx.author.display_avatar.url)
                else:
                    embed.set_author(name="Añadido a la cola", icon_url=ctx.author.display_avatar.url)
                    
                embed.description = f"**[{track.title}]({constants.COMMANDS_PAGE_URL})** `[{duration}]`"
                await msg.edit(content=None, embed=embed)

            if not player.is_playing:
                await player.play(player.queue.get())
                
        except pomice.TrackLoadError as e:
            await msg.edit(content=f"❌ Error al cargar la canción desde el origen: {e}")
        except Exception as e:
            await msg.edit(content=f"❌ Error inesperado: {e}")
            print(f"Error en play: {e}")

    @commands.hybrid_command(name='skip', description="Salta la canción actual.")
    async def skip(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        player: UmapyoiPlayer = ctx.guild.voice_client
        if not player: return await self.send_response(ctx, "No estoy en ningún canal de voz.", ephemeral=True)
        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            return await self.send_response(ctx, "❌ Debes estar en mi canal de voz para usar este comando.", ephemeral=True)
            
        if player and player.is_playing:
            await player.stop()
            await self.send_response(ctx, "⏭️ Canción saltada.", ephemeral=True)
        else: await self.send_response(ctx, "No hay nada que saltar.", ephemeral=True)

    @commands.hybrid_command(name='stop', description="Detiene la reproducción y limpia la cola.")
    async def stop(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        player: UmapyoiPlayer = ctx.guild.voice_client
        if not player: return await self.send_response(ctx, "No estoy conectado.", ephemeral=True)
        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            return await self.send_response(ctx, "❌ Debes estar en mi canal de voz para usar este comando.", ephemeral=True)
        
        player.queue.clear()
        player.loop_state = LoopState.OFF
        player.autoplay = False
        
        if player.active_panel:
            try: await player.active_panel.edit(content="⏹️ La reproducción ha sido detenida.", embed=None, view=None)
            except: pass
            
        await player.stop()
        await self.send_response(ctx, "⏹️ Reproducción detenida y cola limpiada.", ephemeral=True)

    @commands.hybrid_command(name='pause', description="Pausa o reanuda la canción actual.")
    async def pause(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        player: UmapyoiPlayer = ctx.guild.voice_client
        if not player or not player.is_playing: return await self.send_response(ctx, "No hay nada reproduciéndose.", ephemeral=True)
        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            return await self.send_response(ctx, "❌ Debes estar en mi canal de voz para usar este comando.", ephemeral=True)
        
        if player.is_paused:
            await player.set_pause(False)
            await self.send_response(ctx, "▶️ Canción reanudada.", ephemeral=True)
        else:
            await player.set_pause(True)
            await self.send_response(ctx, "⏸️ Canción pausada.", ephemeral=True)

    @commands.hybrid_command(name='queue', aliases=['q'], description="Muestra la cola de canciones.")
    async def queue(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        player: UmapyoiPlayer = ctx.guild.voice_client
        if not player or (not player.current and player.queue.is_empty): 
            return await self.send_response(ctx, "La cola está vacía.", ephemeral=True)
            
        embed = discord.Embed(title="🎵 Cola de Música 🎵", color=self.bot.CREAM_COLOR)
        if player.current: 
            embed.add_field(name="Reproduciendo ahora", value=f"**[{player.current.title}]({constants.COMMANDS_PAGE_URL})**", inline=False)
            
        if not player.queue.is_empty:
            queue_list = list(player.queue.get_queue())
            next_songs = "\n".join([f"`{i+1}.` {t.title}" for i, t in enumerate(queue_list[:10])])
            embed.add_field(name="A continuación:", value=next_songs, inline=False)
            if len(queue_list) > 10: embed.set_footer(text=f"Y {len(queue_list) - 10} más...")
            
        await self.send_response(ctx, embed=embed, ephemeral=True)

    @commands.hybrid_command(name='nowplaying', aliases=['np'], description="Muestra la canción que está sonando.")
    async def nowplaying(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        player: UmapyoiPlayer = ctx.guild.voice_client
        if not player or not player.current: return await self.send_response(ctx, "No hay ninguna canción reproduciéndose.", ephemeral=True)
        
        track = player.current
        embed = discord.Embed(title="🎵 Sonando Ahora", description=f"**[{track.title}]({constants.COMMANDS_PAGE_URL})**", color=self.bot.CREAM_COLOR)
        requester_name = getattr(track.requester, "display_name", "Desconocido") if hasattr(track, 'requester') else "Desconocido"
        embed.set_footer(text=f"Pedida por: {requester_name}")
        
        if hasattr(track, 'thumbnail') and track.thumbnail: embed.set_thumbnail(url=track.thumbnail)
        await self.send_response(ctx, embed=embed, ephemeral=True)

    @commands.hybrid_command(name='lyrics', description="Busca la letra de la canción actual.")
    async def lyrics(self, ctx: commands.Context):
        if not self.genius: return await self.send_response(ctx, "❌ La función de letras no está configurada.", ephemeral=True)
        await ctx.defer(ephemeral=True)
        
        player: UmapyoiPlayer = ctx.guild.voice_client
        if not player or not player.current: return await self.send_response(ctx, "No hay ninguna canción reproduciéndose.", ephemeral=True)
        
        raw_title = player.current.title
        clean_title = re.sub(r'(?i)(\(|\[).*?(letra|lyric|video|audio|official|oficial|live|en vivo).*?(\)|\])', '', raw_title)
        clean_title = re.sub(r'(?i)(official video|video oficial|audio oficial|official audio|con letra)', '', clean_title)
        
        if '-' in clean_title:
            parts = clean_title.split('-', 1)
            artist = parts[0].strip()
            title = parts[1].strip()
        else:
            artist = player.current.author or ""
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
        player: UmapyoiPlayer = ctx.guild.voice_client
        if not player or player.queue.is_empty: return await self.send_response(ctx, "La cola está vacía.", ephemeral=True)
        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            return await self.send_response(ctx, "❌ Debes estar en mi canal de voz para usar este comando.", ephemeral=True)
        
        player.queue.shuffle()
        await self.send_response(ctx, "🔀 ¡La cola ha sido barajada!", ephemeral=True)

    @commands.hybrid_command(name='previous', description="Reproduce la canción anterior del historial.")
    async def previous(self, ctx: commands.Context):
        player: UmapyoiPlayer = ctx.guild.voice_client
        if not player or len(player.history) < 2: return await self.send_response(ctx, "No hay historial suficiente.", ephemeral=True)
        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            return await self.send_response(ctx, "❌ Debes estar en mi canal de voz para usar este comando.", ephemeral=True)
        
        if player.current: player.queue.put_at_front(player.current)
        prev_track = player.history[-2]
        player.history = player.history[:-2]
        
        player.queue.put_at_front(prev_track)
        await player.stop()
        await self.send_response(ctx, "⏪ Reproduciendo la canción anterior.", ephemeral=True)
    
    @commands.hybrid_command(name='volume', aliases=['vol'], description="Ajusta el volumen del reproductor (0-150%).")
    async def volume(self, ctx: commands.Context, new_volume: commands.Range[int, 0, 150]):
        player: UmapyoiPlayer = ctx.guild.voice_client
        if not player: return await self.send_response(ctx, "No estoy en un canal de voz.", ephemeral=True)
        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            return await self.send_response(ctx, "❌ Debes estar en mi canal de voz para usar este comando.", ephemeral=True)
        
        await player.set_volume(new_volume)
        await self.send_response(ctx, f"🔊 Volumen ajustado a **{new_volume}%**.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))