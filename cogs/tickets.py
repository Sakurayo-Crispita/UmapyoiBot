import discord
from discord.ext import commands
from typing import Optional
from utils import database_manager as db
from utils.lang_utils import _t

class TicketCloseView(discord.ui.View):
    def __init__(self, lang: str = 'es'):
        super().__init__(timeout=None)
        self.lang = lang
        self.close_button.label = _t('bot.tickets.close_button', lang=lang)
        
    @discord.ui.button(label="Cerrar Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close_btn")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Fetch lang again just in case or use self.lang
        lang = self.lang
        await interaction.response.send_message(_t('bot.tickets.closing_wait', lang=lang))
        import asyncio
        await asyncio.sleep(5)
        await interaction.channel.delete()

class TicketOpenView(discord.ui.View):
    def __init__(self, lang: str = 'es'):
        super().__init__(timeout=None)
        self.lang = lang
        self.open_button.label = _t('bot.tickets.open_button', lang=lang)
        
    @discord.ui.button(label="Abrir Ticket", style=discord.ButtonStyle.primary, emoji="🎟️", custom_id="ticket_open_btn")
    async def open_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verificar si el módulo está habilitado
        settings = await db.get_cached_server_settings(interaction.guild.id)
        lang = settings.get('language', 'es')
        
        if settings and not settings.get('tickets_enabled', 1):
            return await interaction.response.send_message(_t('bot.config.module_disabled_msg', lang=lang), ephemeral=True)

        guild = interaction.guild
        category_id = settings.get('ticket_category_id')
        category = guild.get_channel(category_id) if category_id else interaction.channel.category
        
        if not category:
            return await interaction.response.send_message(_t('bot.tickets.no_category', lang=lang), ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites,
            topic=f"Ticket de {interaction.user.id}"
        )
        
        embed = discord.Embed(
            title=_t('bot.tickets.support_title', lang=lang), 
            description=_t('bot.tickets.welcome_msg', lang=lang, user=interaction.user.mention), 
            color=discord.Color.blue()
        )
        await channel.send(embed=embed, view=TicketCloseView(lang=lang))
        
        await interaction.response.send_message(_t('bot.tickets.ticket_created', lang=lang, channel=channel.mention), ephemeral=True)

class TicketsCog(commands.Cog, name="Tickets"):
    """Gestión de tickets de soporte."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(TicketOpenView())
        self.bot.add_view(TicketCloseView())

    async def cog_check(self, ctx: commands.Context):
        """Check global para este Cog."""
        if not ctx.guild: return True
        settings = await db.get_cached_server_settings(ctx.guild.id)
        lang = settings.get('language', 'es')
        if settings and not settings.get('tickets_enabled', 1):
            await ctx.send(_t('bot.config.module_disabled_msg', lang=lang), ephemeral=True)
            return False
        return True

    @commands.hybrid_group(name="ticket", description="Configura el sistema de soporte automatizado.")
    @commands.has_permissions(administrator=True)
    async def ticket(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Comandos: `/ticket setup`", ephemeral=True)

    @ticket.command(name="setup", description="Genera el panel interactivo de creación de tickets en este canal.")
    async def ticket_setup(self, ctx: commands.Context):
        settings = await db.get_cached_server_settings(ctx.guild.id)
        lang = settings.get('language', 'es')
        
        embed = discord.Embed(
            title=_t('bot.tickets.setup_title', lang=lang), 
            description=_t('bot.tickets.setup_desc', lang=lang), 
            color=self.bot.CREAM_COLOR
        )
        await ctx.send(embed=embed, view=TicketOpenView(lang=lang))
        if ctx.message:
            try: await ctx.message.delete()
            except: pass

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
