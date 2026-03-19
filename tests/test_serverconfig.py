import pytest
from cogs.serverconfig import ServerConfigCog
from utils import database_manager as db
import discord

@pytest.fixture
async def config_cog(mock_bot):
    return ServerConfigCog(mock_bot)

class MockInteraction:
    def __init__(self, guild):
        self.guild = guild
        self.response = self
    
    async def send_message(self, content=None, embed=None, ephemeral=False):
        pass

async def test_toggle_leveling(config_cog, mock_ctx):
    # Configurar el servidor en la BD antes de la prueba
    await db.execute("INSERT INTO server_settings (guild_id, leveling_enabled) VALUES (?, ?)", (mock_ctx.guild.id, 1))

    # Desactivar niveles
    await config_cog.toggle_leveling.callback(config_cog, mock_ctx, "off")
    
    settings = await db.fetchone("SELECT leveling_enabled FROM server_settings WHERE guild_id = ?", (mock_ctx.guild.id,))
    assert settings["leveling_enabled"] == 0
    
    # Verificar que el mensaje refleje el éxito
    assert any("desactivado" in msg for msg in mock_ctx.responses or mock_ctx.ephemeral_responses)

async def test_toggle_module_case_insensitive(config_cog, mock_ctx):
    # Insertar configuración inicial
    await db.execute("INSERT INTO server_settings (guild_id, music_enabled) VALUES (?, ?)", (mock_ctx.guild.id, 0))

    # Probar con "Musica" (capitalizada)
    await config_cog.toggle_module.callback(config_cog, mock_ctx, "Musica", "on")

    settings = await db.fetchone("SELECT music_enabled FROM server_settings WHERE guild_id = ?", (mock_ctx.guild.id,))
    assert settings["music_enabled"] == 1
    assert any("activado" in msg for msg in mock_ctx.responses or mock_ctx.ephemeral_responses)

    # Probar con "MUSICA" (mayúsculas)
    await config_cog.toggle_module.callback(config_cog, mock_ctx, "MUSICA", "off")
    settings = await db.fetchone("SELECT music_enabled FROM server_settings WHERE guild_id = ?", (mock_ctx.guild.id,))
    assert settings["music_enabled"] == 0
