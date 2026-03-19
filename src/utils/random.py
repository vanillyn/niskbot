from __future__ import annotations

import random as _random
import secrets

_rng = _random.SystemRandom()


def coin() -> str:
    return "heads" if secrets.randbelow(2) == 0 else "tails"


def choose(options: list[str]) -> str:
    if not options:
        raise ValueError("options must be non-empty")
    return _rng.choice(options)


def random_int(low: int, high: int) -> int:
    if low > high:
        raise ValueError("low must be <= high")
    return _rng.randint(low, high)


def shuffle(items: list[str]) -> list[str]:
    copy = list(items)
    _rng.shuffle(copy)
    return copy


def weighted_choice(options: list[str], weights: list[float]) -> str:
    if len(options) != len(weights):
        raise ValueError("options and weights must have the same length")
    if not options:
        raise ValueError("options must be non-empty")
    return _rng.choices(options, weights=weights, k=1)[0]


def dice(sides: int = 6, *, count: int = 1) -> list[int]:
    if sides < 2:
        raise ValueError("sides must be >= 2")
    if count < 1:
        raise ValueError("count must be >= 1")
    return [_rng.randint(1, sides) for _ in range(count)]
