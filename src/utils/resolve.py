from __future__ import annotations

import re

import discord

_LEGACY_DISCRIM_RE = re.compile(r"#0{4}$")
_MENTION_RE = re.compile(r"^<@!?(\d+)>$")


def strip_legacy_discriminator(raw: str) -> str:
    return _LEGACY_DISCRIM_RE.sub("", raw.strip())


def extract_user_id(raw: str) -> int | None:
    cleaned = strip_legacy_discriminator(raw)
    mention_match = _MENTION_RE.match(cleaned)
    if mention_match is not None:
        return int(mention_match.group(1))
    if cleaned.isdigit():
        return int(cleaned)
    return None


async def resolve_user(
    guild: discord.Guild,
    raw: str,
) -> discord.Member | None:
    user_id = extract_user_id(raw)
    if user_id is not None:
        member = guild.get_member(user_id)
        if member is not None:
            return member
        try:
            return await guild.fetch_member(user_id)
        except discord.NotFound:
            return None
        except discord.HTTPException:
            return None

    cleaned = strip_legacy_discriminator(raw).lower()
    for member in guild.members:
        if member.name.lower() == cleaned:
            return member
        if member.display_name.lower() == cleaned:
            return member
        global_name = member.global_name
        if global_name is not None and global_name.lower() == cleaned:
            return member
    return None