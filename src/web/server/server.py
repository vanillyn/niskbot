from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING

import aiohttp
import discord
from aiohttp import web

if TYPE_CHECKING:
    from src.bot import Bot

_DISCORD_API = "https://discord.com/api/v10"
_ADMIN_BIT = 0x8

_ALLOWED_GUILDS: dict[str, str | None] = {
    "1470258699665932321": None,
    "1395939916189405325": os.environ.get("OWNER_DISCORD_ID", ""),
}

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
        return bool(int(raw) & _ADMIN_BIT) or bool(guild.get("owner", False))
    except ValueError:
        return bool(guild.get("owner", False))


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

    async def _auth(request: web.Request) -> tuple[str, str] | web.Response:
        token = _extract_token(request)
        if not token:
            return web.json_response({"error": "unauthorized"}, status=401)
        session: aiohttp.ClientSession = request.app["session"]
        user = await _fetch_user(session, token)
        if not user:
            return web.json_response({"error": "unauthorized"}, status=401)
        return token, str(user.get("id", ""))

    async def _check_guild_access(
        token: str, user_id: str, guild_id_str: str, request: web.Request
    ) -> web.Response | None:
        required_owner = _ALLOWED_GUILDS.get(guild_id_str)
        if guild_id_str not in _ALLOWED_GUILDS:
            return web.json_response({"error": "forbidden"}, status=403)
        if required_owner and user_id != required_owner:
            return web.json_response({"error": "forbidden"}, status=403)
        session: aiohttp.ClientSession = request.app["session"]
        raw = await _fetch_guilds(session, token)
        if not any(str(g.get("id")) == guild_id_str and _is_admin(g) for g in raw):
            return web.json_response({"error": "forbidden"}, status=403)
        return None

    async def guilds(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        session: aiohttp.ClientSession = request.app["session"]
        raw = await _fetch_guilds(session, token)
        bot_ids = {str(g.id) for g in bot.guilds}
        out: list[dict[str, object]] = []
        for g in raw:
            gid = str(g.get("id", ""))
            if gid not in _ALLOWED_GUILDS:
                continue
            required_owner = _ALLOWED_GUILDS[gid]
            if required_owner and user_id != required_owner:
                continue
            if not _is_admin(g):
                continue
            out.append(
                {
                    "id": gid,
                    "name": str(g.get("name", "")),
                    "icon": g.get("icon"),
                    "in_server": gid in bot_ids,
                }
            )
        return web.json_response(out)

    async def get_config(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        try:
            guild_id = int(guild_id_str)
        except ValueError:
            return web.json_response({"error": "bad guild id"}, status=400)
        from src.data.config import get_all_config

        cfg = await get_all_config(bot.db, guild_id)
        return web.json_response(cfg)

    async def set_config(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
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

    async def get_channels(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        guild = bot.get_guild(int(guild_id_str))
        if guild is None:
            return web.json_response({"error": "guild not found"}, status=404)
        channels = sorted(
            [
                {
                    "id": str(ch.id),
                    "name": ch.name,
                    "category": ch.category.name if ch.category else None,
                }
                for ch in guild.channels
                if isinstance(ch, discord.TextChannel)
            ],
            key=lambda c: (c["category"] or "", c["name"]),
        )
        return web.json_response(channels)

    async def get_roles(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        guild = bot.get_guild(int(guild_id_str))
        if guild is None:
            return web.json_response({"error": "guild not found"}, status=404)
        roles = [
            {
                "id": str(r.id),
                "name": r.name,
                "color": f"#{r.color.value:06x}" if r.color.value else "#99aab5",
            }
            for r in reversed(guild.roles)
            if not r.is_default() and not r.managed
        ]
        return web.json_response(roles)

    async def list_resources(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        try:
            guild_id = int(guild_id_str)
        except ValueError:
            return web.json_response({"error": "bad guild id"}, status=400)
        rows = await bot.db.fetchall(
            "select name, content, created_at from resources where guild_id = ? order by name",
            (guild_id,),
        )
        return web.json_response(
            [
                {"name": str(r[0]), "content": str(r[1]), "created_at": int(r[2])}  # type: ignore[arg-type]
                for r in rows
            ]
        )

    async def save_resource(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        try:
            guild_id = int(guild_id_str)
            data: dict[str, object] = await request.json()
        except Exception:
            return web.json_response({"error": "bad request"}, status=400)
        name = str(data.get("name", "")).strip().lower().replace(" ", "-")
        content = str(data.get("content", "")).strip()
        if not name or not content:
            return web.json_response({"error": "name and content required"}, status=400)
        creator_id = int(user_id)
        await bot.db.execute(
            "insert into resources (guild_id, name, creator_id, content, created_at)"
            " values (?, ?, ?, ?, ?)"
            " on conflict (guild_id, name) do update set content = excluded.content",
            (guild_id, name, creator_id, content, int(time.time())),
        )
        return web.json_response({"ok": True, "name": name})

    async def delete_resource(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        try:
            guild_id = int(guild_id_str)
        except ValueError:
            return web.json_response({"error": "bad guild id"}, status=400)
        name = request.match_info["name"]
        await bot.db.execute(
            "delete from resources where guild_id = ? and name = ?",
            (guild_id, name),
        )
        return web.json_response({"ok": True})

    async def list_containers(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        try:
            guild_id = int(guild_id_str)
        except ValueError:
            return web.json_response({"error": "bad guild id"}, status=400)
        rows = await bot.db.fetchall(
            "select name, items, accent_color from containers where guild_id = ? order by name",
            (guild_id,),
        )
        return web.json_response(
            [
                {
                    "name": str(r[0]),
                    "items": json.loads(str(r[1])),
                    "accent_color": int(r[2]) if r[2] is not None else None,  # type: ignore[arg-type]
                }
                for r in rows
            ]
        )

    async def save_container(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        try:
            guild_id = int(guild_id_str)
            data: dict[str, object] = await request.json()
        except Exception:
            return web.json_response({"error": "bad request"}, status=400)
        name = str(data.get("name", "")).strip().lower().replace(" ", "-")
        if not name:
            return web.json_response({"error": "name required"}, status=400)
        items = data.get("items", [])
        accent_color = data.get("accent_color")
        creator_id = int(user_id)
        accent_int: int | None = int(accent_color) if accent_color is not None else None  # type: ignore[arg-type]
        await bot.db.execute(
            "insert into containers (guild_id, name, creator_id, items, accent_color, created_at)"
            " values (?, ?, ?, ?, ?, ?)"
            " on conflict (guild_id, name) do update set"
            " items = excluded.items, accent_color = excluded.accent_color",
            (
                guild_id,
                name,
                creator_id,
                json.dumps(items),
                accent_int,
                int(time.time()),
            ),
        )
        return web.json_response({"ok": True, "name": name})

    async def delete_container(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        try:
            guild_id = int(guild_id_str)
        except ValueError:
            return web.json_response({"error": "bad guild id"}, status=400)
        name = request.match_info["name"]
        await bot.db.execute(
            "delete from containers where guild_id = ? and name = ?",
            (guild_id, name),
        )
        return web.json_response({"ok": True})

    async def list_twitch_alerts(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        try:
            guild_id = int(guild_id_str)
        except ValueError:
            return web.json_response({"error": "bad guild id"}, status=400)
        from src.data.economy import get_streamer_alerts

        entries = await get_streamer_alerts(bot.db, guild_id, "twitch")
        return web.json_response(
            [{"streamer": s, "channel_id": str(c), "message": m} for s, c, m in entries]
        )

    async def add_twitch_alert(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        try:
            guild_id = int(guild_id_str)
            data: dict[str, object] = await request.json()
        except Exception:
            return web.json_response({"error": "bad request"}, status=400)
        streamer = str(data.get("streamer", "")).strip().lower()
        channel_id_raw = data.get("channel_id", "")
        message: str | None = str(data.get("message", "")).strip() or None
        if not streamer or not channel_id_raw:
            return web.json_response(
                {"error": "streamer and channel_id required"}, status=400
            )
        try:
            channel_id = int(str(channel_id_raw))
        except ValueError:
            return web.json_response({"error": "invalid channel_id"}, status=400)
        from src.data.economy import upsert_streamer_alert

        await upsert_streamer_alert(
            bot.db, guild_id, "twitch", streamer, channel_id, message
        )
        return web.json_response({"ok": True})

    async def remove_twitch_alert(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        try:
            guild_id = int(guild_id_str)
        except ValueError:
            return web.json_response({"error": "bad guild id"}, status=400)
        streamer = request.match_info["streamer"]
        from src.data.economy import delete_streamer_alert

        await delete_streamer_alert(bot.db, guild_id, "twitch", streamer)
        return web.json_response({"ok": True})

    async def list_youtube_alerts(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        try:
            guild_id = int(guild_id_str)
        except ValueError:
            return web.json_response({"error": "bad guild id"}, status=400)
        from src.data.economy import get_streamer_alerts

        entries = await get_streamer_alerts(bot.db, guild_id, "youtube")
        return web.json_response(
            [
                {"channel_id": s, "discord_channel_id": str(c), "message": m}
                for s, c, m in entries
            ]
        )

    async def add_youtube_alert(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        try:
            guild_id = int(guild_id_str)
            data: dict[str, object] = await request.json()
        except Exception:
            return web.json_response({"error": "bad request"}, status=400)
        yt_channel_id = str(data.get("channel_id", "")).strip()
        discord_raw = data.get("discord_channel_id", "")
        message: str | None = str(data.get("message", "")).strip() or None
        if not yt_channel_id or not discord_raw:
            return web.json_response(
                {"error": "channel_id and discord_channel_id required"}, status=400
            )
        try:
            discord_channel_id = int(str(discord_raw))
        except ValueError:
            return web.json_response(
                {"error": "invalid discord_channel_id"}, status=400
            )
        from src.data.economy import upsert_streamer_alert

        await upsert_streamer_alert(
            bot.db, guild_id, "youtube", yt_channel_id, discord_channel_id, message
        )
        return web.json_response({"ok": True})

    async def remove_youtube_alert(request: web.Request) -> web.Response:
        result = await _auth(request)
        if isinstance(result, web.Response):
            return result
        token, user_id = result
        guild_id_str = request.match_info["guild_id"]
        denied = await _check_guild_access(token, user_id, guild_id_str, request)
        if denied:
            return denied
        try:
            guild_id = int(guild_id_str)
        except ValueError:
            return web.json_response({"error": "bad guild id"}, status=400)
        yt_channel_id = request.match_info["channel_id"]
        from src.data.economy import delete_streamer_alert

        await delete_streamer_alert(bot.db, guild_id, "youtube", yt_channel_id)
        return web.json_response({"ok": True})

    app.router.add_route(
        "OPTIONS", "/api/{tail:.*}", lambda r: web.Response(status=204)
    )
    app.router.add_get("/api/guilds", guilds)
    app.router.add_get("/api/guild/{guild_id}/config", get_config)
    app.router.add_post("/api/guild/{guild_id}/config", set_config)
    app.router.add_get("/api/guild/{guild_id}/channels", get_channels)
    app.router.add_get("/api/guild/{guild_id}/roles", get_roles)
    app.router.add_get("/api/guild/{guild_id}/resources", list_resources)
    app.router.add_post("/api/guild/{guild_id}/resources", save_resource)
    app.router.add_delete("/api/guild/{guild_id}/resources/{name}", delete_resource)
    app.router.add_get("/api/guild/{guild_id}/containers", list_containers)
    app.router.add_post("/api/guild/{guild_id}/containers", save_container)
    app.router.add_delete("/api/guild/{guild_id}/containers/{name}", delete_container)
    app.router.add_get("/api/guild/{guild_id}/alerts/twitch", list_twitch_alerts)
    app.router.add_post("/api/guild/{guild_id}/alerts/twitch", add_twitch_alert)
    app.router.add_delete(
        "/api/guild/{guild_id}/alerts/twitch/{streamer}", remove_twitch_alert
    )
    app.router.add_get("/api/guild/{guild_id}/alerts/youtube", list_youtube_alerts)
    app.router.add_post("/api/guild/{guild_id}/alerts/youtube", add_youtube_alert)
    app.router.add_delete(
        "/api/guild/{guild_id}/alerts/youtube/{channel_id}", remove_youtube_alert
    )

    return app


async def start(bot: "Bot") -> web.AppRunner:
    port = int(os.environ.get("API_PORT", "8080"))
    app = make_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner
