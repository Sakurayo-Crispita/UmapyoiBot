import discord
from discord.ext import commands
import random
import asyncio
from typing import Optional, Literal

# Importamos el gestor de base de datos
from utils import database_manager as db

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
        
    def get_user_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self.user_locks:
            self.user_locks[user_id] = asyncio.Lock()
        return self.user_locks[user_id]
        
    async def get_max_bank(self, guild_id: int, user_id: int) -> int:
        """El límite del banco aumenta pasivamente en base al nivel de XP del usuario."""
        level, xp = await db.get_user_level(guild_id, user_id)
        # Nivel 1 = 10,000 | Nivel 10 = 55,000 | Nivel 50 = 255,000
        return 5000 + (level * 5000)

    # --- COMANDOS DE ADMINISTRADOR ---
    @commands.hybrid_group(name="economy", description="Configura la economía del servidor.")
    @commands.has_permissions(administrator=True)
    async def economy(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Comandos: `/economy set-currency`", ephemeral=True)

    @economy.command(name="set-currency", description="Cambia el nombre y emoji de la moneda.")
    async def set_currency(self, ctx: commands.Context, nombre: str, emoji: str):
        await db.get_guild_economy_settings(ctx.guild.id) # Asegurar que la fila del server exista
        await db.execute("UPDATE economy_settings SET currency_name = ?, currency_emoji = ? WHERE guild_id = ?", (nombre, emoji, ctx.guild.id))
        await ctx.send(f"✅ La moneda del servidor ahora es **{nombre}** {emoji}.", ephemeral=True)

    @economy.command(name="config-work", description="Configura las ganancias y cooldown del comando /work.")
    async def config_work(self, ctx: commands.Context, minimo: int, maximo: int, cooldown_segundos: int):
        if minimo < 0 or maximo < minimo or cooldown_segundos < 0:
            return await ctx.send("❌ Valores inválidos. Asegúrate de que min >= 0, max >= min y cooldown >= 0.", ephemeral=True)
        await db.get_guild_economy_settings(ctx.guild.id)
        await db.execute("UPDATE economy_settings SET work_min = ?, work_max = ?, work_cooldown = ? WHERE guild_id = ?", (minimo, maximo, cooldown_segundos, ctx.guild.id))
        await ctx.send(f"✅ Configurando trabajo: Min {minimo}, Max {maximo}, Cooldown {cooldown_segundos}s.", ephemeral=True)

    @economy.command(name="config-daily", description="Configura las ganancias del comando /daily.")
    async def config_daily(self, ctx: commands.Context, minimo: int, maximo: int):
        if minimo < 0 or maximo < minimo:
            return await ctx.send("❌ Valores inválidos. Asegúrate de que min >= 0 y max >= min.", ephemeral=True)
        await db.get_guild_economy_settings(ctx.guild.id)
        await db.execute("UPDATE economy_settings SET daily_min = ?, daily_max = ? WHERE guild_id = ?", (minimo, maximo, ctx.guild.id))
        await ctx.send(f"✅ Configurando diario: Min {minimo}, Max {maximo}.", ephemeral=True)

    @economy.command(name="config-rob", description="Configura el cooldown del comando /rob.")
    async def config_rob(self, ctx: commands.Context, cooldown_segundos: int):
        if cooldown_segundos < 0:
            return await ctx.send("❌ El cooldown no puede ser negativo.", ephemeral=True)
        await db.get_guild_economy_settings(ctx.guild.id)
        await db.execute("UPDATE economy_settings SET rob_cooldown = ? WHERE guild_id = ?", (cooldown_segundos, ctx.guild.id))
        await ctx.send(f"✅ Cooldown de robo establecido en {cooldown_segundos}s.", ephemeral=True)

        
    @commands.hybrid_command(name="add-money", description="Añade dinero del servidor a un usuario (Admin).")
    @commands.has_permissions(administrator=True)
    async def add_money(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        await db.update_balance(ctx.guild.id, miembro.id, wallet_change=cantidad)
        await ctx.send(f"✅ Se han impreso **{cantidad} {emoji}** y añadido a la cartera de {miembro.mention}.")

    @commands.hybrid_command(name="remove-money", description="Quita dinero a un usuario. (Paga tus impuestos)")
    @commands.has_permissions(administrator=True)
    async def remove_money(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        await db.update_balance(ctx.guild.id, miembro.id, wallet_change=-cantidad)
        await ctx.send(f"🛑 Se han deducido **{cantidad} {emoji}** de la cartera de {miembro.mention}.")

    # --- BANCOS Y TRANSFERENCIAS ---
    
    @commands.hybrid_command(name='balance', aliases=['bal', 'money'], description="Muestra la cartera y el banco de un usuario.")
    async def balance(self, ctx: commands.Context, miembro: Optional[discord.Member] = None):
        target = miembro or ctx.author
        if target.bot: return await ctx.send("🤖 Los bots formamos parte de una red de consciencia unificada que anula el concepto de capitalismo.")
        await ctx.defer()
        
        wallet, bank = await db.get_balance(ctx.guild.id, target.id)
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        currency_name = settings.get('currency_name', 'créditos')
        emoji = settings.get('currency_emoji', '🪙')
        
        max_bank = await self.get_max_bank(ctx.guild.id, target.id)
        
        embed = discord.Embed(title=f"💳 Balance de {target.display_name}", color=self.bot.CREAM_COLOR)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Cartera (Wallet)", value=f"**{wallet:,}** {emoji}", inline=True)
        embed.add_field(name="Banco (Bank)", value=f"**{bank:,} / {max_bank:,}** {emoji}", inline=True)
        embed.add_field(name="Neto Total", value=f"**{(wallet + bank):,}** {emoji}", inline=False)
        embed.set_footer(text=f"Moneda Oficial: {currency_name.capitalize()}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='deposit', aliases=['dep'], description="Mete dinero a la seguridad de tu banco. Uso: 'all' / 'max' / '100'")
    async def deposit(self, ctx: commands.Context, cantidad: str):
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        
        async with self.get_user_lock(ctx.author.id):
            wallet, bank = await db.get_balance(ctx.guild.id, ctx.author.id)
            amount = parse_amount(cantidad, wallet)
            
            if amount is None or amount <= 0: return await ctx.send("❌ Monto inválido. Puedes usar números o 'all'.", ephemeral=True)
            if amount > wallet: return await ctx.send(f"❌ No tienes suficiente efectivo. (Tienes **{wallet} {emoji}**)", ephemeral=True)
                
            max_bank = await self.get_max_bank(ctx.guild.id, ctx.author.id)
            if bank + amount > max_bank:
                amount = max_bank - bank
                if amount <= 0:
                    return await ctx.send(f"🏦 Tu banco está rebosando el límite ({max_bank:,} {emoji}). ¡Sube tu nivel de XP en el servidor para ampliarlo!", ephemeral=True)
            
            new_wallet, new_bank = await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-amount, bank_change=amount)
            await ctx.send(f"🏦 Has depositado **{amount:,} {emoji}** en el banco.\n**Saldo Protegido:** {new_bank:,} / {max_bank:,} {emoji}")

    @commands.hybrid_command(name='withdraw', aliases=['with'], description="Saca dinero de tu banco a tu cartera. Uso: 'all' / '100'")
    async def withdraw(self, ctx: commands.Context, cantidad: str):
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        
        async with self.get_user_lock(ctx.author.id):
            wallet, bank = await db.get_balance(ctx.guild.id, ctx.author.id)
            amount = parse_amount(cantidad, bank)
            
            if amount is None or amount <= 0: return await ctx.send("❌ Monto inválido. Puedes usar 'all' o números.", ephemeral=True)
            if amount > bank: return await ctx.send(f"❌ Intentas sacar más de lo que tienes en el banco. (Saldo: **{bank} {emoji}**)", ephemeral=True)
            
            await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=amount, bank_change=-amount)
            await ctx.send(f"🏧 Has retirado **{amount:,} {emoji}** de forma líquida. ¡Cuidado en las calles!")

    @commands.hybrid_command(name='give', aliases=['transfer', 'pay'], description="Págale a un usuario (Impuesto gubernamental de 2% para evitar abusos).")
    async def give(self, ctx: commands.Context, miembro: discord.Member, cantidad: str):
        if miembro.bot: return await ctx.send("🤖 La interfaz de las IAs aún no acepta propinas.")
        if miembro.id == ctx.author.id: return await ctx.send("❌ Acabas de inventar el movimiento perpetuo. No te puedes pagar a ti mismo.")
        
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')

        async with self.get_user_lock(ctx.author.id):
            wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
            amount = parse_amount(cantidad, wallet)
            
            if amount is None or amount <= 0: return await ctx.send("❌ Monto inválido.", ephemeral=True)
            if amount > wallet: return await ctx.send(f"❌ Te falta efectivo en la cartera.", ephemeral=True)
            
            # Anti-Lavado de multicuentas
            impuesto = int(amount * 0.02)
            recibe = amount - impuesto
            
            await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-amount)
            await db.update_balance(ctx.guild.id, miembro.id, wallet_change=recibe)
            await ctx.send(f"💸 Le has entregado **{recibe:,} {emoji}** a {miembro.mention} (impuesto estatal: -{impuesto} {emoji}).")

    # --- INGRESOS ACTIVOS ---
    
    @commands.hybrid_command(name='daily', description="Reclama una buena recompensa que puedes sacar una vez cada día.")
    async def daily(self, ctx: commands.Context):
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        min_d = settings.get('daily_min', 900)
        max_d = settings.get('daily_max', 2000)
        emoji = settings.get('currency_emoji', '🪙')
        
        # Cooldown dinámico manejado manualmente para usar el valor de la DB
        # Nota: discord.py no soporta cooldowns dinámicos nativamente de forma simple sin decoradores complejos.
        # Mantendremos el decorador pero informamos que el admin puede cambiar los rangos.
        # Para el cooldown del trabajo/robo sí lo aplicaremos dinámicamente.
        
        ganancia = random.randint(min_d, max_d)
        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=ganancia)
        embed = discord.Embed(title="📅 Ingreso Diario", description=f"¡Has reclamado tu asistencia del día!\nDisfruta en tu bolsillo: **+{ganancia} {emoji}**", color=discord.Color.brand_green())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='work', description="Ponte a trabajar unas horas para tener efectivo.")
    async def work(self, ctx: commands.Context):
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        cooldown = settings.get('work_cooldown', 3600)
        
        # Bucket manual para cooldown dinámico
        bucket = commands.CooldownMapping.from_cooldown(1, cooldown, commands.BucketType.user).get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            return await ctx.send(f"⏳ Estás agotado. Debes descansar un poco más. Intenta de nuevo en **{int(retry_after/60)}m {int(retry_after%60)}s**.", ephemeral=True)

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
        items = await db.fetchall("SELECT * FROM shop_items WHERE guild_id = ?", (ctx.guild.id,))
        if not items: return await ctx.send("🛒 La tienda está vacía. Vuelve más tarde.", ephemeral=True)
        
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        
        embed = discord.Embed(title="🛒 Tienda del Servidor", description="Usa `/buy <ID>` para comprar un artículo.", color=discord.Color.gold())
        for item in items:
            tipo_humano = "🛡️ Rol de Discord" if item['type'] == 'role' else "🧪 Objeto Consumible"
            embed.add_field(name=f"ID: {item['item_id']} | {item['name']}", value=f"*- {tipo_humano}*\n{item['description']}\n**Precio:** {item['price']:,} {emoji}", inline=False)
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='buy', aliases=['comprar'], description="Compra un artículo de la tienda usando su ID.")
    async def buy(self, ctx: commands.Context, item_id: int):
        await ctx.defer()
        item = await db.fetchone("SELECT * FROM shop_items WHERE item_id = ? AND guild_id = ?", (item_id, ctx.guild.id))
        if not item: return await ctx.send("❌ No existe ningún artículo con esa ID en esta tienda.", ephemeral=True)
        
        settings = await db.get_guild_economy_settings(ctx.guild.id)
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
        query = "SELECT i.quantity, s.name, s.description FROM inventory i JOIN shop_items s ON i.item_id = s.item_id WHERE i.guild_id = ? AND i.user_id = ? AND i.quantity > 0"
        items = await db.fetchall(query, (ctx.guild.id, ctx.author.id))
        
        if not items: return await ctx.send("🎒 Tu mochila está completamente vacía.", ephemeral=True)
        
        embed = discord.Embed(title=f"🎒 Mochila de {ctx.author.display_name}", color=self.bot.CREAM_COLOR)
        for row in items:
            embed.add_field(name=f"{row['quantity']}x {row['name']}", value=row['description'], inline=False)
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='rob', aliases=['robar'], description="Intenta adueñarte de lo que no es tuyo. Altamente riesgoso.")
    async def rob(self, ctx: commands.Context, miembro: discord.Member):
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        cooldown = settings.get('rob_cooldown', 21600)
        
        # Bucket manual para permitir resets y cooldown dinámico
        bucket = commands.CooldownMapping.from_cooldown(1, cooldown, commands.BucketType.user).get_bucket(ctx.message)
        
        if miembro.id == ctx.author.id:
            return await ctx.send("Te quitaste la cartera de tu bolsillo izquierdo para meterla en el derecho. Eres un genio.")
        if miembro.bot:
            return await ctx.send("Robarle a una IA es intentar hackear a la Matrix. Imposible.")
        
        retry_after = bucket.update_rate_limit()
        if retry_after:
            return await ctx.send(f"⏳ El último atraco fue demasiado tenso. La policía te busca. Intenta de nuevo en **{int(retry_after/3600)}h {int((retry_after%3600)/60)}m**.", ephemeral=True)
        
        emoji = settings.get('currency_emoji', '🪙')

        
        async with self.get_user_lock(ctx.author.id):
            robador_w, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
            victima_w, _ = await db.get_balance(ctx.guild.id, miembro.id)
            
            # Anti-Exploits Puras Multas
            if robador_w < 500:
                self.rob.reset_cooldown(ctx)
                return await ctx.send(f"❌ ¡Eres pobre! Necesitas tener al menos **500 {emoji}** en la cartera como fianza por si te atrapa la patrulla.", ephemeral=True)
                
            if victima_w < 200:
                self.rob.reset_cooldown(ctx)
                return await ctx.send(f"❌ Pobrecito de {miembro.display_name}, no trae ni 200 {emoji} para el bus. Búscate un objetivo más grande.", ephemeral=True)


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
            if suerte <= 40: 
                cantidad_robada = int(victima_w * random.uniform(0.1, 0.45))
                if cantidad_robada <= 0: cantidad_robada = 1
                await db.update_balance(ctx.guild.id, miembro.id, wallet_change=-cantidad_robada)
                await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=cantidad_robada)
                embed = discord.Embed(title="🥷 ¡Robo Exitoso!", description=f"Corriste hacia {miembro.mention}, agarraste todo lo que pudiste y huiste con **{cantidad_robada:,} {emoji}**.\n*Ojalá hubieran guardado su fe en su banco*", color=discord.Color.green())
                await ctx.send(embed=embed)
            else: 
                multa = int(robador_w * 0.25) # 25% de la cartera líquida del ladrón
                await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-multa)
                embed = discord.Embed(title="🚓 ¡Fuiste Detenido!", description=f"¡Ups! ¡ {miembro.mention} tiene cinturón negro! Trataste de asaltarle pero te inmovilizó hasta que llegó la patrulla.\nLa jueza te quitó **{multa:,} {emoji}**.", color=discord.Color.red())
                await ctx.send(embed=embed)

    @commands.hybrid_command(name='leaderboard', aliases=['richest'], description="Observa qué personas tienen más estatus que tú.")
    async def leaderboard(self, ctx: commands.Context):
        await ctx.defer()
        query = "SELECT user_id, wallet, bank FROM balances WHERE guild_id = ? ORDER BY (wallet + bank) DESC LIMIT 10"
        top_users = await db.fetchall(query, (ctx.guild.id,))
        
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        
        if not top_users: return await ctx.send("Este lugar parece un desierto económico.")
        
        embed = discord.Embed(title=f"🏆 Los Más Poderosos de {ctx.guild.name} 🏆", color=discord.Color.gold())
        description = ""
        for i, row in enumerate(top_users):
            try:
                user = await self.bot.fetch_user(row['user_id'])
                name = user.display_name
            except discord.NotFound: name = f"User ({row['user_id']})"
            
            net = row['wallet'] + row['bank']
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`{i+1}.`"
            description += f"{rank} **{name}**: {net:,} {emoji}\n"
            
        embed.description = description
        embed.set_footer(text="Basado en el NETO (Cartera Líquida + Banco Segurizado)")
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))