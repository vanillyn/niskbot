from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Awaitable, Callable

from quart import Quart, request

from src.utils.logger import get_logger
from src.web.apis.twitch import WEBHOOK_SECRET

log = get_logger("webhook")

app = Quart(__name__)

_callbacks: dict[str, list[Callable[[str], Awaitable[None]]]] = {}


def register(broadcaster_id: str, fn: Callable[[str], Awaitable[None]]) -> None:
    _callbacks.setdefault(broadcaster_id, [])
    if fn not in _callbacks[broadcaster_id]:
        _callbacks[broadcaster_id].append(fn)


def unregister(broadcaster_id: str, fn: Callable[[str], Awaitable[None]]) -> None:
    if broadcaster_id in _callbacks:
        _callbacks[broadcaster_id] = [
            f for f in _callbacks[broadcaster_id] if f is not fn
        ]


def _verify(headers: object, body: bytes) -> bool:
    from quart.datastructures import Headers

    assert isinstance(headers, Headers)
    msg_id = headers.get("twitch-eventsub-message-id", "")
    timestamp = headers.get("twitch-eventsub-message-timestamp", "")
    signature = headers.get("twitch-eventsub-message-signature", "")
    raw = (msg_id + timestamp).encode() + body
    expected = (
        "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


@app.route("/webhook/twitch", methods=["POST"])
async def twitch_webhook() -> tuple[str, int]:
    body = await request.get_data()
    if not _verify(request.headers, body):
        log.warning("invalid twitch webhook signature")
        return "forbidden", 403

    data: dict[str, object] = json.loads(body)
    msg_type = request.headers.get("twitch-eventsub-message-type", "")

    if msg_type == "webhook_callback_verification":
        return str(data["challenge"]), 200

    if msg_type == "notification":
        sub_type = str(
            (data.get("subscription") or {}).get("type", "")  # type: ignore[union-attr]
        )
        if sub_type == "stream.online":
            event: dict[str, str] = data.get("event", {})  # type: ignore[assignment]
            broadcaster_id = event.get("broadcaster_user_id", "")
            for fn in list(_callbacks.get(broadcaster_id, [])):
                try:
                    await fn(broadcaster_id)
                except Exception as exc:
                    log.error(
                        "notification callback error for %s: %s", broadcaster_id, exc
                    )

    return "", 204


@app.route("/health", methods=["GET"])
async def health() -> tuple[str, int]:
    return "ok", 200
