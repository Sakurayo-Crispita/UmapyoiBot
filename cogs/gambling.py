import discord
from discord.ext import commands
import random
from typing import Optional

# Importamos el gestor de base de datos
from utils import database_manager as db

class BlackJackView(discord.ui.View):
    # ... (El código de la vista de Blackjack no necesita cambios)
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
            await interaction.response.send_message("No puedes interactuar con el juego de otra persona.", ephemeral=True, delete_after=10)
            return False
        return True

    async def on_timeout(self):
        for item in self.children: item.disabled = True
        timeout_embed = self.create_embed()
        timeout_embed.description = "⌛ El juego ha terminado por inactividad."
        if self.message:
            try: await self.message.edit(embed=timeout_embed, view=self)
            except: pass

    def update_buttons(self):
        if self.cog.calculate_score(self.player_hand) >= 21:
            for item in self.children:
                if isinstance(item, discord.ui.Button): item.disabled = True

    @discord.ui.button(label="Pedir Carta", style=discord.ButtonStyle.success, emoji="➕")
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
        embed = discord.Embed(title="🃏 Blackjack", color=self.cog.bot.CREAM_COLOR)
        embed.add_field(name=f"Tu Mano ({player_score})", value=" ".join(self.player_hand), inline=False)
        if show_dealer_card:
            embed.add_field(name=f"Mano del Bot ({dealer_score})", value=" ".join(self.dealer_hand), inline=False)
        else:
            embed.add_field(name="Mano del Bot (?)", value=f"{self.dealer_hand[0]} ❔", inline=False)
        embed.set_footer(text=f"Apuesta: {self.bet}")
        return embed


