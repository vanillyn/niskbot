from __future__ import annotations

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
