import discord
from discord.ext import commands
import random
import asyncio
from typing import Optional, Literal

# Importamos el gestor de base de datos
from utils import database_manager as db
from utils.lang_utils import _t

def parse_amount(amount_str: str, current_balance: int) -> Optional[int]:
    """Interpreta textos como 'all', 'max', 'half' para facilitar la vida del usuario."""
    amount_str = amount_str.lower()
    if amount_str in ['all', 'max']:
        return current_balance
    if amount_str == 'half':
        return current_balance // 2
    try:
        val = int(amount_str)
        if val > 0: return val
    except ValueError: pass
    return None

class EconomyCog(commands.Cog, name="Economía"):
    """Sistema de economía dinámico y robusto similar a UnbelievaBoat. Compra, vende y roba."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_locks = {}

    async def cog_check(self, ctx: commands.Context):
        """Check global para este Cog."""
        if not ctx.guild: return True
        settings = await db.get_cached_server_settings(ctx.guild.id)
        if settings and not settings.get('eco_enabled', 1):
            await ctx.send("❌ El módulo de **Economía** está desactivado. Un administrador debe habilitarlo en el dashboard.", ephemeral=True)
            return False
        
        # Check active channels
        allowed_channels = await db.fetchall("SELECT channel_id FROM economy_active_channels WHERE guild_id = ?", (ctx.guild.id,))
        if allowed_channels:
            allowed_ids = [int(ch['channel_id']) for ch in allowed_channels]
            if ctx.channel.id not in allowed_ids:
                channels_mentions = " ".join([f"<#{cid}>" for cid in allowed_ids])
                await ctx.send(f"❌ Los comandos de economía solo están permitidos en: {channels_mentions}", ephemeral=True)
                return False
                
        return True
        
    def get_user_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self.user_locks:
            self.user_locks[user_id] = asyncio.Lock()
        return self.user_locks[user_id]
        
    async def get_max_bank(self, guild_id: int, user_id: int) -> int:
        """El límite del banco aumenta pasivamente en base al nivel de XP del usuario."""
        level, xp = await db.get_user_level(guild_id, user_id)
        # Nivel 1 = 10,000 | Nivel 10 = 55,000 | Nivel 50 = 255,000
        return 5000 + (level * 5000)

# Comandos de administrador
    @commands.hybrid_group(name="economy", description="Configura la economía del servidor.")
    @commands.has_permissions(administrator=True)
    async def economy(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Comandos: `/economy set-currency`, `/economy config-work`, `/economy config-daily`, `/economy config-rob`", ephemeral=True)

    @economy.command(name="set-currency", description="Cambia el nombre y emoji de la moneda.")
    async def set_currency(self, ctx: commands.Context, nombre: str, emoji: str):
        await db.get_guild_economy_settings(ctx.guild.id) # Asegurar que la fila del server exista
        await db.execute("UPDATE economy_settings SET currency_name = ?, currency_emoji = ? WHERE guild_id = ?", (nombre, emoji, ctx.guild.id))
        await ctx.send(f"✅ La moneda del servidor ahora es **{nombre}** {emoji}.", ephemeral=True)

    @economy.command(name="config-work", description="Ajusta ganancias y cooldown del trabajo.")
    @commands.has_permissions(administrator=True)
    async def config_work(self, ctx: commands.Context, min_paga: int, max_paga: int, segundos_espera: int):
        if min_paga < 0 or max_paga < min_paga or segundos_espera < 0:
            return await ctx.send("❌ Valores inválidos. Asegúrate de que min >= 0, max >= min y cooldown >= 0.", ephemeral=True)
        await db.get_guild_economy_settings(ctx.guild.id)
        await db.execute("UPDATE economy_settings SET work_min = ?, work_max = ?, work_cooldown = ? WHERE guild_id = ?", (min_paga, max_paga, segundos_espera, ctx.guild.id))
        await ctx.send(f"✅ **Trabajo configurado:**\n- Min: {min_paga}\n- Max: {max_paga}\n- Cooldown: {segundos_espera}s", ephemeral=True)

    @economy.command(name="config-daily", description="Ajusta ganancias del comando diario.")
    @commands.has_permissions(administrator=True)
    async def config_daily(self, ctx: commands.Context, min_diario: int, max_diario: int):
        if min_diario < 0 or max_diario < min_diario:
            return await ctx.send("❌ Valores inválidos.", ephemeral=True)
        await db.get_guild_economy_settings(ctx.guild.id)
        await db.execute("UPDATE economy_settings SET daily_min = ?, daily_max = ? WHERE guild_id = ?", (min_diario, max_diario, ctx.guild.id))
        await ctx.send(f"✅ **Diario configurado:** Min {min_diario}, Max {max_diario}.", ephemeral=True)

    @economy.command(name="config-rob", description="Ajusta el cooldown para robos.")
    @commands.has_permissions(administrator=True)
    async def config_rob(self, ctx: commands.Context, segundos_espera: int):
        if segundos_espera < 0:
            return await ctx.send("❌ Cooldown inválido.", ephemeral=True)
        await db.get_guild_economy_settings(ctx.guild.id)
        await db.execute("UPDATE economy_settings SET rob_cooldown = ? WHERE guild_id = ?", (segundos_espera, ctx.guild.id))
        await ctx.send(f"✅ **Cooldown de robo:** {segundos_espera}s.", ephemeral=True)

        
    @commands.hybrid_command(name="add-money", description="Añade dinero del servidor a un usuario (Admin).")
    @commands.has_permissions(administrator=True)
    async def add_money(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        if cantidad <= 0: return await ctx.send("❌ La cantidad debe ser mayor a 0.", ephemeral=True)
        settings = await db.get_cached_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        await db.update_balance(ctx.guild.id, miembro.id, wallet_change=cantidad)
        await ctx.send(f"✅ Se han impreso **{cantidad} {emoji}** y añadido a la cartera de {miembro.mention}.")

    @commands.hybrid_command(name="remove-money", description="Quita dinero a un usuario. (Paga tus impuestos)")
    @commands.has_permissions(administrator=True)
    async def remove_money(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        if cantidad <= 0: return await ctx.send("❌ La cantidad debe ser mayor a 0.", ephemeral=True)
        settings = await db.get_cached_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        await db.update_balance(ctx.guild.id, miembro.id, wallet_change=-cantidad)
        await ctx.send(f"🛑 Se han deducido **{cantidad} {emoji}** de la cartera de {miembro.mention}.")

    # Bancos y transferencias
    
    @commands.hybrid_command(name='balance', aliases=['bal', 'money', 'atm'], description="Muestra la cartera y el banco de un usuario.")
    async def balance(self, ctx: commands.Context, miembro: Optional[discord.Member] = None):
        if not ctx.guild: return
        await ctx.defer()
        target = miembro or ctx.author
        if target.bot: return await ctx.send("🤖 Los bots formamos parte de una red de consciencia unificada que anula el concepto de capitalismo.")
        
        wallet, bank = await db.get_balance(ctx.guild.id, target.id)
        settings = await db.get_cached_economy_settings(ctx.guild.id)
        currency_name = settings.get('currency_name', 'créditos')
        emoji = settings.get('currency_emoji', '🪙')
        
        max_bank = await self.get_max_bank(ctx.guild.id, target.id)
        
        # Fetch language for localization
        server_settings = await db.get_cached_server_settings(ctx.guild.id)
        lang = server_settings.get('language', 'es')
        
        embed = discord.Embed(title=_t('bot.economy.balance_title', lang=lang, name=target.display_name), color=self.bot.CREAM_COLOR)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name=_t('bot.economy.wallet', lang=lang), value=f"**{wallet:,}** {emoji}", inline=True)
        embed.add_field(name=_t('bot.economy.bank', lang=lang), value=f"**{bank:,} / {max_bank:,}** {emoji}", inline=True)
        embed.add_field(name=_t('bot.economy.total', lang=lang), value=f"**{(wallet + bank):,}** {emoji}", inline=False)
        embed.set_footer(text=_t('bot.economy.footer', lang=lang, currency=currency_name.capitalize()))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='deposit', aliases=['dep'], description="Mete dinero a la seguridad de tu banco. Uso: 'all' / 'max' / '100'")
    async def deposit(self, ctx: commands.Context, cantidad: str):
        if not ctx.guild: return
        await ctx.defer()
        settings = await db.get_cached_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        
        async with self.get_user_lock(ctx.author.id):
            wallet, bank = await db.get_balance(ctx.guild.id, ctx.author.id)
            amount = parse_amount(cantidad, wallet)
            
            # Fetch language for localization
            server_settings = await db.get_cached_server_settings(ctx.guild.id)
            lang = server_settings.get('language', 'es')
            
            if amount is None or amount <= 0: return await ctx.send(_t('bot.economy.invalid_amount', lang=lang), ephemeral=True)
            if amount > wallet: return await ctx.send(_t('bot.economy.not_enough_money', lang=lang, balance=wallet, emoji=emoji), ephemeral=True)
                
            max_bank = await self.get_max_bank(ctx.guild.id, ctx.author.id)
            if bank + amount > max_bank:
                amount = max_bank - bank
                if amount <= 0:
                    # Generic error for now, could be localized too
                    return await ctx.send(f"🏦 Tu banco está rebosando el límite ({max_bank:,} {emoji}).", ephemeral=True)
            
            new_wallet, new_bank = await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-amount, bank_change=amount)
            await ctx.send(_t('bot.economy.deposit_success', lang=lang, amount=f"{amount:,}", emoji=emoji) + f"\n**Saldo Protegido:** {new_bank:,} / {max_bank:,} {emoji}")

    @commands.hybrid_command(name='withdraw', aliases=['with'], description="Saca dinero de tu banco a tu cartera. Uso: 'all' / '100'")
    async def withdraw(self, ctx: commands.Context, cantidad: str):
        if not ctx.guild: return
        await ctx.defer()
        settings = await db.get_cached_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        
        async with self.get_user_lock(ctx.author.id):
            wallet, bank = await db.get_balance(ctx.guild.id, ctx.author.id)
            amount = parse_amount(cantidad, bank)
            
            # Fetch language for localization
            server_settings = await db.get_cached_server_settings(ctx.guild.id)
            lang = server_settings.get('language', 'es')
            
            if amount is None or amount <= 0: return await ctx.send(_t('bot.economy.invalid_amount', lang=lang), ephemeral=True)
            if amount > bank: return await ctx.send(_t('bot.economy.not_enough_money', lang=lang, balance=bank, emoji=emoji), ephemeral=True)
            
            await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount, bank_change=-amount)
            await ctx.send(_t('bot.economy.withdraw_success', lang=lang, amount=f"{amount:,}", emoji=emoji))

    @commands.hybrid_command(name='give', aliases=['transfer', 'pay'], description="Págale a un usuario (Impuesto gubernamental de 2% para evitar abusos).")
    async def give(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        if not ctx.guild: return
        await ctx.defer()
        if miembro.bot: return await ctx.send("🤖 La interfaz de las IAs aún no acepta propinas.")
        if miembro.id == ctx.author.id: return await ctx.send("❌ No te puedes pagar a ti mismo.")
        
        settings = await db.get_cached_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')

        async with self.get_user_lock(ctx.author.id):
            wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
            
            # Fetch language for localization
            server_settings = await db.get_cached_server_settings(ctx.guild.id)
            lang = server_settings.get('language', 'es')
            
            if cantidad <= 0: return await ctx.send(_t('bot.economy.invalid_amount', lang=lang), ephemeral=True)
            if cantidad > wallet: return await ctx.send(_t('bot.economy.not_enough_money', lang=lang, balance=wallet, emoji=emoji), ephemeral=True)
            
            tax = int(cantidad * 0.02)
            real_amount = cantidad - tax
            
            await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-cantidad)
            await db.update_balance(ctx.guild.id, miembro.id, wallet_change=real_amount)
            
            await ctx.send(_t('bot.economy.give_success', lang=lang, amount=f"{real_amount:,}", emoji=emoji, target=miembro.mention) + f" (Tax: {tax:,} {emoji})")

    # Ingresos activos
    
    @commands.hybrid_command(name='daily', description="Reclama una buena recompensa que puedes sacar una vez cada día.")
    async def daily(self, ctx: commands.Context):
        if not ctx.guild: return
        await ctx.defer()
        
        settings = await db.get_cached_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        
        async with self.get_user_lock(ctx.author.id):
            # Fetch language for localization
            server_settings = await db.get_cached_server_settings(ctx.guild.id)
            lang = server_settings.get('language', 'es')
            
            last_daily = await db.get_last_daily(ctx.guild.id, ctx.author.id)
            now = discord.utils.utcnow()
            
            if last_daily:
                delta = now - last_daily
                if delta.total_seconds() < 86400:
                    wait_time = 86400 - delta.total_seconds()
                    hours = int(wait_time // 3600)
                    minutes = int((wait_time % 3600) // 60)
                    time_str = f"{hours}h {minutes}m"
                    return await ctx.send(_t('bot.economy.daily_cooldown', lang=lang, time=time_str), ephemeral=True)
            
            eco_conf = await db.get_economy_settings(ctx.guild.id)
            d_min = eco_conf.get('daily_min', 900)
            d_max = eco_conf.get('daily_max', 2500)
            
            reward = random.randint(d_min, d_max)
            await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=reward)
            await db.set_last_daily(ctx.guild.id, ctx.author.id, now)
            
            await ctx.send(_t('bot.economy.daily_success', lang=lang, amount=f"{reward:,}", emoji=emoji))


    @commands.hybrid_command(name='work', description="Ponte a trabajar unas horas para tener efectivo.")
    async def work(self, ctx: commands.Context):
        if not ctx.guild: return
        await ctx.defer()
        settings = await db.get_cached_economy_settings(ctx.guild.id)
        cooldown_time = settings.get('work_cooldown', 3600)
        
        now_dt = discord.utils.utcnow()
        last_use_dt = await db.get_cooldown(ctx.guild.id, ctx.author.id, 'work')
        last_use = last_use_dt.timestamp() if last_use_dt else 0
        
        # Fetch language for localization
        server_settings = await db.get_cached_server_settings(ctx.guild.id)
        lang = server_settings.get('language', 'es')

        if now_dt.timestamp() - last_use < cooldown_time:
            retry_after = cooldown_time - (now_dt.timestamp() - last_use)
            hours = int(retry_after // 3600)
            minutes = int((retry_after % 3600) // 60)
            seconds = int(retry_after % 60)
            time_str = ""
            if hours > 0: time_str += f"{hours}h "
            if minutes > 0: time_str += f"{minutes}m "
            time_str += f"{seconds}s"
            return await ctx.send(_t('bot.economy.work_cooldown', lang=lang, time=time_str.strip()), ephemeral=True)

        # Registrar uso en la DB
        await db.set_cooldown(ctx.guild.id, ctx.author.id, 'work', now_dt)

        min_w = settings.get('work_min', 100)

        max_w = settings.get('work_max', 350)
        emoji = settings.get('currency_emoji', '🪙')
        ganancia = random.randint(min_w, max_w)
        
        trabajos = [
            f"Trabajaste limpiando el código de un bot raro y ganaste **{ganancia} {emoji}**.",
            f"Sobreviviste a un turno de 4 horas en el McDonalds y tu jefe te arrojó **{ganancia} {emoji}**.",
            f"Caminaste por la calle mirando el celular y te topaste con **{ganancia} {emoji}**.",
            f"Hiciste comisiones de dudosa moral en Twitter y te depositaron **{ganancia} {emoji}**.",
            f"Fuiste minero de cobalto en Minecraft y recolectaste el equivalente a **{ganancia} {emoji}**."
        ]
        
        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=ganancia)
        embed = discord.Embed(title="💼 El Mundo Laboral", description=random.choice(trabajos), color=0x3498DB)
        await ctx.send(embed=embed)


    @economy.command(name="add-item", description="Añade un artículo a la tienda del servidor.")
    async def add_item(self, ctx: commands.Context, nombre: str, descripcion: str, precio: int, tipo: Literal['role', 'consumable'], raw_data: str):
        if precio <= 0: return await ctx.send("El precio debe ser mayor a 0.")
        if tipo == 'role' and not raw_data.isdigit(): return await ctx.send("Para roles, el `raw_data` debe ser la ID numérica del Rol.", ephemeral=True)
        await db.execute("INSERT INTO shop_items (guild_id, name, description, price, type, raw_data) VALUES (?, ?, ?, ?, ?, ?)", (ctx.guild.id, nombre, descripcion, precio, tipo, raw_data))
        await ctx.send(f"✅ Artículo '{nombre}' (Tipo: {tipo}) añadido a la tienda por {precio:,}.")

    @economy.command(name="remove-item", description="Elimina un artículo de la tienda usando su ID.")
    async def remove_item(self, ctx: commands.Context, item_id: int):
        await db.execute("DELETE FROM shop_items WHERE item_id = ? AND guild_id = ?", (item_id, ctx.guild.id))
        await ctx.send("✅ Si existía, el artículo ha sido pulverizado libremente.")

    @commands.hybrid_command(name='shop', aliases=['tienda'], description="Mira los artículos disponibles para comprar en este servidor.")
    async def shop(self, ctx: commands.Context):
        if not ctx.guild: return
        await ctx.defer()
        items = await db.fetchall("SELECT * FROM shop_items WHERE guild_id = ?", (ctx.guild.id,))
        if not items: return await ctx.send("🛒 La tienda está vacía. Vuelve más tarde.", ephemeral=True)
        
        settings = await db.get_cached_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        
        embed = discord.Embed(title="🛒 Tienda del Servidor", description="Usa `/buy <ID>` para comprar un artículo.", color=discord.Color.gold())
        for item in items:
            tipo_humano = "🛡️ Rol de Discord" if item['type'] == 'role' else "🧪 Objeto Consumible"
            embed.add_field(name=f"ID: {item['item_id']} | {item['name']}", value=f"*- {tipo_humano}*\n{item['description']}\n**Precio:** {item['price']:,} {emoji}", inline=False)
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='buy', aliases=['comprar'], description="Compra un artículo de la tienda usando su ID.")
    async def buy(self, ctx: commands.Context, item_id: int):
        if not ctx.guild: return
        await ctx.defer()
        item = await db.fetchone("SELECT * FROM shop_items WHERE item_id = ? AND guild_id = ?", (item_id, ctx.guild.id))
        if not item: return await ctx.send("❌ No existe ningún artículo con esa ID en esta tienda.", ephemeral=True)
        
        settings = await db.get_cached_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        
        async with self.get_user_lock(ctx.author.id):
            wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
            if wallet < item['price']: return await ctx.send(f"❌ Efectivo insuficiente. Cuesta **{item['price']:,} {emoji}** y tienes **{wallet:,} {emoji}**.", ephemeral=True)
            
            # Procesar la compra
            if item['type'] == 'role':
                # Dar el rol directamente e ignorar el inventario para no ensuciarlo
                role_id = int(item['raw_data'])
                role = ctx.guild.get_role(role_id)
                if not role: return await ctx.send("❌ El rol asociado a este artículo ha sido borrado de Discord. Contacta a un administrador.")
                if role in ctx.author.roles: return await ctx.send("❌ Ya posees este rol.", ephemeral=True)
                
                try:
                    await ctx.author.add_roles(role)
                except discord.Forbidden:
                    return await ctx.send("❌ No tengo permisos suficientes para entregarte el rol. Dile a un admin que suba al bot por encima de este en la lista de roles de Discord.")
                    
                await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-item['price'])
                await ctx.send(f"🛍️ Has comprado exitosamente el rol **{item['name']}** por {item['price']:,} {emoji}.")
                
            elif item['type'] == 'consumable':
                await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-item['price'])
                await db.execute("INSERT INTO inventory (guild_id, user_id, item_id, quantity) VALUES (?, ?, ?, 1) ON CONFLICT(guild_id, user_id, item_id) DO UPDATE SET quantity = quantity + 1", (ctx.guild.id, ctx.author.id, item['item_id']))
                await ctx.send(f"🛍️ Has comprado **{item['name']}** por {item['price']:,} {emoji}. Revisa tu `/inventory`.")

    @commands.hybrid_command(name='inventory', aliases=['inv', 'mochila'], description="Revisa los consumibles y objetos que has comprado.")
    async def inventory(self, ctx: commands.Context):
        if not ctx.guild: return
        await ctx.defer()
        query = "SELECT i.quantity, s.name, s.description FROM inventory i JOIN shop_items s ON i.item_id = s.item_id WHERE i.guild_id = ? AND i.user_id = ? AND i.quantity > 0"
        items = await db.fetchall(query, (ctx.guild.id, ctx.author.id))
        
        if not items: return await ctx.send("🎒 Tu mochila está completamente vacía.", ephemeral=True)
        
        embed = discord.Embed(title=f"🎒 Mochila de {ctx.author.display_name}", color=self.bot.CREAM_COLOR)
        for row in items:
            embed.add_field(name=f"{row['quantity']}x {row['name']}", value=row['description'], inline=False)
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='rob', aliases=['robar'], description="Intenta adueñarte de lo que no es tuyo. Altamente riesgoso.")
    async def rob(self, ctx: commands.Context, miembro: discord.Member):
        if not ctx.guild: return
        await ctx.defer()
        if miembro.id == ctx.author.id:
            return await ctx.send("Te quitaste la cartera de tu bolsillo izquierdo para meterla en el derecho. Eres un genio.")
        if miembro.bot:
            return await ctx.send("Robarle a una IA es intentar hackear a la Matrix. Imposible.")

        settings = await db.get_cached_economy_settings(ctx.guild.id)
        cooldown_time = settings.get('rob_cooldown', 21600)
        
        now_dt = discord.utils.utcnow()
        last_use_dt = await db.get_cooldown(ctx.guild.id, ctx.author.id, 'rob')
        last_use = last_use_dt.timestamp() if last_use_dt else 0
        
        if now_dt.timestamp() - last_use < cooldown_time:
            retry_after = cooldown_time - (now_dt.timestamp() - last_use)
            return await ctx.send(f"⏳ El último atraco fue demasiado tenso. La policía te busca. Intenta de nuevo en **{int(retry_after/3600)}h {int((retry_after%3600)/60)}m**.", ephemeral=True)
        
        emoji = settings.get('currency_emoji', '🪙')
        
        async with self.get_user_lock(ctx.author.id):
            # Fetch language for localization
            server_settings = await db.get_cached_server_settings(ctx.guild.id)
            lang = server_settings.get('language', 'es')
            
            robador_w, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
            victima_w, _ = await db.get_balance(ctx.guild.id, miembro.id)
            
            # Anti-Exploits Puras Multas
            if robador_w < 500:
                return await ctx.send(f"❌ ¡Eres pobre! Necesitas tener al menos **500 {emoji}** en la cartera como fianza por si te atrapa la patrulla.", ephemeral=True)
                
            if victima_w < 200:
                return await ctx.send(f"❌ Pobrecito de {miembro.display_name}, no trae ni 200 {emoji} para el bus. Búscate un objetivo más grande.", ephemeral=True)

            # Si pasa las fianza, aplicamos cooldown ANTES de ver si gana o pierde para que no spamee
            await db.set_cooldown(ctx.guild.id, ctx.author.id, 'rob', now_dt)

            # Revisar si la víctima tiene un consumible protector tipo "escudo" en el inventario
            shield_item = await db.fetchone("""
                SELECT i.item_id 
                FROM inventory i JOIN shop_items s ON i.item_id = s.item_id 
                WHERE i.guild_id = ? AND i.user_id = ? AND s.type = 'consumable' AND LOWER(s.name) LIKE '%escudo%' AND i.quantity > 0
            """, (ctx.guild.id, miembro.id))
            
            if shield_item:
                # Romper el escudo (consumirlo)
                await db.execute("UPDATE inventory SET quantity = quantity - 1 WHERE guild_id = ? AND user_id = ? AND item_id = ?", (ctx.guild.id, miembro.id, shield_item['item_id']))
                # Aplicar emboscada policial automática
                multa = int(robador_w * 0.50) # El ladrón pierde el 50% de sus fondos líquidos
                await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-multa)
                embed = discord.Embed(title="🚨 ¡EMBOSCADA POLICIAL!", description=f"{miembro.mention} tenía un **Escudo de Seguridad** activo.\nAl intentar robarle, saltó la trampa y fuiste acorralado por el FBI.\nHas sido multado severamente perdiendo **{multa:,} {emoji}**.\n\n*El escudo de tu objetivo se ha roto.*", color=discord.Color.red())
                return await ctx.send(embed=embed)

            # Matemáticas regulares: 40% Winrate vs 60% multas
            suerte = random.randint(1, 100)
            # Matemáticas regulares: 45% Winrate vs 55% multas
            exito = random.randint(1, 100)
            if exito <= 45: # 45% probabilidad de éxito
                cantidad = random.randint(10, int(victima_w * 0.35))
                await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=cantidad)
                await db.update_balance(ctx.guild.id, miembro.id, wallet_change=-cantidad)
                await ctx.send(_t('bot.economy.rob_success', lang=lang, amount=f"{cantidad:,}", emoji=emoji, target=miembro.mention))
            else:
                multa = random.randint(10, int(robador_w * 0.20))
                await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-multa)
                await db.update_balance(ctx.guild.id, miembro.id, wallet_change=multa)
                await ctx.send(_t('bot.economy.rob_failed', lang=lang, amount=f"{multa:,}", emoji=emoji, target=miembro.mention))

    @commands.hybrid_command(name='leaderboard', aliases=['richest'], description="Observa qué personas tienen más estatus que tú.")
    async def leaderboard(self, ctx: commands.Context):
        if not ctx.guild: return
        await ctx.defer()
        query = "SELECT user_id, wallet, bank FROM balances WHERE guild_id = ? ORDER BY (wallet + bank) DESC LIMIT 10"
        top_users = await db.fetchall(query, (ctx.guild.id,))
        
        settings = await db.get_cached_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        
        if not top_users: return await ctx.send("Este lugar parece un desierto económico.")
        
        embed = discord.Embed(title=f"🏆 Los Más Poderosos de {ctx.guild.name} 🏆", color=self.bot.CREAM_COLOR)
        description = ""
        for i, row in enumerate(top_users):
            user = self.bot.get_user(row['user_id'])
            if not user:
                try: user = await self.bot.fetch_user(row['user_id'])
                except: name = f"Usuario ({row['user_id']})"
            
            if user: name = user.display_name
            
            net = row['wallet'] + row['bank']
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`{i+1}.`"
            description += f"{rank} **{name}**: {net:,} {emoji}\n"
            
        embed.description = description
        embed.set_footer(text="Basado en el NETO (Cartera Líquida + Banco Segurizado)")
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))