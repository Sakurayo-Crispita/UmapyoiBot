import pytest
import discord
from cogs.gambling import GamblingCog
from utils import database_manager as db

@pytest.fixture
def gambling_cog(mock_bot):
    return GamblingCog(mock_bot)

async def test_coinflip_logic(gambling_cog, mock_ctx):
    # Registrar el canal como activo para apuestas y dar dinero
    await db.execute("INSERT INTO gambling_active_channels (guild_id, channel_id) VALUES (?, ?)", (mock_ctx.guild.id, mock_ctx.channel.id))
    await db.execute("INSERT INTO balances (guild_id, user_id, wallet) VALUES (?, ?, ?)", (mock_ctx.guild.id, mock_ctx.author.id, 500))
    
    # Jugar Cara o Cruz
    await gambling_cog.coinflip.callback(gambling_cog, mock_ctx, 100, "cara")
    
    # Verificar que el balance haya cambiado (ya sea perdido o ganado)
    wallet, _ = await db.get_balance(mock_ctx.guild.id, mock_ctx.author.id)
    assert wallet == 400 or wallet == 600
    
    # Comprobar si hubo un resultado exitoso o fallido reportado en el embed
    assert any("La moneda voló y cayó" in msg or "La moneda dio volteretas" in msg for msg in mock_ctx.responses or mock_ctx.ephemeral_responses)

async def test_slots_loss_prevention(gambling_cog, mock_ctx):
    await db.execute("INSERT OR IGNORE INTO gambling_active_channels (guild_id, channel_id) VALUES (?, ?)", (mock_ctx.guild.id, mock_ctx.channel.id))
    
    # Establecer el balance en 0
    await db.execute("REPLACE INTO balances (guild_id, user_id, wallet) VALUES (?, ?, ?)", (mock_ctx.guild.id, mock_ctx.author.id, 0))
    
    # Intentar apostar 100 en slots
    await gambling_cog.slots.callback(gambling_cog, mock_ctx, 100)
    
    # Verificar el rechazo por falta de fondos (mensaje efímero)
    assert any("Efectivo insuficiente" in msg for msg in mock_ctx.ephemeral_responses)

async def test_blackjack_timeout_refund(gambling_cog, mock_ctx):
    await db.execute("INSERT OR IGNORE INTO gambling_active_channels (guild_id, channel_id) VALUES (?, ?)", (mock_ctx.guild.id, mock_ctx.channel.id))
    await db.execute("REPLACE INTO balances (guild_id, user_id, wallet) VALUES (?, ?, ?)", (mock_ctx.guild.id, mock_ctx.author.id, 1000))
    
    # Iniciar blackjack (esto deduce 200 de la cartera inmediatamente)
    await gambling_cog.blackjack.callback(gambling_cog, mock_ctx, 200)
    
    from cogs.gambling import BlackJackView
    # Encontrar la vista instanciada en el mensaje enviado si se puede (MockCtx devuelve objeto mock)
    # Como la vista requiere un interaction de UI para timeout, instanciaremos la view aquí
    view = BlackJackView(gambling_cog, mock_ctx, 200)
    
    wallet_mid, _ = await db.get_balance(mock_ctx.guild.id, mock_ctx.author.id)
    assert wallet_mid == 800  # Se cobró
    
    # Forzar el on_timeout
    await view.on_timeout()
    
    wallet_final, _ = await db.get_balance(mock_ctx.guild.id, mock_ctx.author.id)
    assert wallet_final == 1000  # Se reembolsó
