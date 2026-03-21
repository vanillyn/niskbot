from __future__ import annotations

from pathlib import Path

import aiosqlite

db_path = Path("data/bot.db")


class Database:
    def __init__(self) -> None:
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "database is not connected"
        return self._conn

    async def connect(self) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(db_path)
        await self._conn.execute("pragma journal_mode=wal")
        await self._conn.execute("pragma foreign_keys=on")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def create_tables(self) -> None:
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS guild_configs (
                guild_id INTEGER NOT NULL,
                key      TEXT    NOT NULL,
                value    TEXT    NOT NULL,
                PRIMARY KEY (guild_id, key)
            );
            CREATE TABLE IF NOT EXISTS infractions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     INTEGER NOT NULL,
                target_id    INTEGER NOT NULL,
                target_name  TEXT    NOT NULL,
                case_number  INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                type         TEXT    NOT NULL,
                reason       TEXT    NOT NULL,
                created_at   INTEGER NOT NULL,
                duration     INTEGER,
                UNIQUE (guild_id, target_id, case_number)
            );
            CREATE TABLE IF NOT EXISTS permission_overrides (
                guild_id INTEGER NOT NULL,
                role_id  INTEGER NOT NULL,
                node     TEXT    NOT NULL,
                PRIMARY KEY (guild_id, role_id, node)
            );
            CREATE TABLE IF NOT EXISTS resources (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                name       TEXT    NOT NULL,
                creator_id INTEGER NOT NULL,
                content    TEXT    NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE (guild_id, name)
            );
            CREATE TABLE IF NOT EXISTS containers (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     INTEGER NOT NULL,
                name         TEXT    NOT NULL,
                creator_id   INTEGER NOT NULL,
                items        TEXT    NOT NULL DEFAULT '[]',
                accent_color INTEGER,
                created_at   INTEGER NOT NULL,
                UNIQUE (guild_id, name)
            );
            CREATE TABLE IF NOT EXISTS resource_buttons (
                button_uuid  TEXT    PRIMARY KEY,
                guild_id     INTEGER NOT NULL,
                message_id   INTEGER,
                button_name  TEXT    NOT NULL,
                button_label TEXT    NOT NULL,
                button_style TEXT    NOT NULL,
                disabled     INTEGER NOT NULL DEFAULT 0,
                action       TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS twitch_stream_cache (
                guild_id     INTEGER NOT NULL,
                streamer     TEXT    NOT NULL,
                is_live      INTEGER NOT NULL DEFAULT 0,
                last_checked INTEGER NOT NULL,
                PRIMARY KEY (guild_id, streamer)
            );
        """)
        await self.conn.commit()

    async def execute(
        self,
        query: str,
        params: tuple[object, ...] = (),
    ) -> None:
        await self.conn.execute(query, params)
        await self.conn.commit()

    async def executemany(
        self,
        query: str,
        params: list[tuple[object, ...]],
    ) -> None:
        await self.conn.executemany(query, params)
        await self.conn.commit()

    async def fetchone(
        self,
        query: str,
        params: tuple[object, ...] = (),
    ) -> tuple[object, ...] | None:
        async with self.conn.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return tuple(row) if row is not None else None

    async def fetchall(
        self,
        query: str,
        params: tuple[object, ...] = (),
    ) -> list[tuple[object, ...]]:
        async with self.conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [tuple(row) for row in rows]

    async def __aenter__(self) -> Database:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
