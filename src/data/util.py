from src.data.db import Database

_CONFIGS: dict[str, list[tuple[str, str, str, str | None]]] = {
    "server": [
        ("server.name", "server name", "text", None),
        ("server.language", "language", "language code — en, fr, de...", "en"),
        ("server.announcements.channel", "announcements channel", "channel id", None),
        (
            "server.announcements.role",
            "announcement ping roles",
            "comma-separated role ids",
            None,
        ),
        ("starboard.channel", "starboard channel", "channel id", None),
        (
            "starboard.react",
            "starboard emoji",
            "emoji char or custom emoji name",
            "star",
        ),
        ("starboard.role", "roles on starboard", "comma-separated role ids", None),
        (
            "starboard.add.role",
            "roles that add to starboard",
            "comma-separated role ids",
            None,
        ),
        ("alias", "allow aliases", "true or false", "true"),
        ("alias.role", "alias manager roles", "comma-separated role ids", None),
        ("server.alias.prefix", "alias prefix", "e.g. ! or .", "!"),
    ],
    "moderation": [
        ("moderation.require_confirm", "require confirmation", "true or false", "true"),
        ("moderation.mod", "moderator role", "role id", None),
        ("moderation.admin", "admin role", "role id", None),
        ("moderation.trial_mod", "trial mod role", "role id", None),
        (
            "moderation.dangerous_permission",
            "bypass-all users",
            "comma-separated user ids",
            None,
        ),
        (
            "moderation.kick.default_reason",
            "kick default reason",
            "text",
            "{user} was kicked",
        ),
        (
            "moderation.ban.default_reason",
            "ban default reason",
            "text",
            "{user} was banned",
        ),
        (
            "moderation.mute.default_reason",
            "mute default reason",
            "text",
            "{user} was muted",
        ),
        (
            "moderation.warn.default_reason",
            "warn default reason",
            "text",
            "{user} was warned",
        ),
        (
            "moderation.ban.default_duration",
            "default ban length",
            "e.g. 7d, 1h, forever",
            "forever",
        ),
        (
            "moderation.mute.default_duration",
            "default mute length",
            "e.g. 7d, 1h, forever",
            "forever",
        ),
        (
            "moderation.auto.bypass.role",
            "automod bypass roles",
            "comma-separated role ids",
            None,
        ),
        (
            "moderation.auto.bypass.permission",
            "automod bypass perms",
            "comma-separated permissions",
            "administrator",
        ),
    ],
    "tickets": [
        (
            "moderation.tickets.category",
            "tickets category",
            "category channel id",
            None,
        ),
        ("moderation.tickets.message", "ticket open message", "text", None),
        ("moderation.tickets.voice", "allow voice tickets", "true or false", "false"),
        (
            "moderation.tickets.creator_permissions",
            "creator can manage",
            "true or false",
            "true",
        ),
        (
            "moderation.tickets.role",
            "who can open tickets",
            "comma-separated role ids",
            None,
        ),
        ("moderation.tickets.admin", "ticket admin role", "role id", None),
        ("moderation.tickets.archive", "enable archival", "true or false", "false"),
        (
            "moderation.tickets.archive.category",
            "archive category",
            "category channel id",
            None,
        ),
        ("moderation.tickets.archive.role", "who can archive", "role id", None),
        ("moderation.tickets.archive.auto", "auto-archive after", "e.g. 24h, 7d", None),
        ("moderation.mute.role", "mute role", "role id", None),
        ("moderation.mute.channel", "mute channel", "channel id", None),
    ],
    "logging": [
        ("log.moderation", "log mod actions", "true or false", "false"),
        ("log.moderation.channel", "mod log channel", "channel id", None),
        (
            "log.moderation.message.show_moderator",
            "show moderator in logs",
            "true or false",
            "true",
        ),
        (
            "log.moderation.message.show_reason",
            "show reason in logs",
            "true or false",
            "true",
        ),
        (
            "log.moderation.message.kick",
            "kick log message",
            "text — {user}, {reason}, {infraction_id}",
            "[{infraction_id}] {user} was kicked",
        ),
        (
            "log.moderation.message.ban",
            "ban log message",
            "text — {user}, {reason}, {infraction_id}",
            "[{infraction_id}] {user} was banned",
        ),
        (
            "log.moderation.message.mute",
            "mute log message",
            "text — {user}, {reason}, {infraction_id}",
            "[{infraction_id}] {user} was muted",
        ),
        (
            "log.moderation.message.warn",
            "warn log message",
            "text — {user}, {reason}, {infraction_id}",
            "[{infraction_id}] {user} was warned",
        ),
        (
            "log.moderation.message.slowmode",
            "slowmode log message",
            "text — {user}, {reason}, {infraction_id}",
            "[{infraction_id}] slowmode set by {user}",
        ),
    ],
    "alerts": [
        ("log.alerts", "log server events", "true or false", "false"),
        ("log.alerts.channel", "default alerts channel", "channel id", None),
        ("log.alerts.joins", "log member joins", "true or false", "true"),
        ("log.alerts.joins.channel", "join alert channel", "channel id", None),
        ("log.alerts.joins.message", "join message", "text — {user}, {server}", None),
        ("log.alerts.leaves", "log member leaves", "true or false", "true"),
        ("log.alerts.leaves.channel", "leave alert channel", "channel id", None),
        ("log.alerts.leaves.message", "leave message", "text — {user}, {server}", None),
        ("log.alerts.twitch", "enable twitch alerts", "true or false", "false"),
        ("log.alerts.youtube", "enable youtube alerts", "true or false", "false"),
        ("log.alerts.free_games", "free game alerts", "true or false", "false"),
        ("log.alerts.free_games.channel", "free games channel", "channel id", None),
        ("log.alerts.free_games.message", "free games message", "text", None),
    ],
}

