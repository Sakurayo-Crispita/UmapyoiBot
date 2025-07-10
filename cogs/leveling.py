import discord
from discord.ext import commands
import random
import asyncio
from typing import Optional

# Importamos el gestor de base de datos
from utils import database_manager as db

class LevelingCog(commands.Cog, name="Niveles"):
    """Comandos para ver tu nivel y competir en el ranking de XP."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Las funciones de base de datos se han eliminado de aquí ---

    async def check_role_rewards(self, member: discord.Member, new_level: int) -> Optional[discord.Role]:
        """Comprueba y asigna recompensas de rol al subir de nivel."""
        # Usamos el gestor de DB
        result = await db.fetchone("SELECT role_id FROM role_rewards WHERE guild_id = ? AND level = ?", (member.guild.id, new_level))
        if result and (role := member.guild.get_role(result['role_id'])):
            try:
                await member.add_roles(role)
                return role
            except discord.Forbidden:
                print(f"No tengo permisos para dar el rol {role.name} en {member.guild.name}")
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Obtenemos la configuración del servidor a través del gestor de DB
        config_settings = await db.fetchone("SELECT leveling_enabled FROM server_settings WHERE guild_id = ?", (message.guild.id,))
        if config_settings and config_settings["leveling_enabled"]:
            await self.process_xp(message)

    async def process_xp(self, message: discord.Message):
        """Procesa la ganancia de XP de un usuario."""
        guild_id, user_id = message.guild.id, message.author.id
        
        level, xp = await db.get_user_level(guild_id, user_id)
        
        new_xp = xp + random.randint(15, 25)
        xp_needed = 5 * (level ** 2) + 50 * level + 100

        if new_xp >= xp_needed:
            new_level = level + 1
            await db.update_user_xp(guild_id, user_id, new_level, new_xp - xp_needed)
            msg = f"🎉 ¡Felicidades {message.author.mention}, has subido al **nivel {new_level}**!"
            if reward_role := await self.check_role_rewards(message.author, new_level):
                msg += f"\n🎁 ¡Has ganado el rol {reward_role.mention}!"
            try:
                await message.channel.send(msg)
            except discord.Forbidden:
                pass
        else:
            await db.update_user_xp(guild_id, user_id, level, new_xp)

    @commands.hybrid_command(name='rank', description="Muestra tu nivel y XP en este servidor.")
    async def rank(self, ctx: commands.Context, miembro: discord.Member | None = None):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        await ctx.defer()
        target = miembro or ctx.author
        
        level, xp = await db.get_user_level(ctx.guild.id, target.id)
        
        xp_needed = 5 * (level ** 2) + 50 * level + 100
        progress = int((xp / xp_needed) * 20) if xp_needed > 0 else 0
        progress_bar = '🟩' * progress + '⬛' * (20 - progress)
        
        embed = discord.Embed(title=f"Estadísticas de Nivel de {target.display_name}", color=target.color)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Nivel", value=f"**{level}**", inline=True)
        embed.add_field(name="XP", value=f"**{xp} / {xp_needed}**", inline=True)
        embed.add_field(name="Progreso", value=f"`{progress_bar}`", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='levelboard', aliases=['lb_level'], description="Muestra a los usuarios con más nivel.")
    async def levelboard(self, ctx: commands.Context):
        if not ctx.guild: return
        await ctx.defer()
        
        top_users = await db.fetchall("SELECT user_id, level, xp FROM levels WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10", (ctx.guild.id,))
        
        if not top_users: return await ctx.send("Nadie tiene nivel en este servidor todavía.")
        
        embed = discord.Embed(title=f"🏆 Ranking de Niveles de {ctx.guild.name} 🏆", color=discord.Color.gold())
        description = ""
        for i, user_row in enumerate(top_users):
            try:
                user = await self.bot.fetch_user(user_row['user_id'])
                name = user.display_name
            except discord.NotFound:
                name = f"Usuario Desconocido ({user_row['user_id']})"
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`{i+1}.`"
            description += f"{rank} **{name}**: Nivel {user_row['level']} ({user_row['xp']} XP)\n"
        embed.description = description
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='set_level_role', description="Asigna un rol como recompensa por alcanzar un nivel.")
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def set_level_role(self, ctx: commands.Context, nivel: int, rol: discord.Role):
        if not ctx.guild: return
        await db.execute("REPLACE INTO role_rewards (guild_id, level, role_id) VALUES (?, ?, ?)", (ctx.guild.id, nivel, rol.id))
        await ctx.send(f"✅ ¡Perfecto! El rol {rol.mention} se dará como recompensa al alcanzar el **nivel {nivel}**.", ephemeral=True)

    @commands.hybrid_command(name='remove_level_role', description="Elimina la recompensa de rol de un nivel.")
    @commands.has_permissions(administrator=True)
    async def remove_level_role(self, ctx: commands.Context, nivel: int):
        if not ctx.guild: return
        await db.execute("DELETE FROM role_rewards WHERE guild_id = ? AND level = ?", (ctx.guild.id, nivel))
        await ctx.send(f"🗑️ Se ha eliminado la recompensa de rol para el **nivel {nivel}**.", ephemeral=True)

    @commands.hybrid_command(name='list_level_roles', description="Muestra todas las recompensas de roles configuradas.")
    async def list_level_roles(self, ctx: commands.Context):
        if not ctx.guild: return
        await ctx.defer()
        rewards = await db.fetchall("SELECT level, role_id FROM role_rewards WHERE guild_id = ? ORDER BY level ASC", (ctx.guild.id,))
        if not rewards: return await ctx.send("No hay recompensas de roles configuradas.")
        embed = discord.Embed(title=f"🎁 Recompensas de Roles de {ctx.guild.name}", color=self.bot.CREAM_COLOR)
        description = "\n".join([f"**Nivel {r['level']}** → {(ctx.guild.get_role(r['role_id']).mention if ctx.guild.get_role(r['role_id']) else 'Rol no encontrado')}" for r in rewards])
        embed.description = description
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='reset_level', description="Reinicia el nivel de un usuario.")
    @commands.has_permissions(administrator=True)
    async def reset_level(self, ctx: commands.Context, miembro: discord.Member):
        if not ctx.guild: return
        await db.update_user_xp(ctx.guild.id, miembro.id, 1, 0)
        await ctx.send(f"🔄 El nivel de {miembro.mention} ha sido reiniciado.", ephemeral=True)

    @commands.hybrid_command(name='give_xp', description="Otorga XP a un usuario.")
    @commands.has_permissions(administrator=True)
    async def give_xp(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        if not ctx.guild: return
        level, xp = await db.get_user_level(ctx.guild.id, miembro.id)
        await db.update_user_xp(ctx.guild.id, miembro.id, level, xp + cantidad)
        await ctx.send(f"✨ Se han añadido **{cantidad} XP** a {miembro.mention}.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingCog(bot))