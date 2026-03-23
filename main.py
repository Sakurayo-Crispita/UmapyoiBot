import discord
# --- PARCHE DE VOZ PARA LINUX (OPUS) ---
try:
    if not discord.opus.is_loaded():
        discord.opus.load_opus("/usr/lib/x86_64-linux-gnu/libopus.so.0")
except Exception as e:
    print(f"Aviso Opus: {e}")
# ---------------------------------------
from discord.ext import commands, tasks
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
from utils.lang_utils import _t
from dotenv import load_dotenv
import asyncio
from web.app import run_app 
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

        self.http_session = None
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        self.first_on_ready = True

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
                    print(f"Cog '{filename[:-3]}' cargado.")
                except Exception as e:
                    print(f"Error al cargar el Cog '{filename[:-3]}': {e}")
        print("Cogs cargados.")
        print("-----------------------------------------")
        print("Sincronizando comandos slash...")
        await self.tree.sync()
        print("¡Comandos sincronizados!")

        if not self.check_broadcasts.is_running():
            self.check_broadcasts.start()

    @tasks.loop(seconds=15)
    async def check_broadcasts(self):
        pending = await database_manager.fetchall("SELECT * FROM broadcast_queue WHERE status = 'pending'")
        if not pending: return
        for item in pending:
            b_id = item['id']
            message = item['message']
            task_type = item.get('type', 'broadcast')
            
            await database_manager.execute("UPDATE broadcast_queue SET status = 'processing' WHERE id = ?", (b_id,))
            
            if task_type == 'broadcast':
                embed = discord.Embed(
                    title="Anuncio Global de UmapyoiBot",
                    description=message,
                    color=0xff6b9e,
                    timestamp=datetime.datetime.now()
                )
                if self.user:
                    embed.set_thumbnail(url=self.user.display_avatar.url)
                    embed.set_footer(text="Comunicado oficial • Administración de UmapyoiBot", icon_url=self.user.display_avatar.url)

                count = 0
                for guild in self.guilds:
                    try:
                        target_channel = guild.system_channel
                        if target_channel and target_channel.permissions_for(guild.me).send_messages:
                            await target_channel.send(embed=embed)
                            count += 1
                            continue
                        for c in guild.text_channels:
                            if c.permissions_for(guild.me).send_messages:
                                await c.send(embed=embed)
                                count += 1
                                break
                    except Exception: pass
                print(f"Broadcast {b_id} enviado a {count} servidores.")
            
            elif task_type == 'leave_guild':
                try:
                    guild_id = int(message)
                    guild = self.get_guild(guild_id)
                    if guild:
                        await guild.leave()
                        print(f"Tarea ejecutada: Me salí del servidor {guild.name} ({guild_id}) por petición administrativa.")
                    else:
                        print(f"Tarea fallida: No pude encontrar el servidor {guild_id} para salir.")
                except Exception as e:
                    print(f"Error procesando leave_guild: {e}")
            
            elif task_type == 'send_dm':
                try:
                    import json
                    data = json.loads(message)
                    u_id = int(data.get('user_id'))
                    content = data.get('content')
                    user = self.get_user(u_id) or await self.fetch_user(u_id)
                    if user:
                        embed = discord.Embed(
                            title="Mensaje Directo de UmapyoiBot",
                            description=content,
                            color=0xff6b9e,
                            timestamp=datetime.datetime.now()
                        )
                        if self.user:
                            embed.set_author(name="Administración", icon_url=self.user.display_avatar.url)
                            embed.set_footer(text="UmapyoiBot System", icon_url=self.user.display_avatar.url)
                        
                        await user.send(embed=embed)
                        print(f"Tarea ejecutada: DM enviado a {user} ({u_id})")
                        await database_manager.log_system_event("INFO", "Broadcast", f"DM enviado con éxito a {user} ({u_id})")
                    else:
                        print(f"Tarea fallida: No se pudo localizar al usuario {u_id}")
                        await database_manager.log_system_event("WARNING", "Broadcast", f"No se pudo enviar DM: usuario {u_id} no encontrado.")
                except Exception as e:
                    print(f"Error procesando send_dm a {u_id}: {e}")
                    await database_manager.log_system_event("ERROR", "Broadcast", f"Error enviando DM a {u_id}: {str(e)}")

            await database_manager.execute("UPDATE broadcast_queue SET status = 'completed' WHERE id = ?", (b_id,))

    async def close(self):
        await super().close()
        database_manager.close_database()
        if self.http_session:
            await self.http_session.close()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.members = True
