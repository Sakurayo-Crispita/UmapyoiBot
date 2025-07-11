import discord
from discord.ext import commands
import datetime
import re
import asyncio
from typing import Optional, Literal

# Importamos el gestor de base de datos
from utils import database_manager as db

def parse_duration(duration_str: str) -> Optional[datetime.timedelta]:
    """Convierte un string de tiempo (ej: 1d, 2h, 10m) a un objeto timedelta."""
    regex = re.compile(r'(\d+)([smhd])')
    matches = regex.findall(duration_str.lower())
    if not matches:
        return None
    
    total_seconds = 0
    for value, unit in matches:
        value = int(value)
        if unit == 's':
            total_seconds += value
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 'h':
            total_seconds += value * 3600
        elif unit == 'd':
            total_seconds += value * 86400
            
    if total_seconds > 2419200: # Límite de Discord de 28 días
        total_seconds = 2419200

    return datetime.timedelta(seconds=total_seconds)


class ModerationCog(commands.Cog, name="Moderación"):
    """Comandos para mantener el orden y la seguridad en el servidor."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    # --- LISTENERS PARA LOGS DE MENSAJES (NUEVO DISEÑO) ---

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Se activa cuando un mensaje es editado."""
        if before.author.bot or not before.guild or before.content == after.content:
            return

        log_settings = await db.fetchone("SELECT log_channel_id FROM server_settings WHERE guild_id = ?", (before.guild.id,))
        if not (log_settings and (log_channel_id := log_settings.get('log_channel_id'))):
            return
        
        log_channel = self.bot.get_channel(log_channel_id)
        if not log_channel:
            return

        embed = discord.Embed(
            title="Mensaje Editado",
            url=after.jump_url, # Enlace para saltar al mensaje
            color=0x3498DB, # Azul Celeste
            timestamp=datetime.datetime.now()
        )
        embed.set_author(name=f"{after.author.display_name}", icon_url=after.author.display_avatar.url)
        embed.description = f"📝 **{after.author.mention} editó un mensaje en {after.channel.mention}**"
        
        before_content = before.content[:1020] + "..." if len(before.content) > 1024 else before.content
        after_content = after.content[:1020] + "..." if len(after.content) > 1024 else after.content

        embed.add_field(name="Contenido Original", value=f"```{before_content}```", inline=False)
        embed.add_field(name="Contenido Nuevo", value=f"```{after_content}```", inline=False)

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Se activa cuando un mensaje es eliminado."""
        if message.author.bot or not message.guild:
            return

        log_settings = await db.fetchone("SELECT log_channel_id FROM server_settings WHERE guild_id = ?", (message.guild.id,))
        if not (log_settings and (log_channel_id := log_settings.get('log_channel_id'))):
            return

        log_channel = self.bot.get_channel(log_channel_id)
        if not log_channel:
            return
            
        # Esperar para dar tiempo al Audit Log a que se actualice
        await asyncio.sleep(1.5)

        actor = None
        try:
            async for entry in message.guild.audit_logs(limit=1, action=discord.AuditLogAction.message_delete):
                if entry.target.id == message.author.id and entry.channel.id == message.channel.id:
                    actor = entry.user
                    break
        except discord.Forbidden:
            print(f"No tengo permiso de 'Ver Registro de Auditoría' en {message.guild.name}")

        # Ignorar si el autor original borró su propio mensaje o si el actor es desconocido
        if actor is None or actor.id == message.author.id:
            return

        embed = discord.Embed(
            color=0xFF8C00, # Naranja
            timestamp=datetime.datetime.now()
        )
        embed.set_author(name=f"{message.author.display_name}", icon_url=message.author.display_avatar.url)
        
        description = (
            f"📙 **Mensaje de {message.author.mention} eliminado en {message.channel.mention}**\n"
            f"**Borrado por:** {actor.mention}"
        )
        embed.description = description
        
        if message.content:
            embed.add_field(name="Contenido", value=f"```{message.content}```", inline=False)

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listener para automod y para procesar comandos."""
        if message.author.bot or not message.guild:
            return

        settings = await db.fetchone("SELECT automod_banned_words, log_channel_id FROM server_settings WHERE guild_id = ?", (message.guild.id,))
        
        if settings and settings.get('automod_banned_words'):
            banned_words = [word for word in settings['automod_banned_words'].lower().split(',') if word]
            if any(word in message.content.lower() for word in banned_words):
                try:
                    await message.delete()
                    # Enviar log de automod
                    if log_channel_id := settings.get('log_channel_id'):
                        if log_channel := self.bot.get_channel(log_channel_id):
                            embed = discord.Embed(
                                color=0x992D22, # Rojo Oscuro
                                timestamp=datetime.datetime.now(),
                                description=f"📛 **Mensaje de {message.author.mention} eliminado por Automod en {message.channel.mention}**"
                            )
                            embed.set_author(name="Automod", icon_url=self.bot.user.display_avatar.url)
                            embed.add_field(name="Contenido Bloqueado", value=f"```{message.content}```", inline=False)
                            await log_channel.send(embed=embed)

                    warning_msg = await message.channel.send(f"⚠️ {message.author.mention}, tu mensaje ha sido eliminado por contener una palabra no permitida.")
                    await asyncio.sleep(10)
                    await warning_msg.delete()
                except Exception as e:
                    print(f"Error en automod on_message: {e}")
                return # Detener procesamiento
        
        await self.bot.process_commands(message)

    # --- FUNCIÓN AUXILIAR PARA LOGS DE COMANDOS ---
    async def _log_command_action(self, ctx: commands.Context, action: str, member: discord.Member | discord.User, reason: str, **kwargs):
        """Función auxiliar para enviar logs de acciones de moderación por comandos."""
        log_settings = await db.fetchone("SELECT log_channel_id FROM server_settings WHERE guild_id = ?", (ctx.guild.id,))
        if not (log_settings and (log_channel_id := log_settings.get('log_channel_id'))):
            return

        log_channel = self.bot.get_channel(log_channel_id)
        if not log_channel:
            return

        embed = discord.Embed(title=f"🚨 Acción de Moderación: {action}", color=discord.Color.red(), timestamp=datetime.datetime.now())
        embed.set_author(name=f"{ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="Usuario Afectado", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="Razón", value=reason, inline=False)
        
        if duration := kwargs.get('duration'):
            embed.add_field(name="Duración", value=duration)
        if channel := kwargs.get('channel'):
            embed.add_field(name="Canal", value=channel.mention, inline=True)
        if count := kwargs.get('count'):
            embed.add_field(name="Cantidad", value=str(count), inline=True)

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # --- COMANDOS DE MODERACIÓN ---

    @commands.hybrid_command(name="clear", description="Borra una cantidad específica de mensajes en el canal.")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clear(self, ctx: commands.Context, cantidad: commands.Range[int, 1, 100]):
        await ctx.defer(ephemeral=True)
        deleted = await ctx.channel.purge(limit=cantidad)
        await self._log_command_action(ctx, "Clear", ctx.author, "Borrado masivo de mensajes.", channel=ctx.channel, count=len(deleted))
        await ctx.send(f"✅ Se han borrado **{len(deleted)}** mensajes.", ephemeral=True)

    @commands.hybrid_command(name="kick", description="Expulsa a un miembro del servidor.")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, miembro: discord.Member, *, razon: str = "No se especificó una razón."):
        if miembro.id == self.bot.user.id:
            return await ctx.send("🥕 No puedo expulsarme a mí misma.", ephemeral=True)
        if miembro.id == ctx.author.id:
            return await ctx.send("❌ No puedes expulsarte a ti mismo.", ephemeral=True)
        if miembro.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("❌ No puedes expulsar a alguien con un rol igual o superior al tuyo.", ephemeral=True)

        await miembro.kick(reason=f"{razon} (Moderador: {ctx.author.name})")
        await db.add_mod_log(ctx.guild.id, miembro.id, ctx.author.id, "Kick", razon)
        await self._log_command_action(ctx, "Kick", miembro, razon)
        await ctx.send(f"✅ **{miembro.display_name}** ha sido expulsado.", ephemeral=True)

    @commands.hybrid_command(name="ban", description="Banea a un miembro del servidor.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, miembro: discord.Member, *, razon: str = "No se especificó una razón."):
        if miembro.id == self.bot.user.id:
            return await ctx.send("🥕 No puedo banearme a mí misma.", ephemeral=True)
        if miembro.id == ctx.author.id:
            return await ctx.send("❌ No puedes banearte a ti mismo.", ephemeral=True)
        if miembro.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("❌ No puedes banear a alguien con un rol igual o superior al tuyo.", ephemeral=True)

        await miembro.ban(reason=f"{razon} (Moderador: {ctx.author.name})")
        await db.add_mod_log(ctx.guild.id, miembro.id, ctx.author.id, "Ban", razon)
        await self._log_command_action(ctx, "Ban", miembro, razon)
        await ctx.send(f"✅ **{miembro.display_name}** ha sido baneado.", ephemeral=True)

    @commands.hybrid_command(name="unban", description="Desbanea a un usuario del servidor.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, usuario_id: str, *, razon: str = "No se especificó una razón."):
        try:
            user = await self.bot.fetch_user(int(usuario_id))
        except (ValueError, discord.NotFound):
            return await ctx.send("❌ No se encontró un usuario con esa ID.", ephemeral=True)

        try:
            await ctx.guild.unban(user, reason=f"{razon} (Moderador: {ctx.author.name})")
            await db.add_mod_log(ctx.guild.id, user.id, ctx.author.id, "Unban", razon)
            await self._log_command_action(ctx, "Unban", user, razon)
            await ctx.send(f"✅ **{user.name}** ha sido desbaneado.", ephemeral=True)
        except discord.NotFound:
            await ctx.send("❌ Este usuario no está en la lista de baneados.", ephemeral=True)

    @commands.hybrid_command(name="timeout", aliases=["mute"], description="Silencia a un miembro por un tiempo determinado.")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, miembro: discord.Member, duracion: str, *, razon: str = "No se especificó una razón."):
        if miembro.id == self.bot.user.id:
            return await ctx.send("🥕 No puedes silenciarme.", ephemeral=True)
        if miembro.id == ctx.author.id:
            return await ctx.send("❌ No puedes silenciarte a ti mismo.", ephemeral=True)
        if miembro.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("❌ No puedes silenciar a alguien con un rol superior.", ephemeral=True)
            
        delta = parse_duration(duracion)
        if delta is None:
            return await ctx.send("❌ Formato de duración inválido (ej: 10m, 2h, 1d).", ephemeral=True)

        await miembro.timeout(delta, reason=f"{razon} (Moderador: {ctx.author.name})")
        await db.add_mod_log(ctx.guild.id, miembro.id, ctx.author.id, "Timeout", razon, duracion)
        await self._log_command_action(ctx, "Timeout", miembro, razon, duration=duracion)
        await ctx.send(f"✅ **{miembro.display_name}** ha sido silenciado por **{duracion}**.", ephemeral=True)

    @commands.hybrid_command(name="unmute", description="Quita el silencio a un miembro.")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, miembro: discord.Member, *, razon: str = "Se ha portado bien."):
        if not miembro.is_timed_out():
            return await ctx.send("Este miembro no está silenciado.", ephemeral=True)
        
        await miembro.timeout(None, reason=f"{razon} (Moderador: {ctx.author.name})")
        await db.add_mod_log(ctx.guild.id, miembro.id, ctx.author.id, "Unmute", razon)
        await self._log_command_action(ctx, "Unmute", miembro, razon)
        await ctx.send(f"✅ Se ha quitado el silencio a **{miembro.display_name}**.", ephemeral=True)

    @commands.hybrid_command(name="warn", description="Advierte a un usuario.")
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, miembro: discord.Member, *, razon: str):
        if miembro.id == self.bot.user.id:
            return await ctx.send("🥕 No puedes advertirme a mí.", ephemeral=True)
        if miembro.id == ctx.author.id:
            return await ctx.send("❌ No puedes advertirte a ti mismo.", ephemeral=True)

        await db.execute("INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)", (ctx.guild.id, miembro.id, ctx.author.id, razon))
        await db.add_mod_log(ctx.guild.id, miembro.id, ctx.author.id, "Warn", razon)
        await self._log_command_action(ctx, "Warn", miembro, razon)
        try:
            await miembro.send(f"Has recibido una advertencia en **{ctx.guild.name}** por: {razon}")
        except discord.Forbidden:
            pass
        await ctx.send(f"⚠️ **{miembro.display_name}** ha sido advertido.", ephemeral=True)

    @commands.hybrid_command(name="clearwarnings", description="Borra todas las advertencias de un usuario.")
    @commands.has_permissions(manage_guild=True)
    async def clearwarnings(self, ctx: commands.Context, miembro: discord.Member):
        razon = "Se borraron todas las advertencias previas."
        await db.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, miembro.id))
        await db.add_mod_log(ctx.guild.id, miembro.id, ctx.author.id, "ClearWarnings", razon)
        await self._log_command_action(ctx, "ClearWarnings", miembro, razon)
        await ctx.send(f"✅ Todas las advertencias de **{miembro.display_name}** han sido borradas.", ephemeral=True)

    @commands.hybrid_command(name="lock", description="Bloquea el canal actual para que nadie (excepto mods) pueda hablar.")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def lock(self, ctx: commands.Context, canal: Optional[discord.TextChannel] = None):
        channel = canal or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Canal bloqueado por {ctx.author.name}")
        await self._log_command_action(ctx, "Lock Channel", ctx.author, f"Canal bloqueado.", channel=channel)
        await ctx.send(f"🔒 El canal {channel.mention} ha sido bloqueado.", ephemeral=True)

    @commands.hybrid_command(name="unlock", description="Desbloquea el canal actual.")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unlock(self, ctx: commands.Context, canal: Optional[discord.TextChannel] = None):
        channel = canal or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Canal desbloqueado por {ctx.author.name}")
        await self._log_command_action(ctx, "Unlock Channel", ctx.author, f"Canal desbloqueado.", channel=channel)
        await ctx.send(f"🔓 El canal {channel.mention} ha sido desbloqueado.", ephemeral=True)

    # --- COMANDOS INFORMATIVOS (SIN CAMBIOS) ---
    # (mutelist, modlogs, warnings, automod)

    @commands.hybrid_command(name="mutelist", description="Muestra la lista de usuarios silenciados actualmente.")
    @commands.has_permissions(moderate_members=True)
    async def mutelist(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        muted_members = [m for m in ctx.guild.members if m.is_timed_out()]
        
        if not muted_members:
            return await ctx.send("No hay nadie silenciado en este momento.", ephemeral=True)
            
        embed = discord.Embed(title="🔇 Usuarios Silenciados", color=discord.Color.orange())
        description = ""
        for member in muted_members:
            if member.timed_out_until:
                description += f"• {member.mention} - Termina en {discord.utils.format_dt(member.timed_out_until, 'R')}\n"
        embed.description = description
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="modlogs", description="Muestra el historial de moderación de un usuario.")
    @commands.has_permissions(moderate_members=True)
    async def modlogs(self, ctx: commands.Context, miembro: discord.Member):
        await ctx.defer(ephemeral=True)
        logs = await db.fetchall("SELECT * FROM mod_logs WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC", (ctx.guild.id, miembro.id))
        
        if not logs:
            return await ctx.send(f"**{miembro.display_name}** no tiene historial de moderación.", ephemeral=True)

        embed = discord.Embed(title=f"Historial de Moderación de {miembro.display_name}", color=discord.Color.blue())
        for log in logs:
            moderator = ctx.guild.get_member(log['moderator_id']) or f"ID: {log['moderator_id']}"
            timestamp = discord.utils.format_dt(datetime.datetime.fromisoformat(log['timestamp']), 'f')
            duration_text = f" (Duración: {log['duration']})" if log['duration'] else ""
            embed.add_field(name=f"Caso #{log['log_id']} - {log['action']}",
                            value=f"**Razón:** {log['reason']}{duration_text}\n"
                                  f"**Moderador:** {moderator}\n"
                                  f"**Fecha:** {timestamp}",
                            inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="warnings", description="Muestra las advertencias de un usuario.")
    @commands.has_permissions(moderate_members=True)
    async def warnings(self, ctx: commands.Context, miembro: discord.Member):
        await ctx.defer(ephemeral=True)
        warnings_list = await db.fetchall("SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC", (ctx.guild.id, miembro.id))
        if not warnings_list:
            return await ctx.send(f"**{miembro.display_name}** no tiene ninguna advertencia.", ephemeral=True)

        embed = discord.Embed(title=f"Advertencias de {miembro.display_name}", color=discord.Color.orange())
        for warn in warnings_list:
            moderator = ctx.guild.get_member(warn['moderator_id']) or f"ID: {warn['moderator_id']}"
            timestamp = discord.utils.format_dt(datetime.datetime.fromisoformat(warn['timestamp']), 'f')
            embed.add_field(name=f"Advertencia #{warn['warning_id']} el {timestamp}", 
                            value=f"**Razón:** {warn['reason']}\n**Moderador:** {moderator}",
                            inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    # --- COMANDOS DE AUTOMODERACIÓN (SIN CAMBIOS) ---
    @commands.hybrid_group(name="automod", description="Configura las opciones de auto-moderación.")
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None: 
            await ctx.send("Comando inválido. Usa `/automod anti-invites` o `/automod badwords`.", ephemeral=True)

    @automod.command(name="anti_invites", description="Activa o desactiva el borrado de invitaciones de Discord.")
    @commands.has_permissions(manage_guild=True)
    async def anti_invites(self, ctx: commands.Context, estado: Literal['on', 'off']):
        await db.execute("UPDATE server_settings SET automod_anti_invite = ? WHERE guild_id = ?", (1 if estado == 'on' else 0, ctx.guild.id))
        await ctx.send(f"✅ Filtro anti-invitaciones **{estado}**.", ephemeral=True)

    @automod.group(name="badwords", description="Gestiona la lista de palabras prohibidas.")
    @commands.has_permissions(manage_guild=True)
    async def badwords(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None: 
            await ctx.send("Comando inválido.", ephemeral=True)

    @badwords.command(name="add", description="Añade una palabra a la lista de prohibidas.")
    @commands.has_permissions(manage_guild=True)
    async def badwords_add(self, ctx: commands.Context, palabra: str):
        settings = await db.fetchone("SELECT automod_banned_words FROM server_settings WHERE guild_id = ?", (ctx.guild.id,))
        current_words_str = settings['automod_banned_words'] if settings and settings['automod_banned_words'] else ""
        current_words = set(current_words_str.lower().split(','))
        current_words.add(palabra.lower())
        await db.execute("UPDATE server_settings SET automod_banned_words = ? WHERE guild_id = ?", (",".join(filter(None, current_words)), ctx.guild.id))
        await ctx.send(f"✅ Palabra `{palabra}` añadida.", ephemeral=True)

    @badwords.command(name="remove", description="Quita una palabra de la lista de prohibidas.")
    @commands.has_permissions(manage_guild=True)
    async def badwords_remove(self, ctx: commands.Context, palabra: str):
        settings = await db.fetchone("SELECT automod_banned_words FROM server_settings WHERE guild_id = ?", (ctx.guild.id,))
        word_list_str = settings['automod_banned_words'] if settings and settings['automod_banned_words'] else ""
        word_list = word_list_str.lower().split(',')
        if palabra.lower() in word_list:
            word_list.remove(palabra.lower())
            await db.execute("UPDATE server_settings SET automod_banned_words = ? WHERE guild_id = ?", (",".join(filter(None, word_list)), ctx.guild.id))
            await ctx.send(f"✅ Palabra `{palabra}` eliminada.", ephemeral=True)
        else: 
            await ctx.send(f"⚠️ La palabra `{palabra}` no estaba en la lista.", ephemeral=True)

    @badwords.command(name="list", description="Muestra la lista de palabras prohibidas.")
    @commands.has_permissions(manage_guild=True)
    async def badwords_list(self, ctx: commands.Context):
        settings = await db.fetchone("SELECT automod_banned_words FROM server_settings WHERE guild_id = ?", (ctx.guild.id,))
        words = settings['automod_banned_words'] if settings and settings['automod_banned_words'] else "La lista está vacía."
        await ctx.send(f"**Lista de palabras prohibidas:**\n`{words}`", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))