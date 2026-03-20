from __future__ import annotations

import json
from dataclasses import dataclass, field

from src.data.db import Database


async def get_config(db: Database, guild_id: int, key: str) -> str | None:
    row = await db.fetchone(
        "select value from guild_configs where guild_id = ? and key = ?",
        (guild_id, key),
    )
    return str(row[0]) if row is not None else None


async def set_config(db: Database, guild_id: int, key: str, value: str) -> None:
    await db.execute(
        "insert into guild_configs (guild_id, key, value) values (?, ?, ?)"
        " on conflict (guild_id, key) do update set value = excluded.value",
        (guild_id, key, value),
    )


async def delete_config(db: Database, guild_id: int, key: str) -> None:
    await db.execute(
        "delete from guild_configs where guild_id = ? and key = ?",
        (guild_id, key),
    )


async def get_all_config(db: Database, guild_id: int) -> dict[str, str]:
    rows = await db.fetchall(
        "select key, value from guild_configs where guild_id = ?",
        (guild_id,),
    )
    return {str(r[0]): str(r[1]) for r in rows}


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() == "true"


def _str(v: str | None, default: str | None = None) -> str | None:
    return v if v is not None else default


def _str_req(v: str | None, default: str) -> str:
    return v if v is not None else default


def _int(v: str | None, default: int | None = None) -> int | None:
    try:
        return int(v) if v is not None else default
    except ValueError:
        return default


def _list(v: str | None, default: list[str] | None = None) -> list[str]:
    if v is None:
        return default or []
    try:
        result = json.loads(v)
        return [str(x) for x in result] if isinstance(result, list) else [str(result)]
    except json.JSONDecodeError:
        return [x.strip() for x in v.split(",") if x.strip()]


@dataclass
class LogConfig:
    moderation: bool = False
    moderation_channel: int | None = None
    moderation_show_moderator: bool = True
    moderation_show_reason: bool = True
    msg_kick: list[str] = field(
        default_factory=lambda: ["[{infraction_id}] {user} was kicked"]
    )
    msg_ban: list[str] = field(
        default_factory=lambda: ["[{infraction_id}] {user} was banned"]
    )
    msg_mute: list[str] = field(
        default_factory=lambda: ["[{infraction_id}] {user} was muted"]
    )
    msg_warn: list[str] = field(
        default_factory=lambda: ["[{infraction_id}] {user} was warned"]
    )
    msg_slowmode: list[str] = field(
        default_factory=lambda: ["[{infraction_id}] {user} had slowmode applied"]
    )
    alerts: bool = False
    alerts_channel: int | None = None
    alerts_joins: bool = True
    alerts_joins_channel: int | None = None
    alerts_joins_message: str | None = None
    alerts_leaves: bool = True
    alerts_leaves_channel: int | None = None
    alerts_leaves_message: str | None = None
    alerts_twitch: bool = False
    alerts_twitch_channel: int | None = None
    alerts_twitch_message: str | None = None
    alerts_youtube: bool = False
    alerts_youtube_channel: int | None = None
    alerts_youtube_message: str | None = None
    alerts_free_games: bool = False
    alerts_free_games_channel: int | None = None
    alerts_free_games_message: str | None = None


@dataclass
class ModerationConfig:
    require_confirm: bool = True
    kick_default_reason: list[str] = field(
        default_factory=lambda: ["{user} was kicked"]
    )
    ban_default_reason: list[str] = field(default_factory=lambda: ["{user} was banned"])
    mute_default_reason: list[str] = field(default_factory=lambda: ["{user} was muted"])
    warn_default_reason: list[str] = field(
        default_factory=lambda: ["{user} was warned"]
    )
    slowmode_default_reason: list[str] = field(
        default_factory=lambda: ["{user} had slowmode applied"]
    )
    ban_default_duration: str = "forever"
    mute_default_duration: str = "forever"
    mod_role: int | None = None
    admin_role: int | None = None
    trial_mod_role: int | None = None
    dangerous_users: list[str] = field(default_factory=list)
    automod_bypass_roles: list[str] = field(default_factory=list)
    automod_bypass_permissions: list[str] = field(
        default_factory=lambda: ["administrator"]
    )
    tickets_category: int | None = None
    tickets_message: str | None = None
    tickets_voice: bool = False
    tickets_creator_permissions: bool = True
    tickets_roles: list[str] = field(default_factory=list)
    tickets_admin_role: int | None = None
    tickets_archive: bool = False
    tickets_archive_category: int | None = None
    tickets_archive_role: int | None = None
    tickets_archive_auto: str | None = None
    kick_dm: list[str] = field(
        default_factory=lambda: ["{user}, you were kicked for: {reason}"]
    )
    kick_channel: list[str] = field(default_factory=lambda: ["{user} has been kicked"])
    ban_dm: list[str] = field(
        default_factory=lambda: ["{user}, you were banned for: {reason}"]
    )
    ban_channel: list[str] = field(default_factory=lambda: ["{user} has been banned"])
    mute_dm: list[str] = field(
        default_factory=lambda: ["{user}, you were muted for: {reason}"]
    )
    mute_channel_msg: list[str] = field(
        default_factory=lambda: ["{user} has been muted"]
    )
    warn_dm: list[str] = field(
        default_factory=lambda: ["{user}, you were warned for: {reason}"]
    )
    warn_channel: list[str] = field(default_factory=lambda: ["{user} has been warned"])
    mute_role: int | None = None
    mute_channel: int | None = None


