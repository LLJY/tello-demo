from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

DEFAULT_PIN_PEPPER = "tello-demo-real-v1"
_BLAKE2S_MAX_KEY_SIZE = 32


def utc_now() -> datetime:
    return datetime.now(UTC)


def derive_daily_pin(utc_date: date, *, pepper: str = DEFAULT_PIN_PEPPER) -> str:
    key = pepper.encode("utf-8")
    if len(key) > _BLAKE2S_MAX_KEY_SIZE:
        raise ValueError("Pepper must be 32 bytes or fewer for blake2s")

    date_token = utc_date.strftime("%d%m%Y").encode("ascii")
    digest = hashlib.blake2s(date_token, key=key, digest_size=8).digest()
    return f"{int.from_bytes(digest, 'big') % 1_000_000:06d}"


@dataclass(slots=True)
class RealModeGate:
    pepper: str = DEFAULT_PIN_PEPPER
    now_provider: Callable[[], datetime] = utc_now
    _unlocked: bool = field(default=False, init=False, repr=False)

    @property
    def unlocked(self) -> bool:
        return self._unlocked

    def expected_pin(self) -> str:
        now = self.now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now_provider must return an aware UTC datetime")
        return derive_daily_pin(now.astimezone(UTC).date(), pepper=self.pepper)

    def validate_pin(self, pin: str) -> bool:
        return pin.strip() == self.expected_pin()

    def unlock(self, pin: str) -> bool:
        if self.validate_pin(pin):
            self._unlocked = True
        return self._unlocked

    def lock(self) -> None:
        self._unlocked = False
