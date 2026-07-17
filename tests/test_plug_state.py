"""
Tests for tri-state plug resolution.

The distinction these protect is subtle but important: a plug sensor that is
`unavailable` must resolve to None (unknown), NOT False (unplugged). Treating a
dropout as an unplug resets the charging session, and the session then re-runs
and re-writes the Octopus charge target when the sensor recovers — potentially
mid-charge, from a different SoC.
"""
from __future__ import annotations

import pytest

from conftest import calculations

resolve_plug_state = calculations.resolve_plug_state


class TestPluggedIn:
    @pytest.mark.parametrize(
        "state",
        ["on", "true", "yes", "1", "home", "connected", "charging", "plugged_in"],
    )
    def test_truthy_states(self, state):
        assert resolve_plug_state(state) is True

    @pytest.mark.parametrize("state", ["ON", "On", "Connected", "CHARGING"])
    def test_truthy_is_case_insensitive(self, state):
        assert resolve_plug_state(state) is True

    def test_surrounding_whitespace_tolerated(self):
        assert resolve_plug_state("  on  ") is True


class TestUnplugged:
    @pytest.mark.parametrize(
        "state",
        ["off", "false", "no", "0", "away", "disconnected", "not_connected", "unplugged"],
    )
    def test_falsy_states(self, state):
        assert resolve_plug_state(state) is False

    @pytest.mark.parametrize("state", ["OFF", "Off", "Disconnected"])
    def test_falsy_is_case_insensitive(self, state):
        assert resolve_plug_state(state) is False


class TestUnknown:
    """The regression guard for the 1.4.1 spurious re-write bug."""

    @pytest.mark.parametrize("state", ["unavailable", "unknown", "", "   "])
    def test_dropout_states_are_unknown_not_unplugged(self, state):
        result = resolve_plug_state(state)
        assert result is None, f"{state!r} must be unknown, not {result!r}"

    def test_missing_entity_is_unknown(self):
        # _get_state returns None when the entity doesn't exist
        assert resolve_plug_state(None) is None

    def test_unrecognised_state_is_unknown(self):
        # Fail safe: never guess that an unfamiliar state means unplugged
        assert resolve_plug_state("some_new_state") is None

    def test_unavailable_is_not_false(self):
        # Explicit: `is None` and `is False` are different outcomes, and a plain
        # truthiness check would conflate them.
        assert resolve_plug_state("unavailable") is not False
        assert resolve_plug_state("off") is False


class TestTriStateIsExhaustive:
    def test_only_ever_returns_true_false_or_none(self):
        samples = [
            "on", "off", "unavailable", "unknown", None, "", "charging",
            "disconnected", "nonsense", "0", "1",
        ]
        for s in samples:
            assert resolve_plug_state(s) in (True, False, None)

    def test_truthy_and_falsy_sets_do_not_overlap(self):
        overlap = calculations.PLUG_TRUTHY & calculations.PLUG_FALSY
        assert not overlap, f"states classified as both: {overlap}"