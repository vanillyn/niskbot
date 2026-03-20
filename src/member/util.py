import discord


def _is_admin(member: discord.Member) -> bool:
    return (
        member.guild_permissions.administrator or member.guild_permissions.manage_guild
    )
