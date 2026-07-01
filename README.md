# Octopus EVSE IOG Manager

<img src="logo/logo.png" align="right" width="140" alt="Octopus EVSE IOG Manager logo">

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

It also estimates the gross grid energy (including charging losses) so you can see how much will actually be drawn, separate from what ends up in the battery.

## Key features

- **Per-vehicle management** — each EV is its own device with its own entities.
- **Automatic scaling** — target is correct regardless of which EV is plugged in.
- **Sensor or manual SoC** — use your car integration's SoC sensor, or enter it by hand.
- **Sensor or manual plug detection** — use a plug/charger sensor, or a manual "plugged in" switch.
- **One-at-a-time enforcement** — only one vehicle can be plugged in; manual switches behave like radio buttons, sensor conflicts resolve to most-recently-plugged.
- **Stabilisation delay** — waits (configurable) after plug-in before reading SoC, for slow car integrations.
- **Set once per session** — writes the target once, then leaves it alone until unplugged or you press recalculate.
- **Dry run mode** — calculate and display everything without writing to Octopus, to validate first.
- **Would-be target sensor** — always shows what *would* be written, updated live for sensor-SoC vehicles.

## Requirements

- Home Assistant **2026.3** or newer.
- [Octopus Energy integration](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy) installed and on an active Intelligent Go tariff.
- Optionally, a per-vehicle SoC sensor and/or plug sensor (both can be manual instead).

## Installation

### Via HACS (custom repository)

1. HACS → three-dot menu → **Custom repositories**
2. Add `https://github.com/RGx01/octopus-evse-iog-manager` with category **Integration**
3. Install **Octopus EVSE IOG Manager**
4. Restart Home Assistant
5. **Settings → Devices & Services → Add Integration → Octopus EVSE IOG Manager**

### Manual

Copy `custom_components/octopus_evse_iog_manager/` into your HA `config/custom_components/` directory and restart.

## Configuration

**Global settings:** registered EV battery size (kWh), charging loss %, plug-in stabilisation delay (minutes), and dry run toggle.

**Per vehicle:** name, usable battery capacity (kWh), optional SoC sensor, optional plug sensor.

Both sensors are optional — leave them blank to control that vehicle manually via its Manual SoC number and Manual Plugged In switch.

## Entities (per vehicle)

| Entity | Purpose |
|---|---|
| `number.…_desired_soc` | Target charge level you want |
| `number.…_manual_soc` | Manual SoC entry / override |
| `switch.…_manual_plugged_in` | Manual plug state (when no plug sensor) |
| `button.…_recalculate` | Recalculate and (if applicable) write the target |
| `sensor.…_would_be_charge_target` | The % that would be written to Octopus |
| `sensor.…_soc` | Effective SoC in use |
| `sensor.…_energy_required` | Estimated gross grid energy |
| `sensor.…_session_state` | idle / waiting / target_set |
| `sensor.…_wait_timer` | Countdown during stabilisation delay |

## When does it write to Octopus?

The actual Intelligent Charge Target is written **only** when all of these hold:
- a vehicle is plugged in,
- the stabilisation delay has elapsed (skipped for manual SoC),
- dry run is off.

The would-be target and energy sensors update regardless, so you can see what it *would* do at any time — pressing Recalculate updates them even with nothing plugged in.

## Logo

The pink tentacle-with-a-Type-2-plug icon ships inside the integration at
`custom_components/octopus_evse_iog_manager/brand/` and is picked up
automatically by Home Assistant (2026.3+), appearing on the HACS card and the
device page. The `kraken.svg` source sits alongside the PNGs if you want to
re-render or tweak it.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

Not affiliated with or endorsed by Octopus Energy. Use at your own risk; always verify behaviour in dry run mode before relying on automated charge target changes.
