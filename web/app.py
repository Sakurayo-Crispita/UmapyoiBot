from quart import Quart, render_template, send_from_directory, redirect, url_for, session, request, send_file
from functools import wraps
from werkzeug.exceptions import HTTPException
import os
import aiohttp
import asyncio
import socket
import psutil
import time
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv
import json

# Resolve paths relative to this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
static_dir = os.path.join(BASE_DIR, 'static')
template_dir = os.path.join(BASE_DIR, 'templates')

# Cargar variables de entorno desde la raíz del proyecto
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

# Agregar la raíz del proyecto al path para importar utils y cogs
sys.path.append(PROJECT_ROOT)
from utils import database_manager, api_helpers
from utils.lang_utils import _t

app = Quart(__name__, 
            static_url_path='/static',
            static_folder=static_dir, 
            template_folder=template_dir)
app.secret_key = os.urandom(24)

# ==== 🛡️ CONFIGURACIONES DE SEGURIDAD (BLINDAJE DE 5 CAPAS) ====
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 # Límite de 5 MB anti-DDoS/Exhaustión de RAM
app.config['SESSION_COOKIE_HTTPONLY'] = True      # Evita que el JS malicioso robe cookies (XSS)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'       # Evita CSRF en navegación de alto nivel

@app.after_request
async def apply_security_headers(response):
    # Cabeceras anti-ataques invisibles para el navegador
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY' # Previene Clickjacking en sitios externos
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

@app.errorhandler(404)
async def not_found_error(error):
    try:
        return await render_template('404.html'), 404
    except:
        return "Página no encontrada", 404

@app.errorhandler(Exception)
async def internal_error(error):
    # Si es un error HTTP estándar (como 413 Payload Too Large o 405), lo dejamos pasar
    if isinstance(error, HTTPException):
        return error

    # Registraremos el error fatal en consola sin exponérselo al atacante o usuario final
    print(f"--- [!] ERROR INTERNO FATAL [!] ---\n{error}")
    try:
        return await render_template('500.html'), 500
    except:
        return "Error Interno del Servidor", 500

# Configuración de Discord
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5000/callback")
API_ENDPOINT = 'https://discord.com/api/v10'

# Webhooks para Reportes y Sugerencias
WEBHOOK_REPORTES = "https://discord.com/api/webhooks/1483736682359554139/hwZt6Rz3Qp6gWU0dm33_EpGkPX48ZA_pfVredc4boZ4QuRUy62YQ18gEXrkF99tkrXuv"
WEBHOOK_SUGERENCIAS = "https://discord.com/api/webhooks/1483737062057185392/tdSlUlqh2lv9OLpLqgx508nK7TVw578MFfzY2QPEIJqRQjk_eATauc-8d8m7-E0TSkQq"

if not CLIENT_ID or not CLIENT_SECRET:
    print(f"--- [!] AVISO DE CONFIGURACIÓN [!] ---")
    print(f"No se detectó DISCORD_CLIENT_ID en el archivo:")
    print(f"Ruta: {os.path.join(PROJECT_ROOT, '.env')}")
    print(f"----------------------------------------")

# Defensas y tiempos de espera de administración
ADMIN_COOLDOWNS = {} # {user_id: last_action_timestamp}
COOLDOWN_SECONDS = 3

# Rate Limiter Global (Anti-Spam DDoS básico)
RATE_LIMITS = {}
RATE_LIMIT_MAX_REQUESTS = 5
RATE_LIMIT_PERIOD_SECONDS = 60
BANNED_IPS = {}
BAN_TIME_SECONDS = 10

