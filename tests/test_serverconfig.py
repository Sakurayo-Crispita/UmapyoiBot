"""Tests para el cog de ServerConfig — incluye verificación del fix de Bug #2."""
import pytest
from unittest.mock import patch
from cogs.serverconfig import ServerConfigCog
from utils import database_manager as db


@pytest.fixture
async def config_cog(mock_bot):
    """Crear el cog patcheando el task loop para evitar RuntimeError."""
    with patch.object(ServerConfigCog, 'cog_unload', lambda self: None):
        # Patch the task start to avoid needing a running discord event loop
        original_init = ServerConfigCog.__init__
        def patched_init(self, bot):
            self.bot = bot
            self.recent_events = {}
            # No llamamos self.cleanup_recent_events.start()
        
        ServerConfigCog.__init__ = patched_init
        cog = ServerConfigCog(mock_bot)
        ServerConfigCog.__init__ = original_init
        return cog


class TestToggleLeveling:
    async def test_disable_leveling(self, config_cog, mock_ctx):
        await config_cog.toggle_leveling.callback(config_cog, mock_ctx, "off")
        settings = await db.fetchone(
            "SELECT leveling_enabled FROM server_settings WHERE guild_id = ?",
            (mock_ctx.guild.id,)
        )
        assert settings["leveling_enabled"] == 0

    async def test_enable_leveling(self, config_cog, mock_ctx):
        # Primero desactivamos
        await config_cog.toggle_leveling.callback(config_cog, mock_ctx, "off")
        db.invalidate_cache(mock_ctx.guild.id)
        mock_ctx.responses.clear()
        mock_ctx.ephemeral_responses.clear()

        # Luego activamos
        await config_cog.toggle_leveling.callback(config_cog, mock_ctx, "on")
        settings = await db.fetchone(
            "SELECT leveling_enabled FROM server_settings WHERE guild_id = ?",
            (mock_ctx.guild.id,)
        )
        assert settings["leveling_enabled"] == 1


class TestToggleModule:
    async def test_toggle_music_off_and_on(self, config_cog, mock_ctx):
        await config_cog.toggle_module.callback(config_cog, mock_ctx, "musica", "off")
        settings = await db.fetchone(
            "SELECT music_enabled FROM server_settings WHERE guild_id = ?",
            (mock_ctx.guild.id,)
        )
        assert settings["music_enabled"] == 0

        db.invalidate_cache(mock_ctx.guild.id)
        mock_ctx.responses.clear()
        mock_ctx.ephemeral_responses.clear()

        await config_cog.toggle_module.callback(config_cog, mock_ctx, "musica", "on")
        settings = await db.fetchone(
            "SELECT music_enabled FROM server_settings WHERE guild_id = ?",
            (mock_ctx.guild.id,)
        )
        assert settings["music_enabled"] == 1

    async def test_toggle_economia(self, config_cog, mock_ctx):
        await config_cog.toggle_module.callback(config_cog, mock_ctx, "economia", "off")
        settings = await db.fetchone(
            "SELECT eco_enabled FROM server_settings WHERE guild_id = ?",
            (mock_ctx.guild.id,)
        )
        assert settings["eco_enabled"] == 0

    async def test_toggle_invalid_module(self, config_cog, mock_ctx):
        await config_cog.toggle_module.callback(config_cog, mock_ctx, "inventado", "on")
        assert any("no válido" in msg.lower() or "módulo" in msg.lower()
                    for msg in mock_ctx.ephemeral_responses)


class TestServerConfigDisplay:
    """Verifica que el Bug #2 (casino_channels vs casino_channels_rows) está corregido."""

    async def test_serverconfig_no_crash(self, config_cog, mock_ctx):
        """El comando /serverconfig no debe crashear por NameError."""
        try:
            await config_cog.serverconfig.callback(config_cog, mock_ctx)
        except NameError as e:
            pytest.fail(f"Bug #2 no corregido: NameError — {e}")