@dataclass
class EconomyConfig:
    enabled: bool = False
    casino: bool = False
    drop: bool = False
    drop_channels: list[str] = field(default_factory=list)
    shop: bool = False
    shop_channel: int | None = None
    currency_name: str = "coins"
    currency_symbol: str = "$"
    currency_fractional: str = "cents"
    pay: bool = True
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=lambda: ["send_messages"])
    pay_roles: list[str] = field(default_factory=list)
    casino_roles: list[str] = field(default_factory=list)
    drop_roles: list[str] = field(default_factory=list)
    shop_roles: list[str] = field(default_factory=list)


@dataclass
class XpConfig:
    roles: list[str] = field(default_factory=list)
    achievements_roles: list[str] = field(default_factory=list)
    cookies_get_roles: list[str] = field(default_factory=list)
    cookies_give_roles: list[str] = field(default_factory=list)


@dataclass
class ServerConfig:
    name: str | None = None
    language: str = "en"
    announcements_channel: int | None = None
    announcements_roles: list[str] = field(default_factory=list)
    starboard_channel: int | None = None
    starboard_react: str = "⭐"
    starboard_roles: list[str] = field(default_factory=list)
    starboard_add_roles: list[str] = field(default_factory=list)
    alias: bool = True
    alias_roles: list[str] = field(default_factory=list)


