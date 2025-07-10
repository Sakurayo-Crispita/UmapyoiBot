import discord
from discord.ext import commands
from typing import Optional, Literal

class ModerationCog(commands.Cog, name="Moderación"):
    """Comandos para mantener el orden y la seguridad en el servidor."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- COMANDOS BÁSICOS DE MODERACIÓN ---

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

        try:
            await miembro.send(f"Has sido expulsado de **{ctx.guild.name}** por la siguiente razón: {razon}")
        except discord.Forbidden:
            pass # El usuario no permite DMs

        await miembro.kick(reason=f"{razon} (Moderador: {ctx.author.name})")
        await ctx.send(f"✅ **{miembro.display_name}** ha sido expulsado del servidor.", ephemeral=True)

    @commands.hybrid_command(name="ban", description="Banea a un miembro del servidor.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, miembro: discord.Member, *, razon: str = "No se especificó una razón."):
        if miembro == ctx.author:
            return await ctx.send("❌ No puedes banearte a ti mismo.", ephemeral=True)
        if miembro.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("❌ No puedes banear a alguien con un rol igual o superior al tuyo.", ephemeral=True)

        try:
            await miembro.send(f"Has sido baneado permanentemente de **{ctx.guild.name}** por la siguiente razón: {razon}")
        except discord.Forbidden:
            pass

        await miembro.ban(reason=f"{razon} (Moderador: {ctx.author.name})")
        await ctx.send(f"✅ **{miembro.display_name}** ha sido baneado permanentemente.", ephemeral=True)

    @commands.hybrid_command(name="unban", description="Desbanea a un usuario del servidor.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, usuario_id: str, *, razon: str = "No se especificó una razón."):
        try:
            user_id = int(usuario_id)
            user = await self.bot.fetch_user(user_id)
        except (ValueError, discord.NotFound):
            return await ctx.send("❌ No se encontró a un usuario con esa ID.", ephemeral=True)

        try:
            await ctx.guild.unban(user, reason=f"{razon} (Moderador: {ctx.author.name})")
            await ctx.send(f"✅ **{user.name}** ha sido desbaneado.", ephemeral=True)
        except discord.NotFound:
            await ctx.send("❌ Este usuario no se encuentra en la lista de baneados.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ No tengo los permisos para desbanear a este usuario.", ephemeral=True)
            
    # --- COMANDOS DE AUTOMODERACIÓN (CORREGIDOS) ---

    @commands.hybrid_group(name="automod", description="Configura las opciones de auto-moderación.")
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None: 
            await ctx.send("Comando inválido. Usa `/automod anti-invites` o `/automod badwords`.", ephemeral=True)

    @automod.command(name="anti_invites", description="Activa o desactiva el borrado de invitaciones de Discord.")
    @commands.has_permissions(manage_guild=True) # <-- PERMISO AÑADIDO
    async def anti_invites(self, ctx: commands.Context, estado: Literal['on', 'off']):
        config_cog = self.bot.get_cog("Configuración del Servidor")
        if not config_cog: return await ctx.send("Error interno: no se pudo acceder a la configuración.", ephemeral=True)
        
        await config_cog.save_setting(ctx.guild.id, 'automod_anti_invite', 1 if estado == 'on' else 0)
        await ctx.send(f"✅ Filtro anti-invitaciones **{estado}**.", ephemeral=True)

    @automod.group(name="badwords", description="Gestiona la lista de palabras prohibidas.")
    @commands.has_permissions(manage_guild=True) # <-- PERMISO AÑADIDO
    async def badwords(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None: 
            await ctx.send("Comando inválido. Usa `/automod badwords add/remove/list`.", ephemeral=True)

    @badwords.command(name="add", description="Añade una palabra a la lista de prohibidas.")
    @commands.has_permissions(manage_guild=True) # <-- PERMISO AÑADIDO
    async def badwords_add(self, ctx: commands.Context, palabra: str):
        config_cog = self.bot.get_cog("Configuración del Servidor")
        if not config_cog: return await ctx.send("Error interno: no se pudo acceder a la configuración.", ephemeral=True)

        settings = await config_cog.get_settings(ctx.guild.id)
        current_words_str = settings['automod_banned_words'] if settings and settings['automod_banned_words'] else ""
        current_words = set(current_words_str.lower().split(','))
        current_words.add(palabra.lower())
        
        await config_cog.save_setting(ctx.guild.id, 'automod_banned_words', ",".join(filter(None, current_words)))
        await ctx.send(f"✅ Palabra `{palabra}` añadida.", ephemeral=True)

    @badwords.command(name="remove", description="Quita una palabra de la lista de prohibidas.")
    @commands.has_permissions(manage_guild=True) # <-- PERMISO AÑADIDO
    async def badwords_remove(self, ctx: commands.Context, palabra: str):
        config_cog = self.bot.get_cog("Configuración del Servidor")
        if not config_cog: return await ctx.send("Error interno: no se pudo acceder a la configuración.", ephemeral=True)
        
        settings = await config_cog.get_settings(ctx.guild.id)
        word_list_str = settings['automod_banned_words'] if settings and settings['automod_banned_words'] else ""
        word_list = word_list_str.lower().split(',')
        
        if palabra.lower() in word_list:
            word_list.remove(palabra.lower())
            await config_cog.save_setting(ctx.guild.id, 'automod_banned_words', ",".join(filter(None, word_list)))
            await ctx.send(f"✅ Palabra `{palabra}` eliminada.", ephemeral=True)
        else: 
            await ctx.send(f"⚠️ La palabra `{palabra}` no estaba en la lista.", ephemeral=True)

    @badwords.command(name="list", description="Muestra la lista de palabras prohibidas.")
    @commands.has_permissions(manage_guild=True) # <-- PERMISO AÑADIDO
    async def badwords_list(self, ctx: commands.Context):
        config_cog = self.bot.get_cog("Configuración del Servidor")
        if not config_cog: return await ctx.send("Error interno: no se pudo acceder a la configuración.", ephemeral=True)
        
        settings = await config_cog.get_settings(ctx.guild.id)
        words = settings['automod_banned_words'] if settings and settings['automod_banned_words'] else "La lista está vacía."
        await ctx.send(f"**Lista de palabras prohibidas:**\n`{words}`", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
