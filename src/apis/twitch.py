from __future__ import annotations

import time

import aiohttp

_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_STREAMS_URL = "https://api.twitch.tv/helix/streams"


class TwitchClient:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expires: float = 0.0
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        session = self._get_session()
        async with session.post(
            _TOKEN_URL,
            params={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
            },
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        self._token = str(data["access_token"])
        self._token_expires = time.time() + int(data.get("expires_in", 3600))
        return self._token

    async def get_stream(self, user_login: str) -> dict[str, object] | None:
        token = await self._ensure_token()
        session = self._get_session()
        async with session.get(
            _STREAMS_URL,
            params={"user_login": user_login},
            headers={
                "Client-ID": self._client_id,
                "Authorization": f"Bearer {token}",
            },
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        streams: list[dict[str, object]] = data.get("data", [])
        return streams[0] if streams else None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