@dataclass
class GuildConfig:
    log: LogConfig = field(default_factory=LogConfig)
    moderation: ModerationConfig = field(default_factory=ModerationConfig)
    economy: EconomyConfig = field(default_factory=EconomyConfig)
    xp: XpConfig = field(default_factory=XpConfig)
    server: ServerConfig = field(default_factory=ServerConfig)

    @classmethod
    async def load(cls, db: Database, guild_id: int) -> GuildConfig:
        r = await get_all_config(db, guild_id)
        g = cls()
        g.log = LogConfig(
            moderation=_bool(r.get("log.moderation")),
            moderation_channel=_int(r.get("log.moderation.channel")),
            moderation_show_moderator=_bool(
                r.get("log.moderation.message.show_moderator"), True
            ),
            moderation_show_reason=_bool(
                r.get("log.moderation.message.show_reason"), True
            ),
            msg_kick=_list(
                r.get("log.moderation.message.kick"),
                ["[{infraction_id}] {user} was kicked"],
            ),
            msg_ban=_list(
                r.get("log.moderation.message.ban"),
                ["[{infraction_id}] {user} was banned"],
            ),
            msg_mute=_list(
                r.get("log.moderation.message.mute"),
                ["[{infraction_id}] {user} was muted"],
            ),
            msg_warn=_list(
                r.get("log.moderation.message.warn"),
                ["[{infraction_id}] {user} was warned"],
            ),
            msg_slowmode=_list(
                r.get("log.moderation.message.slowmode"),
                ["[{infraction_id}] {user} had slowmode applied"],
            ),
            alerts=_bool(r.get("log.alerts")),
            alerts_channel=_int(r.get("log.alerts.channel")),
            alerts_joins=_bool(r.get("log.alerts.joins"), True),
            alerts_joins_channel=_int(r.get("log.alerts.joins.channel")),
            alerts_joins_message=_str(r.get("log.alerts.joins.message")),
            alerts_leaves=_bool(r.get("log.alerts.leaves"), True),
            alerts_leaves_channel=_int(r.get("log.alerts.leaves.channel")),
            alerts_leaves_message=_str(r.get("log.alerts.leaves.message")),
            alerts_twitch=_bool(r.get("log.alerts.twitch")),
            alerts_twitch_channel=_int(r.get("log.alerts.twitch.channel")),
            alerts_twitch_message=_str(r.get("log.alerts.twitch.message")),
            alerts_youtube=_bool(r.get("log.alerts.youtube")),
            alerts_youtube_channel=_int(r.get("log.alerts.youtube.channel")),
            alerts_youtube_message=_str(r.get("log.alerts.youtube.message")),
            alerts_free_games=_bool(r.get("log.alerts.free_games")),
            alerts_free_games_channel=_int(r.get("log.alerts.free_games.channel")),
            alerts_free_games_message=_str(r.get("log.alerts.free_games.message")),
        )
        g.moderation = ModerationConfig(
            require_confirm=_bool(r.get("moderation.require_confirm"), True),
            kick_default_reason=_list(
                r.get("moderation.kick.default_reason"), ["{user} was kicked"]
            ),
            ban_default_reason=_list(
                r.get("moderation.ban.default_reason"), ["{user} was banned"]
            ),
            mute_default_reason=_list(
                r.get("moderation.mute.default_reason"), ["{user} was muted"]
            ),
            warn_default_reason=_list(
                r.get("moderation.warn.default_reason"), ["{user} was warned"]
            ),
            slowmode_default_reason=_list(
                r.get("moderation.slowmode.default_reason"),
                ["{user} had slowmode applied"],
            ),
            ban_default_duration=_str_req(
                r.get("moderation.ban.default_duration"), "forever"
            ),
            mute_default_duration=_str_req(
                r.get("moderation.mute.default_duration"), "forever"
            ),
            mod_role=_int(r.get("moderation.mod")),
            admin_role=_int(r.get("moderation.admin")),
            trial_mod_role=_int(r.get("moderation.trial_mod")),
            dangerous_users=_list(r.get("moderation.dangerous_permission")),
            automod_bypass_roles=_list(r.get("moderation.auto.bypass.role")),
            automod_bypass_permissions=_list(
                r.get("moderation.auto.bypass.permission"), ["administrator"]
            ),
            tickets_category=_int(r.get("moderation.tickets.category")),
            tickets_message=_str(r.get("moderation.tickets.message")),
            tickets_voice=_bool(r.get("moderation.tickets.voice")),
            tickets_creator_permissions=_bool(
                r.get("moderation.tickets.creator_permissions"), True
            ),
            tickets_roles=_list(r.get("moderation.tickets.role")),
            tickets_admin_role=_int(r.get("moderation.tickets.admin")),
            tickets_archive=_bool(r.get("moderation.tickets.archive")),
            tickets_archive_category=_int(r.get("moderation.tickets.archive.category")),
            tickets_archive_role=_int(r.get("moderation.tickets.archive.role")),
            tickets_archive_auto=_str(r.get("moderation.tickets.archive.auto")),
            kick_dm=_list(
                r.get("moderation.kick.message.dm"),
                ["{user}, you were kicked for: {reason}"],
            ),
            kick_channel=_list(
                r.get("moderation.kick.message.channel"), ["{user} has been kicked"]
            ),
            ban_dm=_list(
                r.get("moderation.ban.message.dm"),
                ["{user}, you were banned for: {reason}"],
            ),
            ban_channel=_list(
                r.get("moderation.ban.message.channel"), ["{user} has been banned"]
            ),
            mute_dm=_list(
                r.get("moderation.mute.message.dm"),
                ["{user}, you were muted for: {reason}"],
            ),
            mute_channel_msg=_list(
                r.get("moderation.mute.message.channel"), ["{user} has been muted"]
            ),
            warn_dm=_list(
                r.get("moderation.warn.message.dm"),
                ["{user}, you were warned for: {reason}"],
            ),
            warn_channel=_list(
                r.get("moderation.warn.message.channel"), ["{user} has been warned"]
            ),
            mute_role=_int(r.get("moderation.mute.role")),
            mute_channel=_int(r.get("moderation.mute.channel")),
        )
        g.economy = EconomyConfig(
            enabled=_bool(r.get("economy")),
            casino=_bool(r.get("economy.casino")),
            drop=_bool(r.get("economy.drop")),
            drop_channels=_list(r.get("economy.drop.channels")),
            shop=_bool(r.get("economy.shop")),
            shop_channel=_int(r.get("economy.shop.channel")),
            currency_name=_str_req(r.get("economy.currency.name"), "coins"),
            currency_symbol=_str_req(r.get("economy.currency.symbol"), "$"),
            currency_fractional=_str_req(r.get("economy.currency.fractional"), "cents"),
            pay=_bool(r.get("economy.pay"), True),
            roles=_list(r.get("economy.role")),
            permissions=_list(r.get("economy.permission"), ["send_messages"]),
            pay_roles=_list(r.get("economy.pay.role")),
            casino_roles=_list(r.get("economy.casino.role")),
            drop_roles=_list(r.get("economy.drop.role")),
            shop_roles=_list(r.get("economy.shop.role")),
        )
        g.xp = XpConfig(
            roles=_list(r.get("xp.role")),
            achievements_roles=_list(r.get("xp.achievements.role")),
            cookies_get_roles=_list(r.get("xp.cookies.get.role")),
            cookies_give_roles=_list(r.get("xp.cookies.give.role")),
        )
        g.server = ServerConfig(
            name=_str(r.get("server.name")),
            language=_str_req(r.get("server.language"), "en"),
            announcements_channel=_int(r.get("server.announcements.channel")),
            announcements_roles=_list(r.get("server.announcements.role")),
            starboard_channel=_int(r.get("starboard.channel")),
            starboard_react=_str_req(r.get("starboard.react"), "⭐"),
            starboard_roles=_list(r.get("starboard.role")),
            starboard_add_roles=_list(r.get("starboard.add.role")),
            alias=_bool(r.get("alias"), True),
            alias_roles=_list(r.get("alias.role")),
        )
        return g
