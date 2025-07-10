# /utils/database_manager.py

import sqlite3
import asyncio
from typing import Optional, Any

DB_FILE = "bot_data.db"

def setup_database():
    """Crea todas las tablas necesarias si no existen."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        # Tablas de EconomyCog
        cursor.execute('''CREATE TABLE IF NOT EXISTS balances (guild_id INTEGER, user_id INTEGER, wallet INTEGER DEFAULT 0, bank INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS economy_settings (guild_id INTEGER PRIMARY KEY, currency_name TEXT DEFAULT 'créditos', currency_emoji TEXT DEFAULT '🪙', start_balance INTEGER DEFAULT 100, max_balance INTEGER, log_channel_id INTEGER, daily_min INTEGER DEFAULT 100, daily_max INTEGER DEFAULT 500, work_min INTEGER DEFAULT 50, work_max INTEGER DEFAULT 250, work_cooldown INTEGER DEFAULT 3600, rob_cooldown INTEGER DEFAULT 21600)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS economy_active_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))''')
        # Tablas de GamblingCog
        cursor.execute('''CREATE TABLE IF NOT EXISTS gambling_active_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))''')
        # Tablas de LevelingCog
        cursor.execute('''CREATE TABLE IF NOT EXISTS levels (guild_id INTEGER, user_id INTEGER, level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS role_rewards (guild_id INTEGER, level INTEGER, role_id INTEGER, PRIMARY KEY (guild_id, level))''')
        # Tablas de ModerationCog
        cursor.execute('''CREATE TABLE IF NOT EXISTS warnings (warning_id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER, moderator_id INTEGER, reason TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS mod_logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER, moderator_id INTEGER, action TEXT, reason TEXT, duration TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        # Tablas de ServerConfigCog
        cursor.execute('''CREATE TABLE IF NOT EXISTS server_settings (guild_id INTEGER PRIMARY KEY, welcome_channel_id INTEGER, goodbye_channel_id INTEGER, log_channel_id INTEGER, autorole_id INTEGER, welcome_message TEXT, welcome_banner_url TEXT, goodbye_message TEXT, goodbye_banner_url TEXT, automod_anti_invite INTEGER DEFAULT 1, automod_banned_words TEXT, temp_channel_creator_id INTEGER, leveling_enabled INTEGER DEFAULT 1)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS reaction_roles (guild_id INTEGER, message_id INTEGER, emoji TEXT, role_id INTEGER, PRIMARY KEY (guild_id, message_id, emoji))''')
        # Tablas de TTSCog
        cursor.execute('''CREATE TABLE IF NOT EXISTS tts_guild_settings (guild_id INTEGER PRIMARY KEY, lang TEXT NOT NULL DEFAULT 'es')''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS tts_active_channels (guild_id INTEGER PRIMARY KEY, text_channel_id INTEGER NOT NULL)''')
        conn.commit()
    print("Base de datos verificada y configurada.")

# --- Funciones genéricas para interactuar con la DB ---

async def fetchone(query: str, params: tuple = ()) -> Optional[Any]:
    """Ejecuta una consulta y devuelve una sola fila."""
    def _sync_fetchone():
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()
    return await asyncio.to_thread(_sync_fetchone)

async def fetchall(query: str, params: tuple = ()) -> list[Any]:
    """Ejecuta una consulta y devuelve todas las filas."""
    def _sync_fetchall():
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
    return await asyncio.to_thread(_sync_fetchall)

async def execute(query: str, params: tuple = ()):
    """Ejecuta una consulta que modifica datos (INSERT, UPDATE, DELETE)."""
    def _sync_execute():
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
    return await asyncio.to_thread(_sync_execute)

# --- Funciones específicas por Cog ---

# Economy / Gambling
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
        start_balance = settings['start_balance'] if settings else 100
        await execute("INSERT INTO balances (guild_id, user_id, wallet, bank) VALUES (?, ?, ?, 0)", (guild_id, user_id, start_balance))
        return start_balance, 0

async def update_balance(guild_id: int, user_id: int, wallet_change: int = 0, bank_change: int = 0) -> tuple[int, int]:
    wallet, bank = await get_balance(guild_id, user_id)
    settings = await get_guild_economy_settings(guild_id)
    max_balance = settings['max_balance'] if settings and settings['max_balance'] is not None else -1
    
    new_wallet = wallet + wallet_change
    if max_balance != -1:
        new_wallet = min(new_wallet, max_balance)
    
    new_bank = bank + bank_change
    
    await execute("REPLACE INTO balances (guild_id, user_id, wallet, bank) VALUES (?, ?, ?, ?)", (guild_id, user_id, new_wallet, new_bank))
    return new_wallet, new_bank

# Leveling
async def get_user_level(guild_id: int, user_id: int) -> tuple[int, int]:
    res = await fetchone("SELECT level, xp FROM levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    if res:
        return res['level'], res['xp']
    else:
        await execute("INSERT INTO levels (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
        return 1, 0

async def update_user_xp(guild_id: int, user_id: int, level: int, xp: int):
    await execute("UPDATE levels SET level = ?, xp = ? WHERE guild_id = ? AND user_id = ?", (level, xp, guild_id, user_id))

# Moderation
async def add_mod_log(guild_id: int, user_id: int, mod_id: int, action: str, reason: str, duration: Optional[str] = None):
    await execute("INSERT INTO mod_logs (guild_id, user_id, moderator_id, action, reason, duration) VALUES (?, ?, ?, ?, ?, ?)", (guild_id, user_id, mod_id, action, reason, duration))

# Y así sucesivamente, podrías añadir todas las demás funciones de base de datos aquí...