@app.before_request
async def rate_limit_check():
    # Exceptuar rutas estáticas u otras que no queramos limitar
    if request.path.startswith('/static/'):
        return

    # Obtener IP del cliente (soporte proxy inverso)
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    # Sanitizar en caso de local IPv6 (::1) o similar
    if client_ip and ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()
    
    if not client_ip:
        client_ip = "unknown"
        
    now = time.time()
    print(f"[DEBUG SECURITY] Detected IP: {client_ip}")
    
    # Comprobar si está bloqueado temporalmente (hard-ban)
    ban_expiry = BANNED_IPS.get(client_ip, 0)
    if now < ban_expiry:
        # print(f"[DEBUG SECURITY] IP {client_ip} BANEADA. Quedan {round(ban_expiry - now, 1)}s")
        return await render_template('429.html'), 429
    elif ban_expiry != 0:
        del BANNED_IPS[client_ip] 
    
    if client_ip in RATE_LIMITS:
        RATE_LIMITS[client_ip] = [t for t in RATE_LIMITS[client_ip] if now - t < RATE_LIMIT_PERIOD_SECONDS]
    else:
        RATE_LIMITS[client_ip] = []
    
    # print(f"[DEBUG SECURITY] IP: {client_ip} | Pet. previas: {len(RATE_LIMITS[client_ip])}")
        
    if len(RATE_LIMITS[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        # Castigar con 10 segundos fijos por spamear
        BANNED_IPS[client_ip] = now + BAN_TIME_SECONDS
        print(f"[!] SEGURIDAD: IP {client_ip} ha sido bloqueada por 10s por exceso de peticiones.")
        return await render_template('429.html'), 429
        
    RATE_LIMITS[client_ip].append(now)

# Utilidades internas de la web
async def fetch_user_guilds(access_token):
    headers = {'Authorization': f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as cs:
        # with_counts=true es vital para obtener el approximate_member_count real de los servidores
        async with cs.get(f"{API_ENDPOINT}/users/@me/guilds?with_counts=true", headers=headers) as r:
            if r.status == 200:
                data = await r.json()
                # Debug: print(f"Fetched {len(data)} guilds")
                return data
            return []

def login_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return await f(*args, **kwargs)
    return decorated_function

@app.route('/', methods=['GET', 'POST'])
async def index():
    return await render_template('index.html')

@app.route('/test-payload', methods=['POST'])
async def test_payload():
    # Forzar la lectura de datos para disparar el límite de MAX_CONTENT_LENGTH
    data = await request.get_data()
    return "OK", 200

@app.route('/docs')
async def docs():
    return await render_template('docs.html')

@app.route('/modules/music')
async def music_module():
    return await render_template('music.html')

@app.route('/modules/economy')
async def economy_module():
    return await render_template('economy.html')

@app.route('/modules/levels')
async def levels_module():
    return await render_template('levels.html')

@app.route('/modules/moderation')
async def moderation_module():
    return await render_template('moderation.html')

@app.route('/modules/serverconfig')
async def serverconfig_module():
    return await render_template('serverconfig.html')

@app.route('/report', methods=['GET', 'POST'])
@login_required
async def report():
    
    if request.method == 'POST':
        form = await request.form
        report_type = form.get('type')
        subject = form.get('subject')
        description = form.get('description')
        priority = form.get('priority')
        evidence_url = form.get('evidence_url', '').strip() or 'No proporcionada'
        user_discord_id = form.get('user_discord_id', session['user']['id'])
        user = session['user']
        
        # Guardar en DB
        await database_manager.execute(
            "INSERT INTO user_feedback (user_id, type, subject, description, priority) VALUES (?, ?, ?, ?, ?)",
            (int(user_discord_id), report_type, subject, f"{description}\n\nEvidencia: {evidence_url}", priority)
        )
        # Enviar Webhook con soporte para archivos
        async with aiohttp.ClientSession() as cs:
            color = 0xff4757 # Red for reports
            if priority == 'Baja': color = 0x2ed573
            elif priority == 'Media': color = 0xffa502
            
            embed = {
                "title": f"🚨 Nuevo Reporte: {subject}",
                "description": description,
                "color": color,
                "fields": [
                    {"name": "Tipo", "value": report_type, "inline": True},
                    {"name": "Prioridad", "value": priority, "inline": True},
                    {"name": "Usuario", "value": f"{user['username']} (<@{user_discord_id}>)", "inline": False},
                    {"name": "Evidencia (URL)", "value": evidence_url, "inline": False}
                ],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            # Preparar datos multipart para el webhook
            data = aiohttp.FormData()
            
            files = await request.files
            report_file = files.get('evidence_file')
            
            if report_file and report_file.filename:
                # Si hay un archivo, lo adjuntamos
                file_bytes = report_file.read()
                data.add_field('file', file_bytes, filename=report_file.filename, content_type=report_file.content_type)
                # Si es una imagen, la mostramos en el embed
                if report_file.content_type.startswith('image/'):
                    embed["image"] = {"url": f"attachment://{report_file.filename}"}
            
            # Añadir el JSON del embed (esto debe ir una sola vez)
            data.add_field('payload_json', json.dumps({"embeds": [embed]}))

            await cs.post(WEBHOOK_REPORTES, data=data)
        
        return await render_template('report.html', success=True, user=session['user'])

    return await render_template('report.html', user=session['user'])

@app.route('/suggest', methods=['GET', 'POST'])
@login_required
async def suggest():
    
    if request.method == 'POST':
        form = await request.form
        category = form.get('category')
        title = form.get('title')
        description = form.get('description')
        evidence_url = form.get('evidence_url', '').strip() or 'No proporcionada'
        user = session['user']
        
        # Guardar en DB
        await database_manager.execute(
            "INSERT INTO user_feedback (user_id, type, subject, description) VALUES (?, ?, ?, ?)",
            (int(user['id']), "Sugerencia: " + category, title, f"{description}\n\nAdjuntos: {evidence_url}")
        )
         # Enviar Webhook
        async with aiohttp.ClientSession() as cs:
            embed = {
                "title": f"💡 Nueva Sugerencia: {title}",
                "description": description,
                "color": 0x7d5fff, # Purple for suggestions
                "fields": [
                    {"name": "Categoría", "value": category, "inline": True},
                    {"name": "Usuario", "value": f"{user['username']} (ID: {user['id']})", "inline": True},
                    {"name": "Adjuntos (URL)", "value": evidence_url, "inline": False}
                ],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            data = aiohttp.FormData()
            
            files = await request.files
            suggest_file = files.get('suggest_file')
            if suggest_file and suggest_file.filename:
                file_bytes = suggest_file.read()
                data.add_field('file', file_bytes, filename=suggest_file.filename, content_type=suggest_file.content_type)
                if suggest_file.content_type.startswith('image/'):
                    embed["image"] = {"url": f"attachment://{suggest_file.filename}"}
            
            # Añadir payload_json una sola vez
            data.add_field('payload_json', json.dumps({"embeds": [embed]}))

            await cs.post(WEBHOOK_SUGERENCIAS, data=data)
        
        return await render_template('suggest.html', success=True, user=session['user'])

    return await render_template('suggest.html', user=session['user'])

# Rutas de autenticación de Discord OAuth2

@app.route('/login')
async def login():
    auth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify%20guilds"
    )
    return redirect(auth_url)

@app.route('/callback')
async def callback():
    code = request.args.get('code')
    if not code:
        return redirect(url_for('index'))

    async with aiohttp.ClientSession() as cs:
        # Step 1: Exchange code for token
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        
        async with cs.post(f"{API_ENDPOINT}/oauth2/token", data=data, headers=headers) as r:
            token_json = await r.json()
            if 'access_token' not in token_json:
                return f"Error: {token_json.get('error_description', 'Unknown error')}", 400
            
            access_token = token_json['access_token']
        
        # Step 2: Fetch User Info
        headers = {'Authorization': f"Bearer {access_token}"}
        async with cs.get(f"{API_ENDPOINT}/users/@me", headers=headers) as r:
            user_data = await r.json()
            session['user'] = {
                'id': user_data['id'],
                'username': user_data['username'],
                'avatar': user_data['avatar'],
                'discriminator': user_data['discriminator'],
                'access_token': access_token
            }
            # Registrar login para analíticas
            await database_manager.record_dashboard_login(
                int(user_data['id']), 
                user_data['username'], 
                user_data['avatar']
            )
            # Limpiar servers para forzar refresco
            session.pop('servers', None)

    return redirect(url_for('dashboard'))

@app.route('/logout')
async def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
async def dashboard():
    
    user = session['user']
    owner_id = os.getenv("OWNER_ID")
    is_owner = str(user['id']) == str(owner_id)
    
    # Obtener servidores del usuario
    if 'servers' not in session or request.args.get('refresh') == 'true':
        try:
            all_guilds = await fetch_user_guilds(user['access_token'])
            async with aiohttp.ClientSession() as client:
                headers = {"Authorization": f"Bot {os.getenv('DISCORD_TOKEN')}"}
                async with client.get(f"{API_ENDPOINT}/users/@me/guilds", headers=headers) as resp:
                    bot_guilds = await resp.json() if resp.status == 200 else []
            
            bot_guild_ids = [str(g['id']) for g in bot_guilds]
            
            # Guardamos todos los servidores donde es admin para que pueda invitar
            servers = [
                g for g in all_guilds 
                if (int(g['permissions']) & 0x8) or g['owner']
            ]
            
            # Marcamos cuáles tienen al bot
            for s in servers:
                s['has_bot'] = str(s['id']) in bot_guild_ids

            session['servers'] = servers
        except Exception as e:
            print(f"Error en dashboard: {e}")
            servers = session.get('servers', [])
    else:
        servers = session['servers']

    return await render_template('dashboard.html', 
                               user=user, 
                               servers=servers,
                               is_owner=is_owner,
                               client_id=CLIENT_ID,
                               section='servers')

@app.route('/dashboard/account')
@login_required
async def dashboard_account():
    
    user = session['user']
    owner_id = os.getenv("OWNER_ID")
    is_owner = str(user['id']) == str(owner_id)
    
    # Asegurar servidores en sesión
    servers = session.get('servers', [])
    if not servers:
        access_token = user.get('access_token')
        if access_token:
            all_guilds = await fetch_user_guilds(access_token)
            servers = [g for g in all_guilds if (int(g['permissions']) & 0x8) or g['owner']]
            session['servers'] = servers

    # Calcular servidores mutuos
    mutual_count = 0
    if servers:
        async with aiohttp.ClientSession() as client:
            headers = {"Authorization": f"Bot {os.getenv('DISCORD_TOKEN')}"}
            for s in servers:
                try:
                    async with client.get(f"{API_ENDPOINT}/guilds/{s['id']}", headers=headers) as resp:
                        if resp.status == 200:
                            mutual_count += 1
                except:
                    continue

    return await render_template('dashboard.html', 
                               user=user, 
                               servers=servers,
                               is_owner=is_owner,
                               mutual_count=mutual_count,
                               section='account')



# Ayudantes para la obtención de datos de Discord API
async def fetch_guild_channels(guild_id):
    """Obtiene los canales del servidor via Bot API."""
    text_channels = []
    voice_channels = []
    categories = []
    try:
        async with aiohttp.ClientSession() as client:
            headers = {"Authorization": f"Bot {os.getenv('DISCORD_TOKEN')}"}
            async with client.get(f"{API_ENDPOINT}/guilds/{guild_id}/channels", headers=headers) as resp:
                if resp.status == 200:
                    channels = await resp.json()
                    for ch in sorted(channels, key=lambda c: c.get('position', 0)):
                        ch_type = ch.get('type')
                        ch_data = {'id': ch['id'], 'name': ch['name'], 'type': ch_type}
                        
                        if ch_type in [0, 5]:  # Text or News channel
                            ch_data['icon'] = '#' if ch_type == 0 else '📢'
                            text_channels.append(ch_data)
                        elif ch_type in [2, 13]:  # Voice or Stage channel
                            ch_data['icon'] = '🔊' if ch_type == 2 else '🎭'
                            voice_channels.append(ch_data)
                        elif ch_type == 4:  # Category
                            ch_data['icon'] = '📁'
                            categories.append(ch_data)
    except Exception as e:
        print(f"Error fetching channels for {guild_id}: {e}")
    return text_channels, voice_channels, categories

async def fetch_guild_roles(guild_id):
    """Obtiene los roles del servidor via Bot API."""
    roles = []
    try:
        async with aiohttp.ClientSession() as client:
            headers = {"Authorization": f"Bot {os.getenv('DISCORD_TOKEN')}"}
            async with client.get(f"{API_ENDPOINT}/guilds/{guild_id}/roles", headers=headers) as resp:
                if resp.status == 200:
                    all_roles = await resp.json()
                    for role in sorted(all_roles, key=lambda r: r.get('position', 0), reverse=True):
                        if role['name'] != '@everyone' and not role.get('managed', False):
                            roles.append({'id': role['id'], 'name': role['name'], 'color': role.get('color', 0)})
    except Exception as e:
        print(f"Error fetching roles for {guild_id}: {e}")
    return roles

async def get_server_context(guild_id):
    if 'user' not in session: return None, None
    
    user = session['user']
    access_token = user.get('access_token')
    
    servers = session.get('servers', [])
    if not servers and access_token:
        all_guilds = await fetch_user_guilds(access_token)
        session['servers'] = [g for g in all_guilds if (int(g['permissions']) & 0x8) or g['owner']]
        servers = session['servers']
        
    target_guild = next((g for g in servers if str(g['id']) == str(guild_id)), None)
    if not target_guild: return None, None

    # Cacheo de Discord API data
    cache_key = str(guild_id)
    cache_entry = app.config.setdefault('API_CACHE', {}).get(cache_key)
    
    if cache_entry and time.time() - cache_entry['timestamp'] < 300: # 5 minutos
        bot_on = cache_entry['bot_on']
        member_count = cache_entry['member_count']
        text_channels = cache_entry['text_channels']
        voice_channels = cache_entry['voice_channels']
        categories = cache_entry.get('categories', [])
        roles = cache_entry['roles']
    else:
        bot_on = False
        member_count = 0
        try:
            async with aiohttp.ClientSession() as client:
                headers = {"Authorization": f"Bot {os.getenv('DISCORD_TOKEN')}"}
                async with client.get(f"{API_ENDPOINT}/guilds/{guild_id}?with_counts=true", headers=headers) as resp:
                    print(f"[DEBUG] Fetching guild {guild_id}: Status {resp.status}")
                    if resp.status == 200:
                        bot_on = True
                        guild_data = await resp.json()
                        member_count = guild_data.get('approximate_member_count', 0)
                    else:
                        error_data = await resp.text()
                        print(f"[DEBUG] Error fetching guild: {error_data}")
        except Exception as e:
            print(f"[DEBUG] Exception fetching guild: {e}")
            
        if not member_count:
            member_count = target_guild.get('approximate_member_count', 0)

        # Discord API: canales y roles (solo si el bot está en el servidor)
        text_channels = []
        voice_channels = []
        categories = []
        if bot_on:
            text_channels, voice_channels, categories = await fetch_guild_channels(guild_id)
            roles = await fetch_guild_roles(guild_id)
            
        app.config['API_CACHE'][cache_key] = {
            'timestamp': time.time(),
            'bot_on': bot_on,
            'member_count': member_count,
            'text_channels': text_channels,
            'voice_channels': voice_channels,
            'categories': categories,
            'roles': roles
        }

    # Servidor settings
    settings = await database_manager.fetchone("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
    if not settings:
        await database_manager.execute("INSERT OR IGNORE INTO server_settings (guild_id) VALUES (?)", (int(guild_id),))
        settings = await database_manager.fetchone("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
        if not settings:
            settings = {'prefix': '!', 'language': 'es', 'leveling_enabled': 1}

    # Economy settings
    economy_settings = await database_manager.fetchone("SELECT * FROM economy_settings WHERE guild_id = ?", (guild_id,))
    if not economy_settings:
        await database_manager.execute("INSERT OR IGNORE INTO economy_settings (guild_id) VALUES (?)", (int(guild_id),))
        economy_settings = await database_manager.fetchone("SELECT * FROM economy_settings WHERE guild_id = ?", (guild_id,))
        if not economy_settings:
            economy_settings = {'currency_name': 'créditos', 'currency_emoji': '🪙', 'start_balance': 100,
                               'daily_min': 100, 'daily_max': 500, 'work_min': 50, 'work_max': 250,
                               'work_cooldown': 3600, 'rob_cooldown': 21600}
    
    # Gambling channels
    gambling_channels = await database_manager.fetchall(
        "SELECT channel_id FROM gambling_active_channels WHERE guild_id = ?", (guild_id,)
    )
    gambling_channel_ids = [str(ch['channel_id']) for ch in gambling_channels]
        
    # Economy active channels
    economy_channels = await database_manager.fetchall(
        "SELECT channel_id FROM economy_active_channels WHERE guild_id = ?", (guild_id,)
    )
    economy_channel_ids = [str(ch['channel_id']) for ch in economy_channels]

    # TTS settings
    tts_settings = await database_manager.fetchone("SELECT * FROM tts_guild_settings WHERE guild_id = ?", (guild_id,))
    tts_channel = await database_manager.fetchone("SELECT * FROM tts_active_channels WHERE guild_id = ?", (guild_id,))
    
    # Reaction roles
    reaction_roles = await database_manager.fetchall("SELECT * FROM reaction_roles WHERE guild_id = ?", (guild_id,))
    
    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=8&guild_id={guild_id}&scope=bot%20applications.commands"
    
    # Fetch Level Rewards
    level_rewards = await database_manager.fetchall(
        "SELECT level, role_id FROM role_rewards WHERE guild_id = ? ORDER BY level ASC", 
        (guild_id,)
    )
    # Fetch Shop Items
    shop_items = await database_manager.fetchall(
        "SELECT * FROM shop_items WHERE guild_id = ? ORDER BY price ASC", 
        (guild_id,)
    )
    
    return target_guild, {
        "bot_on": bot_on,
        "member_count": member_count,
        "settings": settings,
        "economy_settings": economy_settings,
        "economy_channel_ids": economy_channel_ids,
        "gambling_channel_ids": gambling_channel_ids,
        "tts_settings": tts_settings,
        "tts_channel": tts_channel,
        "reaction_roles": reaction_roles,
        "text_channels": text_channels,
        "voice_channels": voice_channels,
        "categories": categories,
        "roles": roles,
        "invite_url": invite_url,
        "level_rewards": level_rewards,
        "shop_items": shop_items,
        "user_servers": servers
    }

@app.route('/dashboard/server/<guild_id>/deploy/<feature>', methods=['POST'])
@login_required
async def dashboard_deploy(guild_id, feature):
    target_guild, ctx = await get_server_context(guild_id)
    if not target_guild:
        return "No tienes acceso o permisos de administrador en este servidor.", 403

    settings = await database_manager.fetchone("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
    if not settings:
        return "Configuración no encontrada.", 404

    async with aiohttp.ClientSession() as client:
        headers = {
            "Authorization": f"Bot {os.getenv('DISCORD_TOKEN')}",
            "Content-Type": "application/json"
        }
        
        if feature == 'tickets':
            channel_id = settings.get('ticket_panel_channel_id')
            if not channel_id:
                return "Debes configurar el canal del panel primero.", 400
            
            title = settings.get('ticket_panel_title') or "📠 Soporte Técnico"
            desc = settings.get('ticket_panel_desc') or "¿Necesitas ayuda con algo del servidor o quieres hacer una denuncia?\n\n**Oprime el botón abajo para abrir un ticket de soporte privado.**"
                
            payload = {
                "embeds": [{
                    "title": title,
                    "description": desc,
                    "color": 0xFFFDD0 # CREAM_COLOR
                }],
                "components": [{
                    "type": 1,
                    "components": [{
                        "type": 2,
                        "label": "Abrir Ticket",
                        "style": 1,
                        "custom_id": "ticket_open_btn",
                        "emoji": {"name": "🎟️"}
                    }]
                }]
            }
        elif feature == 'confessions':
            channel_id = settings.get('confessions_channel_id')
            if not channel_id:
                return "Debes configurar el canal de confesiones primero.", 400
            
            title = settings.get('confessions_panel_title') or "🕵️ Buzón de Confesiones"
            desc = settings.get('confessions_panel_desc') or "Haz clic en el botón de abajo para enviar una confesión de forma totalmente anónima.\n\n*Nadie sabrá quién envió el mensaje.*"
                
            payload = {
                "embeds": [{
                    "title": title,
                    "description": desc,
                    "color": 0x4B0082 # Dark Purple
                }],
                "components": [{
                    "type": 1,
                    "components": [{
                        "type": 2,
                        "label": "Confesarse",
                        "style": 2,
                        "custom_id": "confess_open_btn",
                        "emoji": {"name": "🕵️"}
                    }]
                }]
            }
        else:
            return "Característica no válida.", 400

        async with client.post(f"{API_ENDPOINT}/channels/{channel_id}/messages", headers=headers, json=payload) as resp:
            if resp.status == 200:
                return "OK", 200
            else:
                error_text = await resp.text()
                print(f"Error deploying {feature}: {error_text}")
                return f"Error de Discord: {resp.status}", 500

@app.route('/dashboard/server/<guild_id>', defaults={'section': 'general'}, methods=['GET', 'POST'])
@app.route('/dashboard/server/<guild_id>/<section>', methods=['GET', 'POST'])
@login_required
async def dashboard_server(guild_id, section):
    target_guild, ctx = await get_server_context(guild_id)
    if not target_guild:
        return redirect(url_for('dashboard', refresh='true'))

    # Manejo de formularios POST para configuraciones
    if request.method == 'POST':
        form = await request.form
        await database_manager.execute("INSERT OR IGNORE INTO server_settings (guild_id) VALUES (?)", (int(guild_id),))
        
        if section == 'general':
            prefix = form.get('prefix', '!')
            language = form.get('language', 'es')
            leveling = form.get('leveling') == 'on'
            mod_enabled = 1 if form.get('mod_enabled') == 'on' else 0
            eco_enabled = 1 if form.get('eco_enabled') == 'on' else 0
            gamble_enabled = 1 if form.get('gamble_enabled') == 'on' else 0
            tickets_enabled = 1 if form.get('tickets_enabled') == 'on' else 0
            music_enabled = 1 if form.get('music_enabled') == 'on' else 0
            tts_enabled = 1 if form.get('tts_enabled') == 'on' else 0
            rr_enabled = 1 if form.get('rr_enabled') == 'on' else 0

            await database_manager.execute(
                """UPDATE server_settings SET 
                    prefix = ?, language = ?, leveling_enabled = ?,
                    mod_enabled = ?, eco_enabled = ?, gamble_enabled = ?,
                    tickets_enabled = ?, music_enabled = ?, tts_enabled = ?,
                    rr_enabled = ?
                WHERE guild_id = ?""",
                (prefix, language, 1 if leveling else 0, 
                 mod_enabled, eco_enabled, gamble_enabled,
                 tickets_enabled, music_enabled, tts_enabled,
                 rr_enabled, int(guild_id))
            )

        elif section == 'moderation':
            log_channel = form.get('log_channel_id') or None
            autorole = form.get('autorole_id') or None
            anti_invite = 1 if form.get('anti_invite') == 'on' else 0
            banned_words = form.get('banned_words', '').strip()
            mod_enabled = 1 if form.get('mod_enabled') == 'on' else 0
            await database_manager.execute(
                "UPDATE server_settings SET log_channel_id = ?, autorole_id = ?, automod_anti_invite = ?, automod_banned_words = ?, mod_enabled = ? WHERE guild_id = ?",
                (int(log_channel) if log_channel else None, int(autorole) if autorole else None, anti_invite, banned_words, mod_enabled, int(guild_id))
            )

        elif section == 'config':
            welcome_ch = form.get('welcome_channel_id') or None
            goodbye_ch = form.get('goodbye_channel_id') or None
            welcome_msg = form.get('welcome_message', '').strip() or None
            goodbye_msg = form.get('goodbye_message', '').strip() or None
            welcome_banner = form.get('welcome_banner_url', '').strip() or None
            goodbye_banner = form.get('goodbye_banner_url', '').strip() or None
            welcome_title_color = form.get('welcome_title_color', '#000000')
            welcome_subtitle_color = form.get('welcome_subtitle_color', '#000000')
            goodbye_title_color = form.get('goodbye_title_color', '#000000')
            goodbye_subtitle_color = form.get('goodbye_subtitle_color', '#000000')
            welcome_top_text = form.get('welcome_top_text', '').strip() or None
            goodbye_top_text = form.get('goodbye_top_text', '').strip() or None
            await database_manager.execute(
                """UPDATE server_settings SET 
                    welcome_channel_id = ?, goodbye_channel_id = ?,
                    welcome_message = ?, goodbye_message = ?,
                    welcome_banner_url = ?, goodbye_banner_url = ?,
                    welcome_title_color = ?, welcome_subtitle_color = ?,
                    goodbye_title_color = ?, goodbye_subtitle_color = ?,
                    welcome_top_text = ?, goodbye_top_text = ?
                WHERE guild_id = ?""",
                (int(welcome_ch) if welcome_ch else None, int(goodbye_ch) if goodbye_ch else None,
                 welcome_msg, goodbye_msg, welcome_banner, goodbye_banner,
                 welcome_title_color, welcome_subtitle_color,
                 goodbye_title_color, goodbye_subtitle_color,
                 welcome_top_text, goodbye_top_text, int(guild_id))
            )

        elif section == 'economy':
            action = form.get('action')
            if action == 'add_item':
                name = form.get('item_name')
                desc = form.get('item_desc')
                price = form.get('item_price')
                type_ = form.get('item_type')
                raw_data = form.get('item_raw_data', '')
                
                if name and desc and price and price.isdigit() and type_ in ['role', 'consumable']:
                    await database_manager.execute(
                        "INSERT INTO shop_items (guild_id, name, description, price, type, raw_data) VALUES (?, ?, ?, ?, ?, ?)",
                        (int(guild_id), name.strip(), desc.strip(), int(price), type_, raw_data.strip())
                    )
            elif action == 'delete_item':
                item_id = form.get('delete_item_id')
                if item_id and item_id.isdigit():
                    await database_manager.execute(
                        "DELETE FROM shop_items WHERE guild_id = ? AND item_id = ?",
                        (int(guild_id), int(item_id))
                    )
            else:
                eco_enabled = 1 if form.get('eco_enabled') == 'on' else 0
                currency_name = form.get('currency_name', 'créditos')
                currency_emoji = form.get('currency_emoji', '🪙')
                start_balance = form.get('start_balance', 100)
                work_min = form.get('work_min', 50)
                work_max = form.get('work_max', 250)
                work_cooldown = form.get('work_cooldown', 3600)
                daily_min = form.get('daily_min', 100)
                daily_max = form.get('daily_max', 500)
                rob_cooldown = form.get('rob_cooldown', 21600)

                await database_manager.execute(
                    """UPDATE economy_settings SET 
                        currency_name = ?, currency_emoji = ?, start_balance = ?,
                        daily_min = ?, daily_max = ?, work_min = ?, work_max = ?,
                        work_cooldown = ?, rob_cooldown = ?
                    WHERE guild_id = ?""",
                    (currency_name, currency_emoji, int(start_balance),
                     int(daily_min), int(daily_max), int(work_min), int(work_max),
                     int(work_cooldown), int(rob_cooldown), int(guild_id))
                )

                # Update active channels
                selected_channels = form.getlist('economy_channels')
                await database_manager.execute("DELETE FROM economy_active_channels WHERE guild_id = ?", (int(guild_id),))
                for ch_id in selected_channels:
                    if ch_id:
                        await database_manager.execute("INSERT INTO economy_active_channels (guild_id, channel_id) VALUES (?, ?)", (int(guild_id), int(ch_id)))

        elif section == 'gambling':
            gamble_enabled = 1 if form.get('gamble_enabled') == 'on' else 0
            # Get selected channel IDs from form
            selected_channels = form.getlist('gambling_channels')
            # Clear existing and re-insert
            await database_manager.execute("DELETE FROM gambling_active_channels WHERE guild_id = ?", (int(guild_id),))
            for ch_id in selected_channels:
                if ch_id:
                    await database_manager.execute(
                        "INSERT OR IGNORE INTO gambling_active_channels (guild_id, channel_id) VALUES (?, ?)",
                        (int(guild_id), int(ch_id))
                    )
            await database_manager.execute(
                "UPDATE server_settings SET gamble_enabled = ? WHERE guild_id = ?",
                (gamble_enabled, int(guild_id))
            )

        elif section == 'utility':
            utility_enabled = 1 if form.get('utility_enabled') == 'on' else 0
            temp_ch = form.get('temp_channel_creator_id') or None
            confess_ch = form.get('confessions_channel_id') or None
            confess_title = form.get('confessions_panel_title', '').strip() or None
            confess_desc = form.get('confessions_panel_desc', '').strip() or None
            await database_manager.execute(
                """UPDATE server_settings SET 
                    utility_enabled = ?,
                    temp_channel_creator_id = ?,
                    confessions_channel_id = ?,
                    confessions_panel_title = ?,
                    confessions_panel_desc = ?
                WHERE guild_id = ?""",
                (utility_enabled,
                 int(temp_ch) if temp_ch else None, 
                 int(confess_ch) if confess_ch else None,
                 confess_title, confess_desc,
                 int(guild_id))
            )

        elif section == 'levels':
            action = form.get('action')
            print(f"[DEBUG LEVELS] Received action: {action}")
            print(f"[DEBUG LEVELS] Form data: {form}")
            if action == 'add_reward':
                level_req = form.get('level_req')
                role_id = form.get('reward_role_id')
                print(f"[DEBUG LEVELS] add_reward: level={level_req}, role={role_id}")
                if level_req and role_id and level_req.isdigit():
                    await database_manager.execute(
                        "REPLACE INTO role_rewards (guild_id, level, role_id) VALUES (?, ?, ?)",
                        (int(guild_id), int(level_req), int(role_id))
                    )
                    print(f"[DEBUG LEVELS] Replaced into role_rewards")
            elif action == 'delete_reward':
                level_req = form.get('delete_level')
                if level_req and level_req.isdigit():
                    await database_manager.execute(
                        "DELETE FROM role_rewards WHERE guild_id = ? AND level = ?",
                        (int(guild_id), int(level_req))
                    )
            else:
                leveling = form.get('leveling') == 'on'
                await database_manager.execute(
                    "UPDATE server_settings SET leveling_enabled = ? WHERE guild_id = ?",
                    (1 if leveling else 0, int(guild_id))
                )
            
        elif section == 'tts':
            tts_enabled = 1 if form.get('tts_enabled') == 'on' else 0
            tts_lang = form.get('tts_lang', 'es')
            tts_ch = form.get('tts_channel_id')
            await database_manager.execute("REPLACE INTO tts_guild_settings (guild_id, lang) VALUES (?, ?)", (int(guild_id), tts_lang))
            if tts_ch:
                await database_manager.execute("REPLACE INTO tts_active_channels (guild_id, text_channel_id) VALUES (?, ?)", (int(guild_id), int(tts_ch)))
            else:
                await database_manager.execute("DELETE FROM tts_active_channels WHERE guild_id = ?", (int(guild_id),))
            await database_manager.execute(
                "UPDATE server_settings SET tts_enabled = ? WHERE guild_id = ?",
                (tts_enabled, int(guild_id))
            )

        elif section == 'tickets':
            tickets_enabled = 1 if form.get('tickets_enabled') == 'on' else 0
            ticket_cat = form.get('ticket_category_id') or None
            ticket_log = form.get('ticket_log_channel_id') or None
            ticket_panel = form.get('ticket_panel_channel_id') or None
            ticket_panel_title = form.get('ticket_panel_title', '').strip() or None
            ticket_panel_desc = form.get('ticket_panel_desc', '').strip() or None
            ticket_welcome_title = form.get('ticket_welcome_title', '').strip() or None
            ticket_welcome_desc = form.get('ticket_welcome_desc', '').strip() or None
            
            await database_manager.execute(
                """UPDATE server_settings SET 
                    tickets_enabled = ?, 
                    ticket_category_id = ?, 
                    ticket_log_channel_id = ?,
                    ticket_panel_channel_id = ?,
                    ticket_panel_title = ?,
                    ticket_panel_desc = ?,
                    ticket_welcome_title = ?,
                    ticket_welcome_desc = ?
                WHERE guild_id = ?""",
                (tickets_enabled, 
                 int(ticket_cat) if ticket_cat else None, 
                 int(ticket_log) if ticket_log else None,
                 int(ticket_panel) if ticket_panel else None,
                 ticket_panel_title, ticket_panel_desc,
                 ticket_welcome_title, ticket_welcome_desc,
                 int(guild_id))
            )

        elif section == 'music':
            music_enabled = 1 if form.get('music_enabled') == 'on' else 0
            await database_manager.execute(
                "UPDATE server_settings SET music_enabled = ? WHERE guild_id = ?",
                (music_enabled, int(guild_id))
            )

        elif section == 'reaction_roles':
            rr_enabled = 1 if form.get('rr_enabled') == 'on' else 0
            await database_manager.execute(
                "UPDATE server_settings SET rr_enabled = ? WHERE guild_id = ?",
                (rr_enabled, int(guild_id))
            )
            action = form.get('action')
            if action == 'create':
                rr_channel = form.get('rr_channel_id')
                rr_title = form.get('rr_title', 'Reaction Roles')
                rr_desc = form.get('rr_desc', 'Reacciona para obtener un rol')
                rr_color = form.get('rr_color', '#ffb7c5').replace('#', '')
                try: color_int = int(rr_color, 16)
                except: color_int = 16758725
                
                pairs = []
                for i in range(1, 6):
                    emoji = form.get(f'rr_emoji_{i}', '').strip()
                    role = form.get(f'rr_role_{i}', '').strip()
                    if emoji and role:
                        pairs.append((emoji, role))
                
                if rr_channel and pairs:
                    embed = {
                        "title": rr_title,
                        "description": rr_desc,
                        "color": color_int
                    }
                    payload = {"embeds": [embed]}
                    msg_id = await api_helpers.create_discord_message(int(rr_channel), payload, os.getenv("DISCORD_TOKEN"))
                    if msg_id:
                        for emoji, role_id in pairs:
                            success = await api_helpers.add_discord_reaction(int(rr_channel), int(msg_id), emoji, os.getenv("DISCORD_TOKEN"))
                            if success:
                                await database_manager.execute(
                                    "INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
                                    (int(guild_id), int(msg_id), emoji, int(role_id))
                                )
            elif action == 'delete':
                delete_msg = form.get('delete_message_id')
                delete_emoji = form.get('delete_emoji')
                if delete_msg and delete_emoji:
                    await database_manager.execute(
                        "DELETE FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
                        (int(guild_id), int(delete_msg), delete_emoji)
                    )

        return redirect(url_for('dashboard_server', guild_id=guild_id, section=section, saved='true'))

    # Pre-bind translator for the template
    lang = ctx['settings'].get('language', 'es')
    def t(key, **kwargs):
        return _t(key, lang=lang, **kwargs)

    return await render_template('guild_panel.html', 
                               user=session['user'], 
                               server=target_guild, 
                               section=section,
                               saved=request.args.get('saved') == 'true',
                               t=t,
                               **ctx)

# Explicit static route just in case
@app.route('/static/<path:filename>')
async def static_files(filename):
    return await send_from_directory(app.static_folder, filename)

# Histórico simple en RAM para las gráficas (últimos 20 puntos)
stats_history = {
    "labels": [],
    "cpu": [],
    "ram": []
}

@app.route('/api/admin/stats')
async def get_admin_stats():
    if 'user' not in session:
        return {"error": "Unauthorized"}, 401
    
    owner_id = os.getenv("OWNER_ID")
    if str(session['user']['id']) != str(owner_id):
        return {"error": "Forbidden"}, 403

    now = datetime.now().strftime("%H:%M:%S")
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent

    stats_history["labels"].append(now)
    stats_history["cpu"].append(cpu)
    stats_history["ram"].append(ram)

    # Mantener solo los últimos 20 registros
    if len(stats_history["labels"]) > 20:
        stats_history["labels"].pop(0)
        stats_history["cpu"].pop(0)
        stats_history["ram"].pop(0)

    return stats_history

@app.route('/api/stats')
async def global_stats():
    try:
        # Gremios configurados en DB
        server_rows = await database_manager.fetchall("SELECT COUNT(*) as count FROM server_settings")
        total_servers = server_rows[0]['count'] if server_rows else 0
        
        # Usuarios únicos en niveles
        user_rows = await database_manager.fetchall("SELECT COUNT(DISTINCT user_id) as count FROM levels")
        total_users = user_rows[0]['count'] if user_rows else 0
    except:
        total_servers, total_users = 0, 0

    return {
        "servers": total_servers,
        "users": total_users,
        "commands_run": 0 # TODO: Implementar contador de comandos en DB
    }

def admin_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if 'user' not in session or str(session['user']['id']) != str(os.getenv("OWNER_ID", "713211618804367402")):
            return "Acceso Denegado. Esta área es exclusiva para el desarrollador del bot.", 403
        return await f(*args, **kwargs)
    return decorated_function

@app.route('/dashboard/admin')
@admin_required
async def admin_panel():
    user = session.get('user')
    # Todas las guilds donde el bot está activo
    all_guilds = await database_manager.get_bot_guilds()
    total_servers = len(all_guilds)
    
    # Usuarios autenticados (gente que ha entrado al dashboard)
    total_users_rows = await database_manager.fetchall("SELECT COUNT(*) as c FROM dashboard_users")
    total_users = total_users_rows[0]['c'] if total_users_rows else 0
    
    cpu_percent = psutil.cpu_percent(interval=0.1)
    ram_info = psutil.virtual_memory()
    ram_percent = ram_info.percent
    
    blacklist = await database_manager.get_all_blacklisted()
    bot_guilds = await database_manager.get_bot_guilds()
    recent_logs = await database_manager.get_recent_global_logs(50)
    system_logs = await database_manager.get_recent_system_logs(50)
    admin_audit_logs = await database_manager.get_recent_admin_audit_logs(50)
    
    # Obtener lista de tablas para el explorador
    tables_query = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    tables_rows = await database_manager.fetchall(tables_query)
    db_tables = [t['name'] for t in tables_rows]
    
    return await render_template('admin_panel.html', 
                                 user=user, section='admin',
                                 total_users=total_users, 
                                 total_guilds=total_servers,
                                 cpu_percent=cpu_percent,
                                 ram_percent=ram_percent,
                                 blacklist=blacklist,
                                 bot_guilds=bot_guilds,
                                 recent_logs=recent_logs,
                                 system_logs=system_logs,
                                 admin_audit_logs=admin_audit_logs,
                                 db_tables=db_tables)

@app.route('/api/admin/db/table/<table_name>')
@admin_required
async def api_admin_db_table(table_name):
    # Validar que el nombre de la tabla sea seguro (solo letras, números y guiones bajos)
    import re
    if not re.match(r'^[a-zA-Z0-9_]+$', table_name):
        return {"error": "Nombre de tabla inválido"}, 400
        
    try:
        # Paginación básica
        page = int(request.args.get('page', 1))
        per_page = 50
        offset = (page - 1) * per_page
        
        # Obtener datos de la tabla
        data = await database_manager.fetchall(f"SELECT * FROM {table_name} LIMIT ? OFFSET ?", (per_page, offset))
        
        # Obtener información de columnas y PK
        columns_info = await database_manager.fetchall(f"PRAGMA table_info({table_name})")
        pk_col = next((col['name'] for col in columns_info if col['pk'] == 1), None)
        columns = [col['name'] for col in columns_info]
        
        # Si no hay PK explícita, usar la primera columna como fallback
        if not pk_col and columns_info:
            pk_col = columns_info[0]['name']
            
        # Obtener total de filas
        count_row = await database_manager.fetchone(f"SELECT COUNT(*) as c FROM {table_name}")
        total = count_row['c'] if count_row else 0
        
        # Calcular total de páginas
        import math
        total_pages = math.ceil(total / per_page) if total > 0 else 1
        
        return {
            "success": True,
            "table": table_name,
            "data": data,
            "columns": columns,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "pk_col": pk_col
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

@app.route('/api/admin/db/delete', methods=['POST'])
@admin_required
async def api_admin_db_delete():
    user = session['user']
    import re
    data = await request.form
    table_name = data.get('table')
    primary_key_col = data.get('pk_col')
    primary_key_val = data.get('pk_val')
    
    if not table_name or not primary_key_col or not primary_key_val:
        return {"success": False, "message": "Datos de eliminación incompletos."}, 400
        
    if not re.match(r'^[a-zA-Z0-9_]+$', table_name) or not re.match(r'^[a-zA-Z0-9_]+$', primary_key_col):
        return {"success": False, "message": "Nombre de tabla o columna inválido."}, 400
        
    try:
        await database_manager.execute(f"DELETE FROM {table_name} WHERE {primary_key_col} = ?", (primary_key_val,))
        await database_manager.log_admin_action(user['id'], user['username'], f"db_delete_row", target_id=f"{table_name}:{primary_key_val}", details=f"Col: {primary_key_col}")
        return {"success": True, "message": "Fila eliminada correctamente."}
    except Exception as e:
        return {"success": False, "message": f"Error al eliminar: {str(e)}"}, 500

@app.route('/api/admin/db/update', methods=['POST'])
@admin_required
async def api_admin_db_update():
    user = session['user']
    import re
    data = await request.form
    table_name = data.get('table')
    pk_col = data.get('pk_col')
    pk_val = data.get('pk_val')
    
    # Obtener todos los campos a actualizar (excepto los de control)
    updates = {}
    for key, value in data.items():
        if key not in ['table', 'pk_col', 'pk_val']:
            updates[key] = value
            
    if not table_name or not pk_col or not pk_val or not updates:
        return {"success": False, "message": "Datos de actualización incompletos."}, 400
        
    if not re.match(r'^[a-zA-Z0-9_]+$', table_name) or not re.match(r'^[a-zA-Z0-9_]+$', pk_col):
        return {"success": False, "message": "Nombre de tabla o columna inválido."}, 400
        
    try:
        set_clause = ", ".join([f"{col} = ?" for col in updates.keys()])
        values = list(updates.values()) + [pk_val]
        
        query = f"UPDATE {table_name} SET {set_clause} WHERE {pk_col} = ?"
        await database_manager.execute(query, tuple(values))
        
        await database_manager.log_admin_action(user['id'], user['username'], f"db_update_row", target_id=f"{table_name}:{pk_val}", details=f"Cols: {', '.join(updates.keys())}")
        return {"success": True, "message": "Fila actualizada correctamente."}
    except Exception as e:
        return {"success": False, "message": f"Error al actualizar: {str(e)}"}, 500

@app.route('/api/admin/guild/leave', methods=['POST'])
@admin_required
async def api_admin_guild_leave():
    user = session['user']
    now = time.time()
    if str(user['id']) in ADMIN_COOLDOWNS and now - ADMIN_COOLDOWNS[str(user['id'])] < COOLDOWN_SECONDS:
        return {"success": False, "message": f"Por favor, espera {COOLDOWN_SECONDS} segundos entre acciones."}, 429
    
    data = await request.form
    guild_id = data.get('guild_id')
    if guild_id:
        await database_manager.execute(
            "INSERT INTO broadcast_queue (message, type, status) VALUES (?, 'leave_guild', 'pending')", 
            (guild_id,)
        )
        await database_manager.log_admin_action(user['id'], user['username'], "leave_guild", target_id=guild_id)
        ADMIN_COOLDOWNS[str(user['id'])] = now
        return {"success": True, "message": "Tarea de abandono programada correctamente."}
    return {"success": False, "message": "ID de servidor no proporcionado."}, 400

@app.route('/api/admin/blacklist/add', methods=['POST'])
@admin_required
async def api_admin_blacklist_add():
    user = session['user']
    data = await request.form
    discord_id = data.get('discord_id')
    entity_type = data.get('entity_type')
    reason = data.get('reason', 'Sin motivo especificado')
    if discord_id and discord_id.isdigit() and entity_type in ['user', 'guild']:
        await database_manager.add_to_blacklist(int(discord_id), entity_type, reason)
        await database_manager.log_admin_action(user['id'], user['username'], "blacklist_add", target_id=discord_id, details=f"Tipo: {entity_type}, Motivo: {reason}")
        return {"success": True, "message": f"{entity_type.capitalize()} añadido a la lista negra."}
    return {"success": False, "message": "Datos de bloqueo inválidos o incompletos."}, 400

@app.route('/api/admin/blacklist/remove/<int:discord_id>', methods=['POST'])
@admin_required
async def api_admin_blacklist_remove(discord_id):
    user = session['user']
    await database_manager.remove_from_blacklist(discord_id)
    await database_manager.log_admin_action(user['id'], user['username'], "blacklist_remove", target_id=str(discord_id))
    return {"success": True, "message": "Entidad removida de la lista negra correctamente."}

@app.route('/api/admin/backup')
@admin_required
async def api_admin_backup():
    db_path = os.getenv("BOT_DB", "bot_data.db")
    abs_db_path = os.path.abspath(db_path)
    if os.path.exists(abs_db_path):
        return await send_file(abs_db_path, as_attachment=True, attachment_filename=f"umapyoi_backup_{int(time.time())}.db")
    return "Base de datos no encontrada.", 404

@app.route('/api/admin/broadcast', methods=['POST'])
@admin_required
async def api_admin_broadcast():
    user = session['user']
    now = time.time()
    if str(user['id']) in ADMIN_COOLDOWNS and now - ADMIN_COOLDOWNS[str(user['id'])] < COOLDOWN_SECONDS:
        return {"success": False, "message": f"Cuidado con el spam. Espera {COOLDOWN_SECONDS} segundos."}, 429

    data = await request.form
    message = data.get('message')
    if message:
        await database_manager.execute("INSERT INTO broadcast_queue (message) VALUES (?)", (message,))
        await database_manager.log_admin_action(user['id'], user['username'], "global_broadcast", details=message[:100])
        ADMIN_COOLDOWNS[str(user['id'])] = now
        return {"success": True, "message": "Transmisión global programada correctamente."}
    return {"success": False, "message": "El mensaje no puede estar vacío."}, 400

@app.route('/api/admin/dm/send', methods=['POST'])
@admin_required
async def api_admin_dm_send():
    user = session['user']
    now = time.time()
    if str(user['id']) in ADMIN_COOLDOWNS and now - ADMIN_COOLDOWNS[str(user['id'])] < COOLDOWN_SECONDS:
        return {"success": False, "message": f"Espera un momento antes de enviar otro DM."}, 429

    data = await request.form
    user_id = data.get('user_id')
    content = data.get('message')
    if user_id and content:
        import json
        payload = json.dumps({"user_id": user_id, "content": content})
        await database_manager.execute(
            "INSERT INTO broadcast_queue (message, type, status) VALUES (?, 'send_dm', 'pending')", 
            (payload,)
        )
        await database_manager.log_admin_action(user['id'], user['username'], "send_dm", target_id=user_id, details=content[:100])
        ADMIN_COOLDOWNS[str(user['id'])] = now
        return {"success": True, "message": "Mensaje directo programado correctamente."}
    return {"success": False, "message": "ID de usuario o contenido faltante."}, 400

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

async def run_app():
    # El puerto por defecto en Quart es 5000, pero permitimos configurarlo
    port = int(os.getenv("PORT", 5000))
    if is_port_in_use(port):
        print(f"ERROR: El puerto {port} ya está en uso. ¿Hay otro servidor ejecutándose?")
        return

    config = {
        'host': '0.0.0.0',
        'port': port
    }
    
    # Asegurar que la base de datos esté inicializada (tablas de reportes, etc)
    database_manager.setup_database()
    
    print(f"Servidor web iniciado en http://localhost:{config['port']}")
    try:
        await app.run_task(**config)
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\nDeteniendo servidor web...")

if __name__ == '__main__':
    try:
        asyncio.run(run_app())
    except KeyboardInterrupt:
        pass
    finally:
        print("Servidor web apagado.")