intents.moderation = True 

async def get_prefix(bot, message):
    if not message.guild:
        return '!'
    settings = await database_manager.get_cached_server_settings(message.guild.id)
    return settings.get('prefix', '!') if settings else '!'

bot = UmapyoiBot(command_prefix=get_prefix, intents=intents, case_insensitive=True, help_command=None)

async def ensure_bot_role(guild: discord.Guild):
    existing_role = discord.utils.get(guild.roles, name=bot.user.name)
    if existing_role:
        if existing_role not in guild.me.roles:
            await guild.me.add_roles(existing_role, reason="Asignando rol único del bot")
        return

    try:
        role = await guild.create_role(
            name=bot.user.name,
            mentionable=True,
            reason="Rol único para mencionar al bot"
        )
        await guild.me.add_roles(role, reason="Asignando rol único del bot")
        print(f"Rol '{role.name}' creado y asignado en {guild.name}")
    except discord.Forbidden:
        print(f"No tengo permisos para crear rol en {guild.name}")

async def get_guild_inviter(guild):
    """Intenta encontrar quién invitó al bot mediante los logs de auditoría."""
    try:
        if guild.me.guild_permissions.view_audit_log:
            async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.bot_add):
                if entry.target and entry.target.id == bot.user.id:
                    return entry.user
    except Exception:
        pass
    return None

@bot.event
async def on_ready():
    if not bot.first_on_ready:
        return
    bot.first_on_ready = False
    
    print(f'¡Umapyoi está en línea! Conectado como {bot.user}')
    await bot.change_presence(activity=discord.Game(name="¡Umapyoi ready! | /help"))

    for guild in bot.guilds:
        await ensure_bot_role(guild)
    
    # Iniciar sincronización en segundo plano para no bloquear on_ready
    asyncio.create_task(sync_guilds_background())
    
    # Log de sistema: Bot en línea
    await database_manager.log_system_event("INFO", "System", f"UmapyoiBot está en línea. Conectado como {bot.user}")

async def sync_guilds_background():
    """Sincroniza la lista de servidores en segundo plano."""
    print("Iniciando sincronización de servidores en segundo plano...")
    guilds_data = []
    # Consultamos lo que ya tenemos
    try:
        existing_bg = await database_manager.get_bot_guilds()
        bg_dict = {g['guild_id']: g for g in existing_bg}
    except Exception as e:
        print(f"Error cargando gremios existentes: {e}")
        bg_dict = {}

    for g in bot.guilds:
        inviter_id = None
        inviter_name = None
        inviter_avatar = None
        
        if g.id in bg_dict and bg_dict[g.id].get('inviter_id'):
            inviter_id = bg_dict[g.id]['inviter_id']
            inviter_name = bg_dict[g.id]['inviter_name']
            inviter_avatar = bg_dict[g.id]['inviter_avatar']
        else:
            if g.member_count < 1000:
                inviter = await get_guild_inviter(g)
                if inviter:
                    inviter_id = inviter.id
                    inviter_name = str(inviter)
                    inviter_avatar = str(inviter.display_avatar.url)

        guilds_data.append({
            'id': g.id,
            'name': g.name,
            'member_count': g.member_count,
            'icon_url': str(g.icon.url) if g.icon else None,
            'owner_id': g.owner_id,
            'owner_name': str(g.owner) if g.owner else f"ID: {g.owner_id}",
            'inviter_id': inviter_id,
            'inviter_name': inviter_name,
            'inviter_avatar': inviter_avatar
        })
    
    await database_manager.sync_bot_guilds(guilds_data)
    print(f"Sincronización completada: {len(guilds_data)} servidores actualizados.")

