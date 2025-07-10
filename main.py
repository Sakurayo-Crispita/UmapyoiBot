import discord
from discord.ext import commands
import os
import traceback
import datetime
import glob 

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

    async def setup_hook(self):
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

@bot.event
async def on_guild_join(guild: discord.Guild):
    """
    Se ejecuta cuando el bot es añadido a un nuevo servidor.
    Envía un mensaje de bienvenida público y uno privado a quien lo invitó.
    """
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
        
        public_embed.set_image(url="https://i.imgur.com/LQxAWOz.png") # Puedes cambiar esta imagen
        public_embed.set_footer(text="¡A disfrutar de la carrera!")
        
        try:
            await target_channel.send(embed=public_embed)
        except discord.Forbidden:
            print(f"No pude enviar el mensaje de bienvenida público en {guild.name}")

    inviter = None
    try:
        if guild.me.guild_permissions.view_audit_log:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=5):
                if entry.target.id == bot.user.id:
                    inviter = entry.user
                    break
    except discord.Forbidden:
        print(f"No tengo permiso para ver el registro de auditoría en {guild.name}.")
    
    embed = discord.Embed(
        title=f"¡Gracias por invitar a Umapyoi a {guild.name}!",
        description="¡Hola! Estoy aquí para llenar tu servidor de música, juegos y diversión. ✨",
        color=bot.CREAM_COLOR
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="🚀 ¿Cómo empezar?", value="El comando más importante es `/help`. Úsalo en cualquier canal para ver todas mis categorías y comandos.", inline=False)
    embed.add_field(name="🎵 Para escuchar música", value="Simplemente únete a un canal de voz y escribe `/play <nombre de la canción o enlace>`.", inline=False)
    embed.add_field(name="💬 ¿Necesitas ayuda?", value="Si tienes alguna duda o encuentras un error, puedes unirte a mi [servidor de soporte oficial](https://discord.gg/fwNeZsGkSj).", inline=False)
    embed.set_footer(text="¡Espero que disfrutes de mi compañía!")

    if inviter:
        try:
            await inviter.send(embed=embed)
            print(f"Mensaje de bienvenida enviado por MD a {inviter.name} por añadirme a {guild.name}.")
            return
        except discord.Forbidden:
            print(f"No pude enviar el MD a {inviter.name}. Probablemente tiene los MDs desactivados.")

    if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
        try:
            content = f"¡Hola {inviter.mention}!" if inviter else ""
            await guild.system_channel.send(content=content, embed=embed)
        except discord.Forbidden:
            pass

@bot.event
async def on_command_error(ctx: commands.Context, error):
    # Ignorar errores específicos
    if isinstance(error, (commands.CommandNotFound, commands.errors.NotOwner)):
        return
    if isinstance(error, commands.errors.HybridCommandError) and isinstance(error.original, (discord.errors.InteractionResponded, discord.errors.NotFound)):
        print(f"Ignorando error de interacción ya respondida o no encontrada.")
        return

    # --- MANEJADOR DE COOLDOWN MEJORADO ---
    if isinstance(error, commands.CommandOnCooldown):
        # Convertir segundos a horas, minutos y segundos
        seconds = int(error.retry_after)
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Construir el mensaje de tiempo
        time_str = ""
        if days > 0:
            time_str += f"{days}d "
        if hours > 0:
            time_str += f"{hours}h "
        if minutes > 0:
            time_str += f"{minutes}m "
        if seconds > 0 and days == 0 and hours == 0: # Solo mostrar segundos si es menos de un minuto
            time_str += f"{seconds}s"
            
        await ctx.send(f"⏳ Vuelve a intentarlo en **{time_str.strip()}**.", ephemeral=True)
        return # Importante: salimos para no procesar otros errores

    # Errores comunes que se le notifican al usuario
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes los permisos necesarios para usar este comando.", ephemeral=True)
    elif isinstance(error, commands.BotMissingPermissions):
        permisos = ", ".join(p.replace('_', ' ').capitalize() for p in error.missing_permissions)
        await ctx.send(f"⚠️ No puedo ejecutar esa acción porque me faltan los siguientes permisos: **{permisos}**", ephemeral=True)
    
    # Para cualquier otro error, lo registramos y notificamos al usuario
    else:
        print(f"Error no manejado en '{ctx.command.name if ctx.command else 'Comando desconocido'}':")
        traceback.print_exception(type(error), error, error.__traceback__)
        with open('bot_errors.log', 'a', encoding='utf-8') as f:
            f.write(f"--- {datetime.datetime.now()} ---\n")
            f.write(f"Comando: {ctx.command.name if ctx.command else 'N/A'}\n")
            if ctx.guild:
                f.write(f"Servidor: {ctx.guild.name} ({ctx.guild.id})\n")
            f.write(f"Usuario: {ctx.author} ({ctx.author.id})\n")
            traceback.print_exception(type(error), error, error.__traceback__, file=f)
            f.write("\n")
        try:
            # Evitar enviar el mensaje de error si el comando tiene su propio manejador de errores local
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
