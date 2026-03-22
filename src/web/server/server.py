from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import aiohttp
from aiohttp import web

if TYPE_CHECKING:
    from src.bot import Bot

_DISCORD_API = "https://discord.com/api/v10"
_ADMIN_BIT = 0x8

_user_cache: dict[str, tuple[dict[str, object], float]] = {}
_guild_cache: dict[str, tuple[list[dict[str, object]], float]] = {}
_CACHE_TTL = 180.0


async def _fetch_user(
    session: aiohttp.ClientSession, token: str
) -> dict[str, object] | None:
    entry = _user_cache.get(token)
    if entry and time.monotonic() < entry[1]:
        return entry[0]
    async with session.get(
        f"{_DISCORD_API}/users/@me",
        headers={"authorization": f"Bearer {token}"},
    ) as resp:
        if resp.status != 200:
            return None
        data: dict[str, object] = await resp.json()
    _user_cache[token] = (data, time.monotonic() + _CACHE_TTL)
    return data


async def _fetch_guilds(
    session: aiohttp.ClientSession, token: str
) -> list[dict[str, object]]:
    entry = _guild_cache.get(token)
    if entry and time.monotonic() < entry[1]:
        return entry[0]
    async with session.get(
        f"{_DISCORD_API}/users/@me/guilds",
        headers={"authorization": f"Bearer {token}"},
    ) as resp:
        if resp.status != 200:
            return []
        data: list[dict[str, object]] = await resp.json()
    _guild_cache[token] = (data, time.monotonic() + _CACHE_TTL)
    return data


def _is_admin(guild: dict[str, object]) -> bool:
    raw = str(guild.get("permissions", "0"))
    try:
        perms = int(raw)
    except ValueError:
        perms = 0
    return bool(perms & _ADMIN_BIT) or bool(guild.get("owner", False))


def _extract_token(request: web.Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    return auth[7:].strip() or None


def _cors(origin: str) -> dict[str, str]:
    return {
        "access-control-allow-origin": origin,
        "access-control-allow-headers": "authorization, content-type",
        "access-control-allow-methods": "GET, POST, DELETE, OPTIONS",
        "access-control-max-age": "86400",
    }


def make_app(bot: "Bot") -> web.Application:
    origin = os.environ.get("DASHBOARD_ORIGIN", "*")
    app = web.Application()
    app["bot"] = bot

    async def on_startup(a: web.Application) -> None:
        a["session"] = aiohttp.ClientSession()

    async def on_cleanup(a: web.Application) -> None:
        s: aiohttp.ClientSession | None = a.get("session")
        if s and not s.closed:
            await s.close()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    @web.middleware
    async def cors_middleware(
        request: web.Request, handler: web.Handler
    ) -> web.StreamResponse:
        if request.method == "OPTIONS":
            return web.Response(headers=_cors(origin), status=204)
        resp = await handler(request)
        for k, v in _cors(origin).items():
            resp.headers[k] = v
        return resp

    app.middlewares.append(cors_middleware)

    async def guilds(request: web.Request) -> web.Response:
        token = _extract_token(request)
        if not token:
            return web.json_response({"error": "unauthorized"}, status=401)
        session: aiohttp.ClientSession = request.app["session"]
        raw = await _fetch_guilds(session, token)
        bot_ids = {str(g.id) for g in bot.guilds}
        result = [
            {
                "id": str(g.get("id", "")),
                "name": str(g.get("name", "")),
                "icon": g.get("icon"),
                "in_server": str(g.get("id", "")) in bot_ids,
            }
            for g in raw
            if _is_admin(g)
        ]
        return web.json_response(result)

    async def get_config(request: web.Request) -> web.Response:
        token = _extract_token(request)
        if not token:
            return web.json_response({"error": "unauthorized"}, status=401)
        guild_id_str = request.match_info["guild_id"]
        session: aiohttp.ClientSession = request.app["session"]
        raw = await _fetch_guilds(session, token)
        if not any(str(g.get("id")) == guild_id_str and _is_admin(g) for g in raw):
            return web.json_response({"error": "forbidden"}, status=403)
        try:
            guild_id = int(guild_id_str)
        except ValueError:
            return web.json_response({"error": "bad guild id"}, status=400)
        from src.data.config import get_all_config

        cfg = await get_all_config(bot.db, guild_id)
        return web.json_response(cfg)

    async def set_config(request: web.Request) -> web.Response:
        token = _extract_token(request)
        if not token:
            return web.json_response({"error": "unauthorized"}, status=401)
        guild_id_str = request.match_info["guild_id"]
        session: aiohttp.ClientSession = request.app["session"]
        raw = await _fetch_guilds(session, token)
        if not any(str(g.get("id")) == guild_id_str and _is_admin(g) for g in raw):
            return web.json_response({"error": "forbidden"}, status=403)
        try:
            guild_id = int(guild_id_str)
            data: dict[str, str | None] = await request.json()
        except Exception:
            return web.json_response({"error": "bad request"}, status=400)
        from src.data.config import delete_config, set_config

        for key, value in data.items():
            if not value:
                await delete_config(bot.db, guild_id, key)
            else:
                await set_config(bot.db, guild_id, key, str(value))
        return web.json_response({"ok": True})

    app.router.add_route(
        "OPTIONS", "/api/{tail:.*}", lambda r: web.Response(status=204)
    )
    app.router.add_get("/api/guilds", guilds)
    app.router.add_get("/api/guild/{guild_id}/config", get_config)
    app.router.add_post("/api/guild/{guild_id}/config", set_config)

    return app


async def start(bot: "Bot") -> web.AppRunner:
    port = int(os.environ.get("API_PORT", "8080"))
    app = make_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner
