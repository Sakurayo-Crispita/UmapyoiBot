import sqlite3
import asyncio
import threading
from typing import Optional, Any, List, Dict

import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Si existe BOT_TEST_DB, usamos esa ruta (ej: para tests automatizados en memoria o archivo temporal)
if os.environ.get("BOT_TEST_DB"):
    DB_FILE = os.environ.get("BOT_TEST_DB")
else:
    DB_FILE = os.path.join(PROJECT_ROOT, "bot_data.db")

# Conexión persistente y bloqueo para evitar corrupción
_conn = None
_db_lock = threading.Lock()

def get_connection():
    """Obtiene o crea una conexión persistente a la base de datos."""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn

def run_migrations(conn):
    """Añade columnas faltantes a las tablas existentes."""
    cursor = conn.cursor()
    
    # Migraciones de base de datos para añadir columnas nuevas
    try:
        cursor.execute("PRAGMA table_info(economy_settings)")
        columns = [row[1] for row in cursor.fetchall()]
        
        expected_columns = {
            "daily_min": "INTEGER DEFAULT 100", "daily_max": "INTEGER DEFAULT 500",
            "work_min": "INTEGER DEFAULT 50", "work_max": "INTEGER DEFAULT 250",
            "work_cooldown": "INTEGER DEFAULT 3600", "rob_cooldown": "INTEGER DEFAULT 21600"
        }
        for col, definition in expected_columns.items():
            if col not in columns:
                cursor.execute(f"ALTER TABLE economy_settings ADD COLUMN {col} {definition}")
        
        # Migración para broadcast_queue
        cursor.execute("PRAGMA table_info(broadcast_queue)")
        b_cols = [row[1] for row in cursor.fetchall()]
        if 'type' not in b_cols:
            cursor.execute("ALTER TABLE broadcast_queue ADD COLUMN type TEXT DEFAULT 'broadcast'")
            
        # Migración para bot_guilds (dueños e invitados)
        cursor.execute("PRAGMA table_info(bot_guilds)")
        bg_cols = [row[1] for row in cursor.fetchall()]
        if 'owner_id' not in bg_cols:
            cursor.execute("ALTER TABLE bot_guilds ADD COLUMN owner_id INTEGER")
        if 'owner_name' not in bg_cols:
            cursor.execute("ALTER TABLE bot_guilds ADD COLUMN owner_name TEXT")
        if 'inviter_id' not in bg_cols:
            cursor.execute("ALTER TABLE bot_guilds ADD COLUMN inviter_id INTEGER")
        if 'inviter_name' not in bg_cols:
            cursor.execute("ALTER TABLE bot_guilds ADD COLUMN inviter_name TEXT")
        if 'inviter_avatar' not in bg_cols:
            cursor.execute("ALTER TABLE bot_guilds ADD COLUMN inviter_avatar TEXT")
        
        for col_name, col_definition in expected_columns.items():
            if col_name not in columns:
                print(f"MIGRACIÓN: Añadiendo columna '{col_name}' a 'economy_settings'...")
                cursor.execute(f"ALTER TABLE economy_settings ADD COLUMN {col_name} {col_definition}")
    except sqlite3.Error as e:
        print(f"Error durante la migración de 'economy_settings': {e}")

    # --- Migración para la tabla server_settings ---
    try:
        cursor.execute("PRAGMA table_info(server_settings)")
        columns = [row[1] for row in cursor.fetchall()]
        
        new_columns = {
            "welcome_title_color": "TEXT DEFAULT '#000000'", "welcome_subtitle_color": "TEXT DEFAULT '#000000'",
            "goodbye_title_color": "TEXT DEFAULT '#000000'", "goodbye_subtitle_color": "TEXT DEFAULT '#000000'",
            "welcome_top_text": "TEXT", "goodbye_top_text": "TEXT",
            "prefix": "TEXT DEFAULT '!'", "language": "TEXT DEFAULT 'es'",
            "mod_enabled": "INTEGER DEFAULT 1", "eco_enabled": "INTEGER DEFAULT 1",
            "gamble_enabled": "INTEGER DEFAULT 1", "tickets_enabled": "INTEGER DEFAULT 1",
            "music_enabled": "INTEGER DEFAULT 1", "tts_enabled": "INTEGER DEFAULT 1",
            "ticket_category_id": "INTEGER", "ticket_log_channel_id": "INTEGER",
            "confessions_channel_id": "INTEGER", "ticket_panel_channel_id": "INTEGER",
            "ticket_panel_title": "TEXT", "ticket_panel_desc": "TEXT",
            "ticket_welcome_title": "TEXT", "ticket_welcome_desc": "TEXT",
            "confessions_panel_title": "TEXT", "confessions_panel_desc": "TEXT",
            "rr_enabled": "INTEGER DEFAULT 1", "utility_enabled": "INTEGER DEFAULT 1"
        }
        
        for col_name, col_definition in new_columns.items():
            if col_name not in columns:
                print(f"MIGRACIÓN: Añadiendo columna '{col_name}' a 'server_settings'...")
                cursor.execute(f"ALTER TABLE server_settings ADD COLUMN {col_name} {col_definition}")
    except sqlite3.Error as e:
        print(f"Error durante la migración de 'server_settings': {e}")

    conn.commit()

