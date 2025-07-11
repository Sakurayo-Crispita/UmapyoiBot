CREAM_COLOR = 0xF0EAD6 # Usamos el valor hexadecimal directamente

# --- Mensajes y Banners de ServerConfig ---
DEFAULT_WELCOME_MESSAGE = "¡Bienvenid@ a {server.name}! Contigo somos {member_count}"
# URL del banner de bienvenida por defecto actualizada
DEFAULT_WELCOME_BANNER = "https://i.postimg.cc/YqsSwMMN/10-jul-2025-04-13-17-p-m.png" 

DEFAULT_GOODBYE_MESSAGE = "{user.name} ha dejado el nido. ¡Hasta la próxima!"
# URL del banner de despedida por defecto actualizada para mantener consistencia
DEFAULT_GOODBYE_BANNER = "https://i.postimg.cc/YqsSwMMN/10-jul-2025-04-13-17-p-m.png" 

TEMP_CHANNEL_PREFIX = "Sala de "

# --- URLs de Plantillas ---
WANTED_TEMPLATE_URL = "https://i.imgur.com/wNvXv8i.jpeg"

# --- Opciones de FFMPEG y YDL para Música ---
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -ar 48000 -ac 2 -b:a 192k'
}
YDL_OPTIONS = {
    'format': 'bestaudio[ext=webm][acodec=opus]/bestaudio/best',
    'quiet': True, 
    'default_search': 'ytsearch', 
    'source_address': '0.0.0.0',
    'noplaylist': True, 
    'cookiefile': 'cookies.txt',
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
}
