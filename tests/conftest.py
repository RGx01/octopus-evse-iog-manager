"""
Shared test setup.

`calculations.py` is deliberately free of Home Assistant imports, so we load it
straight from its path rather than importing the package. Importing
`custom_components.octopus_evse_iog_manager.calculations` would execute the
package's __init__.py, which pulls in Home Assistant — turning a fast, pure unit
test run into one that needs a full HA install pinned to a matching version.

If HA-dependent tests are added later (coordinator, config flow), they belong in
their own module using pytest-homeassistant-custom-component's `hass` fixture,
and can be skipped when HA isn't installed.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_CALCULATIONS_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "octopus_evse_iog_manager"
    / "calculations.py"
)


def _load_calculations():
    spec = importlib.util.spec_from_file_location("iog_calculations", _CALCULATIONS_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"Could not load {_CALCULATIONS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


calculations = _load_calculations()


@pytest.fixture(scope="session")
def calc():
    """The pure calculations module."""
    return calculations