def setup_database():
    """Crea todas las tablas necesarias y abre la conexión inicial."""
    conn = get_connection()
    with _db_lock:
        cursor = conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS server_settings (
            guild_id INTEGER PRIMARY KEY, welcome_channel_id INTEGER, goodbye_channel_id INTEGER, 
            log_channel_id INTEGER, autorole_id INTEGER, welcome_message TEXT, welcome_banner_url TEXT, 
            goodbye_message TEXT, goodbye_banner_url TEXT, automod_anti_invite INTEGER DEFAULT 1, 
            automod_banned_words TEXT, temp_channel_creator_id INTEGER, leveling_enabled INTEGER DEFAULT 1,
            welcome_title_color TEXT DEFAULT '#000000', welcome_subtitle_color TEXT DEFAULT '#000000',
            goodbye_title_color TEXT DEFAULT '#000000', goodbye_subtitle_color TEXT DEFAULT '#000000',
            welcome_top_text TEXT, goodbye_top_text TEXT,
            prefix TEXT DEFAULT '!', language TEXT DEFAULT 'es',
            mod_enabled INTEGER DEFAULT 1, eco_enabled INTEGER DEFAULT 1,
            gamble_enabled INTEGER DEFAULT 1, tickets_enabled INTEGER DEFAULT 1,
            music_enabled INTEGER DEFAULT 1, tts_enabled INTEGER DEFAULT 1,
            ticket_category_id INTEGER, ticket_log_channel_id INTEGER,
            confessions_channel_id INTEGER, ticket_panel_channel_id INTEGER,
            ticket_panel_title TEXT, ticket_panel_desc TEXT,
            ticket_welcome_title TEXT, ticket_welcome_desc TEXT,
            confessions_panel_title TEXT, confessions_panel_desc TEXT,
            rr_enabled INTEGER DEFAULT 1, utility_enabled INTEGER DEFAULT 1
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS balances (guild_id INTEGER, user_id INTEGER, wallet INTEGER DEFAULT 0, bank INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS economy_settings (guild_id INTEGER PRIMARY KEY, currency_name TEXT DEFAULT 'créditos', currency_emoji TEXT DEFAULT '🪙', start_balance INTEGER DEFAULT 100, max_balance INTEGER, log_channel_id INTEGER, daily_min INTEGER DEFAULT 100, daily_max INTEGER DEFAULT 500, work_min INTEGER DEFAULT 50, work_max INTEGER DEFAULT 250, work_cooldown INTEGER DEFAULT 3600, rob_cooldown INTEGER DEFAULT 21600)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS levels (guild_id INTEGER, user_id INTEGER, level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS role_rewards (guild_id INTEGER, level INTEGER, role_id INTEGER, PRIMARY KEY (guild_id, level))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS warnings (warning_id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER, moderator_id INTEGER, reason TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS mod_logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER, moderator_id INTEGER, action TEXT, reason TEXT, duration TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS reaction_roles (guild_id INTEGER, message_id INTEGER, emoji TEXT, role_id INTEGER, PRIMARY KEY (guild_id, message_id, emoji))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS tts_guild_settings (guild_id INTEGER PRIMARY KEY, lang TEXT NOT NULL DEFAULT 'es')''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS tts_active_channels (guild_id INTEGER PRIMARY KEY, text_channel_id INTEGER NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS shop_items (item_id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, name TEXT COLLATE NOCASE, description TEXT, price INTEGER, type TEXT, raw_data TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS inventory (guild_id INTEGER, user_id INTEGER, item_id INTEGER, quantity INTEGER DEFAULT 1, PRIMARY KEY (guild_id, user_id, item_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS gacha_collection (guild_id INTEGER, user_id INTEGER, character_name TEXT, rarity TEXT, image_url TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS gambling_active_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS economy_active_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, subject TEXT, description TEXT, priority TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS global_blacklist (discord_id INTEGER PRIMARY KEY, entity_type TEXT NOT NULL, reason TEXT, date_added DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS broadcast_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT NOT NULL, type TEXT DEFAULT 'broadcast', status TEXT DEFAULT 'pending', date_added DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS bot_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS bot_guilds (
            guild_id INTEGER PRIMARY KEY,
            name TEXT,
            member_count INTEGER,
            icon_url TEXT,
            owner_id INTEGER,
            owner_name TEXT,
            inviter_id INTEGER,
            inviter_name TEXT,
            inviter_avatar TEXT,
            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS global_command_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            guild_name TEXT,
            user_id INTEGER,
            user_name TEXT,
            command_name TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS admin_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            action TEXT,
            target_id TEXT,
            details TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS dashboard_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            avatar TEXT,
            last_login DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        run_migrations(conn)
        conn.commit()
    print("Base de datos verificada y conexión persistente establecida.")

def close_database():
    """Cierra la conexión persistente."""
    global _conn
    if _conn:
        _conn.close()
        _conn = None

# Sistema de caché para configuraciones de servidores
_settings_cache = {}

def invalidate_cache(guild_id: int):
    if guild_id in _settings_cache:
        del _settings_cache[guild_id]

async def get_cached_server_settings(guild_id: int) -> Optional[Dict[str, Any]]:
    # TTL reducido a 5 segundos para que los cambios en la web sean casi instantáneos en el bot.
    import time
    now = time.time()
    if guild_id in _settings_cache and 'server' in _settings_cache[guild_id]:
        cached = _settings_cache[guild_id]
        if now - cached.get('last_update', 0) < 5: # 5 segundos de cache
            return cached['server']
            
    settings = await fetchone("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
    if settings:
        _settings_cache.setdefault(guild_id, {})['server'] = settings
        _settings_cache[guild_id]['last_update'] = now
    return settings

async def get_cached_economy_settings(guild_id: int) -> Optional[Dict[str, Any]]:
    if guild_id in _settings_cache and 'economy' in _settings_cache[guild_id]:
        return _settings_cache[guild_id]['economy']
    settings = await get_guild_economy_settings(guild_id)
    if settings:
        _settings_cache.setdefault(guild_id, {})['economy'] = settings
    return settings

# Funciones asíncronas para consultas y ejecución

async def fetchone(query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    def _sync_fetchone():
        with _db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None
    return await asyncio.to_thread(_sync_fetchone)

async def fetchall(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    def _sync_fetchall():
        with _db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    return await asyncio.to_thread(_sync_fetchall)

async def execute(query: str, params: tuple = ()):
    # Invalidación de caché
    query_lower = query.lower()
    if any(k in query_lower for k in ["update", "replace", "delete", "insert"]):
        if "server_settings" in query_lower or "economy_settings" in query_lower:
            for p in params:
                if isinstance(p, int) and p > 1000000:
                    invalidate_cache(p)
                    # No hacemos break porque podría haber otros IDs (aunque lo normal es uno por query)
                    # Pero sobre todo para no confundir un channel_id con el guild_id.
                    # Al invalidar ambos si son > 1M no pasa nada malo (solo un poco más de carga),
                    # asegurando que el guild_id sea procesado.

    def _sync_execute():
        with _db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
    return await asyncio.to_thread(_sync_execute)

# Consultas específicas de economía, niveles y logs

async def get_guild_economy_settings(guild_id: int) -> Optional[Dict[str, Any]]:
    settings = await fetchone("SELECT * FROM economy_settings WHERE guild_id = ?", (guild_id,))
    if not settings:
        await execute("INSERT OR IGNORE INTO economy_settings (guild_id) VALUES (?)", (guild_id,))
        settings = await fetchone("SELECT * FROM economy_settings WHERE guild_id = ?", (guild_id,))
    return settings

async def get_balance(guild_id: int, user_id: int) -> tuple[int, int]:
    res = await fetchone("SELECT wallet, bank FROM balances WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    if res: return res['wallet'], res['bank']
    settings = await get_guild_economy_settings(guild_id)
    start = settings.get('start_balance', 100) if settings else 100
    await execute("INSERT OR IGNORE INTO balances (guild_id, user_id, wallet, bank) VALUES (?, ?, ?, 0)", (guild_id, user_id, start))
    return start, 0

async def update_balance(guild_id: int, user_id: int, wallet_change: int = 0, bank_change: int = 0) -> tuple[int, int]:
    await get_balance(guild_id, user_id)
    settings = await get_guild_economy_settings(guild_id)
    max_bal = settings.get('max_balance') if settings else None
    await execute("UPDATE balances SET wallet = wallet + ?, bank = bank + ? WHERE guild_id = ? AND user_id = ?", (wallet_change, bank_change, guild_id, user_id))
    if max_bal is not None:
        await execute("UPDATE balances SET wallet = ? WHERE guild_id = ? AND user_id = ? AND wallet > ?", (max_bal, guild_id, user_id, max_bal))
    return await get_balance(guild_id, user_id)

async def get_user_level(guild_id: int, user_id: int) -> tuple[int, int]:
    res = await fetchone("SELECT level, xp FROM levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    if res: return res['level'], res['xp']
    await execute("INSERT OR IGNORE INTO levels (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
    return 1, 0

async def update_user_xp(guild_id: int, user_id: int, level: int, xp: int):
    await execute("UPDATE levels SET level = ?, xp = ? WHERE guild_id = ? AND user_id = ?", (level, xp, guild_id, user_id))

async def add_mod_log(guild_id: int, user_id: int, mod_id: int, action: str, reason: str, duration: Optional[str] = None):
    await execute("INSERT INTO mod_logs (guild_id, user_id, moderator_id, action, reason, duration) VALUES (?, ?, ?, ?, ?, ?)", (guild_id, user_id, mod_id, action, reason, duration))

# Sistema de lista negra global (Blacklist)
async def add_to_blacklist(discord_id: int, entity_type: str, reason: str = ""):
    await execute("INSERT OR REPLACE INTO global_blacklist (discord_id, entity_type, reason) VALUES (?, ?, ?)", (discord_id, entity_type, reason))

async def remove_from_blacklist(discord_id: int):
    await execute("DELETE FROM global_blacklist WHERE discord_id = ?", (discord_id,))

async def is_blacklisted(discord_id: int) -> bool:
    result = await fetchone("SELECT discord_id FROM global_blacklist WHERE discord_id = ?", (discord_id,))
    return result is not None

async def get_all_blacklisted():
    return await fetchall("SELECT discord_id, entity_type, reason, date_added FROM global_blacklist ORDER BY date_added DESC")

async def sync_bot_guilds(guilds_data: List[Dict]):
    """Sincroniza masivamente la lista de servidores."""
    # Desactivar todos temporalmente
    await execute("UPDATE bot_guilds SET is_active = 0")
    for g in guilds_data:
        await execute('''INSERT INTO bot_guilds (guild_id, name, member_count, icon_url, owner_id, owner_name, inviter_id, inviter_name, inviter_avatar, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        ON CONFLICT(guild_id) DO UPDATE SET
                        name=excluded.name, member_count=excluded.member_count,
                        icon_url=excluded.icon_url, owner_id=excluded.owner_id,
                        owner_name=excluded.owner_name, inviter_id=COALESCE(excluded.inviter_id, bot_guilds.inviter_id),
                        inviter_name=COALESCE(excluded.inviter_name, bot_guilds.inviter_name),
                        inviter_avatar=COALESCE(excluded.inviter_avatar, bot_guilds.inviter_avatar),
                        is_active=1''',
                     (g['id'], g['name'], g['member_count'], g['icon_url'], g['owner_id'], g['owner_name'], g.get('inviter_id'), g.get('inviter_name'), g.get('inviter_avatar')))

async def update_guild_status(guild_id: int, is_active: int, name: str = None, members: int = None, icon: str = None, owner_id: int = None, owner_name: str = None, inviter_id: int = None, inviter_name: str = None, inviter_avatar: str = None):
    if is_active:
        await execute('''INSERT INTO bot_guilds (guild_id, name, member_count, icon_url, owner_id, owner_name, inviter_id, inviter_name, inviter_avatar, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        ON CONFLICT(guild_id) DO UPDATE SET
                        name=COALESCE(excluded.name, bot_guilds.name),
                        member_count=COALESCE(excluded.member_count, bot_guilds.member_count),
                        icon_url=COALESCE(excluded.icon_url, bot_guilds.icon_url),
                        owner_id=COALESCE(excluded.owner_id, bot_guilds.owner_id),
                        owner_name=COALESCE(excluded.owner_name, bot_guilds.owner_name),
                        inviter_id=COALESCE(excluded.inviter_id, bot_guilds.inviter_id),
                        inviter_name=COALESCE(excluded.inviter_name, bot_guilds.inviter_name),
                        inviter_avatar=COALESCE(excluded.inviter_avatar, bot_guilds.inviter_avatar),
                        is_active=1''',
                     (guild_id, name, members, icon, owner_id, owner_name, inviter_id, inviter_name, inviter_avatar))
    else:
        await execute("UPDATE bot_guilds SET is_active = 0 WHERE guild_id = ?", (guild_id,))

async def get_bot_guilds():
    return await fetchall("SELECT * FROM bot_guilds WHERE is_active = 1 ORDER BY member_count DESC")

# Registro de logs de comandos y sistema
async def log_global_command(guild_id: int, guild_name: str, user_id: int, user_name: str, command_name: str):
    await execute("INSERT INTO global_command_logs (guild_id, guild_name, user_id, user_name, command_name) VALUES (?, ?, ?, ?, ?)",
                 (guild_id, guild_name, user_id, user_name, command_name))

async def get_recent_global_logs(limit: int = 50):
    return await fetchall("SELECT * FROM global_command_logs ORDER BY timestamp DESC LIMIT ?", (limit,))

# Registro de eventos del bot
async def log_system_event(level: str, category: str, message: str):
    await execute("INSERT INTO bot_logs (level, category, message) VALUES (?, ?, ?)", (level, category, message))

async def get_recent_system_logs(limit: int = 50):
    return await fetchall("SELECT * FROM bot_logs ORDER BY timestamp DESC LIMIT ?", (limit,))

# Auditoría de acciones administrativas en el dashboard
async def log_admin_action(user_id: int, user_name: str, action: str, target_id: str = None, details: str = None):
    await execute("INSERT INTO admin_audit_logs (user_id, user_name, action, target_id, details) VALUES (?, ?, ?, ?, ?)",
                 (user_id, user_name, action, target_id, details))

async def get_recent_admin_audit_logs(limit: int = 50):
    return await fetchall("SELECT * FROM admin_audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))

async def record_dashboard_login(user_id: int, username: str, avatar: str):
    await execute(
        "INSERT INTO dashboard_users (user_id, username, avatar, last_login) VALUES (?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, avatar=excluded.avatar, last_login=CURRENT_TIMESTAMP",
        (user_id, username, avatar)
    )
