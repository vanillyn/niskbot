from __future__ import annotations

import re
import uuid as _uuid_mod
from dataclasses import dataclass, field

import discord

_BUTTON_RE = re.compile(
    r"\{(?:button|b):([^:}]+):([^:}]+):([^:}]+):((?:[^{}]|\{[^}]*\})+)\}"
)
_CONTAINER_RE = re.compile(r"\{container:([^}]+)\}")
_ROLE_RE = re.compile(r"^\{role:(add|remove):([^:}]+)(?::([^}]*))?\}$")
_CHANNEL_RE = re.compile(
    r"^\{channel:(add|remove|rename|slowmode):([^:}]+)(?::([^}]*))?\}$"
)
_USER_RE = re.compile(r"^\{user:(rename|message):([^:}]+):([^}]+)\}$")
_MSG_RE = re.compile(r"^\{message:([^:}]+):(.+)\}$")
_DUR_RE = re.compile(r"(\d+)\s*([smhd])", re.IGNORECASE)

_STYLE_MAP: dict[str, discord.ButtonStyle] = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "disabled": discord.ButtonStyle.secondary,
    "danger": discord.ButtonStyle.danger,
    "success": discord.ButtonStyle.success,
}


@dataclass
class ParsedButton:
    internal_id: str
    name: str
    label: str
    style: discord.ButtonStyle
    disabled: bool
    is_link: bool
    action: str
    url: str | None = None


@dataclass
class ParseResult:
    text: str
    buttons: list[ParsedButton] = field(default_factory=list)
    container_refs: list[str] = field(default_factory=list)


def resolve_text(
    text: str,
    guild: discord.Guild,
    member: discord.Member,
    channel: discord.abc.GuildChannel | discord.Thread | None = None,
) -> str:
    mapping: dict[str, str] = {
        "{user}": member.mention,
        "{username}": member.name,
        "{display_name}": member.display_name,
        "{user_id}": str(member.id),
        "{mention}": member.mention,
        "{server}": guild.name,
        "{server_id}": str(guild.id),
        "{member_count}": str(guild.member_count or 0),
    }
    if isinstance(channel, (discord.TextChannel, discord.Thread)):
        mapping["{channel}"] = channel.name
        mapping["{channel_id}"] = str(channel.id)
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text


def parse_buttons(text: str) -> ParseResult:
    result = ParseResult(text=text)
    for m in _CONTAINER_RE.finditer(text):
        result.container_refs.append(m.group(1).strip())
    for m in _BUTTON_RE.finditer(text):
        name = m.group(1).strip()
        label = m.group(2).strip()
        btype = m.group(3).strip().lower()
        action = m.group(4).strip()
        is_link = btype == "link"
        is_disabled = btype == "disabled"
        style = _STYLE_MAP.get(btype, discord.ButtonStyle.secondary)
        result.buttons.append(
            ParsedButton(
                internal_id=str(_uuid_mod.uuid4()),
                name=name,
                label=label,
                style=style,
                disabled=is_disabled,
                is_link=is_link,
                action="" if is_link else action,
                url=action if is_link else None,
            )
        )
    clean = _BUTTON_RE.sub("", _CONTAINER_RE.sub("", text)).strip()
    result.text = clean
    return result


def action_needs_admin(action: str) -> bool:
    if _CHANNEL_RE.match(action) or _MSG_RE.match(action):
        return True
    if _USER_RE.match(action):
        return True
    m = _ROLE_RE.match(action)
    if m:
        target_ref = (m.group(3) or "").strip()
        return bool(target_ref) and target_ref != "{user}"
    return False


def _parse_secs(s: str) -> int:
    total = 0
    for n, u in _DUR_RE.findall(s):
        n = int(n)
        match u.lower():
            case "s":
                total += n
            case "m":
                total += n * 60
            case "h":
                total += n * 3600
            case "d":
                total += n * 86400
    return total if total > 0 else (int(s) if s.isdigit() else 0)


def _find_role(guild: discord.Guild, ref: str) -> discord.Role | None:
    ref = ref.strip()
    if ref.startswith("<@&") and ref.endswith(">"):
        ref = ref[3:-1]
    if ref.isdigit():
        return guild.get_role(int(ref))
    return discord.utils.get(guild.roles, name=ref)


