import pytest
from cogs.economy import EconomyCog
from utils import database_manager as db

@pytest.fixture
def eco_cog(mock_bot):
    return EconomyCog(mock_bot)

async def test_work_command(eco_cog, mock_ctx):
    # Ejecutamos el comando work por primera vez
    await eco_cog.work.callback(eco_cog, mock_ctx)
    
    # Comprobamos que el balance en la BDD aumentó
    user_data = await db.fetchone("SELECT wallet FROM balances WHERE guild_id = ? AND user_id = ?", (mock_ctx.guild.id, mock_ctx.author.id))
    assert user_data is not None
    assert user_data['wallet'] > 0
    
    initial_wallet = user_data['wallet']
    
    # Ejecutamos de nuevo inmediatamente para forzar el cooldown
    await eco_cog.work.callback(eco_cog, mock_ctx)
    
    # Comprobamos que el wallet NO subió debido al cooldown
    user_data_cooldown = await db.fetchone("SELECT wallet FROM balances WHERE guild_id = ? AND user_id = ?", (mock_ctx.guild.id, mock_ctx.author.id))
    assert user_data_cooldown['wallet'] == initial_wallet
    
    # Buscamos la respuesta de error de cooldown en los envíos efímeros
    assert any("Estás agotado" in msg for msg in mock_ctx.ephemeral_responses)