# --- EVENTO ON_MESSAGE ---
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
        
    if message.content == f'<@{bot.user.id}>' or message.content == f'<@!{bot.user.id}>':
        # Fetch language for localization
        settings = await database_manager.get_cached_server_settings(message.guild.id)
        lang = settings.get('language', 'es')
        
        embed = discord.Embed(
            title=_t('bot.general.ping_title', lang=lang, user=message.author.display_name),
            description=_t('bot.general.ping_desc', lang=lang),
            color=bot.CREAM_COLOR
        )
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label=_t('bot.general.btn_commands', lang=lang), emoji="🌐", url=constants.COMMANDS_PAGE_URL))
        invite_link = discord.utils.oauth_url(bot.user.id, permissions=discord.Permissions(permissions=8))
        view.add_item(discord.ui.Button(label=_t('bot.general.btn_invite', lang=lang), emoji="🥳", url=invite_link))
        view.add_item(discord.ui.Button(label=_t('bot.general.btn_support', lang=lang), emoji="🆘", url="https://discord.gg/fwNeZsGkSj"))
        
        await message.channel.send(embed=embed, view=view)
        return

    await bot.process_commands(message)

# --- EVENTO ON_GUILD_JOIN (RESTAURADO Y MEJORADO) ---
@bot.event
async def on_guild_join(guild: discord.Guild):
    await ensure_bot_role(guild)
    
    inviter = await get_guild_inviter(guild)
    inv_id = inviter.id if inviter else None
    inv_name = str(inviter) if inviter else "Desconocido/Link"
    inv_avatar = str(inviter.display_avatar.url) if inviter else None

    await database_manager.update_guild_status(
        guild.id, True, guild.name, guild.member_count, 
        str(guild.icon.url) if guild.icon else None,
        guild.owner_id, str(guild.owner) if guild.owner else "Desconocido",
        inv_id, inv_name, inv_avatar
    )
    # 1. Mensaje público
    target_channel = guild.system_channel
    if not (target_channel and target_channel.permissions_for(guild.me).send_messages):
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                target_channel = channel
                break
    # Fetch language for localization (default ES for new join)
    lang = 'es' 

    if target_channel:
        public_embed = discord.Embed(
            title=_t('bot.general.welcome_public_title', lang=lang),
            description=_t('bot.general.welcome_public_desc', lang=lang),
            color=bot.CREAM_COLOR
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label=_t('bot.general.btn_commands', lang=lang), emoji="🌐", url=constants.COMMANDS_PAGE_URL))
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
                title=_t('bot.general.welcome_private_title', lang=lang, server=guild.name),
                description=_t('bot.general.welcome_private_desc', lang=lang),
                color=bot.CREAM_COLOR
            )
            initial_embed.set_thumbnail(url=bot.user.display_avatar.url)
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label=_t('bot.general.btn_guide', lang=lang), emoji="📘", url=constants.COMMANDS_PAGE_URL))
            view.add_item(discord.ui.Button(label=_t('bot.general.btn_support_server', lang=lang), emoji="🆘", url="https://discord.gg/fwNeZsGkSj"))
            await inviter.send(embed=initial_embed, view=view)

            # Diccionario de emojis para cada categoría
            emoji_map = {
                "Música": "🎵", "Niveles": "📈", "Economía": "💰", "Juegos de Azar": "🎲",
                "Juegos e IA": "🎮", "Interacción": "👋", "Moderación": "🛡️",
                "Configuración del Servidor": "⚙️", "Texto a Voz": "🔊", "Utilidad": "�️"
            }

            # Enviar la lista detallada de comandos por categoría
            for cog_name, cog in bot.cogs.items():
                commands_list = cog.get_commands()
                if not commands_list or cog_name in ["Juegos de Azar", "Economía"]:
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
async def on_guild_remove(guild: discord.Guild):
    await database_manager.update_guild_status(guild.id, False)
    # Log de sistema
    await database_manager.log_system_event("WARNING", "Guild", f"Bot fue expulsado o salió del servidor: {guild.name} ({guild.id})")
    print(f"Me salí del servidor {guild.name} ({guild.id}).")

@bot.event
async def on_command(ctx):
    if ctx.command:
        guild_name = ctx.guild.name if ctx.guild else "DM"
        guild_id = ctx.guild.id if ctx.guild else 0
        await database_manager.log_global_command(
            guild_id, guild_name, ctx.author.id, str(ctx.author), ctx.command.name
        )

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.application_command:
        guild_name = interaction.guild.name if interaction.guild else "DM"
        guild_id = interaction.guild.id if interaction.guild else 0
        command_name = interaction.data.get('name', 'unknown-slash')
        await database_manager.log_global_command(
            guild_id, guild_name, interaction.user.id, str(interaction.user), command_name
        )
    # Importante procesar la interacción para que los comandos slash sigan funcionando
    await bot.process_application_commands(interaction)

