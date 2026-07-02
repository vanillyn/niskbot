from __future__ import annotations

import time

from src.data.db import Database


async def record_name(
    db: Database,
    guild_id: int,
    user_id: int,
    username: str,
    display_name: str,
) -> None:
    await db.execute(
        "insert into member_name_history (guild_id, user_id, username, display_name, recorded_at)"
        " values (?, ?, ?, ?, ?)",
        (guild_id, user_id, username, display_name, int(time.time())),
    )


async def get_name_history(
    db: Database,
    guild_id: int,
    user_id: int,
) -> list[tuple[str, str, int]]:
    rows = await db.fetchall(
        "select username, display_name, recorded_at from member_name_history"
        " where guild_id = ? and user_id = ? order by recorded_at desc limit 15",
        (guild_id, user_id),
    )
    return [(str(r[0]), str(r[1]), int(r[2])) for r in rows]  # type: ignore[arg-type]


async def record_last_message(
    db: Database,
    guild_id: int,
    user_id: int,
    channel_id: int,
    message_id: int,
) -> None:
    await db.execute(
        "insert into member_last_message (guild_id, user_id, channel_id, message_id, recorded_at)"
        " values (?, ?, ?, ?, ?)"
        " on conflict (guild_id, user_id) do update set"
        " channel_id = excluded.channel_id,"
        " message_id = excluded.message_id,"
        " recorded_at = excluded.recorded_at",
        (guild_id, user_id, channel_id, message_id, int(time.time())),
    )


async def get_last_message(
    db: Database,
    guild_id: int,
    user_id: int,
) -> tuple[int, int, int] | None:
    row = await db.fetchone(
        "select channel_id, message_id, recorded_at from member_last_message"
        " where guild_id = ? and user_id = ?",
        (guild_id, user_id),
    )
    if row is None:
        return None
    return int(row[0]), int(row[1]), int(row[2])  # type: ignore[arg-type]
