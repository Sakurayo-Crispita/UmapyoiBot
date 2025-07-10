import discord
from discord.ext import commands
import datetime
import re
from typing import Optional, Literal

# Importamos el gestor de base de datos
from utils import database_manager as db

def parse_duration(duration_str: str) -> Optional[datetime.timedelta]:
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

    # --- Las funciones de base de datos se han eliminado de aquí ---

    @commands.hybrid_command(name="clear", description="Borra una cantidad específica de mensajes en el canal.")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clear(self, ctx: commands.Context, cantidad: commands.Range[int, 1, 100]):
        await ctx.defer(ephemeral=True)
        deleted = await ctx.channel.purge(limit=cantidad)
        await ctx.send(f"✅ Se han borrado **{len(deleted)}** mensajes.", ephemeral=True)

    @commands.hybrid_command(name="kick", description="Expulsa a un miembro del servidor.")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, miembro: discord.Member, *, razon: str = "No se especificó una razón."):
        if miembro == ctx.author:
            return await ctx.send("❌ No puedes expulsarte a ti mismo.", ephemeral=True)
        if miembro.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("❌ No puedes expulsar a alguien con un rol igual o superior al tuyo.", ephemeral=True)

        await miembro.kick(reason=f"{razon} (Moderador: {ctx.author.name})")
        await db.add_mod_log(ctx.guild.id, miembro.id, ctx.author.id, "Kick", razon)
        await ctx.send(f"✅ **{miembro.display_name}** ha sido expulsado del servidor por: **{razon}**", ephemeral=True)

    @commands.hybrid_command(name="ban", description="Banea a un miembro del servidor.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, miembro: discord.Member, *, razon: str = "No se especificó una razón."):
        if miembro == ctx.author:
            return await ctx.send("❌ No puedes banearte a ti mismo.", ephemeral=True)
        if miembro.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("❌ No puedes banear a alguien con un rol igual o superior al tuyo.", ephemeral=True)

        await miembro.ban(reason=f"{razon} (Moderador: {ctx.author.name})")
        await db.add_mod_log(ctx.guild.id, miembro.id, ctx.author.id, "Ban", razon)
        await ctx.send(f"✅ **{miembro.display_name}** ha sido baneado permanentemente por: **{razon}**", ephemeral=True)

    @commands.hybrid_command(name="unban", description="Desbanea a un usuario del servidor.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, usuario_id: str, *, razon: str = "No se especificó una razón."):
        try:
            user = await self.bot.fetch_user(int(usuario_id))
        except (ValueError, discord.NotFound):
            return await ctx.send("❌ No se encontró a un usuario con esa ID.", ephemeral=True)

        try:
            await ctx.guild.unban(user, reason=f"{razon} (Moderador: {ctx.author.name})")
            await db.add_mod_log(ctx.guild.id, user.id, ctx.author.id, "Unban", razon)
            await ctx.send(f"✅ **{user.name}** ha sido desbaneado.", ephemeral=True)
        except discord.NotFound:
            await ctx.send("❌ Este usuario no se encuentra en la lista de baneados.", ephemeral=True)

    @commands.hybrid_command(name="timeout", aliases=["mute"], description="Silencia a un miembro por un tiempo determinado (ej: 10m, 2h, 1d).")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, miembro: discord.Member, duracion: str, *, razon: str = "No se especificó una razón."):
        if miembro == ctx.author:
            return await ctx.send("❌ No puedes silenciarte a ti mismo.", ephemeral=True)
        if miembro.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("❌ No puedes silenciar a alguien con un rol igual o superior al tuyo.", ephemeral=True)
            
        delta = parse_duration(duracion)
        if delta is None:
            return await ctx.send("❌ Formato de duración inválido. Usa `d` para días, `h` para horas, `m` para minutos, `s` para segundos.", ephemeral=True)

        await miembro.timeout(delta, reason=f"{razon} (Moderador: {ctx.author.name})")
        await db.add_mod_log(ctx.guild.id, miembro.id, ctx.author.id, "Timeout", razon, duracion)
        await ctx.send(f"✅ **{miembro.display_name}** ha sido silenciado por **{duracion}** por la razón: **{razon}**", ephemeral=True)

    @commands.hybrid_command(name="unmute", description="Quita el silencio a un miembro.")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, miembro: discord.Member, *, razon: str = "Se ha portado bien."):
        if not miembro.is_timed_out():
            return await ctx.send("Este miembro no está silenciado.", ephemeral=True)
        
        await miembro.timeout(None, reason=f"{razon} (Moderador: {ctx.author.name})")
        await db.add_mod_log(ctx.guild.id, miembro.id, ctx.author.id, "Unmute", razon)
        await ctx.send(f"✅ Se ha quitado el silencio a **{miembro.display_name}**.", ephemeral=True)

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

    @commands.hybrid_command(name="lock", description="Bloquea el canal actual para que nadie (excepto mods) pueda hablar.")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def lock(self, ctx: commands.Context, canal: Optional[discord.TextChannel] = None):
        channel = canal or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Canal bloqueado por {ctx.author.name}")
        await ctx.send(f"🔒 El canal {channel.mention} ha sido bloqueado.", ephemeral=True)

    @commands.hybrid_command(name="unlock", description="Desbloquea el canal actual.")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unlock(self, ctx: commands.Context, canal: Optional[discord.TextChannel] = None):
        channel = canal or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Canal desbloqueado por {ctx.author.name}")
        await ctx.send(f"🔓 El canal {channel.mention} ha sido desbloqueado.", ephemeral=True)

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
        
    @commands.hybrid_command(name="warn", description="Advierte a un usuario.")
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, miembro: discord.Member, *, razon: str):
        await db.execute("INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)", (ctx.guild.id, miembro.id, ctx.author.id, razon))
        await db.add_mod_log(ctx.guild.id, miembro.id, ctx.author.id, "Warn", razon)
        try:
            await miembro.send(f"Has recibido una advertencia en **{ctx.guild.name}** por: {razon}")
        except discord.Forbidden:
            pass
        await ctx.send(f"⚠️ **{miembro.display_name}** ha sido advertido por: **{razon}**", ephemeral=True)

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

    @commands.hybrid_command(name="clearwarnings", description="Borra todas las advertencias de un usuario.")
    @commands.has_permissions(manage_guild=True)
    async def clearwarnings(self, ctx: commands.Context, miembro: discord.Member):
        await db.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, miembro.id))
        await db.add_mod_log(ctx.guild.id, miembro.id, ctx.author.id, "ClearWarnings", "Se borraron todas las advertencias previas.")
        await ctx.send(f"✅ Todas las advertencias de **{miembro.display_name}** han sido borradas.", ephemeral=True)

    # --- COMANDOS DE AUTOMODERACIÓN ---

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