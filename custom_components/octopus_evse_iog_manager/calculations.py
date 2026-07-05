"""
Core calculation logic for Octopus EVSE IOG Manager.

All functions are pure — no HA dependencies — making them straightforward to unit test.
"""
from __future__ import annotations


def calculate_charging_time(
    battery_kwh: float,
    current_soc_percent: float,
    desired_soc_percent: float,
    charger_power_kw: float,
    charging_loss_percent: float,
    rate_limit_soc_percent: float = 100.0,
    rate_limit_power_kw: float = 0.0,
) -> dict:
    """
    Estimate charging time using a two-phase (single-knee) model.

    Phase 1 — from current SoC up to the rate-limit knee — charges at the
              charger power.
    Phase 2 — from the knee up to the desired SoC — charges at the reduced
              rate_limit_power_kw.

    If rate_limit_soc_percent is 100 (the default), there is no knee: the whole
    charge happens at charger power and rate_limit_power_kw is ignored.

    Charging losses inflate the grid energy, so the effective energy delivered
    to the battery per hour is power × (1 − loss), which lengthens the time.

    Returns a dict with total hours, per-phase hours, and the knee used.
    All times are wall-clock hours to move charge into the battery.

    Args:
        battery_kwh:             Usable battery capacity of the vehicle.
        current_soc_percent:     Current SoC (0–100).
        desired_soc_percent:     Target SoC (0–100).
        charger_power_kw:        Charger power below the knee (kW).
        charging_loss_percent:   AC→DC / thermal losses (%).
        rate_limit_soc_percent:  SoC at which the vehicle tapers (default 100 = no taper).
        rate_limit_power_kw:     Reduced power above the knee (kW). Ignored if knee is 100.
    """
    current = max(0.0, min(100.0, current_soc_percent))
    desired = max(0.0, min(100.0, desired_soc_percent))
    knee = max(0.0, min(100.0, rate_limit_soc_percent))

    efficiency = 1.0 - charging_loss_percent / 100.0
    if efficiency <= 0:
        efficiency = 1.0  # guard against nonsensical 100% loss

    if desired <= current or battery_kwh <= 0:
        return {
            "total_hours": 0.0,
            "phase1_hours": 0.0,
            "phase2_hours": 0.0,
            "knee_soc_percent": round(knee, 1),
            "phase1_kwh": 0.0,
            "phase2_kwh": 0.0,
        }

    def phase_time(soc_from: float, soc_to: float, power_kw: float) -> tuple[float, float]:
        """Return (hours, battery_kwh) for a SoC span at a given power."""
        span = max(0.0, soc_to - soc_from)
        kwh = (span / 100.0) * battery_kwh
        if power_kw <= 0 or kwh <= 0:
            return 0.0, kwh
        # Effective delivered power into the battery after losses
        hours = kwh / (power_kw * efficiency)
        return hours, kwh

    # No taper if knee is at/above 100 or at/below current (or reduced power unset)
    taper_active = knee < 100.0 and rate_limit_power_kw > 0

    if not taper_active:
        h1, k1 = phase_time(current, desired, charger_power_kw)
        h2, k2 = 0.0, 0.0
    else:
        # Phase 1: current → min(knee, desired) at charger power
        phase1_end = min(knee, desired)
        h1, k1 = phase_time(current, phase1_end, charger_power_kw)
        # Phase 2: max(knee, current) → desired at reduced power (only if desired above knee)
        phase2_start = max(knee, current)
        h2, k2 = phase_time(phase2_start, desired, rate_limit_power_kw)

    total = h1 + h2
    return {
        "total_hours": round(total, 3),
        "phase1_hours": round(h1, 3),
        "phase2_hours": round(h2, 3),
        "knee_soc_percent": round(knee, 1),
        "phase1_kwh": round(k1, 3),
        "phase2_kwh": round(k2, 3),
    }


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