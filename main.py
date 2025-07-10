# main.py
import discord
from discord.ext import commands
import os
import traceback
import datetime

# Importamos nuestros módulos de utilidades
from utils import database_manager
from utils import constants
from dotenv import load_dotenv

# --- CONFIGURACIÓN DE APIS Y CONSTANTES ---
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DB_FILE = "bot_data.db" 

# --- CLASE DE BOT PERSONALIZADA ---
class UmapyoiBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db_file = DB_FILE

        # --- CONSTANTES GLOBALES DEL BOT ---
        self.GENIUS_API_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        
        self.CREAM_COLOR = discord.Color(constants.CREAM_COLOR)
        self.FFMPEG_OPTIONS = constants.FFMPEG_OPTIONS
        self.YDL_OPTIONS = constants.YDL_OPTIONS

    async def setup_hook(self):
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

# --- DEFINICIÓN DE INTENTS E INICIO DEL BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.members = True
# Necesitamos el permiso para ver el registro de auditoría
intents.moderation = True 

bot = UmapyoiBot(command_prefix='!', intents=intents, case_insensitive=True, help_command=None)

# --- EVENTOS GLOBALES DEL BOT ---
@bot.event
async def on_ready():
    print(f'¡Umapyoi está en línea! Conectado como {bot.user}')
    await bot.change_presence(activity=discord.Game(name="Música y Juegos | /help"))

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    if bot.user.mentioned_in(message) and not message.mention_everyone and not message.reference:
        await message.channel.send(f'¡Hola, {message.author.mention}! Usa `/help` para ver todos mis comandos. ✨')
    await bot.process_commands(message)

# --- ¡NUEVO EVENTO AÑADIDO! ---
@bot.event
async def on_guild_join(guild: discord.Guild):
    """
    Se ejecuta cuando el bot es añadido a un nuevo servidor.
    Envía un mensaje de bienvenida a quien lo invitó.
    """
    # 1. Encontrar a la persona que invitó al bot
    inviter = None
    # Para esto, necesitamos el permiso "Ver registro de auditoría"
    if guild.me.guild_permissions.view_audit_log:
        async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=5):
            if entry.target.id == bot.user.id:
                inviter = entry.user
                break
    
    # 2. Preparar el mensaje de bienvenida
    embed = discord.Embed(
        title=f"¡Gracias por invitar a Umapyoi a {guild.name}!",
        description="¡Hola! Estoy aquí para llenar tu servidor de música, juegos y diversión. ✨",
        color=bot.CREAM_COLOR
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(
        name="🚀 ¿Cómo empezar?",
        value="El comando más importante es `/help`. Úsalo en cualquier canal para ver todas mis categorías y comandos.",
        inline=False
    )
    embed.add_field(
        name="🎵 Para escuchar música",
        value="Simplemente únete a un canal de voz y escribe `/play <nombre de la canción o enlace>`.",
        inline=False
    )
    embed.add_field(
        name="💬 ¿Necesitas ayuda?",
        value="Si tienes alguna duda o encuentras un error, puedes unirte a mi [servidor de soporte oficial](https://discord.gg/fwNeZsGkSj).",
        inline=False
    )
    embed.set_footer(text="¡Espero que disfrutes de mi compañía!")

    # 3. Intentar enviar el mensaje por MD a quien lo invitó
    if inviter:
        try:
            await inviter.send(embed=embed)
            print(f"Mensaje de bienvenida enviado por MD a {inviter.name} por añadirme a {guild.name}.")
        except discord.Forbidden:
            print(f"No pude enviar el MD a {inviter.name}. Probablemente tiene los MDs desactivados.")
            # Si no se puede enviar por MD, se intenta en el canal del sistema
            if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
                await guild.system_channel.send(content=f"¡Hola {inviter.mention}!", embed=embed)
    # 4. Si no se encontró a quien invitó, se envía al canal del sistema
    else:
        if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
            try:
                await guild.system_channel.send(embed=embed)
            except discord.Forbidden:
                pass


@bot.event
async def on_command_error(ctx: commands.Context, error):
    # Errores que queremos ignorar o manejar de forma silenciosa
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.errors.HybridCommandError) and isinstance(error.original, (discord.errors.InteractionResponded, discord.errors.NotFound)):
        print(f"Ignorando error de interacción ya respondida o no encontrada.")
        return

    # Errores comunes que se le notifican al usuario
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Espera {round(error.retry_after, 1)} segundos.", ephemeral=True)
    elif isinstance(error, commands.MissingPermissions):
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
            await ctx.send("🔧 ¡Vaya! Algo salió mal. El error ha sido registrado y mi creador lo revisará.", ephemeral=True)
        except discord.errors.InteractionResponded:
            await ctx.followup.send("🔧 ¡Vaya! Algo salió mal. El error ha sido registrado y mi creador lo revisará.", ephemeral=True)

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