import sqlite3
import asyncio
from typing import Optional, Any

DB_FILE = "bot_data.db"

def run_migrations(conn):
    """
    Añade columnas faltantes a las tablas existentes para evitar errores
    después de una actualización. Es la solución para los errores de economía.
    """
    cursor = conn.cursor()
    
    # --- Migración para la tabla economy_settings ---
    try:
        cursor.execute("PRAGMA table_info(economy_settings)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Columnas que deberían existir y su tipo de dato + valor por defecto
        expected_columns = {
            "daily_min": "INTEGER DEFAULT 100",
            "daily_max": "INTEGER DEFAULT 500",
            "work_min": "INTEGER DEFAULT 50",
            "work_max": "INTEGER DEFAULT 250",
            "work_cooldown": "INTEGER DEFAULT 3600",
            "rob_cooldown": "INTEGER DEFAULT 21600"
        }
        
        for col_name, col_definition in expected_columns.items():
            if col_name not in columns:
                print(f"MIGRACIÓN: Añadiendo columna '{col_name}' a la tabla 'economy_settings'...")
                cursor.execute(f"ALTER TABLE economy_settings ADD COLUMN {col_name} {col_definition}")
                print(f"MIGRACIÓN: Columna '{col_name}' añadida con éxito.")
    except sqlite3.Error as e:
        print(f"Error durante la migración de 'economy_settings': {e}")

    # Aquí se pueden añadir futuras migraciones para otras tablas
    
    conn.commit()


def setup_database():
    """Crea todas las tablas necesarias y ejecuta migraciones si es necesario."""
    with sqlite3.connect(DB_FILE) as conn:
        # Ejecutamos las migraciones ANTES de crear las tablas
        # para asegurarnos de que las tablas existentes estén actualizadas.
        run_migrations(conn)

        cursor = conn.cursor()
        # El resto de las sentencias CREATE TABLE IF NOT EXISTS no cambian.
        cursor.execute('''CREATE TABLE IF NOT EXISTS balances (guild_id INTEGER, user_id INTEGER, wallet INTEGER DEFAULT 0, bank INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS economy_settings (guild_id INTEGER PRIMARY KEY, currency_name TEXT DEFAULT 'créditos', currency_emoji TEXT DEFAULT '🪙', start_balance INTEGER DEFAULT 100, max_balance INTEGER, log_channel_id INTEGER, daily_min INTEGER DEFAULT 100, daily_max INTEGER DEFAULT 500, work_min INTEGER DEFAULT 50, work_max INTEGER DEFAULT 250, work_cooldown INTEGER DEFAULT 3600, rob_cooldown INTEGER DEFAULT 21600)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS economy_active_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS gambling_active_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS levels (guild_id INTEGER, user_id INTEGER, level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS role_rewards (guild_id INTEGER, level INTEGER, role_id INTEGER, PRIMARY KEY (guild_id, level))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS warnings (warning_id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER, moderator_id INTEGER, reason TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS mod_logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER, moderator_id INTEGER, action TEXT, reason TEXT, duration TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS server_settings (guild_id INTEGER PRIMARY KEY, welcome_channel_id INTEGER, goodbye_channel_id INTEGER, log_channel_id INTEGER, autorole_id INTEGER, welcome_message TEXT, welcome_banner_url TEXT, goodbye_message TEXT, goodbye_banner_url TEXT, automod_anti_invite INTEGER DEFAULT 1, automod_banned_words TEXT, temp_channel_creator_id INTEGER, leveling_enabled INTEGER DEFAULT 1)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS reaction_roles (guild_id INTEGER, message_id INTEGER, emoji TEXT, role_id INTEGER, PRIMARY KEY (guild_id, message_id, emoji))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS tts_guild_settings (guild_id INTEGER PRIMARY KEY, lang TEXT NOT NULL DEFAULT 'es')''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS tts_active_channels (guild_id INTEGER PRIMARY KEY, text_channel_id INTEGER NOT NULL)''')
        conn.commit()
    print("Base de datos verificada, configurada y migrada.")

# --- El resto del archivo (fetchone, fetchall, execute, etc.) no necesita cambios ---
async def fetchone(query: str, params: tuple = ()) -> Optional[Any]:
    def _sync_fetchone():
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()
    return await asyncio.to_thread(_sync_fetchone)

async def fetchall(query: str, params: tuple = ()) -> list[Any]:
    def _sync_fetchall():
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
    return await asyncio.to_thread(_sync_fetchall)

async def execute(query: str, params: tuple = ()):
    def _sync_execute():
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
    return await asyncio.to_thread(_sync_execute)

async def get_guild_economy_settings(guild_id: int) -> Optional[sqlite3.Row]:
    settings = await fetchone("SELECT * FROM economy_settings WHERE guild_id = ?", (guild_id,))
    if not settings:
        await execute("INSERT OR IGNORE INTO economy_settings (guild_id) VALUES (?)", (guild_id,))
        settings = await fetchone("SELECT * FROM economy_settings WHERE guild_id = ?", (guild_id,))
    return settings

async def get_balance(guild_id: int, user_id: int) -> tuple[int, int]:
    res = await fetchone("SELECT wallet, bank FROM balances WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    if res:
        return res['wallet'], res['bank']
    else:
        settings = await get_guild_economy_settings(guild_id)
        start_balance = settings.get('start_balance', 100) if settings else 100
        await execute("INSERT INTO balances (guild_id, user_id, wallet, bank) VALUES (?, ?, ?, 0)", (guild_id, user_id, start_balance))
        return start_balance, 0

async def update_balance(guild_id: int, user_id: int, wallet_change: int = 0, bank_change: int = 0) -> tuple[int, int]:
    await get_balance(guild_id, user_id)
    settings = await get_guild_economy_settings(guild_id)
    max_balance = settings.get('max_balance') if settings and settings.get('max_balance') is not None else None
    query = "UPDATE balances SET wallet = wallet + ?, bank = bank + ? WHERE guild_id = ? AND user_id = ?"
    await execute(query, (wallet_change, bank_change, guild_id, user_id))
    if max_balance is not None:
        await execute("UPDATE balances SET wallet = ? WHERE guild_id = ? AND user_id = ? AND wallet > ?", (max_balance, guild_id, user_id, max_balance))
    return await get_balance(guild_id, user_id)

async def get_user_level(guild_id: int, user_id: int) -> tuple[int, int]:
    res = await fetchone("SELECT level, xp FROM levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    if res:
        return res['level'], res['xp']
    else:
        await execute("INSERT INTO levels (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
        return 1, 0

async def update_user_xp(guild_id: int, user_id: int, level: int, xp: int):
    await execute("UPDATE levels SET level = ?, xp = ? WHERE guild_id = ? AND user_id = ?", (level, xp, guild_id, user_id))

async def add_mod_log(guild_id: int, user_id: int, mod_id: int, action: str, reason: str, duration: Optional[str] = None):
    await execute("INSERT INTO mod_logs (guild_id, user_id, moderator_id, action, reason, duration) VALUES (?, ?, ?, ?, ?, ?)", (guild_id, user_id, mod_id, action, reason, duration))