def _find_channel(guild: discord.Guild, ref: str) -> discord.TextChannel | None:
    ref = ref.strip()
    if ref.startswith("<#") and ref.endswith(">"):
        ref = ref[2:-1]
    if ref.isdigit():
        ch = guild.get_channel(int(ref))
        return ch if isinstance(ch, discord.TextChannel) else None
    return discord.utils.get(guild.text_channels, name=ref)


def _find_member(guild: discord.Guild, ref: str) -> discord.Member | None:
    ref = ref.strip()
    if ref.startswith("<@") and ref.endswith(">"):
        ref = ref[2:-1].lstrip("!")
    if ref.isdigit():
        return guild.get_member(int(ref))
    return discord.utils.get(guild.members, name=ref)


async def execute_action(
    interaction: discord.Interaction,
    action: str,
) -> None:
    guild = interaction.guild
    if not isinstance(guild, discord.Guild):
        await interaction.response.send_message("not in a guild", ephemeral=True)
        return
    member = guild.get_member(interaction.user.id)
    if member is None:
        await interaction.response.send_message("member not found", ephemeral=True)
        return

    resolved = action.replace("{user}", str(member.id))

    m = _ROLE_RE.match(resolved)
    if m:
        act, role_ref, target_ref = m.groups()
        tid = int(target_ref) if (target_ref or "").strip().isdigit() else member.id
        target = guild.get_member(tid) or member
        role = _find_role(guild, role_ref)
        if role is None:
            await interaction.response.send_message(
                f"role not found: `{role_ref}`", ephemeral=True
            )
            return
        try:
            if act == "add":
                await target.add_roles(role, reason="resource button")
                await interaction.response.send_message(
                    f"added **{role.name}**", ephemeral=True
                )
            else:
                await target.remove_roles(role, reason="resource button")
                await interaction.response.send_message(
                    f"removed **{role.name}**", ephemeral=True
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
        return

    m2 = _CHANNEL_RE.match(resolved)
    if m2:
        act, ch_ref, extra = m2.groups()
        if act == "add":
            cname = ch_ref.replace(str(member.id), member.name)
            try:
                ch = await guild.create_text_channel(cname)
                await interaction.response.send_message(
                    f"created {ch.mention}", ephemeral=True
                )
            except discord.Forbidden:
                await interaction.response.send_message(
                    "missing permissions", ephemeral=True
                )
            return
        channel = _find_channel(guild, ch_ref)
        if channel is None:
            await interaction.response.send_message(
                f"channel not found: `{ch_ref}`", ephemeral=True
            )
            return
        try:
            if act == "rename" and extra:
                await channel.edit(name=extra)
                await interaction.response.send_message(
                    f"renamed \u2192 **{extra}**", ephemeral=True
                )
            elif act == "slowmode" and extra:
                secs = _parse_secs(extra)
                await channel.edit(slowmode_delay=secs)
                await interaction.response.send_message(
                    f"slowmode \u2192 {secs}s", ephemeral=True
                )
            elif act == "remove":
                await channel.delete()
                await interaction.response.send_message(
                    "channel deleted", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "invalid channel action", ephemeral=True
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
        return

    m3 = _USER_RE.match(resolved)
    if m3:
        act, target_ref, value = m3.groups()
        target_member = _find_member(guild, target_ref)
        if target_member is None:
            await interaction.response.send_message(
                f"user not found: `{target_ref}`", ephemeral=True
            )
            return
        if target_member.id != member.id and not member.guild_permissions.administrator:
            await interaction.response.send_message(
                "can only target yourself", ephemeral=True
            )
            return
        try:
            if act == "rename":
                await target_member.edit(nick=value.strip('"'))
                await interaction.response.send_message(
                    f"nick \u2192 **{value}**", ephemeral=True
                )
            elif act == "message":
                await target_member.send(value.strip('"'))
                await interaction.response.send_message("dm sent", ephemeral=True)
            else:
                await interaction.response.send_message(
                    "invalid user action", ephemeral=True
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
        return

    m4 = _MSG_RE.match(resolved)
    if m4:
        ch_ref, content = m4.groups()
        dest = _find_channel(guild, ch_ref)
        if dest is None:
            await interaction.response.send_message(
                f"channel not found: `{ch_ref}`", ephemeral=True
            )
            return
        try:
            await dest.send(content.strip('"'))
            await interaction.response.send_message("sent", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
        return

    await interaction.response.send_message("unknown action", ephemeral=True)
