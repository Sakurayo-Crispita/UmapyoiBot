import discord
from discord.ext import commands
import random
import datetime
from typing import Literal, Optional

# Importamos el gestor de base de datos
from utils import database_manager as db

class EconomyCog(commands.Cog, name="Economía"):
    """Sistema de economía configurable por servidor."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._work_cd = commands.CooldownMapping.from_cooldown(1, 3600, commands.BucketType.user)
        self._rob_cd = commands.CooldownMapping.from_cooldown(1, 21600, commands.BucketType.user)

    async def _send_response(self, ctx: commands.Context, content: str = None, embed: discord.Embed = None, ephemeral: bool = False):
        """Función de ayuda para enviar respuestas de forma segura en comandos híbridos."""
        if ctx.interaction and ctx.interaction.response.is_done():
            await ctx.followup.send(content=content, embed=embed, ephemeral=ephemeral)
        else:
            await ctx.send(content=content, embed=embed, ephemeral=ephemeral)

    async def is_economy_active(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False

        active_channels_rows = await db.fetchall("SELECT channel_id FROM economy_active_channels WHERE guild_id = ?", (ctx.guild.id,))
        active_channels = [r['channel_id'] for r in active_channels_rows]
        
        if not active_channels:
            if ctx.author.guild_permissions.administrator:
                 await self._send_response(ctx, "La economía no está activada en ningún canal. Un admin debe usar `/economy addchannel`.", ephemeral=True)
            return False

        if ctx.channel.id not in active_channels:
            if not ctx.author.guild_permissions.manage_guild:
                await self._send_response(ctx, "Los comandos de economía solo están permitidos en los canales designados.", ephemeral=True)
            return False
            
        return True

    async def log_transaction(self, guild: discord.Guild, author: discord.Member, message: str):
        settings = await db.get_guild_economy_settings(guild.id)
        if settings and settings.get('log_channel_id'):
            if channel := guild.get_channel(settings['log_channel_id']):
                embed = discord.Embed(description=message, color=self.bot.CREAM_COLOR, timestamp=datetime.datetime.now())
                embed.set_author(name=f"Auditoría Económica | {author.display_name}", icon_url=author.display_avatar.url)
                try: await channel.send(embed=embed)
                except discord.Forbidden: pass

    @commands.hybrid_group(name="economy", description="Comandos para configurar la economía del servidor.")
    @commands.has_permissions(administrator=True)
    async def economy(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.defer(ephemeral=True)
            settings = await db.get_guild_economy_settings(ctx.guild.id)
            active_channels_rows = await db.fetchall("SELECT channel_id FROM economy_active_channels WHERE guild_id = ?", (ctx.guild.id,))
            active_channels = [r['channel_id'] for r in active_channels_rows]
            channels = "\n".join([f"<#{cid}>" for cid in active_channels]) if active_channels else "Ninguno"
            
            currency_name = settings.get('currency_name', 'créditos')
            currency_emoji = settings.get('currency_emoji', '🪙')
            start_balance = settings.get('start_balance', 100)
            max_bal = f"{settings.get('max_balance')}" if settings.get('max_balance') is not None else "Sin límite"

            embed = discord.Embed(title="⚙️ Estado de la Economía", color=self.bot.CREAM_COLOR, description="Usa los subcomandos para configurar el sistema.")
            embed.add_field(name="Canales Activos", value=channels, inline=False)
            embed.add_field(name="Moneda", value=f"{currency_name} {currency_emoji}", inline=True)
            embed.add_field(name="Saldo Inicial", value=f"{start_balance}", inline=True)
            embed.add_field(name="Saldo Máximo", value=max_bal, inline=True)
            await self._send_response(ctx, embed=embed)

    @economy.command(name="addchannel", description="Activa los comandos de economía en un canal.")
    @commands.has_permissions(administrator=True)
    async def add_channel(self, ctx: commands.Context, canal: discord.TextChannel):
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
        await ctx.defer(ephemeral=True)
        if not await self.is_economy_active(ctx): return
        if cantidad <= 0: return await self._send_response(ctx, "La cantidad debe ser positiva.")
        await db.update_balance(ctx.guild.id, miembro.id, wallet_change=cantidad)
        await self._send_response(ctx, f"✅ Se han añadido **{cantidad}** a la cartera de {miembro.mention}.")
        await self.log_transaction(ctx.guild, ctx.author, f"Añadió **{cantidad}** a la cartera de {miembro.mention} (`{miembro.id}`).")

    @commands.hybrid_command(name="remove-money", description="Quita dinero de la cartera de un usuario.")
    @commands.has_permissions(manage_guild=True)
    async def remove_money(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        await ctx.defer(ephemeral=True)
        if not await self.is_economy_active(ctx): return
        if cantidad <= 0: return await self._send_response(ctx, "La cantidad debe ser positiva.")
        await db.update_balance(ctx.guild.id, miembro.id, wallet_change=-cantidad)
        await self._send_response(ctx, f"✅ Se han quitado **{cantidad}** de la cartera de {miembro.mention}.")
        await self.log_transaction(ctx.guild, ctx.author, f"Quitó **{cantidad}** de la cartera de {miembro.mention} (`{miembro.id}`).")

    @commands.hybrid_command(name="reset-economy", description="Reinicia la economía del servidor (ACCIÓN PELIGROSA).")
    @commands.has_permissions(administrator=True)
    async def reset_economy(self, ctx: commands.Context):
        await ctx.defer()
        if not await self.is_economy_active(ctx): return
        await db.execute("DELETE FROM balances WHERE guild_id = ?", (ctx.guild.id,))
        await self._send_response(ctx, "💥 **¡La economía del servidor ha sido reiniciada!**", ephemeral=False)
        await self.log_transaction(ctx.guild, ctx.author, "🚨 **REINICIÓ LA ECONOMÍA DEL SERVIDOR.**")

    @commands.hybrid_command(name='deposit', aliases=['dep'], description="Deposita dinero de tu cartera al banco.")
    async def deposit(self, ctx: commands.Context, cantidad: str):
        await ctx.defer(ephemeral=True)
        if not await self.is_economy_active(ctx): return
        wallet, bank = await db.get_balance(ctx.guild.id, ctx.author.id)
        if cantidad.lower() == 'all': amount = wallet
        else:
            try: amount = int(cantidad)
            except ValueError: return await self._send_response(ctx, "Introduce un número válido o la palabra 'all'.")
        if amount <= 0: return await self._send_response(ctx, "Debes depositar una cantidad positiva.")
        if wallet < amount: return await self._send_response(ctx, f"No tienes suficiente dinero. Cartera: **{wallet}**.")
        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-amount, bank_change=amount)
        new_bank_balance = bank + amount
        await self._send_response(ctx, f"🏦 Has depositado **{amount}**. Tu banco ahora tiene **{new_bank_balance}**.")

    @commands.hybrid_command(name='withdraw', description="Retira dinero de tu banco a tu cartera.")
    async def withdraw(self, ctx: commands.Context, cantidad: str):
        await ctx.defer(ephemeral=True)
        if not await self.is_economy_active(ctx): return
        _, bank = await db.get_balance(ctx.guild.id, ctx.author.id)
        if cantidad.lower() == 'all': amount = bank
        else:
            try: amount = int(cantidad)
            except ValueError: return await self._send_response(ctx, "Introduce un número válido o la palabra 'all'.")
        if amount <= 0: return await self._send_response(ctx, "Debes retirar una cantidad positiva.")
        if bank < amount: return await self._send_response(ctx, f"No tienes suficiente en el banco. Banco: **{bank}**.")
        new_wallet, _ = await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount, bank_change=-amount)
        await self._send_response(ctx, f"💸 Has retirado **{amount}**. Tu cartera ahora tiene **{new_wallet}**.")

    @commands.hybrid_command(name='balance', aliases=['bal'], description="Muestra tu balance de cartera y banco.")
    async def balance(self, ctx: commands.Context, miembro: Optional[discord.Member] = None):
        await ctx.defer(ephemeral=True)
        if not await self.is_economy_active(ctx): return
        target = miembro or ctx.author
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        wallet, bank = await db.get_balance(ctx.guild.id, target.id)
        embed = discord.Embed(title=f"{settings.get('currency_emoji', '🪙')} Balance de {target.display_name}", color=self.bot.CREAM_COLOR)
        embed.add_field(name="Cartera", value=f"`{wallet}`", inline=True).add_field(name="Banco", value=f"`{bank}`", inline=True).add_field(name="Total", value=f"`{wallet + bank}`", inline=True)
        await self._send_response(ctx, embed=embed)

    @commands.hybrid_command(name='daily', description="Reclama tu recompensa diaria en la cartera.")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx: commands.Context):
        await ctx.defer()
        if not await self.is_economy_active(ctx): return
        
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        if not settings:
            return await self._send_response(ctx, "Error: No se pudieron cargar las configuraciones de economía.", ephemeral=True)
            
        daily_min = settings.get('daily_min', 100)
        daily_max = settings.get('daily_max', 500)
        currency_name = settings.get('currency_name', 'créditos')
        currency_emoji = settings.get('currency_emoji', '🪙')

        amount = random.randint(daily_min, daily_max)
        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount)
        embed = discord.Embed(title=f"{currency_emoji} Recompensa Diaria", description=f"¡Felicidades! Has reclamado **{amount} {currency_name}**.", color=discord.Color.gold())
        await self._send_response(ctx, embed=embed)
        
    # --- MANEJADOR DE ERROR LOCAL ELIMINADO ---
    # Ya no necesitamos daily_error porque el manejador global en main.py lo hará.
    # Esto soluciona el problema del doble mensaje.

    @commands.hybrid_command(name='work', description="Trabaja para ganar un dinero extra.")
    async def work(self, ctx: commands.Context):
        await ctx.defer()

        if not await self.is_economy_active(ctx):
            return

        settings = await db.get_guild_economy_settings(ctx.guild.id)
        if not settings:
            return await self._send_response(ctx, "Error: No se pudieron cargar las configuraciones de economía.", ephemeral=True)

        source = ctx.interaction or ctx.message
        bucket = self._work_cd.get_bucket(source)
        
        work_cooldown = settings.get('work_cooldown', 3600)
        bucket.per = work_cooldown

        # Verificamos el cooldown. Si el comando está en cooldown, el manejador global se encargará.
        if bucket.update_rate_limit():
            return

        work_min = settings.get('work_min', 50)
        work_max = settings.get('work_max', 250)
        amount = random.randint(work_min, work_max)
        
        currency_name = settings.get('currency_name', 'créditos')

        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount)
        embed = discord.Embed(title="💼 ¡A trabajar!", description=f"Ganaste **{amount} {currency_name}**.", color=discord.Color.green())
        await self._send_response(ctx, embed=embed)

    @commands.hybrid_command(name='rob', description="Intenta robarle a otro usuario de su cartera.")
    async def rob(self, ctx: commands.Context, miembro: discord.Member):
        await ctx.defer()

        if not await self.is_economy_active(ctx):
            return

        settings = await db.get_guild_economy_settings(ctx.guild.id)
        if not settings:
            return await self._send_response(ctx, "Error: No se pudieron cargar las configuraciones de economía.", ephemeral=True)

        source = ctx.interaction or ctx.message
        bucket = self._rob_cd.get_bucket(source)
        
        rob_cooldown = settings.get('rob_cooldown', 21600)
        bucket.per = rob_cooldown

        # Verificamos el cooldown. Si el comando está en cooldown, el manejador global se encargará.
        if bucket.update_rate_limit():
            return

        if miembro.id == ctx.author.id: return await self._send_response(ctx, "No te puedes robar a ti mismo.", ephemeral=True)
        if miembro.bot: return await self._send_response(ctx, "No puedes robarle a los bots.", ephemeral=True)
        
        robber_wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
        victim_wallet, _ = await db.get_balance(ctx.guild.id, miembro.id)
        
        if victim_wallet < 200: return await self._send_response(ctx, f"{miembro.display_name} no tiene suficiente en su cartera.", ephemeral=True)
        
        if random.random() < 0.5:
            amount = int(victim_wallet * random.uniform(0.1, 0.25))
            await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount)
            await db.update_balance(ctx.guild.id, miembro.id, wallet_change=-amount)
            embed = discord.Embed(title="🎭 ¡Robo Exitoso!", description=f"Robaste **{amount}** de la cartera a {miembro.mention}.", color=discord.Color.dark_green())
        else:
            amount = max(50, int(robber_wallet * random.uniform(0.05, 0.15)))
            await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-amount)
            embed = discord.Embed(title="🚓 ¡Te Pillaron!", description=f"Te vieron venir. Perdiste **{amount}**.", color=discord.Color.dark_red())
        await self._send_response(ctx, embed=embed)

    @commands.hybrid_command(name='give', description="Transfiere dinero de tu cartera a otro usuario.")
    async def give(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        await ctx.defer(ephemeral=True)
        if not await self.is_economy_active(ctx): return
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        if ctx.author.id == miembro.id: return await self._send_response(ctx, "No puedes darte dinero a ti mismo.")
        if cantidad <= 0: return await self._send_response(ctx, "La cantidad debe ser positiva.")
        sender_wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
        if sender_wallet < cantidad: return await self._send_response(ctx, f"No tienes suficientes {settings.get('currency_name', 'créditos')}. Tienes: **{sender_wallet}**.")
        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-cantidad)
        await db.update_balance(ctx.guild.id, miembro.id, wallet_change=cantidad)
        embed = discord.Embed(title="💸 Transferencia Realizada", description=f"{ctx.author.mention} ha transferido **{cantidad}** a {miembro.mention}.", color=self.bot.CREAM_COLOR)
        await self._send_response(ctx, embed=embed, ephemeral=False)
        await self.log_transaction(ctx.guild, ctx.author, f"Transfirió **{cantidad}** a {miembro.mention}.")

    @commands.hybrid_command(name='leaderboard', aliases=['lb'], description="Muestra a los usuarios más ricos del servidor.")
    async def leaderboard(self, ctx: commands.Context):
        await ctx.defer()
        if not await self.is_economy_active(ctx): return
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        top_users = await db.fetchall("SELECT user_id, wallet, bank, (wallet + bank) as total FROM balances WHERE guild_id = ? ORDER BY total DESC LIMIT 10", (ctx.guild.id,))
        if not top_users: return await self._send_response(ctx, f"Nadie tiene {settings.get('currency_name', 'créditos')} todavía.")
        embed = discord.Embed(title=f"🏆 Ranking de {settings.get('currency_name', 'créditos')} 🏆", color=discord.Color.gold())
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
        await self._send_response(ctx, embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))