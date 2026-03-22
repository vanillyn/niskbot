from __future__ import annotations

import aiohttp

_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"


class YouTubeClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def get_live_stream(self, channel_id: str) -> dict[str, object] | None:
        session = self._get_session()
        async with session.get(
            _SEARCH_URL,
            params={
                "part": "id,snippet",
                "channelId": channel_id,
                "eventType": "live",
                "type": "video",
                "key": self._api_key,
            },
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        items: list[dict[str, object]] = data.get("items", [])
        if not items:
            return None
        item = items[0]
        snippet: dict[str, object] = item.get("snippet", {})  # type: ignore[assignment]
        video_id_obj: dict[str, object] = item.get("id", {})  # type: ignore[assignment]
        video_id = str(video_id_obj.get("videoId", ""))
        return {
            "title": str(snippet.get("title", "")),
            "channel_title": str(snippet.get("channelTitle", "")),
            "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
            "channel_id": channel_id,
        }

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
