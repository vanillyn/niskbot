from __future__ import annotations

import discord

from src.data.config import EconomyConfig
from src.data.db import Database
from src.server.permissions import has_permission


def fmt(amount: int, cfg: EconomyConfig) -> str:
    return f"{cfg.currency_symbol}{amount:,}"


async def can_manage(db: Database, member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return await has_permission(db, member, "economy.manage")
