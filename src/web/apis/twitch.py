from __future__ import annotations

import os
import time

import aiohttp

_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
WEBHOOK_SECRET = os.getenv("TWITCH_WEBHOOK_SECRET", "")

_HELIX = "https://api.twitch.tv/helix"
_TOKEN_URL = "https://id.twitch.tv/oauth2/token"

_token: str = ""
_token_expires: float = 0.0


async def _ensure_token() -> str:
    global _token, _token_expires
    if _token and time.monotonic() < _token_expires - 60:
        return _token
    async with aiohttp.ClientSession() as session:
        async with session.post(
            _TOKEN_URL,
            params={
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
        ) as resp:
            data = await resp.json()
    _token = str(data["access_token"])
    _token_expires = time.monotonic() + int(data.get("expires_in", 3600))
    return _token


def _headers(token: str) -> dict[str, str]:
    return {"Client-Id": _CLIENT_ID, "Authorization": f"Bearer {token}"}


async def get_user(
    *, login: str | None = None, user_id: str | None = None
) -> dict[str, str] | None:
    token = await _ensure_token()
    params: dict[str, str] = {}
    if login:
        params["login"] = login
    if user_id:
        params["id"] = user_id
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{_HELIX}/users", params=params, headers=_headers(token)
        ) as resp:
            data = await resp.json()
    items = data.get("data", [])
    return items[0] if items else None


async def get_stream(broadcaster_id: str) -> dict[str, str] | None:
    token = await _ensure_token()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{_HELIX}/streams",
            params={"user_id": broadcaster_id},
            headers=_headers(token),
        ) as resp:
            data = await resp.json()
    items = data.get("data", [])
    return items[0] if items else None


async def get_follower_count(broadcaster_id: str) -> int:
    token = await _ensure_token()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{_HELIX}/channels/followers",
            params={"broadcaster_id": broadcaster_id},
            headers=_headers(token),
        ) as resp:
            if resp.status != 200:
                return 0
            data = await resp.json()
    return int(data.get("total", 0))


async def eventsub_subscribe(broadcaster_id: str, callback_url: str) -> str | None:
    token = await _ensure_token()
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{_HELIX}/eventsub/subscriptions",
            headers={**_headers(token), "content-type": "application/json"},
            json={
                "type": "stream.online",
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_id},
                "transport": {
                    "method": "webhook",
                    "callback": callback_url,
                    "secret": WEBHOOK_SECRET,
                },
            },
        ) as resp:
            if resp.status != 202:
                return None
            data = await resp.json()
    return str(data["data"][0]["id"])


async def eventsub_unsubscribe(subscription_id: str) -> None:
    token = await _ensure_token()
    async with aiohttp.ClientSession() as session:
        await session.delete(
            f"{_HELIX}/eventsub/subscriptions",
            params={"id": subscription_id},
            headers=_headers(token),
        )


async def eventsub_list() -> list[dict[str, object]]:
    token = await _ensure_token()
    results: list[dict[str, object]] = []
    cursor: str | None = None
    async with aiohttp.ClientSession() as session:
        while True:
            params: dict[str, str] = {"status": "enabled"}
            if cursor:
                params["after"] = cursor
            async with session.get(
                f"{_HELIX}/eventsub/subscriptions",
                params=params,
                headers=_headers(token),
            ) as resp:
                data = await resp.json()
            results.extend(data.get("data", []))
            cursor = data.get("pagination", {}).get("cursor")
            if not cursor:
                break
    return results
