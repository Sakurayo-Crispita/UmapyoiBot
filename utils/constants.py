CREAM_COLOR = 0xF0EAD6 # Usamos el valor hexadecimal directamente

# - Mensajes y Banners de ServerConfig -
DEFAULT_WELCOME_MESSAGE = "¡Bienvenid@ a {server.name}! Contigo somos {member_count}"
# URL del banner de bienvenida por defecto actualizada
DEFAULT_WELCOME_BANNER = "https://i.postimg.cc/YqsSwMMN/10-jul-2025-04-13-17-p-m.png" 

DEFAULT_GOODBYE_MESSAGE = "{user.name} ha dejado el nido. ¡Hasta la próxima!"
# URL del banner de despedida por defecto actualizada para mantener consistencia
DEFAULT_GOODBYE_BANNER = "https://i.postimg.cc/YqsSwMMN/10-jul-2025-04-13-17-p-m.png"
# - NUEVO: URL de la página de comandos -
COMMANDS_PAGE_URL = "https://sakurayo-crispita.github.io/UmaPage/" 

TEMP_CHANNEL_PREFIX = "Sala de "

# - URLs de Plantillas -
WANTED_TEMPLATE_URL = "https://i.imgur.com/wNvXv8i.jpeg"

# - Emojis Personalizados -
# Para usar emojis personalizados, coloca su ID en este formato: "<:nombre:id>"
EMOJI_CHECK = "✅"
EMOJI_QUEUE = "🎵"
EMOJI_ERROR = "❌"
EMOJI_LEAVE = "🚪"

# - Opciones de FFMPEG y YDL para Música -
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -http_proxy http://f3aadc356489963dafc5:060b354af4eb4134@gw.dataimpulse.com:823',
    'options': '-vn -ar 48000 -ac 2 -b:a 192k'
}

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True, 
    'default_search': 'ytsearch', 
    'source_address': '0.0.0.0',
    'noplaylist': True, 
    'proxy': 'http://f3aadc356489963dafc5:060b354af4eb4134@gw.dataimpulse.com:823',
    'nocheckcertificate': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['web', 'mweb'],
            'js_runtimes': ['/usr/bin/node']
        },
        'cookiefile': 'cookies.txt'
    }
}
