from __future__ import annotations

from dataclasses import dataclass

from src.data.db import Database


@dataclass
class ShopItem:
    id: int
    guild_id: int
    name: str
    description: str
    price: int
    role_add: int | None
    role_remove: int | None


def _shop_row(r: tuple[object, ...]) -> ShopItem:
    return ShopItem(
        id=int(r[0]),  # type: ignore[arg-type]
        guild_id=int(r[1]),  # type: ignore[arg-type]
        name=str(r[2]),
        description=str(r[3]),
        price=int(r[4]),  # type: ignore[arg-type]
        role_add=int(r[5]) if r[5] is not None else None,  # type: ignore[arg-type]
        role_remove=int(r[6]) if r[6] is not None else None,  # type: ignore[arg-type]
    )


async def get_balance(db: Database, guild_id: int, user_id: int) -> int:
    row = await db.fetchone(
        "select balance from member_economy where guild_id = ? and user_id = ?",
        (guild_id, user_id),
    )
    return int(row[0]) if row is not None else 0  # type: ignore[arg-type]


async def set_balance(db: Database, guild_id: int, user_id: int, amount: int) -> None:
    await db.execute(
        "insert into member_economy (guild_id, user_id, balance) values (?, ?, ?)"
        " on conflict (guild_id, user_id) do update set balance = excluded.balance",
        (guild_id, user_id, max(0, amount)),
    )


async def add_balance(db: Database, guild_id: int, user_id: int, amount: int) -> int:
    current = await get_balance(db, guild_id, user_id)
    new = current + amount
    await set_balance(db, guild_id, user_id, new)
    return new


async def subtract_balance(
    db: Database, guild_id: int, user_id: int, amount: int
) -> tuple[int, bool]:
    current = await get_balance(db, guild_id, user_id)
    if current < amount:
        return current, False
    new = current - amount
    await set_balance(db, guild_id, user_id, new)
    return new, True


async def get_cookies(db: Database, guild_id: int, user_id: int) -> int:
    row = await db.fetchone(
        "select amount from member_cookies where guild_id = ? and user_id = ?",
        (guild_id, user_id),
    )
    return int(row[0]) if row is not None else 0  # type: ignore[arg-type]


async def set_cookies(db: Database, guild_id: int, user_id: int, amount: int) -> None:
    await db.execute(
        "insert into member_cookies (guild_id, user_id, amount) values (?, ?, ?)"
        " on conflict (guild_id, user_id) do update set amount = excluded.amount",
        (guild_id, user_id, max(0, amount)),
    )


async def add_cookies(db: Database, guild_id: int, user_id: int, amount: int) -> int:
    current = await get_cookies(db, guild_id, user_id)
    new = current + amount
    await set_cookies(db, guild_id, user_id, new)
    return new


async def subtract_cookies(
    db: Database, guild_id: int, user_id: int, amount: int
) -> tuple[int, bool]:
    current = await get_cookies(db, guild_id, user_id)
    if current < amount:
        return current, False
    new = current - amount
    await set_cookies(db, guild_id, user_id, new)
    return new, True


async def get_shop_items(db: Database, guild_id: int) -> list[ShopItem]:
    rows = await db.fetchall(
        "select id, guild_id, name, description, price, role_add, role_remove"
        " from shop_items where guild_id = ? order by price",
        (guild_id,),
    )
    return [_shop_row(r) for r in rows]


async def get_shop_item(db: Database, guild_id: int, name: str) -> ShopItem | None:
    row = await db.fetchone(
        "select id, guild_id, name, description, price, role_add, role_remove"
        " from shop_items where guild_id = ? and name = ?",
        (guild_id, name),
    )
    return _shop_row(row) if row is not None else None


async def upsert_shop_item(
    db: Database,
    guild_id: int,
    name: str,
    description: str,
    price: int,
    role_add: int | None,
    role_remove: int | None,
) -> None:
    await db.execute(
        "insert into shop_items (guild_id, name, description, price, role_add, role_remove)"
        " values (?, ?, ?, ?, ?, ?)"
        " on conflict (guild_id, name) do update set"
        " description = excluded.description, price = excluded.price,"
        " role_add = excluded.role_add, role_remove = excluded.role_remove",
        (guild_id, name, description, price, role_add, role_remove),
    )


async def delete_shop_item(db: Database, guild_id: int, name: str) -> bool:
    row = await db.fetchone(
        "select id from shop_items where guild_id = ? and name = ?",
        (guild_id, name),
    )
    if row is None:
        return False
    await db.execute(
        "delete from shop_items where guild_id = ? and name = ?",
        (guild_id, name),
    )
    return True
