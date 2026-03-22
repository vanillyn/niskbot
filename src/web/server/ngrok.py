from __future__ import annotations

import asyncio
import subprocess

import aiohttp

from src.utils.logger import get_logger

log = get_logger("ngrok")

_proc: subprocess.Popen[bytes] | None = None


async def start(port: int) -> str:
    global _proc
    _proc = subprocess.Popen(
        ["ngrok", "http", str(port), "--log=stdout", "--log-format=json"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    log.info("ngrok process started (pid %s)", _proc.pid)
    url = await _wait_for_url()
    log.info("ngrok tunnel ready: %s", url)
    return url


async def _wait_for_url(retries: int = 30, interval: float = 0.5) -> str:
    async with aiohttp.ClientSession() as session:
        for _ in range(retries):
            try:
                async with session.get("http://localhost:4040/api/tunnels") as resp:
                    data = await resp.json()
                    for tunnel in data.get("tunnels", []):
                        if tunnel.get("proto") == "https":
                            return str(tunnel["public_url"])
            except Exception:
                pass
            await asyncio.sleep(interval)
    raise RuntimeError("ngrok tunnel did not become available in time")


def stop() -> None:
    global _proc
    if _proc is not None:
        _proc.terminate()
        _proc = None
        log.info("ngrok process stopped")
