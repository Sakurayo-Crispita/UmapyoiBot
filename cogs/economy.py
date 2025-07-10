import discord
from discord.ext import commands
import random
import datetime
from typing import Literal, Optional

# 1. Importamos el gestor de base de datos y le ponemos el apodo "db"
from utils import database_manager as db

class EconomyCog(commands.Cog, name="Economía"):
    """Sistema de economía configurable por servidor."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # El cog ya no necesita saber nada del archivo de la base de datos.
        # Los cooldowns se quedan aquí porque son parte de la lógica de los comandos.
        self._work_cd = commands.CooldownMapping.from_cooldown(1, 3600, commands.BucketType.user)
        self._rob_cd = commands.CooldownMapping.from_cooldown(1, 21600, commands.BucketType.user)

    # --- TODAS LAS FUNCIONES DE BASE DE DATOS (sync y async) HAN SIDO ELIMINADAS DE AQUÍ ---
    # Ahora viven en utils/database_manager.py

    # --- FUNCIONES DE LÓGICA (Se quedan en el cog) ---

    async def is_economy_active(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False

        # Usamos el gestor "db" para obtener los canales
        active_channels_rows = await db.fetchall("SELECT channel_id FROM economy_active_channels WHERE guild_id = ?", (ctx.guild.id,))
        active_channels = [r['channel_id'] for r in active_channels_rows]
        
        if not active_channels:
            if ctx.author.guild_permissions.administrator:
                await ctx.send("La economía no está activada en ningún canal. Un admin debe usar `/economy addchannel`.", ephemeral=True, delete_after=10)
            return False

        if ctx.channel.id not in active_channels:
            if not ctx.author.guild_permissions.manage_guild:
                await ctx.send("Los comandos de economía solo están permitidos en los canales designados.", ephemeral=True, delete_after=10)
            return False
            
        return True

    async def log_transaction(self, guild: discord.Guild, author: discord.Member, message: str):
        # Usamos el gestor "db" para obtener la configuración
        settings = await db.get_guild_economy_settings(guild.id)
        if settings and settings['log_channel_id']:
            if channel := guild.get_channel(settings['log_channel_id']):
                embed = discord.Embed(description=message, color=self.bot.CREAM_COLOR, timestamp=datetime.datetime.now())
                embed.set_author(name=f"Auditoría Económica | {author.display_name}", icon_url=author.display_avatar.url)
                try: await channel.send(embed=embed)
                except discord.Forbidden: pass

    # --- COMANDOS (Modificados para usar "db") ---

    @commands.hybrid_group(name="economy", description="Comandos para configurar la economía del servidor.")
    @commands.has_permissions(administrator=True)
    async def economy(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            # Usamos "db" para obtener la información
            settings = await db.get_guild_economy_settings(ctx.guild.id)
            active_channels_rows = await db.fetchall("SELECT channel_id FROM economy_active_channels WHERE guild_id = ?", (ctx.guild.id,))
            active_channels = [r['channel_id'] for r in active_channels_rows]
            
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
        # Usamos "db.execute" en lugar de "self.db_execute"
        await db.execute("INSERT OR IGNORE INTO economy_active_channels (guild_id, channel_id) VALUES (?, ?)", (ctx.guild.id, canal.id))
        await ctx.send(f"✅ La economía ha sido **activada** en {canal.mention}.", ephemeral=True)

    @economy.command(name="removechannel", description="Desactiva los comandos de economía en un canal.")
    @commands.has_permissions(administrator=True)
    async def remove_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        await db.execute("DELETE FROM economy_active_channels WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, canal.id))
        await ctx.send(f"❌ La economía ha sido **desactivada** en {canal.mention}.", ephemeral=True)

    @economy.command(name="setstartbalance", description="Establece el saldo inicial para los nuevos miembros.")
    @commands.has_permissions(administrator=True)
    async def set_start_balance(self, ctx: commands.Context, cantidad: int):
        if cantidad < 0: return await ctx.send("El saldo no puede ser negativo.", ephemeral=True)
        await db.execute("UPDATE economy_settings SET start_balance = ? WHERE guild_id = ?", (cantidad, ctx.guild.id))
        await ctx.send(f"✅ El saldo inicial para nuevos miembros ahora es **{cantidad}**.", ephemeral=True)

    @economy.command(name="setmaxbalance", description="Establece un límite de dinero en la cartera.")
    @commands.has_permissions(administrator=True)
    async def set_max_balance(self, ctx: commands.Context, cantidad: int):
        if cantidad <= 0: return await ctx.send("La cantidad debe ser positiva.", ephemeral=True)
        await db.execute("UPDATE economy_settings SET max_balance = ? WHERE guild_id = ?", (cantidad, ctx.guild.id))
        await ctx.send(f"✅ El límite de dinero en cartera se ha fijado en **{cantidad}**.", ephemeral=True)

    @economy.command(name="setauditlog", description="Designa un canal para registrar transacciones importantes.")
    @commands.has_permissions(administrator=True)
    async def set_audit_log(self, ctx: commands.Context, canal: discord.TextChannel):
        await db.execute("UPDATE economy_settings SET log_channel_id = ? WHERE guild_id = ?", (canal.id, ctx.guild.id))
        await ctx.send(f"✅ El canal de auditoría económica ahora es {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name="add-money", description="Añade dinero a la cartera de un usuario.")
    @commands.has_permissions(manage_guild=True)
    async def add_money(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        if not await self.is_economy_active(ctx): return
        if cantidad <= 0: return await ctx.send("La cantidad debe ser positiva.", ephemeral=True)
        # Usamos "db.update_balance" en lugar de "self.update_balance"
        await db.update_balance(ctx.guild.id, miembro.id, wallet_change=cantidad)
        await ctx.send(f"✅ Se han añadido **{cantidad}** a la cartera de {miembro.mention}.", ephemeral=True)
        await self.log_transaction(ctx.guild, ctx.author, f"Añadió **{cantidad}** a la cartera de {miembro.mention} (`{miembro.id}`).")

    @commands.hybrid_command(name="remove-money", description="Quita dinero de la cartera de un usuario.")
    @commands.has_permissions(manage_guild=True)
    async def remove_money(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        if not await self.is_economy_active(ctx): return
        if cantidad <= 0: return await ctx.send("La cantidad debe ser positiva.", ephemeral=True)
        await db.update_balance(ctx.guild.id, miembro.id, wallet_change=-cantidad)
        await ctx.send(f"✅ Se han quitado **{cantidad}** de la cartera de {miembro.mention}.", ephemeral=True)
        await self.log_transaction(ctx.guild, ctx.author, f"Quitó **{cantidad}** de la cartera de {miembro.mention} (`{miembro.id}`).")

    @commands.hybrid_command(name="reset-economy", description="Reinicia la economía del servidor (ACCIÓN PELIGROSA).")
    @commands.has_permissions(administrator=True)
    async def reset_economy(self, ctx: commands.Context):
        if not await self.is_economy_active(ctx): return
        await db.execute("DELETE FROM balances WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send("💥 **¡La economía del servidor ha sido reiniciada!**", ephemeral=False)
        await self.log_transaction(ctx.guild, ctx.author, "🚨 **REINICIÓ LA ECONOMÍA DEL SERVIDOR.**")

    @commands.hybrid_command(name='deposit', aliases=['dep'], description="Deposita dinero de tu cartera al banco.")
    async def deposit(self, ctx: commands.Context, cantidad: str):
        if not await self.is_economy_active(ctx): return
        wallet, bank = await db.get_balance(ctx.guild.id, ctx.author.id)
        if cantidad.lower() == 'all': amount = wallet
        else:
            try: amount = int(cantidad)
            except ValueError: return await ctx.send("Introduce un número válido o la palabra 'all'.", ephemeral=True)
        if amount <= 0: return await ctx.send("Debes depositar una cantidad positiva.", ephemeral=True)
        if wallet < amount: return await ctx.send(f"No tienes suficiente dinero. Cartera: **{wallet}**.", ephemeral=True)
        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-amount, bank_change=amount)
        await ctx.send(f"🏦 Has depositado **{amount}**. Tu banco ahora tiene **{bank + amount}**.", ephemeral=True)

    @commands.hybrid_command(name='withdraw', description="Retira dinero de tu banco a tu cartera.")
    async def withdraw(self, ctx: commands.Context, cantidad: str):
        if not await self.is_economy_active(ctx): return
        _, bank = await db.get_balance(ctx.guild.id, ctx.author.id)
        if cantidad.lower() == 'all': amount = bank
        else:
            try: amount = int(cantidad)
            except ValueError: return await ctx.send("Introduce un número válido o la palabra 'all'.", ephemeral=True)
        if amount <= 0: return await ctx.send("Debes retirar una cantidad positiva.", ephemeral=True)
        if bank < amount: return await ctx.send(f"No tienes suficiente en el banco. Banco: **{bank}**.", ephemeral=True)
        new_wallet, _ = await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount, bank_change=-amount)
        await ctx.send(f"💸 Has retirado **{amount}**. Tu cartera ahora tiene **{new_wallet}**.", ephemeral=True)

    @commands.hybrid_command(name='balance', aliases=['bal'], description="Muestra tu balance de cartera y banco.")
    async def balance(self, ctx: commands.Context, miembro: discord.Member | None = None):
        if not await self.is_economy_active(ctx): return
        target = miembro or ctx.author
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        wallet, bank = await db.get_balance(ctx.guild.id, target.id)
        embed = discord.Embed(title=f"{settings['currency_emoji']} Balance de {target.display_name}", color=self.bot.CREAM_COLOR)
        embed.add_field(name="Cartera", value=f"`{wallet}`", inline=True).add_field(name="Banco", value=f"`{bank}`", inline=True).add_field(name="Total", value=f"`{wallet + bank}`", inline=True)
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='daily', description="Reclama tu recompensa diaria en la cartera.")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx: commands.Context):
        if not await self.is_economy_active(ctx): return
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        amount = random.randint(settings['daily_min'], settings['daily_max'])
        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount)
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
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        bucket = self._work_cd.get_bucket(ctx.message); bucket.per = settings['work_cooldown']
        if retry_after := bucket.update_rate_limit():
            m, s = divmod(retry_after, 60)
            await ctx.send(f"Descansa y vuelve en **{int(m)}m {int(s)}s**.", ephemeral=True)
            return
        amount = random.randint(settings['work_min'], settings['work_max'])
        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount)
        await ctx.send(embed=discord.Embed(title="💼 ¡A trabajar!", description=f"Ganaste **{amount} {settings['currency_name']}**.", color=discord.Color.green()))

    @commands.hybrid_command(name='rob', description="Intenta robarle a otro usuario de su cartera.")
    async def rob(self, ctx: commands.Context, miembro: discord.Member):
        if not await self.is_economy_active(ctx): return
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        bucket = self._rob_cd.get_bucket(ctx.message); bucket.per = settings['rob_cooldown']
        if retry_after := bucket.update_rate_limit():
            h, rem = divmod(retry_after, 3600); m, _ = divmod(rem, 60)
            await ctx.send(f"Acabas de intentar un robo. Espera **{int(h)}h {int(m)}m**.", ephemeral=True)
            return
        if miembro.id == ctx.author.id: return await ctx.send("No te puedes robar a ti mismo.", ephemeral=True)
        if miembro.bot: return await ctx.send("No puedes robarle a los bots.", ephemeral=True)
        robber_wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
        victim_wallet, _ = await db.get_balance(ctx.guild.id, miembro.id)
        if victim_wallet < 200: return await ctx.send(f"{miembro.display_name} no tiene suficiente en su cartera.", ephemeral=True)
        if random.random() < 0.5:
            amount = int(victim_wallet * random.uniform(0.1, 0.25))
            await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount); await db.update_balance(ctx.guild.id, miembro.id, wallet_change=-amount)
            embed = discord.Embed(title="🎭 ¡Robo Exitoso!", description=f"Robaste **{amount}** de la cartera a {miembro.mention}.", color=discord.Color.dark_green())
        else:
            amount = max(50, int(robber_wallet * random.uniform(0.05, 0.15)))
            await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-amount)
            embed = discord.Embed(title="🚓 ¡Te Pillaron!", description=f"Te vieron venir. Perdiste **{amount}**.", color=discord.Color.dark_red())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='give', description="Transfiere dinero de tu cartera a otro usuario.")
    async def give(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        if not await self.is_economy_active(ctx): return
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        if ctx.author.id == miembro.id: return await ctx.send("No puedes darte dinero a ti mismo.", ephemeral=True)
        if cantidad <= 0: return await ctx.send("La cantidad debe ser positiva.", ephemeral=True)
        sender_wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
        if sender_wallet < cantidad: return await ctx.send(f"No tienes suficientes {settings['currency_name']}. Tienes: **{sender_wallet}**.", ephemeral=True)
        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-cantidad); await db.update_balance(ctx.guild.id, miembro.id, wallet_change=cantidad)
        embed = discord.Embed(title="💸 Transferencia Realizada", description=f"{ctx.author.mention} ha transferido **{cantidad}** a {miembro.mention}.", color=self.bot.CREAM_COLOR)
        await ctx.send(embed=embed); await self.log_transaction(ctx.guild, ctx.author, f"Transfirió **{cantidad}** a {miembro.mention}.")

    @commands.hybrid_command(name='leaderboard', aliases=['lb'], description="Muestra a los usuarios más ricos del servidor.")
    async def leaderboard(self, ctx: commands.Context):
        if not await self.is_economy_active(ctx): return
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        top_users = await db.fetchall("SELECT user_id, wallet, bank, (wallet + bank) as total FROM balances WHERE guild_id = ? ORDER BY total DESC LIMIT 10", (ctx.guild.id,))
        if not top_users: return await ctx.send(f"Nadie tiene {settings['currency_name']} todavía.")
        embed = discord.Embed(title=f"🏆 Ranking de {settings['currency_name']} 🏆", color=discord.Color.gold())
        description = ""
        for i, row in enumerate(top_users):
            try: 
                user = await self.bot.fetch_user(row['user_id'])
                name = user.display_name
            except: 
                name = f"Usuario Desconocido ({row['user_id']})"
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`{i+1}.`"
            description += f"{rank} **{name}**: {row['total']} (Cartera: {row['wallet']} / Banco: {row['bank']})\n"
        embed.description = description
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))