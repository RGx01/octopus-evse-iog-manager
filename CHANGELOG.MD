# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.2] - 2026-07-17

### Fixed
- **1.4.1 failed to set up.** That release shipped the updated `coordinator.py`
  alongside the previous `__init__.py`, which didn't pass the new `entry_id`
  argument, so setup raised
  `TypeError: OctopusIOGCoordinator.__init__() missing 1 required positional argument: 'entry_id'`
  and the integration never loaded. No functional change beyond pairing the two
  files correctly — if you are on 1.4.0, upgrade straight to 1.4.2 and skip 1.4.1.

## [1.4.1] - 2026-07-17

Reliability release: the charge target is no longer re-written after it has been
set. Restarts, upgrades, config reloads and sensor dropouts previously all caused
a spurious re-write, sometimes from stale or fabricated data.

### Fixed
- **A restart, upgrade or config reload no longer re-writes the charge target.**
  Session state was held in memory only, so any of these started again from IDLE
  and wrote the target a second time for a car that was already sorted. Per-vehicle
  session state (state, plug-detected time, last written target) is now persisted
  and restored on setup.
- **A plug sensor dropout is no longer mistaken for an unplug.** Plug state is now
  tri-state: `True`, `False`, or **unknown** when the sensor is `unavailable`,
  `unknown`, missing or unrecognised. Unknown holds the current state instead of
  resetting the session, so a blip no longer causes a re-write on recovery.
- **The charge target is never written from a fabricated SoC.** When a vehicle has
  a SoC sensor that is currently unavailable, its SoC now resolves to *unknown*
  rather than silently falling back to the manual value (which defaulted to 50%).
  Previously a dropout during the stabilisation window could write a target
  computed from that 50% — e.g. a car at 80% wanting 100% would have written 57%
  instead of 20%, scheduling roughly triple the energy. The existing
  "SoC unavailable — staying WAITING" guard could never fire; it now does.
- `last_written_target` is tracked **per vehicle** rather than as a single shared
  value.

### Internal
- **A test suite now runs on every pull request.** 56 unit tests covering the
  charging-time model, target/energy calculations, active-vehicle selection and
  the new tri-state plug resolution, alongside the existing hassfest and HACS
  checks. The tests are deliberately free of Home Assistant imports, so they need
  no pinned HA install and the suite runs in well under a second.
- `resolve_plug_state()` moved from `coordinator.py` into the pure
  `calculations.py` module so it can be unit tested without Home Assistant.

### Notes
- Upgrading to 1.4.1 starts with no saved session state, so a car that is already
  plugged in gets one final re-write on the first run. Subsequent restarts won't.
- If you unplug, drive and re-plug entirely while Home Assistant is down, the
  restored session still reads TARGET_SET and the target will be stale — press
  **Recalculate** to refresh it.

## [1.4.0] - 2026-07-16

### Fixed
- **Removing a SoC or plug sensor from a vehicle now actually works.** The
  optional sensor fields used a voluptuous `default`, which meant clearing one
  in the UI simply omitted it from the submitted data and the old value was put
  straight back — so a sensor could never be removed, and the vehicle's entities
  kept behaving as though it were still configured. They now use a suggested
  value instead, so clearing a field genuinely drops it and the vehicle's
  entities update on the next reload.

### Changed
- **"Manual SoC" renamed to "EV SoC at Plug in"** — clearer about what the value
  is actually for. The entity ID is unchanged, so existing dashboards and
  automations keep working; only the display name differs.
- **Controls that can't do anything are now disabled (hidden) rather than shown.**
  Following the existing behaviour of "Manual Plugged In" when a plug sensor is
  configured, entities made redundant by your configuration are now disabled in
  the entity registry, and re-enable automatically if your configuration changes
  to make them relevant again. Specifically:
  - **"EV SoC at Plug in"** is disabled for vehicles that have a SoC sensor —
    the sensor always wins, so manual entry had no effect.
  - **"Manual Plugged In"** is disabled when only one vehicle is configured.
    With a single vehicle there is nothing to disambiguate, so it is treated as
    always plugged in and **Recalculate becomes the trigger** for writing the
    charge target. Add a second vehicle and the switch returns.
  - **"Recalculate"** is disabled only where a plug event already drives the
    write — i.e. vehicles with a SoC sensor *and* an automatic plug trigger. It
    stays available for vehicles with no SoC sensor, and for a lone
    always-plugged vehicle (where no plug event can ever occur).

  If you have explicitly enabled or disabled one of these entities yourself,
  your choice is respected and left alone.

