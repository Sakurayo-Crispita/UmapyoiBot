import pytest
import discord
from cogs.moderation import ModerationCog
from utils import database_manager as db

@pytest.fixture
def mod_cog(mock_bot):
    return ModerationCog(mock_bot)

class MockAvatar:
    @property
    def url(self):
        return "http://mock.avatar/url.png"

class MockMember(discord.Object):
    def __init__(self, id, name, guild):
        super().__init__(id)
        self.name = name
        self.display_name = name
        self.guild = guild
        self.bot = False
        self.display_avatar = MockAvatar()
        self.top_role = discord.Object(id=10)
        self.top_role.position = 10
        
    async def send(self, *args, **kwargs):
        pass

async def test_warn_logging(mod_cog, mock_ctx):
    target = MockMember(555, "MalUsuario", mock_ctx.guild)
    
    # Para bypassear el owner check interno
    mock_ctx.guild.owner_id = 11111111 
    mock_ctx.author.top_role = discord.Object(id=20)
    mock_ctx.author.top_role.position = 20
    
    await mod_cog.warn.callback(mod_cog, mock_ctx, target, razon="Uso de mal lenguaje")
    
    # Verificar que se insertó correctamente en la BDD
    warnings = await db.fetchall("SELECT * FROM warnings WHERE guild_id = ? AND user_id = ?", (mock_ctx.guild.id, target.id))
    assert len(warnings) == 1
    assert warnings[0]["reason"] == "Uso de mal lenguaje"
    assert warnings[0]["moderator_id"] == mock_ctx.author.id

async def test_clear_warnings(mod_cog, mock_ctx):
    target = MockMember(555, "MalUsuario", mock_ctx.guild)
    mock_ctx.author.top_role = discord.Object(id=20)
    mock_ctx.author.top_role.position = 20
    
    # Insertar advertencias directamente
    await db.execute("INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)", (mock_ctx.guild.id, target.id, mock_ctx.author.id, "Spam 1"))
    await db.execute("INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)", (mock_ctx.guild.id, target.id, mock_ctx.author.id, "Spam 2"))
    
    warnings_before = await db.fetchall("SELECT * FROM warnings WHERE guild_id = ? AND user_id = ?", (mock_ctx.guild.id, target.id))
    assert len(warnings_before) == 2
    
    # Limpiar
    await mod_cog.clearwarnings.callback(mod_cog, mock_ctx, target)
    
    warnings_after = await db.fetchall("SELECT * FROM warnings WHERE guild_id = ? AND user_id = ?", (mock_ctx.guild.id, target.id))
    assert len(warnings_after) == 0