_CONFIGS_FLAT: dict[str, tuple[str, str, str | None]] = {
    key: (label, hint, default)
    for entries in _CONFIGS.values()
    for key, label, hint, default in entries
}

async def get_streamer_alerts(
    db: Database, guild_id: int, platform: str
) -> list[tuple[str, int, str | None]]:
    rows = await db.fetchall(
        "select streamer, channel_id, message from streamer_alerts"
        " where guild_id = ? and platform = ?",
        (guild_id, platform),
    )
    return [
        (str(r[0]), int(r[1]), str(r[2]) if r[2] is not None else None)  # type: ignore[arg-type]
        for r in rows
    ]


async def upsert_streamer_alert(
    db: Database,
    guild_id: int,
    platform: str,
    streamer: str,
    channel_id: int,
    message: str | None,
) -> None:
    await db.execute(
        "insert into streamer_alerts (guild_id, platform, streamer, channel_id, message)"
        " values (?, ?, ?, ?, ?)"
        " on conflict (guild_id, platform, streamer) do update set"
        " channel_id = excluded.channel_id, message = excluded.message",
        (guild_id, platform, streamer, channel_id, message),
    )


async def delete_streamer_alert(
    db: Database, guild_id: int, platform: str, streamer: str
) -> bool:
    row = await db.fetchone(
        "select 1 from streamer_alerts where guild_id = ? and platform = ? and streamer = ?",
        (guild_id, platform, streamer),
    )
    if row is None:
        return False
    await db.execute(
        "delete from streamer_alerts where guild_id = ? and platform = ? and streamer = ?",
        (guild_id, platform, streamer),
    )
    return True


async def get_stream_cache(
    db: Database, guild_id: int, platform: str, streamer: str
) -> bool:
    row = await db.fetchone(
        "select is_live from stream_live_cache"
        " where guild_id = ? and platform = ? and streamer = ?",
        (guild_id, platform, streamer),
    )
    return bool(int(row[0])) if row is not None else False  # type: ignore[arg-type]


async def set_stream_cache(
    db: Database,
    guild_id: int,
    platform: str,
    streamer: str,
    is_live: bool,
    last_checked: int,
) -> None:
    await db.execute(
        "insert into stream_live_cache (guild_id, platform, streamer, is_live, last_checked)"
        " values (?, ?, ?, ?, ?)"
        " on conflict (guild_id, platform, streamer) do update set"
        " is_live = excluded.is_live, last_checked = excluded.last_checked",
        (guild_id, platform, streamer, int(is_live), last_checked),
    )
