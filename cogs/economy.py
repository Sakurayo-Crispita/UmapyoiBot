import discord
from discord.ext import commands
import random
import datetime
from typing import Literal, Optional

# Importamos el gestor de base de datos
from utils import database_manager as db

class EconomyCog(commands.Cog, name="Economía"):
    """Sistema de economía configurable por servidor."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._work_cd = commands.CooldownMapping.from_cooldown(1, 3600, commands.BucketType.user)
        self._rob_cd = commands.CooldownMapping.from_cooldown(1, 21600, commands.BucketType.user)

    async def _send_maintenance_message(self, ctx: commands.Context):
        """Envía un mensaje estandarizado de que el sistema está en mantenimiento."""
        await ctx.send("⚙️ El sistema de economía está actualmente en mantenimiento. Por favor, inténtalo más tarde.", ephemeral=True)

    # --- COMANDOS DESACTIVADOS ---
    # Todos los comandos llamarán al mensaje de mantenimiento.

    @commands.hybrid_group(name="economy", description="Comandos para configurar la economía del servidor.")
    @commands.has_permissions(administrator=True)
    async def economy(self, ctx: commands.Context):
        await self._send_maintenance_message(ctx)

    @commands.hybrid_command(name="add-money", description="Añade dinero a la cartera de un usuario.")
    @commands.has_permissions(manage_guild=True)
    async def add_money(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        await self._send_maintenance_message(ctx)

    @commands.hybrid_command(name="remove-money", description="Quita dinero de la cartera de un usuario.")
    @commands.has_permissions(manage_guild=True)
    async def remove_money(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        await self._send_maintenance_message(ctx)

    @commands.hybrid_command(name="reset-economy", description="Reinicia la economía del servidor (ACCIÓN PELIGROSA).")
    @commands.has_permissions(administrator=True)
    async def reset_economy(self, ctx: commands.Context):
        await self._send_maintenance_message(ctx)

    @commands.hybrid_command(name='deposit', aliases=['dep'], description="Deposita dinero de tu cartera al banco.")
    async def deposit(self, ctx: commands.Context, cantidad: str):
        await self._send_maintenance_message(ctx)

    @commands.hybrid_command(name='withdraw', description="Retira dinero de tu banco a tu cartera.")
    async def withdraw(self, ctx: commands.Context, cantidad: str):
        await self._send_maintenance_message(ctx)

    @commands.hybrid_command(name='balance', aliases=['bal'], description="Muestra tu balance de cartera y banco.")
    async def balance(self, ctx: commands.Context, miembro: Optional[discord.Member] = None):
        await self._send_maintenance_message(ctx)

    @commands.hybrid_command(name='daily', description="Reclama tu recompensa diaria en la cartera.")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx: commands.Context):
        await self._send_maintenance_message(ctx)
        
    # El manejador de error local ha sido eliminado para evitar mensajes duplicados.
    # El manejador global en main.py se encargará de los cooldowns.

    @commands.hybrid_command(name='work', description="Trabaja para ganar un dinero extra.")
    async def work(self, ctx: commands.Context):
        await self._send_maintenance_message(ctx)

    @commands.hybrid_command(name='rob', description="Intenta robarle a otro usuario de su cartera.")
    async def rob(self, ctx: commands.Context, miembro: discord.Member):
        await self._send_maintenance_message(ctx)

    @commands.hybrid_command(name='give', description="Transfiere dinero de tu cartera a otro usuario.")
    async def give(self, ctx: commands.Context, miembro: discord.Member, cantidad: int):
        await self._send_maintenance_message(ctx)

    @commands.hybrid_command(name='leaderboard', aliases=['lb'], description="Muestra a los usuarios más ricos del servidor.")
    async def leaderboard(self, ctx: commands.Context):
        await self._send_maintenance_message(ctx)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))