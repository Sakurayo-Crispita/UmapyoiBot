import discord
from discord.ext import commands
import sqlite3
import random
import asyncio
from typing import Optional

class LevelingCog(commands.Cog, name="Niveles"):
    """Comandos para ver tu nivel y competir en el ranking de XP."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_file = bot.db_file

    # --- FUNCIONES SÍNCRONAS ---
    def _get_user_level_sync(self, guild_id: int, user_id: int) -> tuple[int, int]:
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT level, xp FROM levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
            if result := cursor.fetchone():
                return result['level'], result['xp']
            else:
                cursor.execute("INSERT INTO levels (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
                conn.commit()
                return 1, 0

    def _update_user_xp_sync(self, guild_id: int, user_id: int, level: int, xp: int):
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE levels SET level = ?, xp = ? WHERE guild_id = ? AND user_id = ?", (level, xp, guild_id, user_id))
            conn.commit()

    def _get_role_reward_sync(self, guild_id: int, new_level: int) -> Optional[sqlite3.Row]:
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT role_id FROM role_rewards WHERE guild_id = ? AND level = ?", (guild_id, new_level))
            return cursor.fetchone()

    def _db_execute_commit(self, query: str, params: tuple):
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()

    def _get_levelboard_sync(self, guild_id: int) -> list[sqlite3.Row]:
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, level, xp FROM levels WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10", (guild_id,))
            return cursor.fetchall()
        
    def _get_role_rewards_list_sync(self, guild_id: int) -> list[sqlite3.Row]:
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT level, role_id FROM role_rewards WHERE guild_id = ? ORDER BY level ASC", (guild_id,))
            return cursor.fetchall()

    # --- WRAPPERS ASÍNCRONOS ---
    async def get_user_level(self, guild_id: int, user_id: int) -> tuple[int, int]:
        return await asyncio.to_thread(self._get_user_level_sync, guild_id, user_id)

    async def update_user_xp(self, guild_id: int, user_id: int, level: int, xp: int):
        await asyncio.to_thread(self._update_user_xp_sync, guild_id, user_id, level, xp)

    async def check_role_rewards(self, member: discord.Member, new_level: int) -> Optional[discord.Role]:
        result = await asyncio.to_thread(self._get_role_reward_sync, member.guild.id, new_level)
        if result and (role := member.guild.get_role(result['role_id'])):
            try:
                await member.add_roles(role)
                return role
            except discord.Forbidden:
                print(f"No tengo permisos para dar el rol {role.name} en {member.guild.name}")
        return None
    
    async def db_execute(self, query: str, params: tuple = ()):
        await asyncio.to_thread(self._db_execute_commit, query, params)
        
    async def get_levelboard(self, guild_id: int) -> list[sqlite3.Row]:
        return await asyncio.to_thread(self._get_levelboard_sync, guild_id)

    async def get_role_rewards_list(self, guild_id: int) -> list[sqlite3.Row]:
        return await asyncio.to_thread(self._get_role_rewards_list_sync, guild_id)

    # --- LISTENERS Y COMANDOS ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        config_cog = self.bot.get_cog("Configuración del Servidor")
        if not config_cog: return
        settings = await config_cog.get_settings(message.guild.id)
        if settings and settings["leveling_enabled"]:
            await self.process_xp(message)

    async def process_xp(self, message: discord.Message):
        guild_id, user_id = message.guild.id, message.author.id
        level, xp = await self.get_user_level(guild_id, user_id)
        new_xp = xp + random.randint(15, 25)
        xp_needed = 5 * (level ** 2) + 50 * level + 100

        if new_xp >= xp_needed:
            new_level = level + 1
            await self.update_user_xp(guild_id, user_id, new_level, new_xp - xp_needed)
            msg = f"🎉 ¡Felicidades {message.author.mention}, has subido al **nivel {new_level}**!"
            if reward_role := await self.check_role_rewards(message.author, new_level):
                msg += f"\n🎁 ¡Has ganado el rol {reward_role.mention}!"
            try:
                await message.channel.send(msg)
            except discord.Forbidden:
                pass
        else:
            await self.update_user_xp(guild_id, user_id, level, new_xp)

    @commands.hybrid_command(name='rank', description="Muestra tu nivel y XP en este servidor.")
    async def rank(self, ctx: commands.Context, miembro: discord.Member | None = None):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        await ctx.defer()
        target = miembro or ctx.author
        level, xp = await self.get_user_level(ctx.guild.id, target.id)
        xp_needed = 5 * (level ** 2) + 50 * level + 100
        progress = int((xp / xp_needed) * 20) if xp_needed > 0 else 0
        progress_bar = '🟩' * progress + '⬛' * (20 - progress)
        embed = discord.Embed(title=f"Estadísticas de Nivel de {target.display_name}", color=target.color, description=f"Rango para el servidor **{ctx.guild.name}**")
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Nivel", value=f"**{level}**", inline=True)
        embed.add_field(name="XP", value=f"**{xp} / {xp_needed}**", inline=True)
        embed.add_field(name="Progreso", value=f"`{progress_bar}`", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='levelboard', aliases=['lb_level'], description="Muestra a los usuarios con más nivel.")
    async def levelboard(self, ctx: commands.Context):
        if not ctx.guild: return await ctx.send("Este comando solo se puede usar en un servidor.")
        await ctx.defer()
        top_users = await self.get_levelboard(ctx.guild.id)
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
        await self.db_execute("REPLACE INTO role_rewards (guild_id, level, role_id) VALUES (?, ?, ?)", (ctx.guild.id, nivel, rol.id))
        await ctx.send(f"✅ ¡Perfecto! El rol {rol.mention} se dará como recompensa al alcanzar el **nivel {nivel}**.")

    @commands.hybrid_command(name='remove_level_role', description="Elimina la recompensa de rol de un nivel.")
    @commands.has_permissions(administrator=True)
    async def remove_level_role(self, ctx: commands.Context, nivel: int):
        if not ctx.guild: return
        await self.db_execute("DELETE FROM role_rewards WHERE guild_id = ? AND level = ?", (ctx.guild.id, nivel))
        await ctx.send(f"🗑️ Se ha eliminado la recompensa de rol para el **nivel {nivel}**.")

    @commands.hybrid_command(name='list_level_roles', description="Muestra todas las recompensas de roles configuradas.")
    async def list_level_roles(self, ctx: commands.Context):
        if not ctx.guild: return
        await ctx.defer()
        rewards = await self.get_role_rewards_list(ctx.guild.id)
        if not rewards: return await ctx.send("No hay recompensas de roles configuradas.")
        embed = discord.Embed(title=f"🎁 Recompensas de Roles de {ctx.guild.name}", color=self.bot.CREAM_COLOR)
        description = "\n".join([f"**Nivel {r['level']}** → {(ctx.guild.get_role(r['role_id']).mention if ctx.guild.get_role(r['role_id']) else 'Rol no encontrado')}" for r in rewards])
        embed.description = description
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='reset_level', description="Reinicia el nivel de un usuario.")
    @commands.has_permissions(administrator=True)
    async def reset_level(self, ctx: commands.Context, miembro: discord.Member):
        if not ctx.guild: return
        await self.update_user_xp(ctx.guild.id, miembro.id, 1, 0)
        await ctx.send(f"🔄 El nivel de {miembro.mention} ha sido reiniciado.")

    @commands.hybrid_command(name='give_xp', description="Otorga XP a un usuario.")
    @commands.has_permissions(administrator=True)
    async def give_xp(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        if not ctx.guild: return
        level, xp = await self.get_user_level(ctx.guild.id, miembro.id)
        await self.update_user_xp(ctx.guild.id, miembro.id, level, xp + cantidad)
        await ctx.send(f"✨ Se han añadido **{cantidad} XP** a {miembro.mention}.")

async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingCog(bot))