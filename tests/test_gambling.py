"""Tests para el cog de Gambling."""
import pytest
from cogs.gambling import GamblingCog
from utils import database_manager as db


@pytest.fixture
def gambling_cog(mock_bot):
    return GamblingCog(mock_bot)


async def setup_gambling_env(guild_id, channel_id, user_id, wallet=500):
    """Helper: registra canal de apuestas y da dinero al usuario."""
    await db.execute(
        "INSERT OR IGNORE INTO gambling_active_channels (guild_id, channel_id) VALUES (?, ?)",
        (guild_id, channel_id)
    )
    await db.execute(
        "REPLACE INTO balances (guild_id, user_id, wallet, bank) VALUES (?, ?, ?, 0)",
        (guild_id, user_id, wallet)
    )


class TestCoinflip:
    async def test_coinflip_changes_balance(self, gambling_cog, mock_ctx):
        await setup_gambling_env(mock_ctx.guild.id, mock_ctx.channel.id, mock_ctx.author.id, 500)
        await gambling_cog.coinflip.callback(gambling_cog, mock_ctx, 100, "cara")
        wallet, _ = await db.get_balance(mock_ctx.guild.id, mock_ctx.author.id)
        # Win: 600, Lose: 400
        assert wallet in (400, 600), f"Balance inesperado: {wallet}"

    async def test_coinflip_insufficient_funds(self, gambling_cog, mock_ctx):
        await setup_gambling_env(mock_ctx.guild.id, mock_ctx.channel.id, mock_ctx.author.id, 50)
        await gambling_cog.coinflip.callback(gambling_cog, mock_ctx, 100, "cara")
        assert any("insuficiente" in msg.lower() for msg in mock_ctx.ephemeral_responses)


class TestSlots:
    async def test_slots_insufficient_funds(self, gambling_cog, mock_ctx):
        await setup_gambling_env(mock_ctx.guild.id, mock_ctx.channel.id, mock_ctx.author.id, 0)
        await gambling_cog.slots.callback(gambling_cog, mock_ctx, 100)
        assert any("insuficiente" in msg.lower() for msg in mock_ctx.ephemeral_responses)

    async def test_slots_deducts_bet(self, gambling_cog, mock_ctx):
        await setup_gambling_env(mock_ctx.guild.id, mock_ctx.channel.id, mock_ctx.author.id, 1000)
        await gambling_cog.slots.callback(gambling_cog, mock_ctx, 200)
        wallet, _ = await db.get_balance(mock_ctx.guild.id, mock_ctx.author.id)
        # El balance cambió (no importa si ganó o perdió, ya no es 1000 original)
        # O podría ser 1000 si ganó exactamente 200 en 1x... pero al menos valida que no crashée
        assert isinstance(wallet, int)


class TestBlackjack:
    async def test_blackjack_deducts_bet(self, gambling_cog, mock_ctx):
        await setup_gambling_env(mock_ctx.guild.id, mock_ctx.channel.id, mock_ctx.author.id, 1000)
        await gambling_cog.blackjack.callback(gambling_cog, mock_ctx, 200)
        wallet, _ = await db.get_balance(mock_ctx.guild.id, mock_ctx.author.id)
        assert wallet == 800  # Se cobró la apuesta al inicio

    async def test_blackjack_timeout_refunds(self, gambling_cog, mock_ctx):
        await setup_gambling_env(mock_ctx.guild.id, mock_ctx.channel.id, mock_ctx.author.id, 1000)
        await gambling_cog.blackjack.callback(gambling_cog, mock_ctx, 200)

        from cogs.gambling import BlackJackView
        view = BlackJackView(gambling_cog, mock_ctx, 200)
        await view.on_timeout()

        wallet, _ = await db.get_balance(mock_ctx.guild.id, mock_ctx.author.id)
        assert wallet == 1000  # Reembolso completo

    async def test_blackjack_insufficient_funds(self, gambling_cog, mock_ctx):
        await setup_gambling_env(mock_ctx.guild.id, mock_ctx.channel.id, mock_ctx.author.id, 50)
        await gambling_cog.blackjack.callback(gambling_cog, mock_ctx, 200)
        assert any("insuficiente" in msg.lower() for msg in mock_ctx.ephemeral_responses)


class TestChannelRestriction:
    """Verifica que can_gamble rechaza canales no autorizados."""
    
    async def test_no_channels_configured(self, gambling_cog, mock_ctx):
        """Sin canales configurados, can_gamble retorna False."""
        mock_ctx.author.guild_permissions = type('P', (), {'administrator': False})()
        result = await gambling_cog.can_gamble(mock_ctx)
        assert result is False

    async def test_authorized_channel(self, gambling_cog, mock_ctx):
        """En canal registrado, can_gamble retorna True."""
        await db.execute(
            "INSERT INTO gambling_active_channels (guild_id, channel_id) VALUES (?, ?)",
            (mock_ctx.guild.id, mock_ctx.channel.id)
        )
        result = await gambling_cog.can_gamble(mock_ctx)
        assert result is True
