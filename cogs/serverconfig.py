import discord
from discord.ext import commands
import asyncio
import datetime
from typing import Optional, Literal
from utils import database_manager as db
# 1. Importamos las constantes que necesitamos
from utils.constants import (
    DEFAULT_WELCOME_MESSAGE, DEFAULT_WELCOME_BANNER, 
    DEFAULT_GOODBYE_MESSAGE, DEFAULT_GOODBYE_BANNER,
    TEMP_CHANNEL_PREFIX
)

# --- MODALES (No necesitan cambios) ---
class WelcomeConfigModal(discord.ui.Modal, title='Configuración de Bienvenida'):
    def __init__(self, cog, default_message, default_banner):
        super().__init__()
        self.cog = cog
        self.add_item(discord.ui.TextInput(label="Mensaje de Bienvenida", style=discord.TextStyle.long, placeholder="{user.mention}, {server.name}", default=default_message, required=True))
        self.add_item(discord.ui.TextInput(label="URL del Banner", placeholder="https://i.imgur.com/...", default=default_banner, required=False))
    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.save_setting(interaction.guild.id, 'welcome_message', self.children[0].value)
        await self.cog.save_setting(interaction.guild.id, 'welcome_banner_url', self.children[1].value or self.cog.DEFAULT_WELCOME_BANNER)
        await interaction.response.send_message("✅ Configuración de bienvenida guardada.", ephemeral=True)

class GoodbyeConfigModal(discord.ui.Modal, title='Configuración de Despedida'):
    def __init__(self, cog, default_message, default_banner):
        super().__init__()
        self.cog = cog
        self.add_item(discord.ui.TextInput(label="Mensaje de Despedida", style=discord.TextStyle.long, placeholder="{user.name}, {server.name}", default=default_message, required=True))
        self.add_item(discord.ui.TextInput(label="URL del Banner", placeholder="https://i.imgur.com/...", default=default_banner, required=False))
    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.save_setting(interaction.guild.id, 'goodbye_message', self.children[0].value)
        await self.cog.save_setting(interaction.guild.id, 'goodbye_banner_url', self.children[1].value or self.cog.DEFAULT_GOODBYE_BANNER)
        await interaction.response.send_message("✅ Configuración de despedida guardada.", ephemeral=True)

class ReactionRoleModal(discord.ui.Modal, title="Crear Rol por Reacción"):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
        self.add_item(discord.ui.TextInput(label="ID del Mensaje", placeholder="Copia aquí el ID del mensaje", required=True))
        self.add_item(discord.ui.TextInput(label="Emoji", placeholder="Pega el emoji a usar (ej. ✅)", required=True))
        self.add_item(discord.ui.TextInput(label="ID del Rol", placeholder="Copia aquí el ID del rol a asignar", required=True))
    async def on_submit(self, interaction: discord.Interaction):
        try:
            message_id, role_id = int(self.children[0].value), int(self.children[2].value)
            emoji = self.children[1].value
        except ValueError:
            return await interaction.response.send_message("❌ ID de Mensaje o Rol no válidos.", ephemeral=True)
        try:
            await self.cog.add_reaction_role(interaction.guild.id, message_id, emoji, role_id)
            if isinstance(interaction.channel, (discord.TextChannel, discord.ForumChannel, discord.Thread)):
                message = await interaction.channel.fetch_message(message_id)
                await message.add_reaction(emoji)
            await interaction.response.send_message("✅ Rol por reacción creado.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error al crear el rol por reacción: {e}", ephemeral=True)