class GamblingCog(commands.Cog, name="Juegos de Apuestas"):
    """Juegos para apostar tus créditos y probar tu suerte."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cards = ['🇦', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟', '🇯', '🇶', '🇰']
        self.card_values = {'🇦': 11, '2️⃣': 2, '3️⃣': 3, '4️⃣': 4, '5️⃣': 5, '6️⃣': 6, '7️⃣': 7, '8️⃣': 8, '9️⃣': 9, '🔟': 10, '🇯': 10, '🇶': 10, '🇰': 10}

    # --- Las funciones de base de datos se han eliminado de aquí ---

    async def can_gamble(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
            
        economy_cog = self.bot.get_cog("Economía")
        if not economy_cog or not await economy_cog.is_economy_active(ctx):
             await ctx.send("El sistema de economía debe estar activo para poder apostar.", ephemeral=True)
             return False

        # Usamos el gestor de DB
        active_channels_rows = await db.fetchall("SELECT channel_id FROM gambling_active_channels WHERE guild_id = ?", (ctx.guild.id,))
        active_channels = [r['channel_id'] for r in active_channels_rows]

        if not active_channels:
            if ctx.author.guild_permissions.administrator:
                await ctx.send("No se ha designado ningún canal para las apuestas. Usa `/gambling addchannel`.", ephemeral=True)
            return False

        if ctx.channel.id not in active_channels:
            if not ctx.author.guild_permissions.manage_guild:
                await ctx.send("Los juegos de apuestas solo están permitidos en los canales designados.", ephemeral=True)
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

        if player_score > 21:
            result_message = f"Te pasaste de 21. ¡Perdiste **{view.bet}**!"
            await db.update_balance(interaction.guild.id, interaction.user.id, wallet_change=-view.bet)
        elif dealer_score > 21 or player_score > dealer_score:
            result_message = f"¡Ganaste! Recibes **{view.bet * 2}**."
            await db.update_balance(interaction.guild.id, interaction.user.id, wallet_change=view.bet)
        elif player_score < dealer_score:
            result_message = f"El bot gana. ¡Perdiste **{view.bet}**!"
            await db.update_balance(interaction.guild.id, interaction.user.id, wallet_change=-view.bet)
        else:
            result_message = "¡Es un empate! Recuperas tu apuesta."

        final_embed = view.create_embed(show_dealer_card=True)
        final_embed.description = result_message
        await interaction.edit_original_response(embed=final_embed, view=view)

    @commands.hybrid_group(name="gambling", description="Configura los canales para los juegos de apuestas.")
    @commands.has_permissions(administrator=True)
    async def gambling(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            active_channels_rows = await db.fetchall("SELECT channel_id FROM gambling_active_channels WHERE guild_id = ?", (ctx.guild.id,))
            channels_list = "\n".join([f"<#{r['channel_id']}>" for r in active_channels_rows]) if active_channels_rows else "Ninguno"
            embed = discord.Embed(title="🎲 Configuración de Apuestas", color=self.bot.CREAM_COLOR)
            embed.add_field(name="Canales de Apuestas Activos", value=channels_list)
            await ctx.send(embed=embed, ephemeral=True)

    @gambling.command(name="addchannel", description="Permite los juegos de apuestas en un canal.")
    async def add_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        await db.execute("INSERT OR IGNORE INTO gambling_active_channels (guild_id, channel_id) VALUES (?, ?)", (ctx.guild.id, canal.id))
        await ctx.send(f"✅ Los juegos de apuestas ahora están permitidos en {canal.mention}.", ephemeral=True)

    @gambling.command(name="removechannel", description="Prohíbe los juegos de apuestas en un canal.")
    async def remove_channel(self, ctx: commands.Context, canal: discord.TextChannel):
        await db.execute("DELETE FROM gambling_active_channels WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, canal.id))
        await ctx.send(f"❌ Los juegos de apuestas ya no están permitidos en {canal.mention}.", ephemeral=True)

    @commands.hybrid_command(name='blackjack', description="Juega una partida de Blackjack apostando.")
    async def blackjack(self, ctx: commands.Context, apuesta: int):
        if not await self.can_gamble(ctx): return

        balance, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
        if apuesta <= 0: return await ctx.send("La apuesta debe ser mayor que cero.", ephemeral=True)
        if balance < apuesta: return await ctx.send(f"No tienes suficiente para esa apuesta. Tu cartera: **{balance}**", ephemeral=True)

        view = BlackJackView(self, ctx, apuesta)
        msg = await ctx.send(embed=view.create_embed(), view=view)
        view.message = msg

    @commands.hybrid_command(name='tragamonedas', aliases=['slots'], description="Prueba tu suerte en la máquina tragamonedas.")
    async def slots(self, ctx: commands.Context, apuesta: int):
        if not await self.can_gamble(ctx): return
        
        await ctx.defer()
        balance, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
        if apuesta <= 0: return await ctx.send("La apuesta debe ser mayor que cero.", ephemeral=True)
        if balance < apuesta: return await ctx.send(f"No tienes suficiente. Tu cartera: **{balance}**", ephemeral=True)

        emojis = ["🍒", "🔔", "🍋", "⭐", "💎", "🍀"]
        reels = [random.choice(emojis) for _ in range(3)]
        result_text = f"**[ {reels[0]} | {reels[1]} | {reels[2]} ]**"

        if reels[0] == reels[1] == reels[2]:
            winnings = apuesta * 10
            result_text += f"\n\n**¡JACKPOT!** ¡Ganaste **{winnings}**!"
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            winnings = apuesta * 2
            result_text += f"\n\n¡Dos iguales! ¡Ganaste **{winnings}**!"
        else:
            winnings = 0
            result_text += "\n\n¡Mala suerte! Perdiste tu apuesta."
        
        net_change = winnings - apuesta
        new_balance, _ = await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=net_change)

        embed = discord.Embed(title="🎰 Tragamonedas 🎰", description=result_text, color=self.bot.CREAM_COLOR)
        embed.set_footer(text=f"Apostaste {apuesta}. Tu nuevo balance: {new_balance}")
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(GamblingCog(bot))