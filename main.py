import discord
from discord.ext import commands
import os
import traceback
import datetime
import glob 
import aiohttp
from aiohttp import TCPConnector
import ssl  # <-- 1. AÑADIDO: Importamos la librería SSL
import certifi # <-- 2. AÑADIDO: Importamos la librería de certificados

# Importamos nuestros módulos de utilidades
from utils import database_manager
from utils import constants
from dotenv import load_dotenv

# --- CONFIGURACIÓN DE APIS Y CONSTANTES ---
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DB_FILE = "bot_data.db" 

def cleanup_tts_files():
    files = glob.glob("tts_*.mp3")
    if not files: return
    deleted_count = 0
    for f in files:
        try:
            os.remove(f)
            deleted_count += 1
        except OSError as e:
            print(f"Error al borrar el archivo TTS residual {f}: {e}")
    if deleted_count > 0:
        print(f"Limpieza: Se borraron {deleted_count} archivos .mp3 de TTS residuales.")

class UmapyoiBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db_file = DB_FILE
        self.GENIUS_API_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        self.CREAM_COLOR = discord.Color(constants.CREAM_COLOR)
        self.FFMPEG_OPTIONS = constants.FFMPEG_OPTIONS
        self.YDL_OPTIONS = constants.YDL_OPTIONS
        self.http_session = None

    async def setup_hook(self):
        # --- 3. MODIFICADO: Creamos la sesión con un contexto SSL y DNS específico ---
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = TCPConnector(
            resolver=aiohttp.AsyncResolver(nameservers=["8.8.8.8", "8.8.4.4"]),
            ssl=ssl_context,
        )
        self.http_session = aiohttp.ClientSession(connector=connector)
        # -------------------------------------------------------------------------
        
        cleanup_tts_files()
        print("Verificando y creando tablas de la base de datos si no existen...")
        database_manager.setup_database()
        print('-----------------------------------------')
        print("Cargando Cogs...")
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"✅ Cog '{filename[:-3]}' cargado.")
                except Exception as e:
                    print(f"❌ Error al cargar el Cog '{filename[:-3]}': {e}")
        print("Cogs cargados.")
        print("-----------------------------------------")
        print("Sincronizando comandos slash...")
        await self.tree.sync()
        print("¡Comandos sincronizados!")

    async def close(self):
        await super().close()
        if self.http_session:
            await self.http_session.close()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.members = True
intents.moderation = True 

bot = UmapyoiBot(command_prefix='!', intents=intents, case_insensitive=True, help_command=None)

@bot.event
async def on_ready():
    print(f'¡Umapyoi está en línea! Conectado como {bot.user}')
    await bot.change_presence(activity=discord.Game(name="Música y Juegos | /help"))

# --- EVENTO ON_MESSAGE CORREGIDO ---
@bot.event
async def on_message(message: discord.Message):
    # Ignorar mensajes de bots o mensajes privados
    if message.author.bot or not message.guild:
        return
        
    # Comprueba si solo se mencionó al bot en el mensaje
    # Esto evita que responda si se menciona al bot junto con un comando
    if message.content == f'<@{bot.user.id}>' or message.content == f'<@!{bot.user.id}>':
        embed = discord.Embed(
            title=f"¡Holi, {message.author.display_name}!",
            description=f"Mi prefijo de texto aquí es `!`, pero te recomiendo usar mis comandos de barra diagonal (`/`).\nEscribe `/help` para ver todo lo que puedo hacer.",
            color=bot.CREAM_COLOR
        )
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        view = discord.ui.View()
        invite_link = discord.utils.oauth_url(bot.user.id, permissions=discord.Permissions(permissions=8))
        view.add_item(discord.ui.Button(label="¡Invítame!", emoji="🥳", url=invite_link))
        view.add_item(discord.ui.Button(label="Soporte", emoji="🆘", url="https://discord.gg/fwNeZsGkSj"))
        
        await message.channel.send(embed=embed, view=view)
        return # Importante: Salimos para no procesar el mensaje como un comando

    # Si el mensaje no es solo una mención, procesamos los comandos normalmente
    await bot.process_commands(message)