## [1.3.2] - 2026-07-16

### Fixed
- **Desired SoC and Manual SoC now step in 1% increments** instead of 5%, so you
  can set an exact target rather than being snapped to the nearest five.

## [1.3.1] - 2026-07-05

### Changed
- **Estimated Charging Time now displays as `Hh Mm Ss`** (e.g. "2h 8m 53s")
  instead of a decimal number of minutes. Numeric values (`total_seconds`,
  `total_minutes`, `total_hours`) remain available in the sensor's attributes
  for automations and graphs.

## [1.3.0] - 2026-07-05

> **Upgrading?** Max charger power is now a **per-vehicle** setting (it was global
> in 1.2.0). After updating, go to **Configure → Edit an existing vehicle** and set
> each vehicle's charge rate. Existing vehicles fall back to your old global value
> (or 7 kW) until re-saved.

### Changed
- **Max charger power moved from a global setting to per-vehicle.** Different cars
  charge at different rates, so the charge rate — and therefore the estimated
  charging time — is now set per vehicle. Existing configs fall back to the
  previous global value until each vehicle is re-saved.

### Fixed
- Removed a stale global charging-loss field left over from the 1.2.0 move to
  per-vehicle losses.

## [1.2.0] - 2026-07-02

> **Upgrading from 1.1.x?** The new per-vehicle options (charging loss, rate-limit
> SoC and power) won't appear on your existing vehicles automatically. After
> updating, go to **Settings → Devices & Services → Octopus EVSE IOG Manager →
> Configure → Edit an existing vehicle** and save each vehicle once to pick up the
> new fields. Until then, each vehicle uses sensible defaults (10% loss, no taper).

### Added
- **Estimated Charging Time sensor** (per vehicle) — estimates wall-clock time
  to reach the desired SoC using a two-phase model: full charger power up to the
  vehicle's rate-limit knee, then the reduced rate above it, with charging losses
  factored in. Reported in minutes, with hours and per-phase detail in attributes.
- **Per-vehicle rate-limit modelling** — each vehicle can specify the SoC at which
  it tapers (e.g. 95%) and the reduced power it limits to (e.g. 2.9 kW). A knee of
  100% (the default) means no taper and the power field is ignored.
- **Typical Max Charger Power** global setting (default 7 kW) — the charge rate
  below the knee.

### Changed
- **Charging loss is now per-vehicle** rather than a single global value, so each
  car can have its own efficiency. Existing configs fall back to the old global
  value until re-saved.

## [1.1.1] - 2026-07-01

### Fixed
- **Octopus charge target entity is now auto-discovered** by pattern
  (`number.octopus_energy_*_intelligent_charge_target`) instead of a fixed name.
  The real entity contains an account-specific segment, so the previous
  hardcoded name did not match on most setups and live mode would silently write
  nothing. Warns if more than one match is found (multiple accounts).

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

[1.4.2]: https://github.com/RGx01/octopus-evse-iog-manager/releases/tag/v1.4.2
[1.4.1]: https://github.com/RGx01/octopus-evse-iog-manager/releases/tag/v1.4.1
[1.4.0]: https://github.com/RGx01/octopus-evse-iog-manager/releases/tag/v1.4.0
[1.3.2]: https://github.com/RGx01/octopus-evse-iog-manager/releases/tag/v1.3.2
[1.3.1]: https://github.com/RGx01/octopus-evse-iog-manager/releases/tag/v1.3.1
[1.3.0]: https://github.com/RGx01/octopus-evse-iog-manager/releases/tag/v1.3.0
[1.2.0]: https://github.com/RGx01/octopus-evse-iog-manager/releases/tag/v1.2.0
[1.1.1]: https://github.com/RGx01/octopus-evse-iog-manager/releases/tag/v1.1.1
[1.1.0]: https://github.com/RGx01/octopus-evse-iog-manager/releases/tag/v1.1.0