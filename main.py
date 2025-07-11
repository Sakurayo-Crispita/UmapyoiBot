import discord
from discord.ext import commands
import os
import traceback
import datetime
import glob 
import io
import aiohttp
from aiohttp import TCPConnector
import ssl
import certifi

# Importamos nuestros módulos de utilidades
from utils import database_manager
from utils import constants
from dotenv import load_dotenv
# --- CONFIGURACIÓN DE APIS Y CONSTANTES ---
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")
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
        super().__init__(*args, owner_id=int(OWNER_ID) if OWNER_ID else None, **kwargs)
        self.db_file = DB_FILE
        self.GENIUS_API_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        self.CREAM_COLOR = discord.Color(constants.CREAM_COLOR)
        self.FFMPEG_OPTIONS = constants.FFMPEG_OPTIONS
        self.YDL_OPTIONS = constants.YDL_OPTIONS
        self.http_session = None

    async def setup_hook(self):
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = TCPConnector(
            resolver=aiohttp.AsyncResolver(nameservers=["8.8.8.8", "8.8.4.4"]),
            ssl=ssl_context,
        )
        self.http_session = aiohttp.ClientSession(connector=connector)
        
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
    await bot.change_presence(activity=discord.Game(name="¡Umapyoi ready! | /help"))

# --- EVENTO ON_MESSAGE ---
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
        
    if message.content == f'<@{bot.user.id}>' or message.content == f'<@!{bot.user.id}>':
        embed = discord.Embed(
            title=f"🥕 ¡Hola, {message.author.display_name}! Soy Umapyoi.",
            description=(
                "¡Lista para la carrera! Mi objetivo es ser tu compañera todo-en-uno.\n\n"
                "Para descubrir todo mi potencial, usa el comando `/help` o visita mi página web de comandos."
            ),
            color=bot.CREAM_COLOR
        )
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Página de Comandos", emoji="🌐", url=constants.COMMANDS_PAGE_URL))
        invite_link = discord.utils.oauth_url(bot.user.id, permissions=discord.Permissions(permissions=8))
        view.add_item(discord.ui.Button(label="¡Invítame!", emoji="🥳", url=invite_link))
        view.add_item(discord.ui.Button(label="Soporte", emoji="🆘", url="https://discord.gg/fwNeZsGkSj"))
        
        await message.channel.send(embed=embed, view=view)
        return

    await bot.process_commands(message)

# --- EVENTO ON_GUILD_JOIN (RESTAURADO Y MEJORADO) ---
@bot.event
async def on_guild_join(guild: discord.Guild):
    # 1. Mensaje público
    target_channel = guild.system_channel
    if not (target_channel and target_channel.permissions_for(guild.me).send_messages):
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                target_channel = channel
                break
    if target_channel:
        public_embed = discord.Embed(
            title="¡Umapyoi ha llegado para correr!",
            description="¡Hola a todos! Estoy lista para traer la mejor música, juegos y utilidades a su comunidad. ¡Es un placer estar aquí! 🥕\n\nPara empezar, usa `/help` o visita mi página de comandos.",
            color=bot.CREAM_COLOR
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Ver Comandos", emoji="🌐", url=constants.COMMANDS_PAGE_URL))
        public_embed.set_image(url="https://i.imgur.com/LQxAWOz.png")
        public_embed.set_footer(text="¡A disfrutar de la carrera!")
        try:
            await target_channel.send(embed=public_embed, view=view)
        except discord.Forbidden:
            print(f"No pude enviar el mensaje de bienvenida público en {guild.name}")

    # 2. Encontrar a quien invitó
    inviter = None
    try:
        if guild.me.guild_permissions.view_audit_log:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=5):
                if entry.target.id == bot.user.id:
                    inviter = entry.user
                    break
    except discord.Forbidden:
        print(f"No tengo permiso para ver el registro de auditoría en {guild.name}.")
    
    # 3. Enviar guía completa por MD
    if inviter:
        try:
            # Mensaje inicial con botones
            initial_embed = discord.Embed(
                title=f"¡Gracias por invitarme a {guild.name}!",
                description="¡Hola! Para ver la lista completa y detallada de comandos, visita mi página web. También te enviaré la lista completa por aquí para que la tengas a mano.",
                color=bot.CREAM_COLOR
            )
            initial_embed.set_thumbnail(url=bot.user.display_avatar.url)
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Ver Guía de Comandos", emoji="📘", url=constants.COMMANDS_PAGE_URL))
            view.add_item(discord.ui.Button(label="Servidor de Soporte", emoji="🆘", url="https://discord.gg/fwNeZsGkSj"))
            await inviter.send(embed=initial_embed, view=view)

            # Diccionario de emojis para cada categoría
            emoji_map = {
                "Música": "🎵", "Niveles": "📈", "Economía": "💰", "Juegos de Apuestas": "🎲",
                "Juegos e IA": "🎮", "Interacción": "👋", "Moderación": "🛡️",
                "Configuración del Servidor": "⚙️", "Texto a Voz": "🔊", "Utilidad": "�️"
            }

            # Enviar la lista detallada de comandos por categoría
            for cog_name, cog in bot.cogs.items():
                commands_list = cog.get_commands()
                if not commands_list or cog_name in ["Juegos de Apuestas", "Economía"]:
                    continue

                embed = discord.Embed(
                    title=f"{emoji_map.get(cog_name, '➡️')} Comandos de {cog_name}",
                    color=bot.CREAM_COLOR
                )
                
                for command in sorted(commands_list, key=lambda c: c.name):
                    if command.hidden: continue
                    description = command.description or "Sin descripción."
                    if command.name == 'setwelcomechannel' or command.name == 'setgoodbyechannel':
                        description += "\n*Ejemplo: `/setwelcomechannel canal:#general`*\n*Para desactivar, usa el comando sin especificar un canal.*"
                    elif command.name == 'configwelcome' or command.name == 'configgoodbye':
                        description += "\n*Ejemplo: `/configwelcome mensaje:¡Hola {user}! banner_url:https://... texto_superior:¡Nuevo miembro!`*"
                        
                    embed.add_field(name=f"`/{command.name}`", value=description, inline=False)

                if embed.fields:
                    await inviter.send(embed=embed)

        except discord.Forbidden:
            print(f"No pude enviar la guía de bienvenida por MD a {inviter.name} (MDs cerrados).")
        except Exception as e:
            print(f"Error enviando la guía por MD: {e}")

