from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tello_demo.studio.real_mode_gate import RealModeGate, derive_daily_pin


def test_daily_pin_is_deterministic_and_zero_padded() -> None:
    pin = derive_daily_pin(datetime(2026, 4, 13, tzinfo=UTC).date())

    assert pin == "308713"
    assert len(pin) == 6
    assert pin.isdigit()


def test_gate_unlocks_for_matching_pin() -> None:
    gate = RealModeGate(now_provider=lambda: datetime(2026, 4, 13, 9, 0, tzinfo=UTC))

    assert gate.unlocked is False
    assert gate.expected_pin() == "308713"
    assert gate.unlock("308713") is True
    assert gate.unlocked is True


def test_gate_rejects_wrong_pin_without_unlocking() -> None:
    gate = RealModeGate(now_provider=lambda: datetime(2026, 4, 13, 9, 0, tzinfo=UTC))

    assert gate.unlock("000000") is False
    assert gate.unlocked is False


def test_gate_requires_aware_datetime() -> None:
    gate = RealModeGate(now_provider=lambda: datetime(2026, 4, 13, 9, 0))

    with pytest.raises(ValueError, match="aware UTC datetime"):
        gate.expected_pin()
