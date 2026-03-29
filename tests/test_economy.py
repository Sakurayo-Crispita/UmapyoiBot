"""Tests para el cog de Economía."""
import pytest
from cogs.economy import EconomyCog
from utils import database_manager as db


@pytest.fixture
def eco_cog(mock_bot):
    return EconomyCog(mock_bot)


class TestWork:
    async def test_work_gives_money(self, eco_cog, mock_ctx):
        await eco_cog.work.callback(eco_cog, mock_ctx)
        wallet, _ = await db.get_balance(mock_ctx.guild.id, mock_ctx.author.id)
        assert wallet > 100  # default start_balance es 100

    async def test_work_cooldown(self, eco_cog, mock_ctx):
        await eco_cog.work.callback(eco_cog, mock_ctx)
        wallet_after_first, _ = await db.get_balance(mock_ctx.guild.id, mock_ctx.author.id)

        # Resetear respuestas para la segunda llamada
        mock_ctx.responses.clear()
        mock_ctx.ephemeral_responses.clear()

        await eco_cog.work.callback(eco_cog, mock_ctx)
        wallet_after_second, _ = await db.get_balance(mock_ctx.guild.id, mock_ctx.author.id)

        # El wallet no debió subir por cooldown
        assert wallet_after_second == wallet_after_first
        assert any("cansado" in msg.lower() or "tired" in msg.lower() 
                    for msg in mock_ctx.ephemeral_responses)


class TestBalance:
    async def test_balance_shows_info(self, eco_cog, mock_ctx):
        await eco_cog.balance.callback(eco_cog, mock_ctx)
        assert len(mock_ctx.embeds_sent) >= 1

    async def test_balance_bot_rejection(self, eco_cog, mock_ctx, mock_guild):
        from tests.conftest import MockMember
        bot_user = MockMember(888, "BotUser", mock_guild)
        bot_user.bot = True
        await eco_cog.balance.callback(eco_cog, mock_ctx, miembro=bot_user)
        assert any("bots" in msg.lower() or "consciencia" in msg.lower() 
                    for msg in mock_ctx.responses)


class TestDeposit:
    async def test_deposit_amount(self, eco_cog, mock_ctx):
        await db.update_balance(mock_ctx.guild.id, mock_ctx.author.id, wallet_change=500)
        await eco_cog.deposit.callback(eco_cog, mock_ctx, cantidad="200")
        wallet, bank = await db.get_balance(mock_ctx.guild.id, mock_ctx.author.id)
        assert bank == 200
        assert wallet == 400  # 600 - 200

    async def test_deposit_all(self, eco_cog, mock_ctx):
        await db.update_balance(mock_ctx.guild.id, mock_ctx.author.id, wallet_change=500)
        await eco_cog.deposit.callback(eco_cog, mock_ctx, cantidad="all")
        wallet, bank = await db.get_balance(mock_ctx.guild.id, mock_ctx.author.id)
        assert wallet == 0
        assert bank > 0


class TestWithdraw:
    async def test_withdraw_amount(self, eco_cog, mock_ctx):
        await db.update_balance(mock_ctx.guild.id, mock_ctx.author.id, bank_change=500)
        await eco_cog.withdraw.callback(eco_cog, mock_ctx, cantidad="200")
        wallet, bank = await db.get_balance(mock_ctx.guild.id, mock_ctx.author.id)
        assert bank == 300


class TestAdminCommands:
    async def test_add_money(self, eco_cog, mock_ctx, mock_target):
        await eco_cog.add_money.callback(eco_cog, mock_ctx, miembro=mock_target, cantidad=1000)
        wallet, _ = await db.get_balance(mock_ctx.guild.id, mock_target.id)
        assert wallet == 1100  # 100 start + 1000

    async def test_add_money_zero_rejected(self, eco_cog, mock_ctx, mock_target):
        await eco_cog.add_money.callback(eco_cog, mock_ctx, miembro=mock_target, cantidad=0)
        assert any("mayor a 0" in msg for msg in mock_ctx.ephemeral_responses)

    async def test_remove_money(self, eco_cog, mock_ctx, mock_target):
        await db.update_balance(mock_ctx.guild.id, mock_target.id, wallet_change=500)
        await eco_cog.remove_money.callback(eco_cog, mock_ctx, miembro=mock_target, cantidad=200)
        wallet, _ = await db.get_balance(mock_ctx.guild.id, mock_target.id)
        assert wallet == 400  # 600 - 200

    async def test_set_currency(self, eco_cog, mock_ctx):
        await eco_cog.set_currency.callback(eco_cog, mock_ctx, nombre="gemas", emoji="💎")
        settings = await db.get_guild_economy_settings(mock_ctx.guild.id)
        assert settings['currency_name'] == "gemas"
        assert settings['currency_emoji'] == "💎"

    async def test_config_work(self, eco_cog, mock_ctx):
        await eco_cog.config_work.callback(eco_cog, mock_ctx, min_paga=100, max_paga=500, segundos_espera=1800)
        settings = await db.get_guild_economy_settings(mock_ctx.guild.id)
        assert settings['work_min'] == 100
        assert settings['work_max'] == 500
        assert settings['work_cooldown'] == 1800

    async def test_config_work_invalid(self, eco_cog, mock_ctx):
        await eco_cog.config_work.callback(eco_cog, mock_ctx, min_paga=500, max_paga=100, segundos_espera=60)
        assert any("inválidos" in msg.lower() for msg in mock_ctx.ephemeral_responses)


class TestMaxBank:
    async def test_max_bank_scales_with_level(self, eco_cog, mock_ctx):
        await db.get_user_level(mock_ctx.guild.id, mock_ctx.author.id)
        max_bank_l1 = await eco_cog.get_max_bank(mock_ctx.guild.id, mock_ctx.author.id)
        
        await db.update_user_xp(mock_ctx.guild.id, mock_ctx.author.id, 10, 0)
        max_bank_l10 = await eco_cog.get_max_bank(mock_ctx.guild.id, mock_ctx.author.id)
        
        assert max_bank_l10 > max_bank_l1
