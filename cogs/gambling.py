import discord
from discord.ext import commands
import random
import asyncio
from typing import Optional

# Importamos el gestor de base de datos
from utils import database_manager as db

class BlackJackView(discord.ui.View):
    def __init__(self, cog: 'GamblingCog', ctx: commands.Context, bet: int):
        super().__init__(timeout=120.0)
        self.cog = cog
        self.author = ctx.author
        self.bet = bet
        self.player_hand = [self.cog.deal_card(), self.cog.deal_card()]
        self.dealer_hand = [self.cog.deal_card(), self.cog.deal_card()]
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("No puedes jugar en la mesa de otra persona.", ephemeral=True, delete_after=10)
            return False
        return True

    async def on_timeout(self):
        for item in self.children: item.disabled = True
        timeout_embed = self.create_embed()
        timeout_embed.description = "⌛ El crupier ha cerrado la mesa por inactividad. Recuperas tu apuesta."
        if self.message:
            try: await self.message.edit(embed=timeout_embed, view=self)
            except: pass

    def update_buttons(self):
        if self.cog.calculate_score(self.player_hand) >= 21:
            for item in self.children:
                if isinstance(item, discord.ui.Button): item.disabled = True

    @discord.ui.button(label="Pedir", style=discord.ButtonStyle.success, emoji="➕")
    async def hit(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.player_hand.append(self.cog.deal_card())
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
        if self.cog.calculate_score(self.player_hand) >= 21:
            await self.cog.end_blackjack_game(interaction, self)

    @discord.ui.button(label="Plantarse", style=discord.ButtonStyle.danger, emoji="🛑")
    async def stand(self, interaction: discord.Interaction, _: discord.ui.Button):
        for item in self.children: item.disabled = True
        await interaction.response.edit_message(view=self)
        await self.cog.end_blackjack_game(interaction, self)

    def create_embed(self, show_dealer_card=False):
        player_score = self.cog.calculate_score(self.player_hand)
        dealer_score = self.cog.calculate_score(self.dealer_hand)
        embed = discord.Embed(title="🃏 Blackjack Casino", color=self.cog.bot.CREAM_COLOR)
        embed.add_field(name=f"Tu Mano ({player_score})", value=" ".join(self.player_hand), inline=False)
        if show_dealer_card:
            embed.add_field(name=f"Crupier ({dealer_score})", value=" ".join(self.dealer_hand), inline=False)
        else:
            embed.add_field(name="Crupier (?)", value=f"{self.dealer_hand[0]} ❔", inline=False)
        embed.set_footer(text=f"Apuesta Inicial: {self.bet:,}")
        return embed

class GamblingCog(commands.Cog, name="Juegos de Azar"):
    """Juegos para apostar y multiplicar (o perder) el dinero de tu cartera."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cards = ['🇦', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟', '🇯', '🇶', '🇰']
        self.card_values = {'🇦': 11, '2️⃣': 2, '3️⃣': 3, '4️⃣': 4, '5️⃣': 5, '6️⃣': 6, '7️⃣': 7, '8️⃣': 8, '9️⃣': 9, '🔟': 10, '🇯': 10, '🇶': 10, '🇰': 10}

    async def can_gamble(self, ctx: commands.Context) -> bool:
        """Verifica si el usuario puede apostar en este canal."""
        active_channels_rows = await db.fetchall("SELECT channel_id FROM gambling_active_channels WHERE guild_id = ?", (ctx.guild.id,))
        active_channels = [r['channel_id'] for r in active_channels_rows]

        if not active_channels:
            if ctx.author.guild_permissions.administrator:
                await ctx.send("⚙️ El casino está cerrado. Configura canales con `/gambling addchannel`.", ephemeral=True)
            else:
                await ctx.send("⚙️ El casino ha sido cerrado por los administradores.", ephemeral=True)
            return False

        if ctx.channel.id not in active_channels:
            if not ctx.author.guild_permissions.manage_guild:
                await ctx.send("🎲 Los juegos de apuestas solo están permitidos en los canales exclusivos del casino.", ephemeral=True)
            return False
            
        return True

    def deal_card(self):
        return random.choice(self.cards)

    def calculate_score(self, hand):
        score = sum(self.card_values[card] for card in hand)
        aces = hand.count('🇦')
        while score > 21 and aces:
            score -= 10
            aces -= 1
        return score

    async def end_blackjack_game(self, interaction: discord.Interaction, view: BlackJackView):
        player_score = self.calculate_score(view.player_hand)
        while self.calculate_score(view.dealer_hand) < 17:
            view.dealer_hand.append(self.deal_card())
        dealer_score = self.calculate_score(view.dealer_hand)

        settings = await db.get_guild_economy_settings(interaction.guild.id)
        emoji = settings.get('currency_emoji', '🪙')

        # Resolviendo la apuesta contra la DB de forma segura
        
        if player_score > 21:
            result_message = f"Te pasaste de 21. ¡Perdiste tus **{view.bet:,} {emoji}**!"
            await db.update_balance(interaction.guild.id, interaction.user.id, wallet_change=-view.bet)
        elif dealer_score > 21 or player_score > dealer_score:
            ganancia = view.bet # Gana el 100% de lo apostado (devuelve apuesta + ganancia)
            result_message = f"¡Le has ganado al Crupier! ¡Ganas **{ganancia:,} {emoji}** netos!"
            await db.update_balance(interaction.guild.id, interaction.user.id, wallet_change=view.bet)
        elif player_score < dealer_score:
            result_message = f"El Crupier gana. ¡Perdiste tus **{view.bet:,} {emoji}**!"
            await db.update_balance(interaction.guild.id, interaction.user.id, wallet_change=-view.bet)
        else:
            result_message = "Mismo puntaje, ha sido un Empate (Push). Se te devuelve tu dinero."
            # Al ser un empate, no debitamos ni sumamos en el balance real.

        final_embed = view.create_embed(show_dealer_card=True)
        final_embed.description = result_message
        await interaction.edit_original_response(embed=final_embed, view=view)

    @commands.hybrid_group(name="gambling", description="Configura los canales para los juegos de casino.")
    @commands.has_permissions(administrator=True)
    async def gambling(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            active_channels_rows = await db.fetchall("SELECT channel_id FROM gambling_active_channels WHERE guild_id = ?", (ctx.guild.id,))
            channels_list = "\n".join([f"<#{r['channel_id']}>" for r in active_channels_rows]) if active_channels_rows else "Ninguno"
            embed = discord.Embed(title="🎲 Configuración del Casino", color=self.bot.CREAM_COLOR)
            embed.add_field(name="Zonas de Apuestas Activas", value=channels_list)
            await ctx.send(embed=embed, ephemeral=True)

    @gambling.command(name="addchannel", description="Señala este canal como una zona válida para apuestas.")
    async def add_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        await db.execute("INSERT OR IGNORE INTO gambling_active_channels (guild_id, channel_id) VALUES (?, ?)", (ctx.guild.id, canal.id))
        await ctx.send(f"✅ Has inaugurado el casino oficial en {canal.mention}.", ephemeral=True)

    @gambling.command(name="removechannel", description="Prohíbe los juegos de casino en este u otro canal.")
    async def remove_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        await db.execute("DELETE FROM gambling_active_channels WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, canal.id))
        await ctx.send(f"❌ Se ha clausurado el casino de {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name='blackjack', description="Echa una partida de cartas contra la casa.")
    async def blackjack(self, ctx: commands.Context, apuesta: int):
        if not await self.can_gamble(ctx): return

        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')

        if apuesta <= 0: return await ctx.send("❌ Apuesta algo más que aire vacío.", ephemeral=True)
        if apuesta > 100000: return await ctx.send("❌ La casa limita las apuestas de Blackjack a 100,000 máximo para evitar bancarrota.", ephemeral=True)

        wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
        if wallet < apuesta: return await ctx.send(f"❌ Efectivo insuficiente en la cartera. (Tienes **{wallet:,} {emoji}**)", ephemeral=True)

        view = BlackJackView(self, ctx, apuesta)
        msg = await ctx.send(embed=view.create_embed(), view=view)
        view.message = msg

    @commands.hybrid_command(name='tragamonedas', aliases=['slots'], description="Apuesta la cartera en la máquina de la suerte.")
    async def slots(self, ctx: commands.Context, apuesta: int):
        if not await self.can_gamble(ctx): return
        await ctx.defer()
        
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')

        if apuesta <= 0: return await ctx.send("❌ Inserta al menos 1 moneda.", ephemeral=True)
        if apuesta > 100000: return await ctx.send("❌ La máquina tragamonedas solo acepta hasta 100,000 por tirada.", ephemeral=True)
        
        wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
        if wallet < apuesta: return await ctx.send(f"❌ Efectivo insuficiente en tu cartera. (Tienes **{wallet:,} {emoji}**)", ephemeral=True)

        # Configuración "House Edge": Para que la economía no se infle desmedidamente por el trabajo diario.
        emojis = ["🍒", "🔔", "🍋", "⭐", "💎", "🍀", "🍇", "💩"]
        
        reels = [random.choice(emojis) for _ in range(3)]
        
        # Micro-trampa para aumentar las ganancias de la máquina (House Edge)
        hack = random.randint(1, 100)
        if hack <= 10 and reels[0] == reels[1] == reels[2]:
            reels[2] = random.choice(emojis) # Rompemos el jackpot de forma sigilosa
            
        result_text = f"**[ {reels[0]}  |  {reels[1]}  |  {reels[2]} ]**"

        if reels[0] == reels[1] == reels[2]:
            if reels[0] == "💎": winnings = apuesta * 20 # Súper jackpot
            elif reels[0] == "💩": winnings = 1 # Premio troleo
            else: winnings = apuesta * 7
            result_text += f"\n\n**¡JACKPOT ABSOLUTO!** ¡El sistema escupe **{winnings:,} {emoji}**!"
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            # Dos iguales
            winnings = int(apuesta * 1.5)
            result_text += f"\n\n¡Casi! Tienes dos iguales y ganas **{winnings:,} {emoji}**."
        else:
            winnings = 0
            result_text += "\n\n¡Mala suerte, tira otra vez! Perdiste tu apuesta de **{apuesta:,}**."
        
        # Cálculo de dinero
        net_change = winnings - apuesta
        new_wallet, _ = await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=net_change)

        embed = discord.Embed(title="🎰 Tragamonedas Intergaláctica 🎰", description=result_text, color=self.bot.CREAM_COLOR)
        embed.set_footer(text=f"Tu nueva cartera: {new_wallet:,} {emoji}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='coinflip', aliases=['cf'], description="Apuesta al todo o nada lanzando una moneda al aire.")
    async def coinflip(self, ctx: commands.Context, apuesta: int, cara_o_cruz: str):
        if not await self.can_gamble(ctx): return
        
        choice = cara_o_cruz.lower()
        if choice not in ['cara', 'cruz', 'heads', 'tails']:
            return await ctx.send("❌ Debes elegir verbalmente `cara` o `cruz`.", ephemeral=True)
            
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji_currency = settings.get('currency_emoji', '🪙')

        if apuesta <= 0: return await ctx.send("❌ Apostar sentimientos no es válido aquí.", ephemeral=True)

        wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
        if wallet < apuesta: return await ctx.send(f"❌ Efectivo insuficiente en tu cartera. (Tienes **{wallet:,} {emoji_currency}**)", ephemeral=True)

        # Convertir a texto estandarizado
        if choice == 'heads': choice = 'cara'
        if choice == 'tails': choice = 'cruz'

        coin_faces = ['cara', 'cruz']
        # El bot lanza la moneda
        result = random.choice(coin_faces)
        
        # Calculamos si ganó o perdió
        if choice == result:
            ganancia = apuesta
            new_wallet, _ = await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=ganancia)
            desc = f"La moneda voló y cayó en **{result.upper()}**.\n\n🎉 ¡Has acertado con precisión milimétrica! Te llevas tu ganancia de **{ganancia:,} {emoji_currency}**."
            color = discord.Color.green()
        else:
            new_wallet, _ = await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-apuesta)
            desc = f"La moneda dio volteretas y cayó en **{result.upper()}**.\n\n❌ Has fallado la predicción. Perdiste dramáticamente tu apuesta de **{apuesta:,} {emoji_currency}**."
            color = discord.Color.red()
            
        embed = discord.Embed(title="🪙 Lanzamiento de Moneda", description=desc, color=color)
        embed.set_thumbnail(url="https://i.imgur.com/vHq0A6U.gif") # Un gif genérico de una moneda
        embed.set_footer(text=f"Cartera Remanente: {new_wallet:,}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='horse_race', aliases=['carrera'], description="Apuesta en una carrera de caballos interactiva.")
    async def horse_race(self, ctx: commands.Context, apuesta: int, caballo: int):
        if not await self.can_gamble(ctx): return
        
        if caballo not in [1, 2, 3, 4]:
            return await ctx.send("❌ Elige un caballo válido: 1, 2, 3 o 4.", ephemeral=True)
            
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji_currency = settings.get('currency_emoji', '🪙')

        if apuesta <= 0: return await ctx.send("❌ Apostar sentimientos no es válido aquí.", ephemeral=True)
        if apuesta > 100000: return await ctx.send("❌ El hipódromo limita las apuestas a 100,000 máximo.", ephemeral=True)
        
        wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
        if wallet < apuesta: return await ctx.send(f"❌ Efectivo insuficiente en tu cartera. (Tienes **{wallet:,} {emoji_currency}**)", ephemeral=True)

        # Cobro por adelantado para evitar exploits de duplicado durante el delay
        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-apuesta)
        
        # Carrera de caballos visual
        pista_length = 15
        caballos = [0, 0, 0, 0] 
        
        def render_pista():
            lines = []
            for i in range(4):
                pos = caballos[i]
                espacios_antes = " " * pos
                espacios_despues = " " * (pista_length - pos)
                if i + 1 == caballo:
                    lines.append(f"**Carril {i+1}:** 🏁{espacios_despues}🐴{espacios_antes} (Tú)")
                else:
                    lines.append(f"**Carril {i+1}:** 🏁{espacios_despues}🐴{espacios_antes}")
            return "\n".join(lines)
            
        embed = discord.Embed(title="🏇 Carrera de Caballos", description=f"Preparando la carrera...\nApostaste **{apuesta:,} {emoji_currency}** al caballo **{caballo}**.\n\n```text\n{render_pista()}\n```", color=self.bot.CREAM_COLOR)
        msg = await ctx.send(embed=embed)
        
        await asyncio.sleep(2)
        
        ganador = None
        while True:
            for i in range(4):
                caballos[i] += random.randint(1, 3)
                if caballos[i] >= pista_length:
                    caballos[i] = pista_length
                    if ganador is None:
                        ganador = i + 1
            
            embed.description = f"¡La carrera está en marcha!\nApostaste al caballo **{caballo}**.\n\n```text\n{render_pista()}\n```"
            await msg.edit(embed=embed)
            
            if ganador is not None:
                break
            await asyncio.sleep(1.5)
            
        if ganador == caballo:
            ganancia_total = int(apuesta * 3.5) # Devuelve su apuesta + ganancia (2.5x netos)
            new_wallet, _ = await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=ganancia_total)
            embed.description += f"\n\n🎉 ¡Tu caballo finalizó en **primer lugar**! Ganaste **{ganancia_total:,} {emoji_currency}**."
            embed.color = discord.Color.green()
        else:
            new_wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
            embed.description += f"\n\n❌ El caballo **{ganador}** cruzó la meta primero. Perdiste tu apuesta de **{apuesta:,} {emoji_currency}**."
            embed.color = discord.Color.red()
            
        embed.set_footer(text=f"Cartera Remanente: {new_wallet:,} {emoji_currency}")
        await msg.edit(embed=embed)

    @commands.hybrid_command(name='roulette', aliases=['ruleta'], description="Gira la ruleta clásica. Elige rojo, negro, verde o un número (0-36).")
    async def roulette(self, ctx: commands.Context, apuesta: int, eleccion: str):
        if not await self.can_gamble(ctx): return
        
        eleccion = eleccion.lower()
        opciones_validas = ['rojo', 'negro', 'verde'] + [str(i) for i in range(0, 37)]
        if eleccion not in opciones_validas:
            return await ctx.send("❌ Elige: `rojo`, `negro`, `verde`, o un número del `0` al `36`.", ephemeral=True)
            
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji_currency = settings.get('currency_emoji', '🪙')

        if apuesta <= 0: return await ctx.send("❌ Apuesta algo de verdad.", ephemeral=True)
        wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
        if wallet < apuesta: return await ctx.send(f"❌ Efectivo insuficiente. (Tienes **{wallet:,} {emoji_currency}**)", ephemeral=True)

        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-apuesta)
        
        num = random.randint(0, 36)
        rojos = [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
        color = 'verde' if num == 0 else ('rojo' if num in rojos else 'negro')
        
        color_emojis = {'rojo': '🔴', 'negro': '⚫', 'verde': '🟢'}
        emoji_bola = color_emojis[color]
        
        ganancia_total = 0
        if eleccion == str(num): # Pleno
            ganancia_total = apuesta * 36
        elif eleccion == color:
            if color == 'verde': ganancia_total = apuesta * 14
            else: ganancia_total = apuesta * 2
            
        if ganancia_total > 0:
            new_wallet, _ = await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=ganancia_total)
            desc = f"La bola gira y cae en... **{num} {color.upper()} {emoji_bola}**\n\n🎉 ¡Acertaste tu apuesta a **{eleccion}**! Ganaste **{ganancia_total:,} {emoji_currency}**."
            color_embed = discord.Color.green()
        else:
            new_wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
            desc = f"La bola gira y cae en... **{num} {color.upper()} {emoji_bola}**\n\n❌ Apostaste a **{eleccion}**, pierdes tus **{apuesta:,} {emoji_currency}**."
            color_embed = discord.Color.red()
            
        embed = discord.Embed(title="🎡 Ruleta de Casino", description=desc, color=color_embed)
        embed.set_footer(text=f"Cartera: {new_wallet:,} {emoji_currency} | House Edge Activo")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='russian_roulette', aliases=['ruleta_rusa'], description="Alta tensión. Un revólver, una bala, 6 recámaras. Supervivencia pura.")
    async def russian_roulette(self, ctx: commands.Context, apuesta: int):
        if not await self.can_gamble(ctx): return
        
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')

        if apuesta <= 0: return await ctx.send("❌ No puedes jugar gratis.", ephemeral=True)
        wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
        if wallet < apuesta: return await ctx.send(f"❌ Efectivo insuficiente. (Tienes **{wallet:,} {emoji}**)", ephemeral=True)

        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-apuesta)
        
        embed = discord.Embed(title="🔫 Ruleta Rusa", description="Has puesto el revólver en tu cabeza y girado el tambor...\n\n*Click...*", color=self.bot.CREAM_COLOR)
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(2.5)
        
        # 1 bala, 6 recámaras (1/6 de morir)
        muerto = random.randint(1, 6) == 1
        
        if muerto:
            new_wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
            embed.description = f"**B A N G !** 💥\n\nHas muerto. La bala estaba en esa recámara. Toda tu apuesta de **{apuesta:,} {emoji}** está manchada de sangre."
            embed.color = discord.Color.dark_red()
        else:
            ganancia_total = int(apuesta * 1.15) # Retorna el 115% de lo apostado (+15% de fee por supervivencia)
            new_wallet, _ = await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=ganancia_total)
            embed.description = f"**Click.** 💨\n\nSobreviviste. Había una recámara vacía. Te llevas tu apuesta de vuelta y además ganas un bono de supervivencia. Recibes **{ganancia_total:,} {emoji}**."
            embed.color = discord.Color.green()
            
        embed.set_thumbnail(url="https://i.imgur.com/vHq0A6U.gif" if not muerto else "https://static.wikia.nocookie.net/minecraft_gamepedia/images/1/1b/Explosion.gif")
        embed.set_footer(text=f"Cartera Remanente: {new_wallet:,} {emoji}")
        await msg.edit(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(GamblingCog(bot))