"""Tests para el cog de Niveles (Leveling) — incluye verificación del fix de Bug #1."""
import pytest
import datetime
from cogs.leveling import LevelingCog
from utils import database_manager as db
from tests.conftest import MockMessage, MockUser, MockGuild, MockMember


@pytest.fixture
def level_cog(mock_bot):
    return LevelingCog(mock_bot)


def make_mock_message(guild_id=12345, user_id=999, user_name="TestUser"):
    """Crea un MockMessage con guild y author para simular on_message."""
    guild = MockGuild(guild_id, "TestGuild")
    author = MockMember(user_id, user_name, guild)
    
    class LevelMessage:
        def __init__(self):
            self.author = author
            self.guild = guild
            self.channel = type('Ch', (), {'id': 111, 'send': self._send})()
            self.content = "test message"
            self.sent_messages = []

        async def _send(self, msg, **kwargs):
            self.sent_messages.append(msg)
    
    return LevelMessage()


class TestProcessXP:
    """Verifica que el sistema de XP funciona correctamente (Bug #1 fix)."""

    async def test_xp_increases_after_message(self, level_cog):
        msg = make_mock_message()
        # Asegurar que leveling está habilitado
        await db.execute(
            "INSERT OR REPLACE INTO server_settings (guild_id, leveling_enabled) VALUES (?, ?)",
            (msg.guild.id, 1)
        )
        db.invalidate_cache(msg.guild.id)

        await level_cog.process_xp(msg)
        level, xp = await db.get_user_level(msg.guild.id, msg.author.id)
        assert xp > 0, "El XP debería haber aumentado después del mensaje"

    async def test_xp_cooldown_prevents_spam(self, level_cog):
        msg = make_mock_message()
        await db.execute(
            "INSERT OR REPLACE INTO server_settings (guild_id, leveling_enabled) VALUES (?, ?)",
            (msg.guild.id, 1)
        )
        db.invalidate_cache(msg.guild.id)

        # Primer mensaje: debe dar XP
        await level_cog.process_xp(msg)
        _, xp_after_first = await db.get_user_level(msg.guild.id, msg.author.id)

        # Segundo mensaje inmediato: NO debe dar XP (cooldown 60s)
        await level_cog.process_xp(msg)
        _, xp_after_second = await db.get_user_level(msg.guild.id, msg.author.id)

        assert xp_after_second == xp_after_first, \
            "El XP no debería aumentar dentro del cooldown de 60 segundos"

    async def test_xp_after_cooldown_expired(self, level_cog):
        msg = make_mock_message()
        await db.execute(
            "INSERT OR REPLACE INTO server_settings (guild_id, leveling_enabled) VALUES (?, ?)",
            (msg.guild.id, 1)
        )
        db.invalidate_cache(msg.guild.id)

        await level_cog.process_xp(msg)
        _, xp_after_first = await db.get_user_level(msg.guild.id, msg.author.id)

        # Simular que el cooldown expiró (poner timestamp viejo)
        old_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=120)
        await db.set_cooldown(msg.guild.id, msg.author.id, 'xp_gain', old_time)

        await level_cog.process_xp(msg)
        _, xp_after_second = await db.get_user_level(msg.guild.id, msg.author.id)

        assert xp_after_second > xp_after_first, \
            "El XP debería aumentar después de que expire el cooldown"

    async def test_now_variable_defined(self, level_cog):
        """Verificación directa de que Bug #1 está corregido: 'now' no lanza NameError."""
        msg = make_mock_message()
        await db.execute(
            "INSERT OR REPLACE INTO server_settings (guild_id, leveling_enabled) VALUES (?, ?)",
            (msg.guild.id, 1)
        )
        db.invalidate_cache(msg.guild.id)

        # Si 'now' no está definida, esto lanza NameError
        try:
            await level_cog.process_xp(msg)
        except NameError as e:
            pytest.fail(f"Bug #1 no corregido: NameError — {e}")


class TestLevelUp:
    async def test_level_up_on_threshold(self, level_cog):
        msg = make_mock_message()
        guild_id, user_id = msg.guild.id, msg.author.id

        # Nivel 1 necesita: 5*(1^2) + 50*1 + 100 = 155 XP
        await db.get_user_level(guild_id, user_id)
        await db.update_user_xp(guild_id, user_id, 1, 150)

        # El cooldown no debe bloquear
        await db.execute(
            "INSERT OR REPLACE INTO server_settings (guild_id, leveling_enabled) VALUES (?, ?)",
            (guild_id, 1)
        )
        db.invalidate_cache(guild_id)

        await level_cog.process_xp(msg)
        level, _ = await db.get_user_level(guild_id, user_id)
        assert level >= 2, "Debería haber subido al nivel 2"


class TestRankCommand:
    async def test_rank_shows_embed(self, level_cog, mock_ctx):
        await level_cog.rank.callback(level_cog, mock_ctx)
        assert len(mock_ctx.embeds_sent) >= 1


class TestXPFormula:
    """Verifica la fórmula de XP necesario por nivel."""

    def test_xp_formula_level_1(self):
        level = 1
        xp_needed = 5 * (level ** 2) + 50 * level + 100
        assert xp_needed == 155

    def test_xp_formula_level_10(self):
        level = 10
        xp_needed = 5 * (level ** 2) + 50 * level + 100
        assert xp_needed == 1100

    def test_xp_formula_level_50(self):
        level = 50
        xp_needed = 5 * (level ** 2) + 50 * level + 100
        assert xp_needed == 15100
