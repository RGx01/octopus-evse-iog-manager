"""
Static checks on sensor device_class / state_class pairings.

Home Assistant rejects certain combinations at runtime and logs an error against
the integration. Issue #16 was exactly this: IOGEnergyRequiredSensor declared
device_class 'energy' with state_class 'measurement', which HA refuses because
the energy class is meant for meters that accumulate:

    Entity sensor.iog_my_ev_energy_required is using state class 'measurement'
    which is impossible considering device class ('energy') it is using;
    expected None or one of 'total_increasing', 'total'

Nothing crashes — the sensor just logs an error and is excluded from statistics
— so this is invisible to any test that doesn't inspect the declarations. Read
straight from the AST, so no Home Assistant install is needed.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SENSOR_FILE = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "octopus_evse_iog_manager"
    / "sensor.py"
)

# State classes Home Assistant permits for each device class this integration
# uses. Only classes we actually declare are listed — this is a guard against
# our own regressions, not an attempt to mirror all of HA's rules.
#
# ENERGY is the interesting one: it is reserved for accumulating meters, so
# MEASUREMENT is invalid however natural it looks for an estimate.
_ALLOWED: dict[str, set[str | None]] = {
    "ENERGY": {None, "TOTAL", "TOTAL_INCREASING"},
    "BATTERY": {None, "MEASUREMENT"},
    "DURATION": {None, "MEASUREMENT", "TOTAL", "TOTAL_INCREASING"},
    "POWER": {None, "MEASUREMENT"},
}


def _sensor_classes() -> dict[str, dict[str, str | None]]:
    """Map each sensor class to its declared device_class / state_class."""
    tree = ast.parse(_SENSOR_FILE.read_text(), filename=str(_SENSOR_FILE))
    out: dict[str, dict[str, str | None]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        declared: dict[str, str | None] = {"device_class": None, "state_class": None}
        found = False
        for item in node.body:
            if not isinstance(item, ast.Assign):
                continue
            for target in item.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "_attr_device_class":
                    declared["device_class"] = ast.unparse(item.value).split(".")[-1]
                    found = True
                elif target.id == "_attr_state_class":
                    declared["state_class"] = ast.unparse(item.value).split(".")[-1]
                    found = True
        if found:
            out[node.name] = declared
    return out


def test_sensor_file_is_parseable():
    assert _sensor_classes(), "no sensor classes with device/state class found"


@pytest.mark.parametrize("class_name", sorted(_sensor_classes()))
def test_device_class_and_state_class_are_compatible(class_name):
    declared = _sensor_classes()[class_name]
    device_class = declared["device_class"]
    state_class = declared["state_class"]

    if device_class is None:
        # No device class — any state class is acceptable.
        return

    allowed = _ALLOWED.get(device_class)
    if allowed is None:
        pytest.skip(f"no rule recorded for device class {device_class}")

    assert state_class in allowed, (
        f"{class_name} declares device_class '{device_class}' with state_class "
        f"'{state_class}', which Home Assistant rejects. Allowed: "
        f"{sorted(str(a) for a in allowed)}. This is the issue #16 bug."
    )


def test_energy_sensors_never_use_measurement():
    """
    The specific regression from issue #16, called out explicitly.

    An energy estimate that goes up and down is not a meter. If a state class is
    ever wanted here, the sensor needs to stop claiming device_class 'energy'.
    """
    offenders = [
        name
        for name, d in _sensor_classes().items()
        if d["device_class"] == "ENERGY" and d["state_class"] == "MEASUREMENT"
    ]
    assert not offenders, (
        "device_class 'energy' with state_class 'measurement' is rejected by "
        f"Home Assistant: {', '.join(offenders)}"
    )