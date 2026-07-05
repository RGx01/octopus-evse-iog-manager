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
CONF_VEHICLE_CHARGING_LOSS_PERCENT = "vehicle_charging_loss_percent"
CONF_VEHICLE_RATE_LIMIT_SOC_PERCENT = "vehicle_rate_limit_soc_percent"
CONF_VEHICLE_RATE_LIMIT_POWER_KW = "vehicle_rate_limit_power_kw"
CONF_TYPICAL_MAX_CHARGER_POWER_KW = "typical_max_charger_power_kw"

# Bottlecap Dave / Octopus Energy integration entity discovery.
# The real entity IDs contain an account-specific segment, e.g.
#   number.octopus_energy_00000000_..._intelligent_charge_target
# so we discover them by matching a prefix + suffix rather than a fixed name.
IOG_TARGET_ENTITY_PREFIX = "number.octopus_energy_"
IOG_TARGET_ENTITY_SUFFIX = "_intelligent_charge_target"

# Fallback exact name (older/simple setups without the account segment).
IOG_TARGET_SOC_ENTITY = "number.octopus_energy_intelligent_charge_target"

# Default values
DEFAULT_CHARGING_LOSS_PERCENT = 10.0
DEFAULT_DESIRED_SOC_PERCENT = 100.0
DEFAULT_MANUAL_SOC_PERCENT = 50.0
DEFAULT_DRY_RUN = True           # Safe default — calculate only, don't write
DEFAULT_PLUG_STABILISATION_DELAY = 10  # minutes
DEFAULT_REGISTERED_BATTERY_KWH = 60.0
DEFAULT_RATE_LIMIT_SOC_PERCENT = 100.0   # 100 = no taper (rate-limit power disabled)
DEFAULT_RATE_LIMIT_POWER_KW = 2.9        # only used when knee < 100
DEFAULT_TYPICAL_MAX_CHARGER_POWER_KW = 7.0

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