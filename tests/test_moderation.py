"""Tests para el cog de Moderación."""
import pytest
from cogs.moderation import ModerationCog
from utils import database_manager as db
from tests.conftest import MockMember


@pytest.fixture
def mod_cog(mock_bot):
    return ModerationCog(mock_bot)


class TestWarnings:
    async def test_warn_creates_record(self, mod_cog, mock_ctx, mock_target):
        await mod_cog.warn.callback(mod_cog, mock_ctx, mock_target, razon="Spam en general")
        warnings = await db.fetchall(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ?",
            (mock_ctx.guild.id, mock_target.id)
        )
        assert len(warnings) == 1
        assert warnings[0]["reason"] == "Spam en general"
        assert warnings[0]["moderator_id"] == mock_ctx.author.id

    async def test_multiple_warns(self, mod_cog, mock_ctx, mock_target):
        await mod_cog.warn.callback(mod_cog, mock_ctx, mock_target, razon="Primera vez")
        mock_ctx.responses.clear()
        await mod_cog.warn.callback(mod_cog, mock_ctx, mock_target, razon="Segunda vez")
        
        warnings = await db.fetchall(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ?",
            (mock_ctx.guild.id, mock_target.id)
        )
        assert len(warnings) == 2

    async def test_clear_warnings(self, mod_cog, mock_ctx, mock_target):
        # Insertar warns directamente
        await db.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
            (mock_ctx.guild.id, mock_target.id, mock_ctx.author.id, "Spam 1")
        )
        await db.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
            (mock_ctx.guild.id, mock_target.id, mock_ctx.author.id, "Spam 2")
        )

        before = await db.fetchall(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ?",
            (mock_ctx.guild.id, mock_target.id)
        )
        assert len(before) == 2

        await mod_cog.clearwarnings.callback(mod_cog, mock_ctx, mock_target)

        after = await db.fetchall(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ?",
            (mock_ctx.guild.id, mock_target.id)
        )
        assert len(after) == 0


class TestModLogs:
    async def test_warn_creates_mod_log(self, mod_cog, mock_ctx, mock_target):
        await mod_cog.warn.callback(mod_cog, mock_ctx, mock_target, razon="Test log")
        logs = await db.fetchall(
            "SELECT * FROM mod_logs WHERE guild_id = ? AND user_id = ?",
            (mock_ctx.guild.id, mock_target.id)
        )
        assert len(logs) >= 1
        assert logs[0]['action'] == 'Warn'
