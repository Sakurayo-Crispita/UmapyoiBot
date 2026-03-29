"""Tests para el sistema de base de datos (database_manager)."""
import pytest
import datetime
from utils import database_manager as db


class TestDatabaseSetup:
    """Verifica que todas las tablas se crean correctamente."""

    async def test_tables_exist(self):
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        required = [
            'server_settings', 'balances', 'economy_settings', 'levels',
            'warnings', 'mod_logs', 'role_rewards', 'gacha_collection',
            'user_cooldowns', 'broadcast_queue', 'global_blacklist',
            'bot_guilds', 'global_command_logs', 'bot_logs',
            'admin_audit_logs', 'dashboard_users',
        ]
        for table in required:
            assert table in tables, f"Tabla '{table}' no encontrada en la BD"

    async def test_migrations_run_safely_twice(self):
        """Las migraciones no deben fallar si se ejecutan dos veces."""
        conn = db.get_connection()
        db.setup_database()  # Ya se ejecutó en fixture, esta es la segunda vez
        # Si no lanza excepción, pasa


class TestBalances:
    """Tests del sistema de balances (wallet/bank)."""

    async def test_get_balance_creates_default(self):
        wallet, bank = await db.get_balance(12345, 999)
        assert wallet == 100  # start_balance default
        assert bank == 0

    async def test_update_balance_wallet(self):
        await db.get_balance(12345, 999)
        wallet, bank = await db.update_balance(12345, 999, wallet_change=500)
        assert wallet == 600
        assert bank == 0

    async def test_update_balance_bank(self):
        await db.get_balance(12345, 999)
        await db.update_balance(12345, 999, bank_change=300)
        wallet, bank = await db.get_balance(12345, 999)
        assert bank == 300

    async def test_update_balance_negative(self):
        await db.get_balance(12345, 999)
        await db.update_balance(12345, 999, wallet_change=-50)
        wallet, bank = await db.get_balance(12345, 999)
        assert wallet == 50

    async def test_balances_isolated_per_guild(self):
        """Cada guild tiene balances independientes."""
        await db.update_balance(111, 999, wallet_change=1000)
        await db.update_balance(222, 999, wallet_change=5000)
        
        w1, _ = await db.get_balance(111, 999)
        w2, _ = await db.get_balance(222, 999)
        assert w1 != w2


class TestCooldowns:
    """Tests del sistema de cooldowns."""

    async def test_set_and_get_cooldown(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        await db.set_cooldown(12345, 999, 'work', now)
        result = await db.get_cooldown(12345, 999, 'work')
        assert result is not None
        # Comparar hasta segundos (ignorar microsegundos por serialización)
        assert abs((result - now).total_seconds()) < 1

    async def test_get_cooldown_nonexistent(self):
        result = await db.get_cooldown(12345, 999, 'nonexistent')
        assert result is None

    async def test_cooldown_overwrite(self):
        t1 = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
        t2 = datetime.datetime(2025, 6, 15, tzinfo=datetime.timezone.utc)
        await db.set_cooldown(12345, 999, 'daily', t1)
        await db.set_cooldown(12345, 999, 'daily', t2)
        result = await db.get_cooldown(12345, 999, 'daily')
        assert result.month == 6


class TestLevels:
    """Tests del sistema de niveles."""

    async def test_get_level_creates_default(self):
        level, xp = await db.get_user_level(12345, 999)
        assert level == 1
        assert xp == 0

    async def test_update_xp(self):
        await db.get_user_level(12345, 999)
        await db.update_user_xp(12345, 999, 5, 250)
        level, xp = await db.get_user_level(12345, 999)
        assert level == 5
        assert xp == 250


class TestBlacklist:
    """Tests del sistema de blacklist global."""

    async def test_add_and_check(self):
        await db.add_to_blacklist(999, "user", "spam")
        assert await db.is_blacklisted(999) is True

    async def test_not_blacklisted(self):
        assert await db.is_blacklisted(12345) is False

    async def test_remove_from_blacklist(self):
        await db.add_to_blacklist(999, "user", "test")
        await db.remove_from_blacklist(999)
        assert await db.is_blacklisted(999) is False

    async def test_get_all_blacklisted(self):
        await db.add_to_blacklist(1, "user", "r1")
        await db.add_to_blacklist(2, "guild", "r2")
        results = await db.get_all_blacklisted()
        assert len(results) == 2


class TestServerSettings:
    """Tests del caché de server settings."""

    async def test_get_cached_creates_entry(self):
        settings = await db.get_cached_server_settings(12345)
        assert settings is not None
        assert settings.get('leveling_enabled') is not None

    async def test_cache_invalidation(self):
        settings1 = await db.get_cached_server_settings(12345)
        db.invalidate_cache(12345)
        # Después de invalidar, debe re-obtener de la BD
        settings2 = await db.get_cached_server_settings(12345)
        assert settings2 is not None


class TestEconomySettings:
    """Tests de economy settings."""

    async def test_get_creates_default(self):
        settings = await db.get_guild_economy_settings(12345)
        assert settings is not None
        assert 'currency_name' in settings

    async def test_alias_compatibility(self):
        s1 = await db.get_guild_economy_settings(12345)
        s2 = await db.get_economy_settings(12345)
        assert s1['guild_id'] == s2['guild_id']


class TestLogs:
    """Tests del sistema de logging."""

    async def test_log_system_event(self):
        await db.log_system_event("INFO", "Test", "Test message")
        logs = await db.get_recent_system_logs(10)
        assert len(logs) == 1
        assert logs[0]['message'] == "Test message"

    async def test_log_global_command(self):
        await db.log_global_command(12345, "TestGuild", 999, "TestUser", "/test")
        logs = await db.get_recent_global_logs(10)
        assert len(logs) == 1
        assert logs[0]['command_name'] == "/test"

    async def test_admin_audit_log(self):
        await db.log_admin_action(999, "Admin", "ban", "555", "test ban")
        logs = await db.get_recent_admin_audit_logs(10)
        assert len(logs) == 1
        assert logs[0]['action'] == "ban"

    async def test_dashboard_login(self):
        await db.record_dashboard_login(999, "TestUser", "avatar_url")
        row = await db.fetchone("SELECT * FROM dashboard_users WHERE user_id = ?", (999,))
        assert row is not None
        assert row['username'] == "TestUser"
