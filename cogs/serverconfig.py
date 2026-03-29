import discord
from discord.ext import commands, tasks
import asyncio
import datetime
from typing import Optional, Literal
from utils import database_manager as db
from utils.lang_utils import _t
from utils.constants import (
    DEFAULT_WELCOME_MESSAGE, DEFAULT_WELCOME_BANNER, 
    DEFAULT_GOODBYE_MESSAGE, DEFAULT_GOODBYE_BANNER,
    TEMP_CHANNEL_PREFIX
)
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import aiohttp
import re
import urllib.parse

# Generación de imágenes para banners de bienvenida/despedida
async def generate_banner_image(
    session: aiohttp.ClientSession, 
    member: discord.Member, 
    message: str, 
    background_url: str,
    title_color: str = "#000000",
    subtitle_color: str = "#000000"
):
    """
    Genera una imagen de banner personalizada usando la sesión http compartida y colores configurables.
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        async with session.get(background_url, headers=headers) as resp:
            if resp.status != 200:
                print(f"No se pudo descargar el fondo: {background_url} (Estado: {resp.status})")
                return None
            background_bytes = await resp.read()

        async with session.get(member.display_avatar.url, headers=headers) as resp:
            if resp.status != 200:
                print(f"No se pudo descargar el avatar de {member.display_name} (Estado: {resp.status})")
                return None
            avatar_bytes = await resp.read()

        bg = Image.open(BytesIO(background_bytes)).convert("RGBA")
        avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
        bg = bg.resize((1000, 400))
        avatar = avatar.resize((256, 256))
        mask = Image.new('L', avatar.size, 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0) + avatar.size, fill=255)
        bg.paste(avatar, (372, 20), mask)
        draw = ImageDraw.Draw(bg)
        try:
            font_path = "utils/arial.ttf" 
            title_font = ImageFont.truetype(font_path, 60)
            subtitle_font = ImageFont.truetype(font_path, 32)
        except IOError:
            print("Fuente 'utils/arial.ttf' no encontrada, usando la fuente por defecto.")
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()

        processed_message = message.replace(member.mention, f"@{member.display_name}")
        max_length = 60 
        if len(processed_message) > max_length:
            processed_message = processed_message[:max_length] + "..."

        # Para asegurar que se lea en cualquier fondo, le aplicamos un borde negro suave (stroke) y default blanco
        if title_color == "#000000": title_color = "#ffffff"
        if subtitle_color == "#000000": subtitle_color = "#dddddd"
        
        draw.text((500, 320), member.display_name, fill=title_color, font=title_font, anchor="ms", stroke_width=2, stroke_fill="black")
        draw.text((500, 365), processed_message, fill=subtitle_color, font=subtitle_font, anchor="ms", stroke_width=1, stroke_fill="black")

        final_buffer = BytesIO()
        bg.save(final_buffer, format="PNG")
        final_buffer.seek(0)
        
        return discord.File(final_buffer, filename="banner.png")

    except Exception as e:
        print(f"Error generando el banner: {e}")
        return None

# Módulo de configuración principal del servidor
class ServerConfigCog(commands.Cog, name="Configuración del Servidor"):
    """Comandos para que los administradores configuren el bot en el servidor."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.recent_events = {} 
        self.cleanup_recent_events.start()

    def cog_unload(self):
        self.cleanup_recent_events.cancel()

    @tasks.loop(minutes=30)
    async def cleanup_recent_events(self):
        """Limpia periódicamente la caché en RAM de eventos recientes para evitar memory leaks."""
        now = datetime.datetime.now(datetime.timezone.utc)
        for guild_events in self.recent_events.values():
            for event_type in ['join', 'remove']:
                # Crear lista de keys a borrar porque no se puede alterar dict durante iteración
                keys_to_delete = [
                    user_id for user_id, timestamp in guild_events.get(event_type, {}).items() 
                    if (now - timestamp).total_seconds() > 300
                ]
                for k in keys_to_delete:
                    del guild_events[event_type][k] 

    async def get_settings(self, guild_id: int):
        return await db.get_cached_server_settings(guild_id)

    async def save_setting(self, guild_id: int, key: str, value):
        allowed_keys = [
            'welcome_channel_id', 'goodbye_channel_id', 'log_channel_id', 'autorole_id', 
            'welcome_message', 'welcome_banner_url', 'goodbye_message', 'goodbye_banner_url', 
            'automod_anti_invite', 'automod_banned_words', 'temp_channel_creator_id', 'leveling_enabled',
            'welcome_title_color', 'welcome_subtitle_color', 'goodbye_title_color', 'goodbye_subtitle_color',
            'welcome_top_text', 'goodbye_top_text', 'prefix', 'language',
            'mod_enabled', 'eco_enabled', 'gamble_enabled', 'tickets_enabled', 
            'music_enabled', 'tts_enabled', 'rr_enabled'
        ]
        if key not in allowed_keys:
            return
        await self.get_settings(guild_id)
        query = f"UPDATE server_settings SET {key} = ? WHERE guild_id = ?"
        await db.execute(query, (value, guild_id))
        
    async def add_reaction_role(self, guild_id, message_id, emoji, role_id):
        await db.execute("REPLACE INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)", (guild_id, message_id, emoji, role_id))
            
    async def get_reaction_role(self, guild_id, message_id, emoji):
        return await db.fetchone("SELECT role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?", (guild_id, message_id, emoji))

    async def log_event(self, guild_id, embed):
        settings = await db.get_cached_server_settings(guild_id)
        if settings and (log_channel_id := settings.get("log_channel_id")):
            if log_channel := self.bot.get_channel(log_channel_id):
                try: await log_channel.send(embed=embed)
                except discord.Forbidden: pass

    # Eventos de entrada, salida y voz
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # --- NUEVO: Comprobación para evitar mensajes duplicados ---
        now = datetime.datetime.now(datetime.timezone.utc)
        self.recent_events.setdefault(member.guild.id, {'join': {}, 'remove': {}})
        
        if member.id in self.recent_events[member.guild.id]['join']:
            if (now - self.recent_events[member.guild.id]['join'][member.id]).total_seconds() < 5:
                return # Ignora el evento duplicado si ocurrió hace menos de 5 segundos
        
        self.recent_events[member.guild.id]['join'][member.id] = now
        # --- FIN DE LA COMPROBACIÓN ---

        settings = await db.get_cached_server_settings(member.guild.id)
        if not settings: return

        if channel_id := settings.get("welcome_channel_id"):
            if channel := self.bot.get_channel(channel_id):
                try:
                    msg = (settings.get("welcome_message") or DEFAULT_WELCOME_MESSAGE).format(user=member, server=member.guild, member_count=member.guild.member_count)
                except (KeyError, ValueError):
                    msg = DEFAULT_WELCOME_MESSAGE.format(user=member, server=member.guild, member_count=member.guild.member_count)

                top_text = settings.get("welcome_top_text") or "¡Nuevo Miembro!"
                try:
                    top_text = top_text.format(user=member, server=member.guild, member_count=member.guild.member_count)
                except (KeyError, ValueError):
                    pass

                background_url = settings.get("welcome_banner_url") or DEFAULT_WELCOME_BANNER
                parsed_url = urllib.parse.urlparse(background_url)
                if parsed_url.scheme not in ['http', 'https'] or any(x in parsed_url.netloc for x in ['localhost', '127.0.0.1', '::1', '169.254']):
                    background_url = DEFAULT_WELCOME_BANNER

                title_color = settings.get("welcome_title_color", "#000000")
                subtitle_color = settings.get("welcome_subtitle_color", "#000000")
                banner_file = await generate_banner_image(self.bot.http_session, member, msg, background_url, title_color, subtitle_color)

                embed = discord.Embed(
                    description=f"**{top_text}**\n\n{msg}",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else None)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"Ahora somos {member.guild.member_count} miembros 🥕")

                if banner_file:
                    embed.set_image(url="attachment://banner.png")
                    try:
                        await channel.send(embed=embed, file=banner_file)
                    except discord.Forbidden:
                        print(f"No tengo permisos para enviar el banner de bienvenida en {channel.name}")
                else:
                    try:
                        await channel.send(embed=embed)
                    except discord.Forbidden:
                        pass

        if role_id := settings.get("autorole_id"):
            if role := member.guild.get_role(role_id):
                try: await member.add_roles(role, reason="Autorol al unirse")
                except discord.Forbidden: pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # --- NUEVO: Comprobación para evitar mensajes duplicados ---
        now = datetime.datetime.now(datetime.timezone.utc)
        self.recent_events.setdefault(member.guild.id, {'join': {}, 'remove': {}})

        if member.id in self.recent_events[member.guild.id]['remove']:
            if (now - self.recent_events[member.guild.id]['remove'][member.id]).total_seconds() < 5:
                return # Ignora el evento duplicado
        
        self.recent_events[member.guild.id]['remove'][member.id] = now
        # --- FIN DE LA COMPROBACIÓN ---

        settings = await db.get_cached_server_settings(member.guild.id)
        if settings and (channel_id := settings.get("goodbye_channel_id")):
            if channel := self.bot.get_channel(channel_id):
                try:
                    msg = (settings.get("goodbye_message") or DEFAULT_GOODBYE_MESSAGE).format(user=member, server=member.guild, member_count=member.guild.member_count)
                except (KeyError, ValueError):
                    msg = DEFAULT_GOODBYE_MESSAGE.format(user=member, server=member.guild, member_count=member.guild.member_count)

                top_text = settings.get("goodbye_top_text") or "¡Hasta pronto!"
                try:
                    top_text = top_text.format(user=member, server=member.guild, member_count=member.guild.member_count)
                except (KeyError, ValueError):
                    pass

                background_url = settings.get("goodbye_banner_url") or DEFAULT_GOODBYE_BANNER
                parsed_url = urllib.parse.urlparse(background_url)
                if parsed_url.scheme not in ['http', 'https'] or any(x in parsed_url.netloc for x in ['localhost', '127.0.0.1', '::1', '169.254']):
                    background_url = DEFAULT_GOODBYE_BANNER

                title_color = settings.get("goodbye_title_color", "#000000")
                subtitle_color = settings.get("goodbye_subtitle_color", "#000000")
                banner_file = await generate_banner_image(self.bot.http_session, member, msg, background_url, title_color, subtitle_color)

                embed = discord.Embed(
                    description=f"**{top_text}**\n\n{msg}",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else None)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"Ahora somos {member.guild.member_count} miembros 🥕")

                if banner_file:
                    embed.set_image(url="attachment://banner.png")
                    try:
                        await channel.send(embed=embed, file=banner_file)
                    except discord.Forbidden:
                        print(f"No tengo permisos para enviar el banner de despedida en {channel.name}")
                else:
                    try:
                        await channel.send(embed=embed)
                    except discord.Forbidden:
                        pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member and payload.member.bot: return
        result = await db.fetchone("SELECT role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?", (payload.guild_id, payload.message_id, str(payload.emoji)))
        if result and (guild := self.bot.get_guild(payload.guild_id)) and (member := guild.get_member(payload.user_id)) and (role := guild.get_role(result['role_id'])):
            try: await member.add_roles(role)
            except: pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        result = await db.fetchone("SELECT role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?", (payload.guild_id, payload.message_id, str(payload.emoji)))
        if result and (guild := self.bot.get_guild(payload.guild_id)) and (member := guild.get_member(payload.user_id)) and (role := guild.get_role(result['role_id'])):
            try: await member.remove_roles(role)
            except: pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Maneja la creación y eliminación de canales de voz temporales."""
        if member.bot: return
        if before.channel == after.channel: return # Ignorar ensordecidos/silenciados

        settings = await db.get_cached_server_settings(member.guild.id)
        if not settings: return
        
        creator_id = settings.get("temp_channel_creator_id")

        # 1. CREACIÓN: Usuario entra al canal maestro
        if after.channel and after.channel.id == creator_id:
            try:
                category = after.channel.category
                channel_name = f"{TEMP_CHANNEL_PREFIX}{member.display_name}"
                
                new_channel = await member.guild.create_voice_channel(
                    name=channel_name,
                    category=category,
                    reason=f"Canal temporal para {member.display_name}"
                )
                await member.move_to(new_channel)
            except discord.Forbidden:
                print(f"Falta de permisos en {member.guild.name} para crear canales temporales.")
            except Exception as e:
                print(f"Error en canal temporal: {e}")

        # 2. LIMPIEZA: Usuario sale de un canal temporal
        if before.channel:
            # Si el canal empieza con el prefijo y no es el canal creador, y está vacío...
            if before.channel.name.startswith(TEMP_CHANNEL_PREFIX) and before.channel.id != creator_id:
                if len(before.channel.members) == 0:
                    try:
                        await before.channel.delete(reason="Canal temporal vacío.")
                    except:
                        pass
            
    # Comandos administrativos de configuración
    @commands.hybrid_command(name='setwelcomechannel', description="Establece o desactiva el canal para mensajes de bienvenida.")
    @commands.has_permissions(manage_guild=True)
    async def set_welcome_channel(self, ctx: commands.Context, canal: Optional[discord.TextChannel] = None):
        # Fetch language for localization
        server_settings = await db.get_cached_server_settings(ctx.guild.id)
        lang = server_settings.get('language', 'es')

        if canal:
            await self.save_setting(ctx.guild.id, 'welcome_channel_id', canal.id)
            await ctx.send(_t('bot.config.welcome_set', lang=lang, channel=canal.mention), ephemeral=True)
        else:
            await self.save_setting(ctx.guild.id, 'welcome_channel_id', None)
            await ctx.send(_t('bot.config.welcome_disabled', lang=lang), ephemeral=True)

    @commands.hybrid_command(name='setgoodbyechannel', description="Establece o desactiva el canal para mensajes de despedida.")
    @commands.has_permissions(manage_guild=True)
    async def set_goodbye_channel(self, ctx: commands.Context, canal: Optional[discord.TextChannel] = None):
        # Fetch language for localization
        server_settings = await db.get_cached_server_settings(ctx.guild.id)
        lang = server_settings.get('language', 'es')

        if canal:
            await self.save_setting(ctx.guild.id, 'goodbye_channel_id', canal.id)
            await ctx.send(_t('bot.config.goodbye_set', lang=lang, channel=canal.mention), ephemeral=True)
        else:
            await self.save_setting(ctx.guild.id, 'goodbye_channel_id', None)
            await ctx.send(_t('bot.config.goodbye_disabled', lang=lang), ephemeral=True)

    @commands.hybrid_command(name='configwelcome', description="Personaliza el mensaje, banner y colores de la bienvenida.")
    @commands.has_permissions(manage_guild=True)
    async def config_welcome(
        self, ctx: commands.Context, 
        mensaje: str, 
        texto_superior: Optional[str] = None,
        banner_url: Optional[str] = None,
        color_titulo: Optional[str] = None,
        color_subtitulo: Optional[str] = None
    ):
        """
        Configura la bienvenida. Usa {user}, {server}, {member_count}.
        """
        await self.save_setting(ctx.guild.id, 'welcome_message', mensaje)
        response_message = "✅ Mensaje de bienvenida (en el banner) guardado."
        
        if texto_superior:
            await self.save_setting(ctx.guild.id, 'welcome_top_text', texto_superior)
            response_message += "\n✅ Texto superior guardado."

        if banner_url:
            parsed = urllib.parse.urlparse(banner_url)
            if parsed.scheme == "https":
                await self.save_setting(ctx.guild.id, 'welcome_banner_url', banner_url)
                response_message += "\n✅ Banner de bienvenida actualizado."
            else:
                response_message += "\n❌ La URL del banner debe ser `https://`."
        
        if color_titulo and re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', color_titulo):
            await self.save_setting(ctx.guild.id, 'welcome_title_color', color_titulo)
            response_message += f"\n✅ Color del título: `{color_titulo}`."
        
        if color_subtitulo and re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', color_subtitulo):
            await self.save_setting(ctx.guild.id, 'welcome_subtitle_color', color_subtitulo)
            response_message += f"\n✅ Color del subtítulo: `{color_subtitulo}`."

        await ctx.send(response_message, ephemeral=True)

    @commands.hybrid_command(name='configgoodbye', description="Personaliza el mensaje, banner y colores de la despedida.")
    @commands.has_permissions(manage_guild=True)
    async def config_goodbye(
        self, ctx: commands.Context, 
        mensaje: str, 
        texto_superior: Optional[str] = None,
        banner_url: Optional[str] = None,
        color_titulo: Optional[str] = None,
        color_subtitulo: Optional[str] = None
    ):
        """
        Configura la despedida. Usa {user}, {server}, {member_count}.
        """
        await self.save_setting(ctx.guild.id, 'goodbye_message', mensaje)
        response_message = "✅ Mensaje de despedida (en el banner) guardado."

        if texto_superior:
            await self.save_setting(ctx.guild.id, 'goodbye_top_text', texto_superior)
            response_message += "\n✅ Texto superior guardado."

        if banner_url:
            parsed = urllib.parse.urlparse(banner_url)
            if parsed.scheme == "https":
                await self.save_setting(ctx.guild.id, 'goodbye_banner_url', banner_url)
                response_message += "\n✅ Banner de despedida actualizado."
            else:
                response_message += "\n❌ La URL del banner debe ser `https://`."

        if color_titulo and re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', color_titulo):
            await self.save_setting(ctx.guild.id, 'goodbye_title_color', color_titulo)
            response_message += f"\n✅ Color del título: `{color_titulo}`."
        
        if color_subtitulo and re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', color_subtitulo):
            await self.save_setting(ctx.guild.id, 'goodbye_subtitle_color', color_subtitulo)
            response_message += f"\n✅ Color del subtítulo: `{color_subtitulo}`."

        await ctx.send(response_message, ephemeral=True)
    
    @commands.hybrid_command(name='setlogchannel', description="Establece el canal para el registro de moderación.")
    @commands.has_permissions(manage_guild=True)
    async def set_log_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        # Fetch language for localization
        server_settings = await db.get_cached_server_settings(ctx.guild.id)
        lang = server_settings.get('language', 'es')

        await self.save_setting(ctx.guild.id, 'log_channel_id', canal.id)
        await ctx.send(_t('bot.config.log_set', lang=lang, channel=canal.mention), ephemeral=True)

    @commands.hybrid_command(name='setautorole', description="Establece un rol para asignar a nuevos miembros.")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def set_autorole(self, ctx: commands.Context, rol: discord.Role):
        # Fetch language for localization
        server_settings = await db.get_cached_server_settings(ctx.guild.id)
        lang = server_settings.get('language', 'es')

        if ctx.guild.me.top_role <= rol:
            return await ctx.send(_t('bot.config.autorole_error', lang=lang), ephemeral=True)
        await self.save_setting(ctx.guild.id, 'autorole_id', rol.id)
        await ctx.send(_t('bot.config.autorole_set', lang=lang, role=rol.mention), ephemeral=True)

    @commands.hybrid_command(name='createreactionrole', description="Crea un nuevo rol por reacción.")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def create_reaction_role(self, ctx: commands.Context, id_del_mensaje: str, emoji: str, rol: discord.Role):
        await ctx.defer(ephemeral=True)
        # Fetch language for localization
        server_settings = await db.get_cached_server_settings(ctx.guild.id)
        lang = server_settings.get('language', 'es')

        try:
            message_id = int(id_del_mensaje)
        except ValueError:
            return await ctx.send(_t('bot.config.rr_error_msg', lang=lang), ephemeral=True)

        if not ctx.channel:
            return await ctx.send(_t('bot.common.error', lang=lang), ephemeral=True)

        try:
            message = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.send(_t('bot.config.rr_error_not_found', lang=lang), ephemeral=True)
        except discord.Forbidden:
            return await ctx.send(_t('bot.common.error', lang=lang), ephemeral=True)

        try:
            await message.add_reaction(emoji)
            await self.add_reaction_role(ctx.guild.id, message_id, emoji, rol.id)
            await ctx.send(_t('bot.config.rr_created', lang=lang), ephemeral=True)
        except discord.HTTPException:
            await ctx.send(f"❌ No se pudo añadir la reacción. Asegúrate de que el emoji sea válido.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Error al crear el rol por reacción: {e}", ephemeral=True)

    @commands.hybrid_command(name='sendmensaje', description="Envía un mensaje personalizado con formato a un canal.")
    @commands.has_permissions(manage_guild=True)
    async def send_mensaje(self, ctx: commands.Context, canal: discord.TextChannel, mensaje: str, titulo: Optional[str] = None, imagen_url: Optional[str] = None, color: Optional[str] = None):
        await ctx.defer(ephemeral=True)

        final_color = self.bot.CREAM_COLOR
        if color and color.startswith("#") and len(color) == 7:
            try:
                final_color = discord.Color(int(color[1:], 16))
            except ValueError:
                await ctx.send("⚠️ El formato de color no es válido. Se usará el color por defecto.", ephemeral=True)

        embed = discord.Embed(title=titulo, description=mensaje, color=final_color)
        if imagen_url:
            embed.set_image(url=imagen_url)

        try:
            await canal.send(embed=embed)
            await ctx.send(f"✅ Mensaje enviado correctamente a {canal.mention}.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send(f"❌ No tengo permisos para enviar mensajes en {canal.mention}.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Ocurrió un error al enviar el mensaje: {e}", ephemeral=True)

    @commands.hybrid_command(name='setcreatorchannel', description="Establece el canal para crear salas temporales.")
    @commands.has_permissions(manage_guild=True)
    async def set_creator_channel(self, ctx: commands.Context, canal: discord.VoiceChannel):
        await self.save_setting(ctx.guild.id, 'temp_channel_creator_id', canal.id)
        await ctx.send(f"✅ Quien se una a **{canal.name}** creará su propia sala.", ephemeral=True)

    @commands.hybrid_command(name='removecreatorchannel', description="Desactiva la creación de salas temporales.")
    @commands.has_permissions(manage_guild=True)
    async def remove_creator_channel(self, ctx: commands.Context):
        await self.save_setting(ctx.guild.id, 'temp_channel_creator_id', None)
        await ctx.send("✅ Creación de salas temporales desactivada.", ephemeral=True)

    @commands.hybrid_command(name='levels', description="Activa o desactiva el sistema de niveles.")
    @commands.has_permissions(manage_guild=True)
    async def toggle_leveling(self, ctx: commands.Context, estado: Literal['on', 'off']):
        await self.save_setting(ctx.guild.id, 'leveling_enabled', 1 if estado == 'on' else 0)
        await ctx.send(f"✅ Sistema de niveles **{'activado' if estado == 'on' else 'desactivado'}**.", ephemeral=True)

    @commands.hybrid_command(name='module', description="Habilitar o deshabilitar grandes bloques del bot (música, economía, etc).")
    @commands.has_permissions(manage_guild=True)
    async def toggle_module(self, ctx: commands.Context, modulo: Literal['niveles', 'moderacion', 'economia', 'apuestas', 'tickets', 'musica', 'tts', 'reaction_roles'], estado: Literal['on', 'off']):
        module_options = {
            'niveles': 'leveling_enabled',
            'moderacion': 'mod_enabled',
            'economia': 'eco_enabled',
            'apuestas': 'gamble_enabled',
            'tickets': 'tickets_enabled',
            'musica': 'music_enabled',
            'tts': 'tts_enabled',
            'reaction_roles': 'rr_enabled'
        }
        
        modulo_lower = modulo.lower()
        if modulo_lower not in module_options:
            valid_modules = ", ".join(f"`{m}`" for m in module_options.keys())
            return await ctx.send(f"❌ Módulo no válido. Opciones: {valid_modules}", ephemeral=True)

        column = module_options[modulo_lower]
        target_value = 1 if estado == 'on' else 0
        
        # Obtener configuración actual y lenguaje
        settings = await self.get_settings(ctx.guild.id)
        lang = settings.get('language', 'es')
        current_value = settings.get(column, 1 if modulo_lower != 'tickets' else 0) 
        
        status_text = _t(f'bot.config.{ "enabled" if estado == "on" else "disabled" }', lang=lang)
        
        if current_value == target_value:
            return await ctx.send(f"⚠️ El módulo de **{modulo_lower.title()}** ya está **{status_text}**.", ephemeral=True)

        await self.save_setting(ctx.guild.id, column, target_value)
        await ctx.send(_t('bot.config.module_toggled', lang=lang, module=modulo_lower.title(), status=status_text), ephemeral=True)

    @commands.hybrid_command(name='serverconfig', aliases=['configuracion', 'settings'], description="Muestra el panel de configuración completo del servidor.")
    @commands.has_permissions(manage_guild=True)
    async def serverconfig(self, ctx: commands.Context):
        """Muestra un resumen de toda la configuración del bot en este servidor."""
        await ctx.defer()
        
        settings = await db.get_cached_server_settings(ctx.guild.id)
        if not settings: return await ctx.send("❌ Error al cargar la configuración del servidor.", ephemeral=True)
        
        eco_settings = await db.get_cached_economy_settings(ctx.guild.id)
        tts_settings = await db.fetchone("SELECT * FROM tts_guild_settings WHERE guild_id = ?", (ctx.guild.id,))
        tts_channel = await db.fetchone("SELECT * FROM tts_active_channels WHERE guild_id = ?", (ctx.guild.id,))
        casino_channels_rows = await db.fetchall("SELECT channel_id FROM gambling_active_channels WHERE guild_id = ?", (ctx.guild.id,))
        
        embed = discord.Embed(title=f"⚙️ Panel de Configuración: {ctx.guild.name}", color=self.bot.CREAM_COLOR)
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        
        # 1. Canales Principales
        welcome_ch = f"<#{settings['welcome_channel_id']}>" if settings.get('welcome_channel_id') else "🚫 Inactivo"
        goodbye_ch = f"<#{settings['goodbye_channel_id']}>" if settings.get('goodbye_channel_id') else "🚫 Inactivo"
        log_ch = f"<#{settings['log_channel_id']}>" if settings.get('log_channel_id') else "🚫 Inactivo"
        creator_ch = f"<#{settings['temp_channel_creator_id']}>" if settings.get('temp_channel_creator_id') else "🚫 Inactivo"
        
        canales_texto = f"**Bienvenidas:** {welcome_ch} (`/setwelcomechannel`)\n**Despedidas:** {goodbye_ch} (`/setgoodbyechannel`)\n**Moderación (Logs):** {log_ch} (`/setlogchannel`)\n**Creador de Temp Voz:** {creator_ch} (`/setcreatorchannel`)"
        embed.add_field(name="📁 Canales Base", value=canales_texto, inline=False)
        
        # 2. Moderación
        anti_invite = "✅ Activado" if settings.get('automod_anti_invite') else "🚫 Desactivado"
        banned_words = settings.get('automod_banned_words')
        badwords_status = f"✅ Activado ({len([w for w in banned_words.split(',') if w])} palabras)" if banned_words else "🚫 Desactivado"
        autorole = f"<@&{settings['autorole_id']}>" if settings.get('autorole_id') else "🚫 Inactivo"
        
        mod_texto = f"**Anti-Invites:** {anti_invite} (`/automod anti_invites`)\n**Filtro Palabras:** {badwords_status} (`/automod badwords`)\n**Rol Automático:** {autorole} (`/setautorole`)"
        embed.add_field(name="🛡️ Moderación (Automod)", value=mod_texto, inline=False)
        
        # 3. Economía y Sistemas
        leveling = "✅ Activado" if settings.get('leveling_enabled', 1) else "🚫 Desactivado"
        currency = f"**{eco_settings.get('currency_name', 'créditos')}** {eco_settings.get('currency_emoji', '🪙')}" if eco_settings else "**créditos** 🪙"
        casino_ch_list = ", ".join(f"<#{r['channel_id']}>" for r in casino_channels_rows) if casino_channels_rows else "🚫 Inactivo"
        
        work_info = f"{eco_settings['work_min']}-{eco_settings['work_max']}" if eco_settings else "50-250"
        daily_info = f"{eco_settings['daily_min']}-{eco_settings['daily_max']}" if eco_settings else "100-500"
        rob_cd = f"{eco_settings['rob_cooldown'] // 3600}h" if eco_settings else "6h"

        eco_texto = (
            f"**Sistema Niveles:** {leveling} (`/levels`)\n"
            f"**Moneda Local:** {currency} (`/economy set-currency`)\n"
            f"**Canales Casino:** {casino_ch_list} (`/gambling addchannel`)\n"
            f"**Rango Work:** {work_info} (`/economy config-work`)\n"
            f"**Rango Daily:** {daily_info} (`/economy config-daily`)\n"
            f"**Cooldown Rob:** {rob_cd} (`/economy config-rob`)"
        )
        embed.add_field(name="💸 Economía y Niveles", value=eco_texto, inline=False)

        
        # 4. Texto a Voz (TTS)
        tts_lang = tts_settings['lang'] if tts_settings else "es"
        tts_ch = f"<#{tts_channel['text_channel_id']}>" if tts_channel else "🚫 Inactivo"
        
        tts_texto = f"**Idioma:** `{tts_lang}` (`/set_language_tts`)\n**Canal TTS:** {tts_ch} (`/setup_tts`)"
        embed.add_field(name="🔊 Texto a Voz (TTS)", value=tts_texto, inline=False)
        
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(ServerConfigCog(bot))