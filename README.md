# Octopus Intelligent Go Manager

A Home Assistant custom integration that **automatically sets the correct charge target** on Octopus Energy's Intelligent Go (IOG) tariff — so your EV always hits your desired state of charge by the ready time, without any manual fiddling.

---

## How it works

Octopus Intelligent Go uses a **charge target %** to tell the smart charger what to aim for by the ready time. The problem: this percentage is relative to the *registered* battery size, but charging losses (heat, AC→DC conversion) mean you need to set the target *higher* than your desired SoC to actually get there.

This integration does the maths for you:

```
gross_energy_needed = (desired_SoC% - current_SoC%) × battery_kWh ÷ (1 - loss%)
iog_target%         = ceil((current_kWh + gross_energy_needed) ÷ battery_kWh × 100)
```

Every 60 seconds it:
1. Reads the SoC sensor and plug sensor for each configured vehicle
2. Identifies which vehicle is currently plugged in (and needs charging)
3. Calculates the correct IOG target %
4. Writes it to the Octopus Energy integration's `number.octopus_energy_intelligent_charge_target` entity

---

## Prerequisites

- **[Octopus Energy integration](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy)** by BottlecapDave — must be installed and configured
- An active **Octopus Intelligent Go** tariff
- A SoC sensor for your EV (provided by your car's HA integration, e.g. Tesla, Volkswagen, Hyundai, OVMS, etc.)
- A sensor indicating whether the vehicle is plugged in / currently charging

---

## Installation

### Via HACS (recommended)

1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/your-repo/octopus-iog-manager` as an **Integration**
3. Install "Octopus Intelligent Go Manager"
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/octopus_iog_manager/` folder into your HA `config/custom_components/` directory
2. Restart Home Assistant

---

## Configuration

Go to **Settings → Devices & Services → Add Integration** and search for **Octopus IOG Manager**.

### Step 1 — Global settings

| Setting | Default | Description |
|---|---|---|
| Charging loss % | 10% | Round-trip AC charging loss. 10% is typical for a home AC charger. |
| Desired SoC at ready time | 100% | The battery % you want to reach by the IOG ready time. |

### Step 2 — Add vehicle(s)

You can add multiple EVs. For each vehicle:

| Setting | Description |
|---|---|
| Vehicle name | Friendly name (e.g. "Ioniq 5") |
| Battery capacity (kWh) | **Usable** (not gross) battery capacity. Check your manual. |
| SoC sensor | An entity with `device_class: battery` reporting 0–100% |
| Plug sensor | A `binary_sensor`, `switch`, or `input_boolean` that is `on` when plugged in |

### Multiple vehicles

If you have more than one EV sharing the same IOG charger, add them all. The integration will automatically detect which one is plugged in. If multiple are plugged in simultaneously, it will prioritise the vehicle with the **largest energy deficit**.

---

## Entities created

| Entity | Description |
|---|---|
| `sensor.iog_calculated_charge_target` | The % written to Octopus Energy — the headline sensor |
| `sensor.iog_active_vehicle` | Name of the vehicle currently being managed |
| `sensor.iog_active_vehicle_soc` | SoC % of the active vehicle |
| `sensor.iog_energy_required_gross` | Total kWh to draw from the charger (inc. losses) |
| `sensor.iog_energy_required_net` | kWh to store in the battery |
| `sensor.iog_charging_loss` | kWh lost to heat/conversion |
| `sensor.iog_manager_status` | Status string (`ok`, `no_vehicle_plugged_in`, `soc_unavailable`) |

The main target sensor also carries full diagnostic attributes:
- `active_vehicle_name`, `battery_kwh`, `current_soc_percent`, `desired_soc_percent`
- `charging_loss_percent`, `net_energy_kwh`, `gross_energy_kwh`, `loss_kwh`, `soc_delta_percent`

---

## Services

### `octopus_iog_manager.recalculate`

Force an immediate recalculation outside of the 60-second polling cycle. Useful in an automation triggered by your car connecting to the charger.

**Example automation:**

```yaml
alias: "IOG: Recalculate on plug-in"
trigger:
  - platform: state
    entity_id: binary_sensor.my_ev_charger_connected
    to: "on"
action:
  - delay: "00:00:10"  # Brief pause for SoC to update
  - service: octopus_iog_manager.recalculate
```

---

## Finding the right sensors

### SoC sensor

Look for an entity with:
- Domain: `sensor`
- Device class: `battery`
- Unit: `%`
- Provided by your car integration (Tesla, Hyundai, OVMS, BMW Connected Drive, etc.)

### Plug / connected sensor

This needs to be `on`/`true`/`yes` when the car is plugged in and `off` otherwise. Options include:

- A `binary_sensor` from your car integration (e.g. `binary_sensor.my_tesla_charging`)
- The Octopus Energy charger's own plug detection sensor
- An EVSE integration sensor
- A smart plug reporting power draw > 0 W (via a template sensor)

**Template plug sensor example** (if you only have a power sensor):
```yaml
template:
  - binary_sensor:
      - name: "EV Charger Connected"
        device_class: plug
        state: "{{ states('sensor.ev_charger_power') | float(0) > 50 }}"
```

---

## Typical battery capacities (usable kWh)

| Vehicle | Usable kWh |
|---|---|
| Tesla Model 3 Standard Range | 54 |
| Tesla Model 3 Long Range | 75 |
| Tesla Model Y Long Range | 75 |
| Hyundai Ioniq 5 77 kWh | 74 |
| Hyundai Ioniq 5 58 kWh | 54 |
| Volkswagen ID.4 77 kWh | 77 |
| Renault Zoe 52 kWh | 52 |
| Nissan Leaf 40 kWh | 36 |
| Nissan Leaf e+ 62 kWh | 59 |
| Kia EV6 77 kWh | 74 |

---

## Editing or removing vehicles

Go to **Settings → Devices & Services → Octopus IOG Manager → Configure**.

---

## Troubleshooting

**The target isn't being written**
- Check that `number.octopus_energy_intelligent_charge_target` exists in your entity registry
- Make sure the Octopus Energy integration is connected and your IOG tariff is active

**Status is `soc_unavailable`**
- The plug sensor shows the vehicle as connected, but the SoC sensor is returning `unavailable` or `unknown`
- Check the SoC entity in Developer Tools → States

**Target seems too high**
- Your charging loss % may need adjusting. Check your car's onboard data (kWh added vs drawn from grid) to measure actual losses

**Multiple vehicles — wrong one being managed**
- Only one vehicle should be plugged in at a time for simplest operation
- If both are plugged in, the one with the larger deficit is prioritised

---

## Manual SoC & plug control (no sensors required)

Both the SoC sensor and plug sensor are **optional** per vehicle. Every vehicle always gets these fallback entities:

- **`number.iog_manual_soc_<name>`** — set the current SoC by hand. Used automatically whenever no SoC sensor is configured, or when a configured sensor is `unavailable`.
- **`switch.iog_plugged_in_<name>`** — mark the vehicle as plugged in. Used whenever no plug sensor is configured. (Hidden by default when a plug sensor exists, since the sensor takes precedence.)

**Immediate calculation with manual SoC:** when a vehicle's SoC comes from manual entry, pressing the **Recalculate** button skips the stabilisation delay and writes the target immediately — there's no need to wait for a sensor to settle.

**Typical manual workflow (no car integration):**
1. Set `number.iog_manual_soc_corsa` to the car's current %
2. Turn on `switch.iog_plugged_in_corsa`
3. Press `button.iog_recalculate_corsa`
4. The target is calculated and set (or logged, in dry run) straight away

## Devices & dashboards

Each configured EV appears as its own **device** under Settings → Devices & Services → Octopus IOG Manager. Click a vehicle to see all its entities grouped together, each with the standard "add to dashboard" option — no manual dashboard YAML required.

## Resolution rules

| Input | Priority |
|---|---|
| **SoC** | Configured sensor if available → otherwise manual SoC number |
| **Plugged in** | Configured plug sensor → otherwise manual switch |
| **Timing** | Sensor SoC → stabilisation delay applies. Manual SoC → immediate on button press |