@bot.event
async def on_command_error(ctx: commands.Context, error):
    # Ignorar errores comunes que no necesitan notificación
    if isinstance(error, (commands.CommandNotFound, commands.errors.NotOwner)):
        return
    if isinstance(error, commands.errors.HybridCommandError) and isinstance(error.original, (discord.errors.InteractionResponded, discord.errors.NotFound)):
        print(f"Ignorando error de interacción ya respondida o no encontrada.")
        return

    # Manejar cooldowns
    if isinstance(error, commands.CommandOnCooldown):
        seconds = int(error.retry_after)
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = ""
        if days > 0: time_str += f"{days}d "
        if hours > 0: time_str += f"{hours}h "
        if minutes > 0: time_str += f"{minutes}m "
        if seconds > 0 and not time_str: time_str += f"{seconds}s"
        await ctx.send(f"⏳ Vuelve a intentarlo en **{time_str.strip()}**.", ephemeral=True)
        return

    # Manejar permisos faltantes
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes los permisos necesarios para usar este comando.", ephemeral=True)
        return
    elif isinstance(error, commands.BotMissingPermissions):
        permisos = ", ".join(p.replace('_', ' ').capitalize() for p in error.missing_permissions)
        await ctx.send(f"⚠️ No puedo ejecutar esa acción porque me faltan los siguientes permisos: **{permisos}**", ephemeral=True)
        return
    
    # Para todos los demás errores, notificar al dueño
    print(f"Error no manejado en '{ctx.command.name if ctx.command else 'Comando desconocido'}':")
    traceback.print_exception(type(error), error, error.__traceback__)
    
    # --- NUEVO: Notificación de error por MD ---
    if bot.owner_id:
        owner = bot.get_user(bot.owner_id)
        if owner:
            # Crear un embed con la información del error
            embed = discord.Embed(
                title="🚨 ¡Alerta de Error en Umapyoi!",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="Servidor", value=f"{ctx.guild.name} (`{ctx.guild.id}`)", inline=False)
            embed.add_field(name="Canal", value=f"{ctx.channel.mention} (`{ctx.channel.id}`)", inline=False)
            embed.add_field(name="Usuario", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
            embed.add_field(name="Comando", value=f"`{ctx.command.qualified_name}`" if ctx.command else "N/A", inline=False)
            embed.add_field(name="Error", value=f"```py\n{type(error).__name__}: {error}\n```", inline=False)
            
            # Preparar el traceback completo como un archivo de texto
            error_traceback = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            trace_file = discord.File(io.StringIO(error_traceback), filename="traceback.txt")

            try:
                await owner.send(embed=embed, file=trace_file)
            except discord.Forbidden:
                print("No se pudo enviar el MD de error al dueño (MDs cerrados o no es amigo).")
            except Exception as e:
                print(f"Error al enviar el MD de error: {e}")

    # Mensaje genérico para el usuario
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