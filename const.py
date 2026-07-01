"""Constants for the Octopus EVSE IOG Manager integration."""

DOMAIN = "octopus_evse_iog_manager"

# Configuration keys — global
CONF_CHARGING_LOSS_PERCENT = "charging_loss_percent"
CONF_DRY_RUN = "dry_run"
CONF_PLUG_STABILISATION_DELAY = "plug_stabilisation_delay"
CONF_REGISTERED_BATTERY_KWH = "registered_battery_kwh"

# Configuration keys — per vehicle
CONF_VEHICLES = "vehicles"
CONF_VEHICLE_NAME = "vehicle_name"
CONF_VEHICLE_BATTERY_KWH = "vehicle_battery_kwh"
CONF_VEHICLE_SOC_SENSOR = "vehicle_soc_sensor"
CONF_VEHICLE_PLUG_SENSOR = "vehicle_plug_sensor"

# Bottlecap Dave / Octopus Energy integration entity IDs
IOG_TARGET_SOC_ENTITY = "number.octopus_energy_intelligent_charge_target"
IOG_READY_TIME_ENTITY = "sensor.octopus_energy_intelligent_ready_time"
IOG_PLANNED_DISPATCHES_ENTITY = "sensor.octopus_energy_intelligent_planned_dispatches"
IOG_SMART_CHARGE_ENTITY = "switch.octopus_energy_intelligent_smart_charge"

# Default values
DEFAULT_CHARGING_LOSS_PERCENT = 10.0
DEFAULT_DESIRED_SOC_PERCENT = 100.0
DEFAULT_MANUAL_SOC_PERCENT = 50.0
DEFAULT_DRY_RUN = True           # Safe default — calculate only, don't write
DEFAULT_PLUG_STABILISATION_DELAY = 10  # minutes
DEFAULT_REGISTERED_BATTERY_KWH = 60.0

# Polling interval (seconds)
SCAN_INTERVAL_SECONDS = 30

# Coordinator name
COORDINATOR_NAME = "Octopus EVSE IOG Manager"

# Services
SERVICE_RECALCULATE = "recalculate"

# Charge session states
STATE_IDLE = "idle"
STATE_WAITING = "waiting"
STATE_TARGET_SET = "target_set"

# Dispatcher signal — fired when manual plug state changes so switch
# entities can refresh their UI (used for one-at-a-time enforcement)
SIGNAL_MANUAL_PLUG_UPDATED = f"{DOMAIN}_manual_plug_updated"

# Storage key for persisting desired SoC values across restarts
STORAGE_KEY = f"{DOMAIN}.desired_soc"
STORAGE_VERSION = 1
