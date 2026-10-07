"""Rough, honest guidance on where a link of a given length still works (mirrors src/limits.js)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Limit:
    max: float
    level: str
    label: str


LIMITS = (
    Limit(2_000, "ok", "Works almost everywhere: chat apps, email, old browsers."),
    Limit(2_900, "ok", "Works in most apps. Still fits in a QR code (binary, low error correction)."),
    Limit(8_000, "warn", "Too big for a QR code. Some chat apps and email clients may cut it off."),
    Limit(32_000, "warn", "Fine to paste in a browser. Many apps will truncate or refuse it."),
    Limit(2_000_000, "bad", "Only copy-paste between browsers will work. Expect most apps to break it."),
    Limit(math.inf, "bad", "Too large: Chrome refuses URLs over about 2 MB."),
)


def describe_length(length: int) -> Limit:
    return next(limit for limit in LIMITS if length <= limit.max)
