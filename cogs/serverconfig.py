import discord
from discord.ext import commands
import asyncio
import datetime
from typing import Optional, Literal
from utils import database_manager as db
from utils.constants import (
    DEFAULT_WELCOME_MESSAGE, DEFAULT_WELCOME_BANNER, 
    DEFAULT_GOODBYE_MESSAGE, DEFAULT_GOODBYE_BANNER,
    TEMP_CHANNEL_PREFIX
)
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import aiohttp
import re

# --- FUNCIÓN DE GENERACIÓN DE IMÁGENES (CORREGIDA) ---
# Ahora acepta los colores como parámetros
async def generate_banner_image(
    session: aiohttp.ClientSession, 
    member: discord.Member, 
    message: str, 
    background_url: str,
    title_color: str = "#000000",      # Color por defecto: negro
    subtitle_color: str = "#000000"   # Color por defecto: negro
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
            subtitle_font = ImageFont.truetype(font_path, 40)
        except IOError:
            print("Fuente 'utils/arial.ttf' no encontrada, usando la fuente por defecto.")
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()

        processed_message = message.replace(member.mention, f"@{member.display_name}")
        max_length = 50 
        if len(processed_message) > max_length:
            processed_message = processed_message[:max_length] + "..."

        # Usamos los colores pasados como parámetros
        draw.text((500, 280), member.display_name, fill=title_color, font=title_font, anchor="ms")
        draw.text((500, 340), processed_message, fill=subtitle_color, font=subtitle_font, anchor="ms")

        final_buffer = BytesIO()
        bg.save(final_buffer, format="PNG")
        final_buffer.seek(0)
        
        return discord.File(final_buffer, filename="banner.png")

    except Exception as e:
        print(f"Error generando el banner: {e}")
        return None


# --- COG PRINCIPAL ---
class ServerConfigCog(commands.Cog, name="Configuración del Servidor"):
    """Comandos para que los administradores configuren el bot en el servidor."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_settings(self, guild_id: int):
        settings = await db.fetchone("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
        if not settings:
            await db.execute("INSERT OR IGNORE INTO server_settings (guild_id) VALUES (?)", (guild_id,))
            return await db.fetchone("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
        return settings

    async def save_setting(self, guild_id: int, key: str, value):
        # Añadimos las nuevas claves de color a la lista permitida
        allowed_keys = [
            'welcome_channel_id', 'goodbye_channel_id', 'log_channel_id', 'autorole_id', 
            'welcome_message', 'welcome_banner_url', 'goodbye_message', 'goodbye_banner_url', 
            'automod_anti_invite', 'automod_banned_words', 'temp_channel_creator_id', 'leveling_enabled',
            'welcome_title_color', 'welcome_subtitle_color', 'goodbye_title_color', 'goodbye_subtitle_color'
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
        settings = await self.get_settings(guild_id)
        if settings and settings.get("log_channel_id"):
            if log_channel := self.bot.get_channel(settings.get("log_channel_id")):
                try: await log_channel.send(embed=embed)
                except discord.Forbidden: pass

    # --- LISTENERS (CORREGIDOS) ---
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = await self.get_settings(member.guild.id)
        if not settings: return

        if channel_id := settings.get("welcome_channel_id"):
            if channel := self.bot.get_channel(channel_id):
                msg = (settings.get("welcome_message") or DEFAULT_WELCOME_MESSAGE).format(user=member, server=member.guild, member_count=member.guild.member_count)
                background_url = settings.get("welcome_banner_url") or DEFAULT_WELCOME_BANNER
                # Obtenemos los colores de la base de datos
                title_color = settings.get("welcome_title_color", "#000000")
                subtitle_color = settings.get("welcome_subtitle_color", "#000000")
                
                # Pasamos los colores a la función
                banner_file = await generate_banner_image(self.bot.http_session, member, msg, background_url, title_color, subtitle_color)
                
                if banner_file:
                    try: await channel.send(file=banner_file)
                    except discord.Forbidden: print(f"No tengo permisos para enviar el banner de bienvenida en {channel.name}")
                else: 
                    embed = discord.Embed(description=msg, color=discord.Color.green()).set_author(name=f"¡Bienvenido a {member.guild.name}!", icon_url=member.display_avatar.url).set_footer(text=f"Ahora somos {member.guild.member_count} miembros.")
                    try: await channel.send(embed=embed)
                    except discord.Forbidden: pass

        if role_id := settings.get("autorole_id"):
            if role := member.guild.get_role(role_id):
                try: await member.add_roles(role, reason="Autorol al unirse")
                except discord.Forbidden: pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        settings = await self.get_settings(member.guild.id)
        if settings and (channel_id := settings.get("goodbye_channel_id")):
            if channel := self.bot.get_channel(channel_id):
                msg = (settings.get("goodbye_message") or DEFAULT_GOODBYE_MESSAGE).format(user=member, server=member.guild, member_count=member.guild.member_count)
                background_url = settings.get("goodbye_banner_url") or DEFAULT_GOODBYE_BANNER
                # Obtenemos los colores de la base de datos
                title_color = settings.get("goodbye_title_color", "#000000")
                subtitle_color = settings.get("goodbye_subtitle_color", "#000000")

                # Pasamos los colores a la función
                banner_file = await generate_banner_image(self.bot.http_session, member, msg, background_url, title_color, subtitle_color)
                
                if banner_file:
                    try: await channel.send(file=banner_file)
                    except discord.Forbidden: print(f"No tengo permisos para enviar el banner de despedida en {channel.name}")
                else:
                    embed = discord.Embed(description=msg, color=discord.Color.red()).set_author(name=f"Adiós, {member.display_name}", icon_url=member.display_avatar.url).set_footer(text=f"Ahora somos {member.guild.member_count} miembros.")
                    try: await channel.send(embed=embed)
                    except discord.Forbidden: pass

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
            
    # --- COMANDOS (CORREGIDOS) ---
    @commands.hybrid_command(name='setwelcomechannel', description="Establece el canal para mensajes de bienvenida.")
    @commands.has_permissions(manage_guild=True)
    async def set_welcome_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        await self.save_setting(ctx.guild.id, 'welcome_channel_id', canal.id)
        await ctx.send(f"✅ Canal de bienvenida: {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name='setgoodbyechannel', description="Establece el canal para mensajes de despedida.")
    @commands.has_permissions(manage_guild=True)
    async def set_goodbye_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        await self.save_setting(ctx.guild.id, 'goodbye_channel_id', canal.id)
        await ctx.send(f"✅ Canal de despedida: {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name='configwelcome', description="Personaliza el mensaje, banner y colores de la bienvenida.")
    @commands.has_permissions(manage_guild=True)
    async def config_welcome(
        self, ctx: commands.Context, 
        mensaje: str, 
        banner_url: Optional[str] = None,
        color_titulo: Optional[str] = None,
        color_subtitulo: Optional[str] = None
    ):
        """
        Configura la bienvenida. Colores en formato #RRGGBB (ej: #FF0000 para rojo).
        """
        await self.save_setting(ctx.guild.id, 'welcome_message', mensaje)
        response_message = "✅ Mensaje de bienvenida guardado."
        
        if banner_url:
            await self.save_setting(ctx.guild.id, 'welcome_banner_url', banner_url)
            response_message += "\n✅ Banner de bienvenida actualizado."
        
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
        banner_url: Optional[str] = None,
        color_titulo: Optional[str] = None,
        color_subtitulo: Optional[str] = None
    ):
        """
        Configura la despedida. Colores en formato #RRGGBB (ej: #FFFFFF para blanco).
        """
        await self.save_setting(ctx.guild.id, 'goodbye_message', mensaje)
        response_message = "✅ Mensaje de despedida guardado."

        if banner_url:
            await self.save_setting(ctx.guild.id, 'goodbye_banner_url', banner_url)
            response_message += "\n✅ Banner de despedida actualizado."

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
        await self.save_setting(ctx.guild.id, 'log_channel_id', canal.id)
        await ctx.send(f"✅ Canal de logs: {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name='setautorole', description="Establece un rol para asignar a nuevos miembros.")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def set_autorole(self, ctx: commands.Context, rol: discord.Role):
        if ctx.guild.me.top_role <= rol:
            return await ctx.send("❌ No puedo asignar ese rol porque está en una posición igual o superior a la mía.", ephemeral=True)
        await self.save_setting(ctx.guild.id, 'autorole_id', rol.id)
        await ctx.send(f"✅ Rol automático configurado: {rol.mention}.", ephemeral=True)

    @commands.hybrid_command(name='createreactionrole', description="Crea un nuevo rol por reacción.")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def create_reaction_role(self, ctx: commands.Context, id_del_mensaje: str, emoji: str, rol: discord.Role):
        await ctx.defer(ephemeral=True)
        try:
            message_id = int(id_del_mensaje)
        except ValueError:
            return await ctx.send("❌ El ID del mensaje debe ser un número.", ephemeral=True)

        if not ctx.channel:
            return await ctx.send("❌ Este comando no se puede usar aquí.", ephemeral=True)

        try:
            message = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.send("❌ No se encontró un mensaje con ese ID en este canal.", ephemeral=True)
        except discord.Forbidden:
            return await ctx.send("❌ No tengo permisos para leer el historial de este canal.", ephemeral=True)

        try:
            await message.add_reaction(emoji)
            await self.add_reaction_role(ctx.guild.id, message_id, emoji, rol.id)
            await ctx.send(f"✅ Rol por reacción creado. He reaccionado con {emoji} al mensaje.", ephemeral=True)
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

async def setup(bot: commands.Bot):
    await bot.add_cog(ServerConfigCog(bot))