"""
Core calculation logic for Octopus EVSE IOG Manager.

All functions are pure — no HA dependencies — making them straightforward to unit test.
"""
from __future__ import annotations


def calculate_required_energy(
    battery_kwh: float,
    current_soc_percent: float,
    desired_soc_percent: float,
    charging_loss_percent: float,
) -> dict:
    """
    Calculate the energy involved in charging from current to desired SoC.

    net_kwh   — energy stored in the battery (DC)
    gross_kwh — energy drawn from the grid (AC, net + losses)
    loss_kwh  — energy lost to heat / conversion inefficiency

    Used for informational sensors only. Does NOT affect the IOG target %.
    """
    current_soc_percent = max(0.0, min(100.0, current_soc_percent))
    desired_soc_percent = max(0.0, min(100.0, desired_soc_percent))
    soc_delta = max(0.0, desired_soc_percent - current_soc_percent)

    net_kwh = (soc_delta / 100.0) * battery_kwh
    efficiency = 1.0 - charging_loss_percent / 100.0
    multiplier = 1.0 / efficiency if efficiency > 0 else float("inf")
    gross_kwh = net_kwh * multiplier
    loss_kwh = gross_kwh - net_kwh

    return {
        "net_kwh": round(net_kwh, 3),
        "gross_kwh": round(gross_kwh, 3),
        "loss_kwh": round(loss_kwh, 3),
        "soc_delta_percent": round(soc_delta, 1),
    }


def calculate_iog_target_percent(
    current_soc_percent: float,
    desired_soc_percent: float,
    vehicle_battery_kwh: float,
    registered_battery_kwh: float,
) -> int:
    """
    Calculate the integer target % to set on the Octopus Intelligent Go
    'charge target' number entity.

    IOG expresses its charge target as a % of the *registered* battery size
    (the battery size Octopus has on record for the IOG tariff/EVSE). When a
    vehicle with a different battery size is plugged in, the energy required
    must be re-expressed as a percentage of the registered capacity — NOT
    the plugged-in vehicle's own capacity.

    Formula (matches the proven reference logic):
        kwh_needed   = (desired% - current%) / 100 × vehicle_battery_kwh
        iog_target%  = kwh_needed / registered_battery_kwh × 100

    Note this does NOT add current_soc_percent into the result — the IOG
    target is purely "how much energy (as % of registered capacity) should
    be dispatched", not an absolute SoC on the registered battery's own scale.

    Args:
        current_soc_percent:     Current SoC of the plugged-in vehicle (0–100).
        desired_soc_percent:     Desired SoC of the plugged-in vehicle (0–100).
        vehicle_battery_kwh:     Usable battery capacity of the plugged-in vehicle.
        registered_battery_kwh:  Battery size Octopus has registered for IOG.
    """
    current_soc_percent = max(0.0, min(100.0, current_soc_percent))
    desired_soc_percent = max(0.0, min(100.0, desired_soc_percent))
    soc_delta = max(0.0, desired_soc_percent - current_soc_percent)

    kwh_needed = (soc_delta / 100.0) * vehicle_battery_kwh
    target_percent = (kwh_needed / registered_battery_kwh) * 100.0
    target_percent = max(10.0, min(100.0, target_percent))

    return int(target_percent)


def select_active_vehicle(vehicles: list[dict]) -> dict | None:
    """
    Return the plugged-in vehicle with the largest energy deficit.
    Returns None if no vehicle is plugged in with a valid SoC.
    """
    plugged_in = [
        v for v in vehicles
        if v.get("plugged_in") and v.get("current_soc") is not None
    ]

    if not plugged_in:
        return None

    if len(plugged_in) == 1:
        return plugged_in[0]

    def deficit_kwh(v: dict) -> float:
        delta = max(0.0, v["desired_soc"] - v["current_soc"])
        return (delta / 100.0) * v["battery_kwh"]

    return max(plugged_in, key=deficit_kwh)