# --- EVENTO ON_GUILD_JOIN CON MENSAJE ORIGINAL ---
@bot.event
async def on_guild_join(guild: discord.Guild):
    """
    Se ejecuta cuando el bot es añadido a un nuevo servidor.
    Envía un mensaje de bienvenida público y uno privado a quien lo invitó.
    """
    # 1. Enviar el mensaje público en el canal del sistema
    target_channel = guild.system_channel
    if not (target_channel and target_channel.permissions_for(guild.me).send_messages):
        # Si el canal de sistema no existe o no se puede escribir, busca otro canal
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                target_channel = channel
                break

    if target_channel:
        public_embed = discord.Embed(
            title="¡Umapyoi ha llegado para correr!",
            description="¡Hola a todos! Estoy lista para traer la mejor música, juegos y utilidades a su comunidad. ¡Es un placer estar aquí! 🥕",
            color=bot.CREAM_COLOR
        )
        public_embed.add_field(name="🏁 Primeros Pasos", value="Usa `/help` para ver mi lista de comandos.\nPara escuchar música, únete a un canal de voz y usa `/play`.", inline=False)
        public_embed.add_field(name="💡 Mi Propósito", value="He sido creada para ser una compañera todo-en-uno, fácil de usar y siempre lista para la diversión y la carrera.", inline=False)
        public_embed.add_field(name="🔧 Soporte y Comunidad", value="Si tienes alguna duda o sugerencia, únete a nuestro [servidor de soporte](https://discord.gg/fwNeZsGkSj).", inline=False)
        
        public_embed.set_image(url="https://i.imgur.com/LQxAWOz.png")
        public_embed.set_footer(text="¡A disfrutar de la carrera!")
        
        try:
            await target_channel.send(embed=public_embed)
        except discord.Forbidden:
            print(f"No pude enviar el mensaje de bienvenida público en {guild.name}")

    # 2. Encontrar a la persona que invitó al bot para el mensaje privado
    inviter = None
    try:
        if guild.me.guild_permissions.view_audit_log:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=5):
                if entry.target.id == bot.user.id:
                    inviter = entry.user
                    break
    except discord.Forbidden:
        print(f"No tengo permiso para ver el registro de auditoría en {guild.name}.")
    
    # 3. Preparar y enviar el mensaje privado (este no cambia)
    if inviter:
        private_embed = discord.Embed(
            title=f"¡Gracias por invitarme a {guild.name}!",
            description="¡Hola! Estoy aquí para llenar tu servidor de música, juegos y diversión. ✨",
            color=bot.CREAM_COLOR
        )
        private_embed.set_thumbnail(url=bot.user.display_avatar.url)
        private_embed.add_field(name="� ¿Cómo empezar?", value="El comando más importante es `/help`. Úsalo en cualquier canal para ver todas mis categorías y comandos.", inline=False)
        private_embed.add_field(name="🎵 Para escuchar música", value="Simplemente únete a un canal de voz y escribe `/play <nombre de la canción o enlace>`.", inline=False)
        private_embed.set_footer(text="¡Espero que disfrutes de mi compañía!")
        try:
            await inviter.send(embed=private_embed)
            print(f"Mensaje de bienvenida privado enviado a {inviter.name}.")
        except discord.Forbidden:
            print(f"No pude enviar el MD de bienvenida a {inviter.name}.")


@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, (commands.CommandNotFound, commands.errors.NotOwner)):
        return
    if isinstance(error, commands.errors.HybridCommandError) and isinstance(error.original, (discord.errors.InteractionResponded, discord.errors.NotFound)):
        print(f"Ignorando error de interacción ya respondida o no encontrada.")
        return

    if isinstance(error, commands.CommandOnCooldown):
        seconds = int(error.retry_after)
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        time_str = ""
        if days > 0: time_str += f"{days}d "
        if hours > 0: time_str += f"{hours}h "
        if minutes > 0: time_str += f"{minutes}m "
        if seconds > 0 and days == 0 and hours == 0: time_str += f"{seconds}s"
            
        await ctx.send(f"⏳ Vuelve a intentarlo en **{time_str.strip()}**.", ephemeral=True)
        return

    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes los permisos necesarios para usar este comando.", ephemeral=True)
    elif isinstance(error, commands.BotMissingPermissions):
        permisos = ", ".join(p.replace('_', ' ').capitalize() for p in error.missing_permissions)
        await ctx.send(f"⚠️ No puedo ejecutar esa acción porque me faltan los siguientes permisos: **{permisos}**", ephemeral=True)
    
    else:
        print(f"Error no manejado en '{ctx.command.name if ctx.command else 'Comando desconocido'}':")
        traceback.print_exception(type(error), error, error.__traceback__)
        with open('bot_errors.log', 'a', encoding='utf-8') as f:
            f.write(f"--- {datetime.datetime.now()} ---\n")
            f.write(f"Comando: {ctx.command.name if ctx.command else 'N/A'}\n")
            if ctx.guild: f.write(f"Servidor: {ctx.guild.name} ({ctx.guild.id})\n")
            f.write(f"Usuario: {ctx.author} ({ctx.author.id})\n")
            traceback.print_exception(type(error), error, error.__traceback__, file=f)
            f.write("\n")
        try:
            if not hasattr(ctx.command, 'on_error'):
                await ctx.send("🔧 ¡Vaya! Algo salió mal. El error ha sido registrado y mi creador lo revisará.", ephemeral=True)
        except (discord.errors.InteractionResponded, AttributeError):
            try:
                await ctx.followup.send("🔧 ¡Vaya! Algo salió mal. El error ha sido registrado y mi creador lo revisará.", ephemeral=True)
            except Exception:
                pass

def main():
    if not DISCORD_TOKEN:
        print("¡ERROR! No se encontró el DISCORD_TOKEN.")
        return
    try:
        bot.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        print("\n¡ERROR! El token de Discord no es válido.")
    except Exception as e:
        print(f"\nOcurrió un error crítico al iniciar el bot: {e}")

if __name__ == "__main__":
    main()