# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-07-01

First public release.

### Features
- **Automatic Intelligent Charge Target** scaled to the registered battery size,
  so the target is correct for whichever EV is plugged in:
  `iog_target% = (desired − current) / 100 × vehicle_kWh / registered_kWh × 100`.
- **Per-vehicle devices**, each with its own entities: desired SoC, manual SoC,
  manual plugged-in switch, recalculate button, and sensors for SoC, session
  state, wait timer, energy required, and the would-be charge target.
- **Would-be Charge Target sensor** showing the exact % that would be written to
  Octopus — updated live for sensor-SoC vehicles, on button press for manual-SoC.
- **Sensor or manual SoC**, and **sensor or manual plug detection** — both
  optional per vehicle.
- **One-vehicle-at-a-time enforcement**: manual plug switches behave as radio
  buttons; simultaneous sensor plug-ins resolve to the most-recently-plugged.
- **Stabilisation delay** after plug-in before reading SoC (configurable), for
  slow car integrations.
- **Dry run mode** — calculate and display everything without writing to Octopus.
- **Calculation decoupled from plug state**: informational sensors update
  continuously (or on demand for manual SoC), even when nothing is plugged in.
  The actual write to Octopus only happens when a vehicle is plugged in, the
  stabilisation delay has elapsed, and dry run is off.
- **Local brand images** (`brand/`) — the pink tentacle + Type 2 connector icon
  appears automatically on Home Assistant 2026.3+.

### Requirements
- Home Assistant 2026.3 or newer.
- The Octopus Energy integration on an active Intelligent Go tariff.

[1.1.0]: https://github.com/RGx01/octopus-evse-iog-manager/releases/tag/v1.1.0
