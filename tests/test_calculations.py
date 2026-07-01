"""
Unit tests for octopus_evse_iog_manager calculations.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom_components.octopus_evse_iog_manager.calculations import (
    calculate_iog_target_percent,
    calculate_required_energy,
    select_active_vehicle,
)


class TestCalculateRequiredEnergy:
    def test_full_charge_no_losses(self):
        result = calculate_required_energy(100, 0, 100, 0)
        assert result["net_kwh"] == 100.0
        assert result["gross_kwh"] == 100.0

    def test_full_charge_10pct_losses(self):
        result = calculate_required_energy(100, 0, 100, 10)
        assert result["net_kwh"] == 100.0
        assert abs(result["gross_kwh"] - 111.111) < 0.01

    def test_already_at_target(self):
        result = calculate_required_energy(77, 80, 80, 10)
        assert result["net_kwh"] == 0.0

    def test_partial_charge(self):
        result = calculate_required_energy(60, 50, 80, 10)
        assert result["net_kwh"] == 18.0
        assert abs(result["gross_kwh"] - 20.0) < 0.01


class TestCalculateIOGTargetPercent:
    """
    Formula under test (matches the proven reference Jinja template):
        kwh_needed  = (desired% - current%) / 100 × vehicle_battery_kwh
        iog_target% = kwh_needed / registered_battery_kwh × 100
    Truncated to int (not rounded), clamped to [10, 100].
    """

    def test_same_vehicle_as_registered_full_charge(self):
        # Ariya is both the plugged-in vehicle and the registered vehicle
        target = calculate_iog_target_percent(
            current_soc_percent=0,
            desired_soc_percent=100,
            vehicle_battery_kwh=87,
            registered_battery_kwh=87,
        )
        assert target == 100

    def test_ariya_65_to_100_registered_87(self):
        # Confirmed real-world scenario: 65% -> 100%, 87kWh battery == registered
        target = calculate_iog_target_percent(
            current_soc_percent=65,
            desired_soc_percent=100,
            vehicle_battery_kwh=87,
            registered_battery_kwh=87,
        )
        assert target == 35

    def test_smaller_vehicle_scaled_down(self):
        # Corsa (50kWh) plugged in, registered vehicle is Ariya (87kWh)
        # kwh_needed = 40% of 50 = 20 kWh
        # target = 20 / 87 * 100 = 22.99 -> truncates to 22
        target = calculate_iog_target_percent(
            current_soc_percent=40,
            desired_soc_percent=80,
            vehicle_battery_kwh=50,
            registered_battery_kwh=87,
        )
        assert target == 22

    def test_larger_vehicle_scaled_up(self):
        # Plugged-in vehicle bigger than registered — target can exceed
        # what current_soc alone would suggest, clamped at 100
        target = calculate_iog_target_percent(
            current_soc_percent=0,
            desired_soc_percent=50,
            vehicle_battery_kwh=100,
            registered_battery_kwh=50,
        )
        # kwh_needed = 50 kWh, target = 50/50*100 = 100
        assert target == 100

    def test_already_at_desired_soc(self):
        target = calculate_iog_target_percent(
            current_soc_percent=80,
            desired_soc_percent=80,
            vehicle_battery_kwh=60,
            registered_battery_kwh=87,
        )
        assert target == 10  # clamped to minimum

    def test_clamped_to_minimum_10(self):
        target = calculate_iog_target_percent(
            current_soc_percent=99,
            desired_soc_percent=100,
            vehicle_battery_kwh=10,
            registered_battery_kwh=200,
        )
        assert target == 10

    def test_clamped_to_maximum_100(self):
        target = calculate_iog_target_percent(
            current_soc_percent=0,
            desired_soc_percent=100,
            vehicle_battery_kwh=200,
            registered_battery_kwh=10,
        )
        assert target == 100


class TestSelectActiveVehicle:
    def _make_vehicle(self, name, soc, plugged, battery=60, desired=100):
        return {
            "name": name,
            "battery_kwh": battery,
            "current_soc": soc,
            "plugged_in": plugged,
            "desired_soc": desired,
            "charging_loss": 10,
        }

    def test_no_vehicles(self):
        assert select_active_vehicle([]) is None

    def test_none_plugged_in(self):
        vehicles = [self._make_vehicle("A", 50, False), self._make_vehicle("B", 30, False)]
        assert select_active_vehicle(vehicles) is None

    def test_single_plugged_in(self):
        vehicles = [self._make_vehicle("A", 50, True), self._make_vehicle("B", 30, False)]
        result = select_active_vehicle(vehicles)
        assert result["name"] == "A"

    def test_multiple_plugged_picks_largest_deficit(self):
        vehicles = [self._make_vehicle("A", 80, True), self._make_vehicle("B", 20, True)]
        result = select_active_vehicle(vehicles)
        assert result["name"] == "B"

    def test_unavailable_soc_excluded(self):
        vehicles = [self._make_vehicle("A", None, True), self._make_vehicle("B", 40, True)]
        result = select_active_vehicle(vehicles)
        assert result["name"] == "B"
