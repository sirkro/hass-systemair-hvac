"""Root conftest.py - mock homeassistant package before any test imports."""
from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Build a mock 'homeassistant' package so that all integration-level imports
# resolve without installing Home Assistant.
# ---------------------------------------------------------------------------

def _make_module(name: str, attrs: dict[str, Any] | None = None) -> MagicMock:
    """Create a named MagicMock module and register it in sys.modules."""
    mod = MagicMock()
    mod.__name__ = name
    mod.__package__ = name.rsplit(".", 1)[0] if "." in name else name
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# Only install mocks if homeassistant is not actually available
if "homeassistant" not in sys.modules:
    # Core
    _make_module("homeassistant")
    _make_module("homeassistant.core", {
        "HomeAssistant": MagicMock,
        "ServiceCall": MagicMock,
    })
    import enum as _enum

    class _EntityCategory(_enum.StrEnum):
        """Mock for homeassistant.const.EntityCategory."""
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    _make_module("homeassistant.exceptions", {
        "ConfigEntryAuthFailed": type("ConfigEntryAuthFailed", (Exception,), {}),
        "HomeAssistantError": type("HomeAssistantError", (Exception,), {}),
    })

    _make_module("homeassistant.const", {
        "Platform": type("Platform", (), {
            "CLIMATE": "climate",
            "SENSOR": "sensor",
            "BINARY_SENSOR": "binary_sensor",
            "SWITCH": "switch",
            "SELECT": "select",
            "NUMBER": "number",
        })(),
        "ATTR_TEMPERATURE": "temperature",
        "CONF_HOST": "host",
        "CONF_PORT": "port",
        "UnitOfTemperature": type("UnitOfTemperature", (), {"CELSIUS": "°C"})(),
        "PERCENTAGE": "%",
        "REVOLUTIONS_PER_MINUTE": "rpm",
        "CONCENTRATION_PARTS_PER_MILLION": "ppm",
        "UnitOfTime": type("UnitOfTime", (), {"DAYS": "d", "MINUTES": "min", "HOURS": "h"})(),
        "EntityCategory": _EntityCategory,
    })

    # config_entries
    class _MockConfigFlow:
        """Base class mock for ConfigFlow."""
        VERSION = 1
        def __init_subclass__(cls, *, domain: str = "", **kw: Any) -> None:
            cls._domain = domain
        def async_show_form(self, **kw: Any) -> dict:
            return {"type": "form", **kw}
        def async_create_entry(self, **kw: Any) -> dict:
            return {"type": "create_entry", **kw}
        async def async_set_unique_id(self, uid: str) -> None:
            pass
        def _abort_if_unique_id_configured(self) -> None:
            pass

    class _MockOptionsFlowWithConfigEntry:
        """Base class mock for OptionsFlowWithConfigEntry."""
        def __init__(self, config_entry: Any) -> None:
            self.config_entry = config_entry
            self.options = dict(getattr(config_entry, "options", {}) or {})
        def async_show_form(self, **kw: Any) -> dict:
            return {"type": "form", **kw}
        def async_create_entry(self, **kw: Any) -> dict:
            return {"type": "create_entry", **kw}

    _make_module("homeassistant.config_entries", {
        "ConfigEntry": MagicMock,
        "ConfigFlow": _MockConfigFlow,
        "ConfigFlowResult": dict,
        "OptionsFlowWithConfigEntry": _MockOptionsFlowWithConfigEntry,
    })

    # data_entry_flow
    def _mock_section(schema, options=None):
        """Mock for homeassistant.data_entry_flow.section.

        Returns the schema itself so voluptuous validation still works.
        """
        return schema

    _make_module("homeassistant.data_entry_flow", {
        "section": _mock_section,
    })

    # helpers
    _helpers_mod = _make_module("homeassistant.helpers")
    class _MockDataUpdateCoordinator:
        """Base class mock for DataUpdateCoordinator that supports Generic[T]."""
        def __class_getitem__(cls, item):
            return cls
        def __init__(self, *args, **kwargs):
            pass
        async def async_request_refresh(self):
            pass
        async def async_config_entry_first_refresh(self):
            pass
        data = None
        last_update_success = True

    class _MockCoordinatorEntity:
        """Base class mock for CoordinatorEntity that supports Generic[T]."""
        def __class_getitem__(cls, item):
            return cls
        def __init__(self, coordinator, *args, **kwargs):
            self.coordinator = coordinator

        @property
        def available(self) -> bool:
            """Mock available property — always True unless overridden."""
            return True

    _make_module("homeassistant.helpers.update_coordinator", {
        "DataUpdateCoordinator": _MockDataUpdateCoordinator,
        "UpdateFailed": type("UpdateFailed", (Exception,), {}),
        "CoordinatorEntity": _MockCoordinatorEntity,
    })
    _make_module("homeassistant.helpers.entity_platform", {
        "AddEntitiesCallback": MagicMock,
    })
    _make_module("homeassistant.helpers.aiohttp_client", {
        "async_get_clientsession": MagicMock,
    })

    import voluptuous as vol
    _make_module("homeassistant.helpers.config_validation", {
        "entity_id": vol.Schema(str),
    })
    _make_module("homeassistant.helpers.redact", {
        "async_redact_data": lambda data, keys: {
            k: ("**REDACTED**" if k in keys else v) for k, v in data.items()
        },
    })

    # entity_registry — used by __init__.py via `from homeassistant.helpers import entity_registry as er`
    _entity_registry_mod = _make_module("homeassistant.helpers.entity_registry", {
        "async_get": MagicMock(),
    })
    # Ensure `from homeassistant.helpers import entity_registry` resolves to our module
    _helpers_mod.entity_registry = _entity_registry_mod

    # Component bases
    _make_module("homeassistant.components")

    # -- climate --
    class _ClimateEntity:
        """Mock for ClimateEntity."""
        _attr_has_entity_name = True
        _attr_name = None
        _attr_unique_id = None
        _attr_device_info = None
        _attr_supported_features = 0
        _attr_hvac_modes = []
        _attr_fan_modes = []
        _attr_preset_modes = []
        _attr_min_temp = 12
        _attr_max_temp = 30
        _attr_target_temperature_step = 1

    _make_module("homeassistant.components.climate", {
        "ClimateEntity": _ClimateEntity,
        "ClimateEntityFeature": type("ClimateEntityFeature", (), {
            "TARGET_TEMPERATURE": 1,
            "FAN_MODE": 8,
            "PRESET_MODE": 16,
        })(),
        "HVACMode": type("HVACMode", (), {
            "AUTO": "auto",
            "FAN_ONLY": "fan_only",
        })(),
        "HVACAction": type("HVACAction", (), {
            "IDLE": "idle",
            "HEATING": "heating",
            "COOLING": "cooling",
            "FAN": "fan",
        })(),
    })

    # -- sensor --
    from dataclasses import dataclass, field

    @dataclass(frozen=True, kw_only=True)
    class _SensorEntityDescription:
        """Mock for SensorEntityDescription."""
        key: str = ""
        name: str | None = None
        translation_key: str | None = None
        native_unit_of_measurement: str | None = None
        device_class: Any = None
        state_class: Any = None
        icon: str | None = None
        entity_registry_enabled_default: bool = True
        suggested_display_precision: int | None = None
        entity_category: Any = None

    _SensorDeviceClass = type("SensorDeviceClass", (), {
        "TEMPERATURE": "temperature",
        "HUMIDITY": "humidity",
        "DURATION": "duration",
        "CO2": "carbon_dioxide",
    })()
    _SensorStateClass = type("SensorStateClass", (), {
        "MEASUREMENT": "measurement",
    })()

    _make_module("homeassistant.components.sensor", {
        "SensorEntity": type("SensorEntity", (), {
            "_attr_has_entity_name": True,
            "_attr_name": None,
            "_attr_unique_id": None,
            "_attr_device_info": None,
            "_attr_native_value": None,
        }),
        "SensorDeviceClass": _SensorDeviceClass,
        "SensorStateClass": _SensorStateClass,
        "SensorEntityDescription": _SensorEntityDescription,
    })

    # -- binary_sensor --
    @dataclass(frozen=True, kw_only=True)
    class _BinarySensorEntityDescription:
        """Mock for BinarySensorEntityDescription."""
        key: str = ""
        name: str | None = None
        translation_key: str | None = None
        device_class: Any = None
        icon: str | None = None
        entity_registry_enabled_default: bool = True

    _BinarySensorDeviceClass = type("BinarySensorDeviceClass", (), {
        "PROBLEM": "problem",
        "RUNNING": "running",
    })()

    _make_module("homeassistant.components.binary_sensor", {
        "BinarySensorEntity": type("BinarySensorEntity", (), {
            "_attr_has_entity_name": True,
            "_attr_name": None,
            "_attr_unique_id": None,
            "_attr_device_info": None,
            "_attr_is_on": None,
        }),
        "BinarySensorDeviceClass": _BinarySensorDeviceClass,
        "BinarySensorEntityDescription": _BinarySensorEntityDescription,
    })

    # -- switch --
    _make_module("homeassistant.components.switch", {
        "SwitchEntity": type("SwitchEntity", (), {
            "_attr_has_entity_name": True,
            "_attr_name": None,
            "_attr_unique_id": None,
            "_attr_device_info": None,
            "_attr_is_on": None,
            "_attr_icon": None,
        }),
    })

    # -- select --
    _make_module("homeassistant.components.select", {
        "SelectEntity": type("SelectEntity", (), {
            "_attr_has_entity_name": True,
            "_attr_name": None,
            "_attr_unique_id": None,
            "_attr_device_info": None,
            "_attr_options": [],
            "_attr_current_option": None,
        }),
    })

    # -- number --
    @dataclass(frozen=True, kw_only=True)
    class _NumberEntityDescription:
        """Mock for NumberEntityDescription."""
        key: str = ""
        name: str | None = None
        translation_key: str | None = None
        icon: str | None = None
        native_min_value: float | None = None
        native_max_value: float | None = None
        native_step: float | None = None
        native_unit_of_measurement: str | None = None
        mode: Any = None
        entity_registry_enabled_default: bool = True

    _NumberMode = type("NumberMode", (), {
        "AUTO": "auto",
        "BOX": "box",
        "SLIDER": "slider",
    })()

    _make_module("homeassistant.components.number", {
        "NumberEntity": type("NumberEntity", (), {
            "_attr_has_entity_name": True,
            "_attr_name": None,
            "_attr_unique_id": None,
            "_attr_device_info": None,
            "_attr_native_value": None,
            "_attr_native_min_value": None,
            "_attr_native_max_value": None,
            "_attr_native_step": None,
            "_attr_mode": None,
        }),
        "NumberEntityDescription": _NumberEntityDescription,
        "NumberMode": _NumberMode,
    })
