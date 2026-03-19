import discord
from discord.ext import commands
from typing import Optional
import datetime
import io
import psutil
import platform
from utils import constants

class HelpSelect(discord.ui.Select):
    """El menú desplegable para el panel de ayuda interactivo."""
    def __init__(self, bot: commands.Bot, cog_map: dict):
        self.bot = bot
        self.cog_map = cog_map
        
        # Diccionario de emojis para cada categoría
        emoji_map = {
            "Música": "🎵",
            "Niveles": "📈",
            "Economía": "💰",
            "Juegos de Azar": "🎲",
            "Juegos e IA": "🎮",
            "Interacción": "👋",
            "NSFW": "🔞",
            "Moderación": "🛡️",
            "Configuración del Servidor": "⚙️",
            "Texto a Voz": "🔊",
            "Utilidad": "🛠️",
            "Tickets": "🎟️"
        }
        
        options = [discord.SelectOption(label="Inicio", description="Vuelve al panel principal de ayuda.", emoji="🏠")]
        
        # Usamos el cog_map para mantener un orden consistente
        for cog_name in self.cog_map.values():
            cog = self.bot.get_cog(cog_name)
            if cog and any(not cmd.hidden for cmd in cog.get_commands()):
                description = getattr(cog, "description", "Sin descripción.")
                emoji = emoji_map.get(cog_name, "➡️") # Usamos una flecha como emoji por defecto
                options.append(discord.SelectOption(label=cog_name, description=description[:100], emoji=emoji))

        super().__init__(placeholder="Selecciona una categoría para ver los comandos...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_cog_name = self.values[0]
        embed = discord.Embed(color=self.bot.CREAM_COLOR)

        if selected_cog_name == "Inicio":
            embed.title = "📜 Ayuda de Umapyoi"
            embed.description = "**🚀 Cómo empezar a escuchar música**\n`/play <nombre de la canción o enlace>`\n\n**❓ ¿Qué es Umapyoi?**\nUn bot de nueva generación con música, juegos, economía y mucho más. ¡Todo en uno!\n\n**🎛️ Categorías de Comandos:**"
            embed.set_image(url="https://i.imgur.com/WwexK3G.png")
            embed.set_footer(text="Gracias por elegir a Umapyoi ✨")
        else:
            cog = self.bot.get_cog(selected_cog_name)
            if cog:
                embed.title = f"Comandos de: {selected_cog_name}"
                description = ""
                command_list = sorted([cmd for cmd in cog.get_commands() if not cmd.hidden], key=lambda c: c.name)
                for cmd in command_list:
                    if cmd.name != 'help':
                        description += f"**`/{cmd.name}`** - {cmd.description}\n"
                embed.description = description or "Esta categoría no tiene comandos para mostrar."
        await interaction.response.edit_message(embed=embed)

class HelpView(discord.ui.View):
    """La vista que contiene el menú desplegable de ayuda."""
    def __init__(self, bot: commands.Bot, cog_map: dict):
        super().__init__(timeout=180)
        self.add_item(HelpSelect(bot, cog_map))

# Las clases TicketCloseView y TicketOpenView han sido movidas a tickets.py

class UtilityCog(commands.Cog, name="Utilidad"):
    """Comandos útiles y de información."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # --- MAPA DE COGS CORREGIDO ---
        # Este mapa ahora define el orden y los nombres para el autocompletado y el menú
        self.cog_map = {
            "música": "Música",
            "niveles": "Niveles",
            "economía": "Economía",
            "apuestas": "Juegos de Azar",
            "juegos": "Juegos e IA",
            "interaccion": "Interacción",
            "nsfw": "NSFW",
            "moderacion": "Moderación",
            "configuracion": "Configuración del Servidor",
            "tts": "Texto a Voz",
            "utilidad": "Utilidad",
            "tickets": "Tickets"
        }

    @commands.hybrid_command(name='help', description="Muestra ayuda sobre los comandos del bot.")
    async def help(self, ctx: commands.Context, categoría: Optional[str] = None):
        if categoría is None:
            embed = discord.Embed(title="📜 Ayuda de Umapyoi", color=self.bot.CREAM_COLOR)
            # MODIFICADO: El enlace a la página web está integrado en el texto
            embed.description = (
                "**🚀 Cómo empezar a escuchar música**\n`/play <nombre de la canción o enlace>`\n\n"
                "**❓ ¿Qué es Umapyoi?**\nUn bot de nueva generación con música, juegos, economía y mucho más. ¡Todo en uno!\n\n"
                f"**🎛️ Categorías de Comandos:**\n*Para ver todos los comandos, visita nuestra [página de comandos]({constants.COMMANDS_PAGE_URL}).*"
            )
            embed.set_image(url="https://i.imgur.com/WwexK3G.png")
            
            view = discord.ui.View(timeout=180)
            view.add_item(HelpSelect(self.bot, self.cog_map))
            await ctx.send(embed=embed, view=view)
        else:
            cog_name_real = self.cog_map.get(categoría.lower())
            if cog_name_real:
                cog = self.bot.get_cog(cog_name_real)
                if not cog:
                    return await ctx.send(f"No se encontró la categoría '{cog_name_real}'.", ephemeral=True)
                
                embed = discord.Embed(title=f"📜 Comandos de {cog_name_real}", color=self.bot.CREAM_COLOR)
                
                command_list = sorted([cmd for cmd in cog.get_commands() if not cmd.hidden], key=lambda c: c.name)
                description = "\n".join([f"**`/{cmd.name}`** - {cmd.description}" for cmd in command_list if cmd.name != 'help'])
                
                embed.description = description or "Esta categoría no tiene comandos para mostrar."
                
                await ctx.send(embed=embed, ephemeral=True)
            else:
                await ctx.send(f"La categoría '{categoría}' no existe.", ephemeral=True)

    @help.autocomplete('categoría')
    async def help_autocomplete(self, interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice[str]]:
        return [
            discord.app_commands.Choice(name=cog_name, value=cmd_name)
            for cmd_name, cog_name in self.cog_map.items()
            if current.lower() in cmd_name.lower()
        ][:25]

    @commands.command(name='announce', hidden=True)
    @commands.is_owner()
    async def announce(self, ctx: commands.Context, *, mensaje: str):
        await ctx.defer(ephemeral=True) # Hacemos la respuesta efímera para no molestar en el canal
        embed = discord.Embed(title="📢 Anuncio del Bot", description=mensaje, color=self.bot.CREAM_COLOR, timestamp=datetime.datetime.now())
        embed.set_footer(text=f"Enviado por el desarrollador de Umapyoi")
        successful, failed = 0, 0
        for guild in self.bot.guilds:
            # Lógica mejorada para encontrar un canal donde enviar el mensaje
            target_channel = None
            if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
                target_channel = guild.system_channel
            else:
                # Busca el primer canal de texto donde pueda hablar
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        target_channel = channel
                        break
            if target_channel:
                try: 
                    await target_channel.send(embed=embed)
                    successful += 1
                except discord.Forbidden:
                    print(f"Fallo al enviar en {guild.name} ({guild.id}): Sin permisos en {target_channel.name}")
                    failed += 1
                except Exception as e:
                    print(f"Fallo al enviar en {guild.name} ({guild.id}): {e}")
                    failed += 1
            else: 
                print(f"Fallo al enviar en {guild.name} ({guild.id}): No se encontró un canal válido.")
                failed += 1
        await ctx.send(f"✅ Anuncio enviado a **{successful} servidores**.\n❌ Falló en **{failed} servidores**.")

    @commands.command(name='serverlist', hidden=True)
    @commands.is_owner()
    async def serverlist(self, ctx: commands.Context):
        await ctx.typing()
        server_list_str = f"Lista de Servidores ({len(self.bot.guilds)} en total):\n" + "="*45 + "\n"
        for i, guild in enumerate(self.bot.guilds):
            server_list_str += f"{i+1}. {guild.name}\n   ID: {guild.id}\n   Miembros: {guild.member_count}\n\n"
        try:
            await ctx.author.send("Aquí tienes la lista:", file=discord.File(fp=io.StringIO(server_list_str), filename="serverlist.txt"))
            if ctx.guild: await ctx.send("✅ Te he enviado la lista por DM.", delete_after=10)
        except discord.Forbidden:
            await ctx.send("No pude enviarte la lista por DM.", file=discord.File(fp=io.StringIO(server_list_str), filename="serverlist.txt"))

    @commands.hybrid_command(name='contacto', description="Muestra la información de contacto del creador.")
    async def contacto(self, ctx: commands.Context):
        embed = discord.Embed(color=self.bot.CREAM_COLOR)
        embed.set_author(name="📞 Información de Contacto", icon_url=self.bot.user.display_avatar.url)
        embed.description = "Puedes contactar a mi creador a través de Discord:\n👑 **sakurayo_crispy**"
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='serverhelp', description="Obtén el enlace al servidor de ayuda oficial.")
    async def serverhelp(self, ctx: commands.Context):
        embed = discord.Embed(color=self.bot.CREAM_COLOR)
        embed.set_author(name="💬 Servidor de Ayuda", icon_url=self.bot.user.display_avatar.url)
        embed.description = "¿Necesitas ayuda? ¡Únete a nuestro servidor oficial!\n[**Haz clic aquí para unirte**](https://discord.gg/fwNeZsGkSj)"
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='ping', description="Muestra la latencia del bot.")
    async def ping(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(color=self.bot.CREAM_COLOR)
        embed.set_author(name="🏓 Latencia del Sistema", icon_url=self.bot.user.display_avatar.url)
        embed.description = f"La latencia actual es de **{latency}ms**."
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="avatar", description="Muestra el avatar de un usuario.")
    async def avatar(self, ctx: commands.Context, miembro: discord.Member = None):
        await ctx.defer()
        target = miembro or ctx.author
        embed = discord.Embed(title=f"Avatar de {target.display_name}", color=target.color).set_image(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="userinfo", aliases=["whois"], description="Muestra información detallada sobre un usuario.")
    async def userinfo(self, ctx: commands.Context, miembro: discord.Member = None):
        await ctx.defer()
        target = miembro or ctx.author
        embed = discord.Embed(title=f"Información de {target.display_name}", color=target.color).set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ID", value=target.id, inline=False)
        embed.add_field(name="Cuenta Creada", value=f"<t:{int(target.created_at.timestamp())}:D>", inline=True)
        if target.joined_at: embed.add_field(name="Se Unió al Servidor", value=f"<t:{int(target.joined_at.timestamp())}:D>", inline=True)
        roles = [role.mention for role in target.roles[1:]]
        roles_str = ", ".join(roles) if roles else "Ninguno"
        embed.add_field(name=f"Roles ({len(roles)})", value=roles_str[:1020] + "..." if len(roles_str) > 1024 else roles_str, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", aliases=["guildinfo"], description="Muestra información detallada sobre el servidor.")
    async def serverinfo(self, ctx: commands.Context):
        if not ctx.guild: return
        await ctx.defer()
        server = ctx.guild
        embed = discord.Embed(title=f"Información de {server.name}", color=self.bot.CREAM_COLOR)
        if server.icon: embed.set_thumbnail(url=server.icon.url)
        if server.owner: embed.add_field(name="👑 Propietario", value=server.owner.mention, inline=True)
        embed.add_field(name="👥 Miembros", value=str(server.member_count), inline=True)
        embed.add_field(name="📅 Creado el", value=f"<t:{int(server.created_at.timestamp())}:D>", inline=True)
        embed.add_field(name="💬 Canales", value=f"{len(server.text_channels)} de texto | {len(server.voice_channels)} de voz", inline=False)
        embed.add_field(name="✨ Nivel de Boost", value=f"Nivel {server.premium_tier} ({server.premium_subscription_count} boosts)", inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='status', description="Muestra el estado técnico del bot y del sistema.")
    async def status(self, ctx: commands.Context):
        """Muestra un panel con estadísticas de uso de CPU, RAM, Uptime y versiones."""
        await ctx.defer()
        
        # Cálculo de Uptime
        now = datetime.datetime.now(datetime.timezone.utc)
        uptime = now - self.bot.start_time
        days, remainder = divmod(int(uptime.total_seconds()), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"

        # Uso de sistema
        process = psutil.Process()
        ram_usage = process.memory_info().rss / 1024**2 # MB
        cpu_usage = psutil.cpu_percent()
        
        embed = discord.Embed(color=self.bot.CREAM_COLOR)
        embed.set_author(name="📊 Panel de Estado Técnico", icon_url=self.bot.user.display_avatar.url)
        
        status_info = (
            f"🚀 **Uptime:** `{uptime_str}`\n"
            f"📡 **Latencia:** `{round(self.bot.latency * 1000)}ms`\n"
            f"🧠 **RAM:** `{ram_usage:.1f} MB` | **CPU:** `{cpu_usage}%`\n"
            f"🏠 **Gilds:** `{len(self.bot.guilds):,}` | **Users:** `{sum(g.member_count for g in self.bot.guilds):,}`\n"
            f"🔧 **Discord.py:** `{discord.__version__}`"
        )
        embed.description = status_info
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text=f"ID: {self.bot.user.id}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='say', description="Hace que el bot repita tu mensaje.")
    @commands.has_permissions(manage_messages=True)
    async def say(self, ctx: commands.Context, *, mensaje: str):
        if ctx.interaction:
            await ctx.interaction.response.send_message("Mensaje enviado.", ephemeral=True, delete_after=5)
            await ctx.channel.send(mensaje)
        else:
            await ctx.message.delete()
            await ctx.send(mensaje)
    
# Los comandos de ticket han sido movidos a tickets.py
        
    @commands.command(name='sync', hidden=True)
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        await ctx.typing()
        try:
            # Sincroniza los comandos globalmente
            synced = await self.bot.tree.sync()
            await ctx.send(f"✅ Sincronizados **{len(synced)}** comandos globalmente.")
            print(f"Sincronizados {len(synced)} comandos.")
        except Exception as e:
            await ctx.send(f"❌ Error al sincronizar: {e}")
            print(f"Error al sincronizar: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(UtilityCog(bot))