@bot.check
async def global_blacklist_check(ctx):
    # Validar si el usuario o el servidor están en la lista negra
    try:
        if await database_manager.is_blacklisted(ctx.author.id):
            return False
        if ctx.guild and await database_manager.is_blacklisted(ctx.guild.id):
            return False
        return True
    except Exception as e:
        print(f"Error en el check de blacklist: {e}")
        return True # En caso de error en DB, permitimos el comando para no romper el bot

@bot.event
async def on_command_error(ctx: commands.Context, error):
    # Log de sistema
    if not isinstance(error, (commands.CommandNotFound, commands.errors.NotOwner, commands.CheckFailure)):
        await database_manager.log_system_event("ERROR", "Command", f"Error en '{ctx.command}': {str(error)}")

    # Ignorar errores comunes que no necesitan notificación
    if isinstance(error, (commands.CommandNotFound, commands.errors.NotOwner)):
        return
    # Ignorar la clase base CheckFailure porque los cog_checks ya envían sus propios mensajes
    if type(error) == commands.CheckFailure:
        return
    if isinstance(error, commands.errors.HybridCommandError) and isinstance(error.original, (discord.errors.InteractionResponded, discord.errors.NotFound)):
        print(f"Ignorando error de interacción ya respondida o no encontrada.")
        return

    # Fetch language for localization
    settings = await database_manager.get_cached_server_settings(ctx.guild.id) if ctx.guild else None
    lang = settings.get('language', 'es') if settings else 'es'

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
        await ctx.send(_t('bot.common.on_cooldown', lang=lang, time=time_str.strip()), ephemeral=True)
        return

    # Desempaquetar HybridCommandError para procesar el error original correctamente
    if isinstance(error, commands.errors.HybridCommandError):
        error = error.original

    # Manejar permisos faltantes
    if isinstance(error, (commands.MissingPermissions, discord.app_commands.errors.MissingPermissions)):
        await ctx.send(_t('bot.common.no_perms', lang=lang), ephemeral=True)
        return
    elif isinstance(error, (commands.BotMissingPermissions, discord.app_commands.errors.BotMissingPermissions)):
        permisos = ", ".join(p.replace('_', ' ').capitalize() for p in (getattr(error, 'missing_permissions', [])))
        await ctx.send(_t('bot.common.bot_no_perms', lang=lang, perms=permisos), ephemeral=True)
        return

    # Manejar argumentos faltantes o malos
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(_t('bot.common.missing_args', lang=lang, arg=error.param.name), ephemeral=True)
        return
    elif isinstance(error, commands.BadLiteralArgument):
        literals = ", ".join(f"`{l}`" for l in error.literals)
        await ctx.send(_t('bot.common.bad_args', lang=lang), ephemeral=True)
        return
    elif isinstance(error, commands.BadArgument):
        await ctx.send(_t('bot.common.bad_args', lang=lang), ephemeral=True)
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
    except (discord.errors.InteractionResponded, discord.errors.NotFound, AttributeError):
        try:
            # Si la interacción ya expiró o fue respondida, intentamos un followup o ignoramos el error de envío
            if ctx.interaction and not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message("🔧 ¡Vaya! Algo salió mal.", ephemeral=True)
            else:
                await ctx.followup.send("🔧 ¡Vaya! Algo salió mal. El error ha sido registrado y mi creador lo revisará.", ephemeral=True)
        except Exception:
            pass
    except Exception:
        pass

async def main_async():
    if not DISCORD_TOKEN:
        print("¡ERROR! No se encontró el DISCORD_TOKEN.")
        return
    
    # Iniciamos el bot
    print("Iniciando bot de Discord...")
    try:
        async with bot:
            await bot.start(DISCORD_TOKEN)
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\nCerrando bot...")
    except discord.errors.LoginFailure:
        print("\n¡ERROR! El token de Discord no es válido.")
    except Exception as e:
        print(f"\nOcurrió un error crítico al iniciar el bot: {e}")
    finally:
        if not bot.is_closed():
            await bot.close()
        print("Bot apagado exitosamente.")

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()