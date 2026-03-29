import pytest
import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from cogs.serverconfig import ServerConfigCog
from discord.ext import commands
import discord

# Fake Bot object to test the cooldown injection
class DummyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!!", intents=discord.Intents.default())
        # Mock para evitar que el setup_hook llame a await self.tree.sync() real
        self.tree.sync = AsyncMock()
        self.check_broadcasts = MagicMock()
        self.tree.sync = AsyncMock()
        self.check_broadcasts = MagicMock()
        
    async def setup_hook(self):
        # Esta es una versión reducida exacta del código insertado en main.py 
        # para aislar la prueba de la lógica de rate limiting.
        OWNER_ID = "11111111"
        
        async def global_interaction_cooldown(interaction: discord.Interaction):
            if interaction.type != discord.InteractionType.application_command:
                return True
            exempt_commands = {'work', 'rob', 'daily', 'deposit', 'withdraw', 'balance', 'rank', 'play', 'pause', 'resume', 'skip'}
            if interaction.command and interaction.command.name in exempt_commands:
                return True
            now = datetime.datetime.now(datetime.timezone.utc).timestamp()
            user_id = interaction.user.id
            if str(user_id) == OWNER_ID:
                return True
            if not hasattr(self, '_last_cmd_times'):
                self._last_cmd_times = {}
            last_time = self._last_cmd_times.get(user_id, 0)
            if now - last_time < 3.0:
                time_left = 3.0 - (now - last_time)
                await interaction.response.send_message(f"⏳ Te estás apresurando. Por favor, espera **{time_left:.1f}** segundos.", ephemeral=True)
                return False
            self._last_cmd_times[user_id] = now
            return True
        
        self.tree.interaction_check = global_interaction_cooldown

        @self.check
        async def global_prefix_cooldown(ctx: commands.Context):
            if not ctx.command: return True
            exempt_commands = {'work', 'rob', 'daily', 'deposit', 'withdraw', 'balance', 'rank', 'play', 'pause', 'resume', 'skip'}
            if ctx.command.name in exempt_commands: return True
            now = datetime.datetime.now(datetime.timezone.utc).timestamp()
            user_id = ctx.author.id
            if str(user_id) == OWNER_ID: return True
            if not hasattr(self, '_last_cmd_times'):
                self._last_cmd_times = {}
            last_time = self._last_cmd_times.get(user_id, 0)
            if now - last_time < 3.0:
                time_left = 3.0 - (now - last_time)
                try:
                    await ctx.send(f"⏳ Te estás apresurando. Por favor, espera **{time_left:.1f}** segundos.", delete_after=3.0)
                except discord.HTTPException:
                    pass
                return False
            self._last_cmd_times[user_id] = now
            return True


@pytest.mark.asyncio
async def test_global_prefix_cooldown():
    bot = DummyBot()
    await bot.setup_hook()
    
    # 1. Simular un usuario normal ejecutando !!ping
    mock_ctx = AsyncMock()
    mock_ctx.command = MagicMock()
    mock_ctx.command.name = "ping"
    mock_ctx.author.id = 999999999  # No es dueño
    
    # Primera petición: Debe pasar
    assert await bot._checks[0](mock_ctx) is True
    
    # Segunda petición inmediata: Debe fallar y enviar aviso
    assert await bot._checks[0](mock_ctx) is False
    mock_ctx.send.assert_called_once()
    
    args, kwargs = mock_ctx.send.call_args
    assert "Te estás apresurando" in args[0]
    assert kwargs.get('delete_after') == 3.0

@pytest.mark.asyncio
async def test_global_prefix_cooldown_exemptions():
    bot = DummyBot()
    await bot.setup_hook()
    
    mock_ctx = AsyncMock()
    mock_ctx.command = MagicMock()
    mock_ctx.author.id = 999999999
    
    # Comandos como !!work están exentos, no deberian activar cooldown
    mock_ctx.command.name = "work"
    assert await bot._checks[0](mock_ctx) is True
    assert await bot._checks[0](mock_ctx) is True # 2da vez inmediata sigue pasando

@pytest.mark.asyncio
async def test_global_owner_bypass():
    bot = DummyBot()
    await bot.setup_hook()
    
    mock_ctx = AsyncMock()
    mock_ctx.command = MagicMock()
    mock_ctx.command.name = "ping"
    mock_ctx.author.id = 11111111  # Mismo que OWNER_ID configurado
    
    # El dueño puede spamear
    assert await bot._checks[0](mock_ctx) is True
    assert await bot._checks[0](mock_ctx) is True
    assert await bot._checks[0](mock_ctx) is True
