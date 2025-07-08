import discord
from discord.ext import commands
import sqlite3
import random
import asyncio

class LevelingCog(commands.Cog, name="Niveles"):
    """Comandos para ver tu nivel y competir en el ranking de XP."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn = bot.db_conn
        self.cursor = self.conn.cursor()
        self.db_lock = bot.db_lock
        self.setup_database()

    def setup_database(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS levels (guild_id INTEGER, user_id INTEGER, level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS role_rewards (guild_id INTEGER, level INTEGER, role_id INTEGER, PRIMARY KEY (guild_id, level))''')
        self.conn.commit()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        config_cog = self.bot.get_cog("Configuración del Servidor")
        if not config_cog: return
        settings = await config_cog.get_settings(message.guild.id)
        if settings and settings.get("leveling_enabled", 1):
            await self.process_xp(message)

    async def get_user_level(self, guild_id: int, user_id: int):
        async with self.db_lock:
            self.cursor.execute("SELECT level, xp FROM levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
            if result := self.cursor.fetchone(): return result['level'], result['xp']
            else:
                self.cursor.execute("INSERT INTO levels (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id)); self.conn.commit()
                return 1, 0

    async def update_user_xp(self, guild_id: int, user_id: int, level: int, xp: int):
        async with self.db_lock:
            self.cursor.execute("UPDATE levels SET level = ?, xp = ? WHERE guild_id = ? AND user_id = ?", (level, xp, guild_id, user_id)); self.conn.commit()

    async def check_role_rewards(self, member: discord.Member, new_level: int):
        async with self.db_lock:
            self.cursor.execute("SELECT role_id FROM role_rewards WHERE guild_id = ? AND level = ?", (member.guild.id, new_level))
            result = self.cursor.fetchone()
        if result and (role := member.guild.get_role(result['role_id'])):
            try: await member.add_roles(role); return role
            except discord.Forbidden: print(f"No tengo permisos para dar el rol {role.name} en {member.guild.name}")
        return None

    async def process_xp(self, message: discord.Message):
        guild_id, user_id = message.guild.id, message.author.id
        level, xp = await self.get_user_level(guild_id, user_id)
        new_xp = xp + random.randint(15, 25)
        xp_needed = 5 * (level ** 2) + 50 * level + 100
        if new_xp >= xp_needed:
            new_level = level + 1
            await self.update_user_xp(guild_id, user_id, new_level, new_xp - xp_needed)
            msg = f"🎉 ¡Felicidades {message.author.mention}, has subido al **nivel {new_level}**!"
            if reward_role := await self.check_role_rewards(message.author, new_level): msg += f"\n🎁 ¡Has ganado el rol {reward_role.mention}!"
            try: await message.channel.send(msg)
            except discord.Forbidden: pass
        else: await self.update_user_xp(guild_id, user_id, level, new_xp)

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
        async with self.db_lock:
            self.cursor.execute("SELECT user_id, level, xp FROM levels WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10", (ctx.guild.id,))
            top_users = self.cursor.fetchall()
        if not top_users: return await ctx.send("Nadie tiene nivel en este servidor todavía.")
        embed = discord.Embed(title=f"🏆 Ranking de Niveles de {ctx.guild.name} 🏆", color=discord.Color.gold())
        description = ""
        for i, user_row in enumerate(top_users):
            try: user = await self.bot.fetch_user(user_row['user_id']); name = user.display_name
            except discord.NotFound: name = f"Usuario Desconocido ({user_row['user_id']})"
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`{i+1}.`"
            description += f"{rank} **{name}**: Nivel {user_row['level']} ({user_row['xp']} XP)\n"
        embed.description = description
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='set_level_role', description="Asigna un rol como recompensa por alcanzar un nivel.")
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def set_level_role(self, ctx: commands.Context, nivel: int, rol: discord.Role):
        if not ctx.guild: return
        async with self.db_lock:
            self.cursor.execute("REPLACE INTO role_rewards (guild_id, level, role_id) VALUES (?, ?, ?)", (ctx.guild.id, nivel, rol.id)); self.conn.commit()
        await ctx.send(f"✅ ¡Perfecto! El rol {rol.mention} se dará como recompensa al alcanzar el **nivel {nivel}**.")

    @commands.hybrid_command(name='remove_level_role', description="Elimina la recompensa de rol de un nivel.")
    @commands.has_permissions(administrator=True)
    async def remove_level_role(self, ctx: commands.Context, nivel: int):
        if not ctx.guild: return
        async with self.db_lock:
            self.cursor.execute("DELETE FROM role_rewards WHERE guild_id = ? AND level = ?", (ctx.guild.id, nivel)); self.conn.commit()
        await ctx.send(f"🗑️ Se ha eliminado la recompensa de rol para el **nivel {nivel}**.")

    @commands.hybrid_command(name='list_level_roles', description="Muestra todas las recompensas de roles configuradas.")
    async def list_level_roles(self, ctx: commands.Context):
        if not ctx.guild: return
        await ctx.defer()
        async with self.db_lock:
            self.cursor.execute("SELECT level, role_id FROM role_rewards WHERE guild_id = ? ORDER BY level ASC", (ctx.guild.id,))
            rewards = self.cursor.fetchall()
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