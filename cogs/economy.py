import discord
from discord.ext import commands
import random, sqlite3, datetime
from typing import Literal

class EconomyCog(commands.Cog, name="Economía"):
    """Sistema de economía configurable por servidor."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn = bot.db_conn
        self.cursor = self.conn.cursor()
        self.db_lock = bot.db_lock
        self._work_cd = commands.CooldownMapping.from_cooldown(1, 3600, commands.BucketType.user)
        self._rob_cd = commands.CooldownMapping.from_cooldown(1, 21600, commands.BucketType.user)
        self.setup_database()

    def setup_database(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS balances (guild_id INTEGER, user_id INTEGER, wallet INTEGER DEFAULT 0, bank INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS economy_settings (guild_id INTEGER PRIMARY KEY, currency_name TEXT DEFAULT 'créditos', currency_emoji TEXT DEFAULT '🪙', start_balance INTEGER DEFAULT 100, max_balance INTEGER, log_channel_id INTEGER, daily_min INTEGER DEFAULT 100, daily_max INTEGER DEFAULT 500, work_min INTEGER DEFAULT 50, work_max INTEGER DEFAULT 250, work_cooldown INTEGER DEFAULT 3600, rob_cooldown INTEGER DEFAULT 21600)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS economy_active_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))''')
        try: self.cursor.execute("ALTER TABLE economy_settings ADD COLUMN max_balance INTEGER")
        except: pass
        try: self.cursor.execute("ALTER TABLE economy_settings ADD COLUMN daily_min INTEGER DEFAULT 100")
        except: pass
        try: self.cursor.execute("ALTER TABLE economy_settings ADD COLUMN daily_max INTEGER DEFAULT 500")
        except: pass
        try: self.cursor.execute("ALTER TABLE economy_settings ADD COLUMN work_min INTEGER DEFAULT 50")
        except: pass
        try: self.cursor.execute("ALTER TABLE economy_settings ADD COLUMN work_max INTEGER DEFAULT 250")
        except: pass
        try: self.cursor.execute("ALTER TABLE economy_settings ADD COLUMN work_cooldown INTEGER DEFAULT 3600")
        except: pass
        try: self.cursor.execute("ALTER TABLE economy_settings ADD COLUMN rob_cooldown INTEGER DEFAULT 21600")
        except: pass
        self.conn.commit()

    async def get_guild_settings(self, guild_id: int) -> sqlite3.Row:
        async with self.db_lock:
            self.cursor.execute("SELECT * FROM economy_settings WHERE guild_id = ?", (guild_id,))
            if not (settings := self.cursor.fetchone()):
                self.cursor.execute("INSERT INTO economy_settings (guild_id) VALUES (?)", (guild_id,)); self.conn.commit()
                self.cursor.execute("SELECT * FROM economy_settings WHERE guild_id = ?", (guild_id,)); settings = self.cursor.fetchone()
            return settings
            
    async def get_active_channels(self, guild_id: int) -> list[int]:
        async with self.db_lock:
            self.cursor.execute("SELECT channel_id FROM economy_active_channels WHERE guild_id = ?", (guild_id,)); return [r['channel_id'] for r in self.cursor.fetchall()]

    async def is_economy_active(self, ctx: commands.Context) -> bool:
        if not ctx.guild: return False
        active_channels = await self.get_active_channels(ctx.guild.id)
        if not active_channels:
            if not ctx.author.guild_permissions.manage_guild: await ctx.send("La economía no está activada en ningún canal. Un admin debe usar `/economy addchannel`.", ephemeral=True, delete_after=10); return False
        if ctx.channel.id not in active_channels and not ctx.author.guild_permissions.manage_guild:
             await ctx.send("Los comandos de economía no están permitidos aquí.", ephemeral=True, delete_after=10); return False
        return True

    async def log_transaction(self, guild: discord.Guild, author: discord.Member, message: str):
        settings = await self.get_guild_settings(guild.id)
        if log_channel_id := settings.get('log_channel_id'):
            if channel := guild.get_channel(log_channel_id):
                embed = discord.Embed(description=message, color=self.bot.CREAM_COLOR, timestamp=datetime.datetime.now())
                embed.set_author(name=f"Auditoría Económica | {author.display_name}", icon_url=author.display_avatar.url)
                try: await channel.send(embed=embed)
                except discord.Forbidden: pass

    async def get_balance(self, guild_id: int, user_id: int) -> tuple[int, int]:
        async with self.db_lock:
            self.cursor.execute("SELECT wallet, bank FROM balances WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
            if result := self.cursor.fetchone(): return result['wallet'], result['bank']
            else:
                settings = await self.get_guild_settings(guild_id)
                start_balance = settings['start_balance']
                self.cursor.execute("INSERT INTO balances (guild_id, user_id, wallet, bank) VALUES (?, ?, ?, 0)", (guild_id, user_id, start_balance)); self.conn.commit()
                return start_balance, 0

    async def update_balance(self, guild_id: int, user_id: int, wallet_change: int=0, bank_change: int=0) -> tuple[int, int]:
        async with self.db_lock:
            wallet, bank = await self.get_balance(guild_id, user_id)
            settings = await self.get_guild_settings(guild_id)
            new_wallet = wallet + wallet_change
            if settings['max_balance'] is not None: new_wallet = min(new_wallet, settings['max_balance'])
            new_bank = bank + bank_change
            self.cursor.execute("REPLACE INTO balances (guild_id, user_id, wallet, bank) VALUES (?, ?, ?, ?)", (guild_id, user_id, new_wallet, new_bank)); self.conn.commit()
            return new_wallet, new_bank

    @commands.hybrid_group(name="economy", description="Comandos para configurar la economía del servidor.")
    @commands.has_permissions(administrator=True)
    async def economy(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            settings = await self.get_guild_settings(ctx.guild.id); active_channels = await self.get_active_channels(ctx.guild.id)
            channels = "\n".join([f"<#{cid}>" for cid in active_channels]) if active_channels else "Ninguno"
            max_bal = f"{settings['max_balance']}" if settings['max_balance'] is not None else "Sin límite"
            embed = discord.Embed(title="⚙️ Estado de la Economía", color=self.bot.CREAM_COLOR, description="Usa los subcomandos para configurar el sistema.")
            embed.add_field(name="Canales Activos", value=channels, inline=False)
            embed.add_field(name="Moneda", value=f"{settings['currency_name']} {settings['currency_emoji']}", inline=True)
            embed.add_field(name="Saldo Inicial", value=f"{settings['start_balance']}", inline=True)
            embed.add_field(name="Saldo Máximo", value=max_bal, inline=True)
            await ctx.send(embed=embed, ephemeral=True)

    @economy.command(name="addchannel", description="Activa los comandos de economía en un canal.")
    @commands.has_permissions(administrator=True)
    async def add_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        async with self.db_lock: self.cursor.execute("INSERT OR IGNORE INTO economy_active_channels (guild_id, channel_id) VALUES (?, ?)", (ctx.guild.id, canal.id)); self.conn.commit()
        await ctx.send(f"✅ La economía ha sido **activada** en {canal.mention}.", ephemeral=True)

    @economy.command(name="removechannel", description="Desactiva los comandos de economía en un canal.")
    @commands.has_permissions(administrator=True)
    async def remove_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        async with self.db_lock: self.cursor.execute("DELETE FROM economy_active_channels WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, canal.id)); self.conn.commit()
        await ctx.send(f"❌ La economía ha sido **desactivada** en {canal.mention}.", ephemeral=True)

    @economy.command(name="setstartbalance", description="Establece el saldo inicial para los nuevos miembros.")
    @commands.has_permissions(administrator=True)
    async def set_start_balance(self, ctx: commands.Context, cantidad: int):
        if cantidad < 0: return await ctx.send("El saldo no puede ser negativo.", ephemeral=True)
        async with self.db_lock: self.cursor.execute("UPDATE economy_settings SET start_balance = ? WHERE guild_id = ?", (cantidad, ctx.guild.id)); self.conn.commit()
        await ctx.send(f"✅ El saldo inicial para nuevos miembros ahora es **{cantidad}**.", ephemeral=True)

    @economy.command(name="setmaxbalance", description="Establece un límite de dinero en la cartera.")
    @commands.has_permissions(administrator=True)
    async def set_max_balance(self, ctx: commands.Context, cantidad: int):
        if cantidad <= 0: return await ctx.send("La cantidad debe ser positiva.", ephemeral=True)
        async with self.db_lock: self.cursor.execute("UPDATE economy_settings SET max_balance = ? WHERE guild_id = ?", (cantidad, ctx.guild.id)); self.conn.commit()
        await ctx.send(f"✅ El límite de dinero en cartera se ha fijado en **{cantidad}**.", ephemeral=True)

    @economy.command(name="setauditlog", description="Designa un canal para registrar transacciones importantes.")
    @commands.has_permissions(administrator=True)
    async def set_audit_log(self, ctx: commands.Context, canal: discord.TextChannel):
        async with self.db_lock: self.cursor.execute("UPDATE economy_settings SET log_channel_id = ? WHERE guild_id = ?", (canal.id, ctx.guild.id)); self.conn.commit()
        await ctx.send(f"✅ El canal de auditoría económica ahora es {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name="add-money", description="Añade dinero a la cartera de un usuario.")
    @commands.has_permissions(manage_guild=True)
    async def add_money(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        if cantidad <= 0: return await ctx.send("La cantidad debe ser positiva.", ephemeral=True)
        await self.update_balance(ctx.guild.id, miembro.id, wallet_change=cantidad)
        await ctx.send(f"✅ Se han añadido **{cantidad}** a la cartera de {miembro.mention}.", ephemeral=True)
        await self.log_transaction(ctx.guild, ctx.author, f"Añadió **{cantidad}** a la cartera de {miembro.mention} (`{miembro.id}`).")

    @commands.hybrid_command(name="remove-money", description="Quita dinero de la cartera de un usuario.")
    @commands.has_permissions(manage_guild=True)
    async def remove_money(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        if cantidad <= 0: return await ctx.send("La cantidad debe ser positiva.", ephemeral=True)
        await self.update_balance(ctx.guild.id, miembro.id, wallet_change=-cantidad)
        await ctx.send(f"✅ Se han quitado **{cantidad}** de la cartera de {miembro.mention}.", ephemeral=True)
        await self.log_transaction(ctx.guild, ctx.author, f"Quitó **{cantidad}** de la cartera de {miembro.mention} (`{miembro.id}`).")

    @commands.hybrid_command(name="reset-economy", description="Reinicia la economía del servidor (ACCIÓN PELIGROSA).")
    @commands.has_permissions(administrator=True)
    async def reset_economy(self, ctx: commands.Context):
        async with self.db_lock: self.cursor.execute("DELETE FROM balances WHERE guild_id = ?", (ctx.guild.id,)); self.conn.commit()
        await ctx.send("💥 **¡La economía del servidor ha sido reiniciada!**", ephemeral=False)
        await self.log_transaction(ctx.guild, ctx.author, "🚨 **REINICIÓ LA ECONOMÍA DEL SERVIDOR.**")

    @commands.hybrid_command(name='deposit', aliases=['dep'], description="Deposita dinero de tu cartera al banco.")
    async def deposit(self, ctx: commands.Context, cantidad: str):
        if not await self.is_economy_active(ctx): return
        wallet, bank = await self.get_balance(ctx.guild.id, ctx.author.id)
        if cantidad.lower() == 'all': amount = wallet
        else:
            try: amount = int(cantidad)
            except ValueError: return await ctx.send("Introduce un número válido o la palabra 'all'.", ephemeral=True)
        if amount <= 0: return await ctx.send("Debes depositar una cantidad positiva.", ephemeral=True)
        if wallet < amount: return await ctx.send(f"No tienes suficiente dinero. Cartera: **{wallet}**.", ephemeral=True)
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-amount, bank_change=amount)
        await ctx.send(f"🏦 Has depositado **{amount}**. Tu banco ahora tiene **{bank + amount}**.", ephemeral=True)

    @commands.hybrid_command(name='withdraw', description="Retira dinero de tu banco a tu cartera.")
    async def withdraw(self, ctx: commands.Context, cantidad: str):
        if not await self.is_economy_active(ctx): return
        _, bank = await self.get_balance(ctx.guild.id, ctx.author.id)
        if cantidad.lower() == 'all': amount = bank
        else:
            try: amount = int(cantidad)
            except ValueError: return await ctx.send("Introduce un número válido o la palabra 'all'.", ephemeral=True)
        if amount <= 0: return await ctx.send("Debes retirar una cantidad positiva.", ephemeral=True)
        if bank < amount: return await ctx.send(f"No tienes suficiente en el banco. Banco: **{bank}**.", ephemeral=True)
        new_wallet, _ = await self.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount, bank_change=-amount)
        await ctx.send(f"💸 Has retirado **{amount}**. Tu cartera ahora tiene **{new_wallet}**.", ephemeral=True)

    @commands.hybrid_command(name='balance', aliases=['bal'], description="Muestra tu balance de cartera y banco.")
    async def balance(self, ctx: commands.Context, miembro: discord.Member | None = None):
        if not await self.is_economy_active(ctx): return
        target = miembro or ctx.author
        settings = await self.get_guild_settings(ctx.guild.id)
        wallet, bank = await self.get_balance(ctx.guild.id, target.id)
        embed = discord.Embed(title=f"{settings['currency_emoji']} Balance de {target.display_name}", color=self.bot.CREAM_COLOR)
        embed.add_field(name="Cartera", value=f"`{wallet}`", inline=True).add_field(name="Banco", value=f"`{bank}`", inline=True).add_field(name="Total", value=f"`{wallet + bank}`", inline=True)
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='daily', description="Reclama tu recompensa diaria en la cartera.")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx: commands.Context):
        if not await self.is_economy_active(ctx): return
        settings = await self.get_guild_settings(ctx.guild.id)
        amount = random.randint(settings['daily_min'], settings['daily_max'])
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount)
        embed = discord.Embed(title=f"{settings['currency_emoji']} Recompensa Diaria", description=f"¡Felicidades! Has reclamado **{amount} {settings['currency_name']}**.", color=discord.Color.gold())
        await ctx.send(embed=embed)
    @daily.error
    async def daily_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandOnCooldown):
            m, s = divmod(error.retry_after, 60); h, m = divmod(m, 60)
            await ctx.send(f"Vuelve en **{int(h)}h {int(m)}m**.", ephemeral=True)

    @commands.hybrid_command(name='work', description="Trabaja para ganar un dinero extra.")
    async def work(self, ctx: commands.Context):
        if not await self.is_economy_active(ctx): return
        settings = await self.get_guild_settings(ctx.guild.id)
        bucket = self._work_cd.get_bucket(ctx.message); bucket.per = settings['work_cooldown']
        if retry_after := bucket.update_rate_limit():
            m, s = divmod(retry_after, 60)
            await ctx.send(f"Descansa y vuelve en **{int(m)}m {int(s)}s**.", ephemeral=True)
            return
        amount = random.randint(settings['work_min'], settings['work_max'])
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount)
        await ctx.send(embed=discord.Embed(title="💼 ¡A trabajar!", description=f"Ganaste **{amount} {settings['currency_name']}**.", color=discord.Color.green()))

    @commands.hybrid_command(name='rob', description="Intenta robarle a otro usuario de su cartera.")
    async def rob(self, ctx: commands.Context, miembro: discord.Member):
        if not await self.is_economy_active(ctx): return
        settings = await self.get_guild_settings(ctx.guild.id)
        bucket = self._rob_cd.get_bucket(ctx.message); bucket.per = settings['rob_cooldown']
        if retry_after := bucket.update_rate_limit():
            h, rem = divmod(retry_after, 3600); m, _ = divmod(rem, 60)
            await ctx.send(f"Acabas de intentar un robo. Espera **{int(h)}h {int(m)}m**.", ephemeral=True)
            return
        if miembro.id == ctx.author.id: return await ctx.send("No te puedes robar a ti mismo.", ephemeral=True)
        if miembro.bot: return await ctx.send("No puedes robarle a los bots.", ephemeral=True)
        robber_wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        victim_wallet, _ = await self.get_balance(ctx.guild.id, miembro.id)
        if victim_wallet < 200: return await ctx.send(f"{miembro.display_name} no tiene suficiente en su cartera.", ephemeral=True)
        if random.random() < 0.5:
            amount = int(victim_wallet * random.uniform(0.1, 0.25))
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount); await self.update_balance(ctx.guild.id, miembro.id, wallet_change=-amount)
            embed = discord.Embed(title="🎭 ¡Robo Exitoso!", description=f"Robaste **{amount}** de la cartera a {miembro.mention}.", color=discord.Color.dark_green())
        else:
            amount = max(50, int(robber_wallet * random.uniform(0.05, 0.15)))
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-amount)
            embed = discord.Embed(title="🚓 ¡Te Pillaron!", description=f"Te vieron venir. Perdiste **{amount}**.", color=discord.Color.dark_red())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='give', description="Transfiere dinero de tu cartera a otro usuario.")
    async def give(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        if not await self.is_economy_active(ctx): return
        settings = await self.get_guild_settings(ctx.guild.id)
        if ctx.author.id == miembro.id: return await ctx.send("No puedes darte dinero a ti mismo.", ephemeral=True)
        if cantidad <= 0: return await ctx.send("La cantidad debe ser positiva.", ephemeral=True)
        sender_wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if sender_wallet < cantidad: return await ctx.send(f"No tienes suficientes {settings['currency_name']}. Tienes: **{sender_wallet}**.", ephemeral=True)
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-cantidad); await self.update_balance(ctx.guild.id, miembro.id, wallet_change=cantidad)
        embed = discord.Embed(title="💸 Transferencia Realizada", description=f"{ctx.author.mention} ha transferido **{cantidad}** a {miembro.mention}.", color=self.bot.CREAM_COLOR)
        await ctx.send(embed=embed); await self.log_transaction(ctx.guild, ctx.author, f"Transfirió **{cantidad}** a {miembro.mention}.")

    @commands.hybrid_command(name='leaderboard', aliases=['lb'], description="Muestra a los usuarios más ricos del servidor.")
    async def leaderboard(self, ctx: commands.Context):
        if not await self.is_economy_active(ctx): return
        settings = await self.get_guild_settings(ctx.guild.id)
        async with self.db_lock:
            self.cursor.execute("SELECT user_id, wallet, bank, (wallet + bank) as total FROM balances WHERE guild_id = ? ORDER BY total DESC LIMIT 10", (ctx.guild.id,))
            top_users = self.cursor.fetchall()
        if not top_users: return await ctx.send(f"Nadie tiene {settings['currency_name']} todavía.")
        embed = discord.Embed(title=f"🏆 Ranking de {settings['currency_name']} 🏆", color=discord.Color.gold())
        description = ""
        for i, row in enumerate(top_users):
            try: user = await self.bot.fetch_user(row['user_id']); name = user.display_name
            except: name = f"Usuario Desconocido ({row['user_id']})"
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`{i+1}.`"
            description += f"{rank} **{name}**: {row['total']} (Cartera: {row['wallet']} / Banco: {row['bank']})\n"
        embed.description = description
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))