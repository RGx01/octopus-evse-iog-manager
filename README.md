# Octopus EVSE IOG Manager

<img src="https://raw.githubusercontent.com/RGx01/octopus-evse-iog-manager/main/custom_components/octopus_evse_iog_manager/brand/icon.png" align="right" width="120" alt="Octopus EVSE IOG Manager logo">

A Home Assistant custom integration that **automatically sets the correct Intelligent Charge Target** on Octopus Energy's Intelligent Go (IOG) tariff — so whichever EV is plugged into your charger reaches your desired state of charge by the ready time, without manual fiddling.

Works with the [BottlecapDave Octopus Energy integration](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy), writing to its Intelligent Charge Target entity.

[![Validate](https://github.com/RGx01/octopus-evse-iog-manager/actions/workflows/validate.yml/badge.svg)](https://github.com/RGx01/octopus-evse-iog-manager/actions/workflows/validate.yml)

---

## What it does

Intelligent Go expresses its charge target as a percentage of the **registered** battery size (the EV registered with your EVSE when you signed up). If you have more than one EV, or a car whose battery differs from the registered one, the target percentage has to be scaled so the *energy delivered* is right.

This integration handles that scaling automatically:

```
kwh_needed  = (desired_SoC% − current_SoC%) / 100 × plugged_in_vehicle_kWh
iog_target% = kwh_needed / registered_battery_kWh × 100
```

It also estimates the gross grid energy (including charging losses) and the total charging time, so you can see how much will be drawn and how long it will take — separate from what ends up in the battery.

## Key features

- **Per-vehicle management** — each EV is its own device with its own entities and its own settings.
- **Automatic scaling** — target is correct regardless of which EV is plugged in.
- **Sensor or manual SoC** — use your car integration's SoC sensor, or enter it by hand via **EV SoC at Plug in**. Where a sensor is configured it always wins, so the manual entry is disabled for that vehicle.
- **Sensor or manual plug detection** — use a plug/charger sensor, or a manual "plugged in" switch.
- **One-at-a-time enforcement** — only one vehicle can be plugged in; manual switches behave like radio buttons, sensor conflicts resolve to most-recently-plugged. With a single vehicle configured there is nothing to disambiguate, so it is treated as always plugged in and the manual switch is hidden.
- **Estimated charging time** — per-vehicle two-phase estimate that accounts for the vehicle's charge rate, its end-of-charge taper, and charging losses.
- **Stabilisation delay** — waits (configurable) after plug-in before reading SoC, for slow car integrations.
- **Set once per session** — writes the target once, then leaves it alone until unplugged or you press recalculate.
- **Dry run mode** — calculate and display everything without writing to Octopus, to validate first.
- **Would-be target sensor** — always shows what *would* be written, updated live for sensor-SoC vehicles.

## How charging time is estimated

Each vehicle's **Estimated Charging Time** uses a two-phase model:

1. **Full power** from the current SoC up to the vehicle's rate-limit knee, at its max charger power.
2. **Reduced power** from the knee up to the desired SoC (many EVs taper near full).

Charging losses inflate the grid energy, lengthening the estimate. If a vehicle's rate-limit SoC is left at **100%** (the default), no taper is modelled and the reduced-power value is ignored.

Example — a 50 kWh car, 7 kW charger, 10% loss, tapering to 2.9 kW at 95%, charging 80% → 100%:
- 80 → 95% at 7 kW ≈ 71 min
- 95 → 100% at 2.9 kW ≈ 57 min
- **Total ≈ 2 h 8 m** (that slow final 5% is why modelling the knee matters)

## Requirements

- Home Assistant **2026.3** or newer.
- [Octopus Energy integration](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy) installed and on an active Intelligent Go tariff.
- **A single EVSE configured in the Octopus Energy integration** — see [Limitations](#limitations).
- Optionally, a per-vehicle SoC sensor and/or plug sensor (both can be manual instead).

## Installation

### Via HACS (custom repository)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=RGx01&repository=octopus-evse-iog-manager&category=integration)

1. HACS → three-dot menu → **Custom repositories**
2. Add `https://github.com/RGx01/octopus-evse-iog-manager` with category **Integration**
3. Install **Octopus EVSE IOG Manager**
4. Restart Home Assistant
5. **Settings → Devices & Services → Add Integration → Octopus EVSE IOG Manager**

### Manual

Copy `custom_components/octopus_evse_iog_manager/` into your HA `config/custom_components/` directory and restart.

## Configuration

### Global settings
- **Registered EV battery size (kWh)** — the battery Octopus has on record; the reference for scaling.
- **Plug-in stabilisation delay (minutes)** — how long to wait after plug-in before reading SoC.
- **Dry run** — calculate and display only, don't write to Octopus.

### Per vehicle
- **Name** and **usable battery capacity (kWh)**.
- **Max charger power (kW)** — the vehicle's typical charge rate (default 7 kW). Used for charging-time estimates.
- **Charging loss (%)** — round-trip loss for this vehicle (default 10%).
- **Rate-limit SoC (%)** — the SoC where the car tapers (e.g. 95%). Leave at 100% for no taper.
- **Rate-limited power (kW)** — the reduced rate above the knee (used only if the knee is below 100%).
- **SoC sensor** and **plug sensor** — both optional. Leave the SoC sensor blank to enter the vehicle's SoC by hand via its **EV SoC at Plug in** number; leave the plug sensor blank to use its Manual Plugged In switch.

### Reconfiguring / after an upgrade

To change settings or pick up new options added in an update, go to **Settings → Devices & Services → Octopus EVSE IOG Manager → Configure**, choose **Edit an existing vehicle**, and save. New per-vehicle fields default to sensible values until you set them.

## Entities (per vehicle)

Entities your configuration makes redundant are **disabled** automatically, and
re-enable themselves if the configuration changes to make them relevant again.
If you enable or disable one of them yourself, that choice is respected.

| Entity | Purpose |
|---|---|
| `number.…_desired_soc` | Target charge level you want |
| `number.…_manual_soc` | **EV SoC at Plug in** — the SoC to use for vehicles with no SoC sensor (disabled if a sensor is configured) |
| `switch.…_manual_plugged_in` | Manual plug state (disabled unless 2+ vehicles and no plug sensor) |
| `button.…_recalculate` | Recalculate and (if applicable) write the target. Disabled where a plug event already drives the write |
| `sensor.…_would_be_charge_target` | The % that would be written to Octopus |
| `sensor.…_estimated_charging_time` | Estimated time to reach the desired SoC |
| `sensor.…_soc` | Effective SoC in use |
| `sensor.…_energy_required` | Estimated gross grid energy |
| `sensor.…_session_state` | idle / waiting / target_set |
| `sensor.…_wait_timer` | Countdown during stabilisation delay |

## Limitations

**One EVSE only.** This integration supports a single EVSE (charger) configured in
the Octopus Energy integration. It discovers the Intelligent Charge Target entity by
matching `number.octopus_energy_*_intelligent_charge_target`, and expects exactly one
match. If you have more than one Octopus account or EVSE set up, several entities will
match, the integration will use the first one it finds and log a warning — which may
not be the charger you intended.

Multiple *vehicles* on that one EVSE are fully supported — that is the whole point of
the integration. It is multiple *chargers* that aren't.

## When does it write to Octopus?

The Intelligent Charge Target is written on **one transition only** — a vehicle
reaching `TARGET_SET` — which requires all of:

- the vehicle is plugged in (a lone vehicle with no plug sensor always counts as
  plugged in),
- the stabilisation delay has elapsed (skipped for manual-SoC vehicles),
- a **real** SoC reading is available,
- dry run is off.

Once set, the target is left alone for the rest of that charging session.

Session state is **persisted**, so restarts, upgrades and config reloads restore
the session rather than re-writing the target for a car that is already sorted.

Sensor dropouts are handled conservatively:

| situation | behaviour |
|---|---|
| Plug sensor `unavailable` / `unknown` | Plug state is *unknown* — the session is **held**, never reset, so there's no re-write when it recovers. |
| SoC sensor `unavailable` | SoC is *unknown* — the integration **waits** rather than writing a target from a stale or default value. |
| Genuine unplug (sensor reads `off`) | Session resets; the next plug-in starts a fresh one. |

To force a fresh write at any time, press **Recalculate**.

The would-be target, energy and charging-time sensors update regardless of all
this, so you can always see what it *would* do — pressing Recalculate updates
them even with nothing plugged in.

## Logo

The pink tentacle-with-a-Type-2-plug icon ships inside the integration at
`custom_components/octopus_evse_iog_manager/brand/` and is picked up
automatically by Home Assistant (2026.3+), appearing on the device page. The
`kraken.svg` source sits alongside the PNGs if you want to re-render or tweak it.

## Development

Unit tests cover the calculation and resolution logic and need no Home Assistant
install:

```bash
pip install -r requirements-test.txt
pytest
```

They run automatically on every pull request, alongside hassfest and HACS
validation.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

Not affiliated with or endorsed by Octopus Energy. Use at your own risk; always verify behaviour in dry run mode before relying on automated charge target changes.
