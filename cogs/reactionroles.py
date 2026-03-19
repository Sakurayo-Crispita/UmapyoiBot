import discord
from discord.ext import commands
from utils import database_manager

class ReactionRoles(commands.Cog, name="Roles por Reacción"):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or payload.member is None or payload.member.bot:
            return

        emoji_name = str(payload.emoji)

        role_data = await database_manager.fetchone(
            "SELECT role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
            (payload.guild_id, payload.message_id, emoji_name)
        )

        if role_data:
            role_id = role_data['role_id']
            guild = self.bot.get_guild(payload.guild_id)
            if guild:
                role = guild.get_role(role_id)
                if role and role not in payload.member.roles:
                    try:
                        await payload.member.add_roles(role, reason="Rol por Reacción")
                    except discord.Forbidden:
                        pass
                    except discord.HTTPException:
                        pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return

        emoji_name = str(payload.emoji)

        role_data = await database_manager.fetchone(
            "SELECT role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
            (payload.guild_id, payload.message_id, emoji_name)
        )

        if role_data:
            role_id = role_data['role_id']
            guild = self.bot.get_guild(payload.guild_id)
            if guild:
                member = guild.get_member(payload.user_id)
                if not member:
                    # In case the member is not cached
                    try:
                        member = await guild.fetch_member(payload.user_id)
                    except:
                        pass
                
                if member and not member.bot:
                    role = guild.get_role(role_id)
                    if role and role in member.roles:
                        try:
                            await member.remove_roles(role, reason="Rol por Reacción Eliminado")
                        except discord.Forbidden:
                            pass
                        except discord.HTTPException:
                            pass

async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