# --- COG PRINCIPAL ---
class ServerConfigCog(commands.Cog, name="Configuración del Servidor"):
    """Comandos para que los administradores configuren el bot en el servidor."""
    # 2. Las constantes de clase ahora usan los valores importados
    DEFAULT_WELCOME_MESSAGE = DEFAULT_WELCOME_MESSAGE
    DEFAULT_WELCOME_BANNER = DEFAULT_WELCOME_BANNER
    DEFAULT_GOODBYE_MESSAGE = DEFAULT_GOODBYE_MESSAGE
    DEFAULT_GOODBYE_BANNER = DEFAULT_GOODBYE_BANNER
    TEMP_CHANNEL_PREFIX = TEMP_CHANNEL_PREFIX

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_settings(self, guild_id: int):
        settings = await db.fetchone("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
        if not settings:
            await db.execute("INSERT OR IGNORE INTO server_settings (guild_id) VALUES (?)", (guild_id,))
            return await db.fetchone("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
        return settings

    async def save_setting(self, guild_id: int, key: str, value):
        allowed_keys = [
            'welcome_channel_id', 'goodbye_channel_id', 'log_channel_id', 
            'autorole_id', 'welcome_message', 'welcome_banner_url', 
            'goodbye_message', 'goodbye_banner_url', 'automod_anti_invite', 
            'automod_banned_words', 'temp_channel_creator_id', 'leveling_enabled'
        ]
        if key not in allowed_keys:
            print(f"ALERTA DE SEGURIDAD: Intento de guardar clave no permitida: {key}")
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
        if settings and settings["log_channel_id"]:
            if log_channel := self.bot.get_channel(settings["log_channel_id"]):
                try: await log_channel.send(embed=embed)
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
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        settings = await self.get_settings(member.guild.id)
        if not settings or not settings["temp_channel_creator_id"]: return
        
        creator_id = settings["temp_channel_creator_id"]
        if after.channel and after.channel.id == creator_id:
            overwrites = { member.guild.default_role: discord.PermissionOverwrite(view_channel=True), member: discord.PermissionOverwrite(view_channel=True, manage_channels=True, manage_permissions=True, move_members=True) }
            try:
                temp_channel = await member.guild.create_voice_channel(name=f"{self.TEMP_CHANNEL_PREFIX}{member.display_name}", category=after.channel.category, overwrites=overwrites)
                await member.move_to(temp_channel)
            except Exception as e: print(f"Error creando canal temporal: {e}")
        if before.channel and before.channel.name.startswith(self.TEMP_CHANNEL_PREFIX) and not before.channel.members:
            try: 
                await asyncio.sleep(1)
                await before.channel.delete(reason="Canal temporal vacío.")
            except Exception as e: print(f"Error borrando canal temporal: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = await self.get_settings(member.guild.id)
        if not settings: return
        if channel_id := settings["welcome_channel_id"]:
            if channel := self.bot.get_channel(channel_id):
                msg = (settings["welcome_message"] or self.DEFAULT_WELCOME_MESSAGE).format(user=member, server=member.guild, member_count=member.guild.member_count)
                banner = settings["welcome_banner_url"] or self.DEFAULT_WELCOME_BANNER
                embed = discord.Embed(description=msg, color=discord.Color.green()).set_author(name=f"¡Bienvenido a {member.guild.name}!", icon_url=member.display_avatar.url).set_footer(text=f"Ahora somos {member.guild.member_count} miembros.")
                if banner: embed.set_image(url=banner)
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
                msg = (settings["goodbye_message"] or self.DEFAULT_GOODBYE_MESSAGE).format(user=member, server=member.guild, member_count=member.guild.member_count)
                banner = settings["goodbye_banner_url"] or self.DEFAULT_GOODBYE_BANNER
                embed = discord.Embed(description=msg, color=discord.Color.red()).set_author(name=f"Adiós, {member.display_name}", icon_url=member.display_avatar.url).set_footer(text=f"Ahora somos {member.guild.member_count} miembros.")
                if banner: embed.set_image(url=banner)
                try: await channel.send(embed=embed)
                except discord.Forbidden: pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member and payload.member.bot: return
        result = await self.get_reaction_role(payload.guild_id, payload.message_id, str(payload.emoji))
        if result and (guild := self.bot.get_guild(payload.guild_id)) and (member := guild.get_member(payload.user_id)) and (role := guild.get_role(result['role_id'])):
            try: await member.add_roles(role)
            except: pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        result = await self.get_reaction_role(payload.guild_id, payload.message_id, str(payload.emoji))
        if result and (guild := self.bot.get_guild(payload.guild_id)) and (member := guild.get_member(payload.user_id)) and (role := guild.get_role(result['role_id'])):
            try: await member.remove_roles(role)
            except: pass

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

    @commands.hybrid_command(name='setlogchannel', description="Establece el canal para el registro de moderación.")
    @commands.has_permissions(manage_guild=True)
    async def set_log_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        await self.save_setting(ctx.guild.id, 'log_channel_id', canal.id)
        await ctx.send(f"✅ Canal de logs: {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name='setautorole', description="Establece un rol para asignar a nuevos miembros.")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def set_autorole(self, ctx: commands.Context, rol: discord.Role):
        await self.save_setting(ctx.guild.id, 'autorole_id', rol.id)
        await ctx.send(f"✅ Rol automático: {rol.mention}.", ephemeral=True)

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
    @commands.has_permissions(manage_roles=True)
    async def create_reaction_role(self, ctx: commands.Context):
        await ctx.interaction.response.send_modal(ReactionRoleModal(self))

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
