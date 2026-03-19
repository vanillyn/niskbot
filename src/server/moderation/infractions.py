from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from src.data.db import Database

InfractionType = Literal["warn", "mute", "kick", "ban", "slowmode"]


@dataclass
class Infraction:
    id: int
    guild_id: int
    target_id: int
    target_name: str
    case_number: int
    moderator_id: int
    type: InfractionType
    reason: str
    created_at: int
    duration: int | None

    @property
    def case_str(self) -> str:
        return f"{self.case_number:09d}"


def _row(r: tuple[object, ...]) -> Infraction:
    return Infraction(
        id=int(r[0]),  # type: ignore[arg-type]
        guild_id=int(r[1]),  # type: ignore[arg-type]
        target_id=int(r[2]),  # type: ignore[arg-type]
        target_name=str(r[3]),
        case_number=int(r[4]),  # type: ignore[arg-type]
        moderator_id=int(r[5]),  # type: ignore[arg-type]
        type=str(r[6]),  # type: ignore[arg-type]
        reason=str(r[7]),
        created_at=int(r[8]),  # type: ignore[arg-type]
        duration=int(r[9]) if r[9] is not None else None,  # type: ignore[arg-type]
    )


async def add_infraction(
    db: Database,
    guild_id: int,
    target_id: int,
    target_name: str,
    moderator_id: int,
    infraction_type: InfractionType,
    reason: str,
    duration: int | None = None,
) -> Infraction:
    count_row = await db.fetchone(
        "select count(*) from infractions where guild_id = ? and target_id = ?",
        (guild_id, target_id),
    )
    assert count_row is not None
    case_number = int(count_row[0]) + 1  # type: ignore[arg-type]
    now = int(time.time())

    await db.execute(
        "insert into infractions"
        " (guild_id, target_id, target_name, case_number, moderator_id, type, reason, created_at, duration)"
        " values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            guild_id,
            target_id,
            target_name,
            case_number,
            moderator_id,
            infraction_type,
            reason,
            now,
            duration,
        ),
    )
    row = await db.fetchone("select last_insert_rowid()")
    assert row is not None

    return Infraction(
        id=int(row[0]),  # type: ignore[arg-type]
        guild_id=guild_id,
        target_id=target_id,
        target_name=target_name,
        case_number=case_number,
        moderator_id=moderator_id,
        type=infraction_type,
        reason=reason,
        created_at=now,
        duration=duration,
    )


async def get_infractions(
    db: Database,
    guild_id: int,
    target_id: int,
) -> list[Infraction]:
    rows = await db.fetchall(
        "select id, guild_id, target_id, target_name, case_number, moderator_id, type, reason, created_at, duration"
        " from infractions where guild_id = ? and target_id = ? order by created_at desc",
        (guild_id, target_id),
    )
    return [_row(r) for r in rows]


async def get_infraction_by_case(
    db: Database,
    guild_id: int,
    target_id: int,
    case_number: int,
) -> Infraction | None:
    row = await db.fetchone(
        "select id, guild_id, target_id, target_name, case_number, moderator_id, type, reason, created_at, duration"
        " from infractions where guild_id = ? and target_id = ? and case_number = ?",
        (guild_id, target_id, case_number),
    )
    return _row(row) if row is not None else None


async def remove_infraction(
    db: Database,
    guild_id: int,
    target_id: int,
    case_number: int,
) -> bool:
    row = await db.fetchone(
        "select id from infractions where guild_id = ? and target_id = ? and case_number = ?",
        (guild_id, target_id, case_number),
    )
    if row is None:
        return False
    await db.execute("delete from infractions where id = ?", (row[0],))
    return True


async def count_infractions(
    db: Database,
    guild_id: int,
    target_id: int,
    infraction_type: InfractionType | None = None,
) -> int:
    if infraction_type is not None:
        row = await db.fetchone(
            "select count(*) from infractions where guild_id = ? and target_id = ? and type = ?",
            (guild_id, target_id, infraction_type),
        )
    else:
        row = await db.fetchone(
            "select count(*) from infractions where guild_id = ? and target_id = ?",
            (guild_id, target_id),
        )
    assert row is not None
    return int(row[0])  # type: ignore[arg-type]
