from __future__ import annotations

from dataclasses import dataclass, field

import discord


@dataclass
class Placeholder:
    guild: discord.Guild | None = field(default=None)
    member: discord.Member | None = field(default=None)
    channel: discord.TextChannel | discord.Thread | None = field(default=None)


def _build_map(ctx: Placeholder) -> dict[str, str]:
    result: dict[str, str] = {}

    if ctx.guild is not None:
        result["{server}"] = ctx.guild.name
        result["{server_id}"] = str(ctx.guild.id)
        result["{member_count}"] = str(ctx.guild.member_count or 0)

    if ctx.member is not None:
        result["{user}"] = str(ctx.member)
        result["{username}"] = ctx.member.name
        result["{display_name}"] = ctx.member.display_name
        result["{user_id}"] = str(ctx.member.id)
        result["{mention}"] = ctx.member.mention

    if ctx.channel is not None:
        result["{channel}"] = ctx.channel.name
        result["{channel_id}"] = str(ctx.channel.id)

    return result


def resolve(text: str, ctx: Placeholder) -> str:
    mapping = _build_map(ctx)
    for key in mapping:
        if key in text:
            text = text.replace(key, mapping[key])
    return text


def from_message(msg: discord.Message) -> Placeholder:
    return Placeholder(
        guild=msg.guild,
        member=msg.author if isinstance(msg.author, discord.Member) else None,
        channel=(
            msg.channel
            if isinstance(msg.channel, (discord.TextChannel, discord.Thread))
            else None
        ),
    )


def from_interaction(interaction: discord.Interaction) -> Placeholder:
    return Placeholder(
        guild=interaction.guild,
        member=(
            interaction.user if isinstance(interaction.user, discord.Member) else None
        ),
        channel=(
            interaction.channel
            if isinstance(interaction.channel, (discord.TextChannel, discord.Thread))
            else None
        ),
    )
