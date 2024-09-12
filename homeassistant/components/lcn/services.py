"""Service calls related dependencies for LCN component."""

from enum import StrEnum, auto
from typing import Any

import pypck
import voluptuous as vol

from homeassistant.const import CONF_DEVICE_ID, CONF_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_KEY,
    CONF_KEY_STATE,
    CONF_LED,
    CONF_LED_STATE,
    CONF_LOCK_STATE,
    CONF_PCK,
    CONF_RELVARREF,
    CONF_ROW,
    CONF_SETPOINT,
    CONF_TEXT,
    CONF_TIME,
    CONF_TIME_UNIT,
    CONF_VALUE,
    CONF_VARIABLE,
    DEVICE_CONNECTIONS,
    DOMAIN,
    LED_PORTS,
    LED_STATUS,
    RELVARREF,
    SENDKEYCOMMANDS,
    SETPOINTS,
    THRESHOLDS,
    TIME_UNITS,
    VAR_UNITS,
    VARIABLES,
)
from .helpers import DeviceConnectionType


class LcnServiceCall:
    """Parent class for all LCN service calls."""

    extra_fields: dict[vol.Required | vol.Optional, Any] = {
        vol.Required(CONF_DEVICE_ID): cv.string
    }
    schema = vol.Schema(extra_fields)

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize service call."""
        self.hass = hass

    def get_device_connection(self, service: ServiceCall) -> DeviceConnectionType:
        """Get address connection object."""
        device_id = service.data[CONF_DEVICE_ID]
        device_registry = dr.async_get(self.hass)
        if not (device := device_registry.async_get(device_id)):
            return None

        return self.hass.data[DOMAIN][device.primary_config_entry][DEVICE_CONNECTIONS][
            device_id
        ]

    async def async_call_service(self, service: ServiceCall) -> None:
        """Execute service call."""
        raise NotImplementedError


class Led(LcnServiceCall):
    """Set the led state."""

    extra_fields = {
        vol.Required(CONF_LED): vol.All(vol.Upper, vol.In(LED_PORTS)),
        vol.Required(CONF_LED_STATE): vol.All(vol.Upper, vol.In(LED_STATUS)),
    }
    schema = LcnServiceCall.schema.extend(extra_fields)

    async def async_call_service(self, service: ServiceCall) -> None:
        """Execute service call."""
        led = pypck.lcn_defs.LedPort[service.data[CONF_LED]]
        led_state = pypck.lcn_defs.LedStatus[service.data[CONF_LED_STATE]]

        device_connection = self.get_device_connection(service)
        await device_connection.control_led(led, led_state)


class VarAbs(LcnServiceCall):
    """Set absolute value of a variable or setpoint.

    Variable has to be set as counter!
    Regulator setpoints can also be set using R1VARSETPOINT, R2VARSETPOINT.
    """

    extra_fields = {
        vol.Required(CONF_VARIABLE): vol.All(vol.Upper, vol.In(VARIABLES + SETPOINTS)),
        vol.Optional(CONF_VALUE, default=0): vol.Coerce(float),
        vol.Optional(CONF_UNIT_OF_MEASUREMENT, default="native"): vol.All(
            vol.Upper, vol.In(VAR_UNITS)
        ),
    }
    schema = LcnServiceCall.schema.extend(extra_fields)

    async def async_call_service(self, service: ServiceCall) -> None:
        """Execute service call."""
        var = pypck.lcn_defs.Var[service.data[CONF_VARIABLE]]
        value = service.data[CONF_VALUE]
        unit = pypck.lcn_defs.VarUnit.parse(service.data[CONF_UNIT_OF_MEASUREMENT])

        device_connection = self.get_device_connection(service)
        await device_connection.var_abs(var, value, unit)


class VarReset(LcnServiceCall):
    """Reset value of variable or setpoint."""

    extra_fields = {
        vol.Required(CONF_VARIABLE): vol.All(vol.Upper, vol.In(VARIABLES + SETPOINTS))
    }
    schema = LcnServiceCall.schema.extend(extra_fields)

    async def async_call_service(self, service: ServiceCall) -> None:
        """Execute service call."""
        var = pypck.lcn_defs.Var[service.data[CONF_VARIABLE]]

        device_connection = self.get_device_connection(service)
        await device_connection.var_reset(var)


class VarRel(LcnServiceCall):
    """Shift value of a variable, setpoint or threshold."""

    extra_fields = {
        vol.Required(CONF_VARIABLE): vol.All(
            vol.Upper, vol.In(VARIABLES + SETPOINTS + THRESHOLDS)
        ),
        vol.Optional(CONF_VALUE, default=0): vol.Coerce(float),
        vol.Optional(CONF_UNIT_OF_MEASUREMENT, default="native"): vol.All(
            vol.Upper, vol.In(VAR_UNITS)
        ),
        vol.Optional(CONF_RELVARREF, default="current"): vol.All(
            vol.Upper, vol.In(RELVARREF)
        ),
    }
    schema = LcnServiceCall.schema.extend(extra_fields)

    async def async_call_service(self, service: ServiceCall) -> None:
        """Execute service call."""
        var = pypck.lcn_defs.Var[service.data[CONF_VARIABLE]]
        value = service.data[CONF_VALUE]
        unit = pypck.lcn_defs.VarUnit.parse(service.data[CONF_UNIT_OF_MEASUREMENT])
        value_ref = pypck.lcn_defs.RelVarRef[service.data[CONF_RELVARREF]]

        device_connection = self.get_device_connection(service)
        await device_connection.var_rel(var, value, unit, value_ref)


class LockRegulator(LcnServiceCall):
    """Locks a regulator setpoint."""

    extra_fields = {
        vol.Required(CONF_SETPOINT): vol.All(vol.Upper, vol.In(SETPOINTS)),
        vol.Optional(CONF_LOCK_STATE, default=False): bool,
    }
    schema = LcnServiceCall.schema.extend(extra_fields)

    async def async_call_service(self, service: ServiceCall) -> None:
        """Execute service call."""
        setpoint = pypck.lcn_defs.Var[service.data[CONF_SETPOINT]]
        state = service.data[CONF_LOCK_STATE]

        reg_id = pypck.lcn_defs.Var.to_set_point_id(setpoint)
        device_connection = self.get_device_connection(service)
        await device_connection.lock_regulator(reg_id, state)


class SendKey(LcnServiceCall):
    """Sends key (which executes bound commands)."""

    extra_fields = {
        vol.Required(CONF_KEY): vol.All(
            vol.Upper, vol.In([key.name for key in pypck.lcn_defs.Key])
        ),
        vol.Optional(CONF_KEY_STATE, default="hit"): vol.All(
            vol.Upper, vol.In(SENDKEYCOMMANDS)
        ),
        vol.Optional(CONF_TIME, default=0): cv.positive_int,
        vol.Optional(CONF_TIME_UNIT, default="S"): vol.All(
            vol.Upper, vol.In(TIME_UNITS)
        ),
    }
    schema = LcnServiceCall.schema.extend(extra_fields)

    async def async_call_service(self, service: ServiceCall) -> None:
        """Execute service call."""
        device_connection = self.get_device_connection(service)

        keys = [[False] * 8 for i in range(4)]

        key_strings = zip(
            service.data[CONF_KEY][::2], service.data[CONF_KEY][1::2], strict=False
        )

        for table, key in key_strings:
            table_id = ord(table) - 65
            key_id = int(key) - 1
            keys[table_id][key_id] = True

        if (delay_time := service.data[CONF_TIME]) != 0:
            hit = pypck.lcn_defs.SendKeyCommand.HIT
            if pypck.lcn_defs.SendKeyCommand[service.data[CONF_KEY_STATE]] != hit:
                raise ValueError(
                    "Only hit command is allowed when sending deferred keys."
                )
            delay_unit = pypck.lcn_defs.TimeUnit.parse(service.data[CONF_TIME_UNIT])
            await device_connection.send_keys_hit_deferred(keys, delay_time, delay_unit)
        else:
            state = pypck.lcn_defs.SendKeyCommand[service.data[CONF_KEY_STATE]]
            await device_connection.send_keys(keys, state)


class LockKey(LcnServiceCall):
    """Lock keys."""

    extra_fields = {
        vol.Required(CONF_KEY): vol.All(
            vol.Upper, vol.In([key.name for key in pypck.lcn_defs.Key])
        ),
        vol.Required(CONF_LOCK_STATE): vol.All(
            vol.Upper, vol.In([mod.name for mod in pypck.lcn_defs.KeyLockStateModifier])
        ),
        vol.Optional(CONF_TIME, default=0): cv.positive_int,
        vol.Optional(CONF_TIME_UNIT, default="S"): vol.All(
            vol.Upper, vol.In(TIME_UNITS)
        ),
    }
    schema = LcnServiceCall.schema.extend(extra_fields)

    async def async_call_service(self, service: ServiceCall) -> None:
        """Execute service call."""
        device_connection = self.get_device_connection(service)

        table_id = ord(service.data[CONF_KEY][0]) - 65
        key_number = int(service.data[CONF_KEY][1]) - 1

        states = [pypck.lcn_defs.KeyLockStateModifier["NOCHANGE"]] * 8
        states[key_number] = pypck.lcn_defs.KeyLockStateModifier[
            service.data[CONF_LOCK_STATE]
        ]

        if (delay_time := service.data[CONF_TIME]) != 0:
            if table_id != 0:
                raise ValueError(
                    "Only table A is allowed when locking keys for a specific time."
                )
            delay_unit = pypck.lcn_defs.TimeUnit.parse(service.data[CONF_TIME_UNIT])
            await device_connection.lock_keys_tab_a_temporary(
                delay_time, delay_unit, states
            )
        else:
            await device_connection.lock_keys(table_id, states)

        handler = device_connection.status_requests_handler
        await handler.request_status_locked_keys_timeout()


class DynText(LcnServiceCall):
    """Send dynamic text to LCN-GTxD displays."""

    extra_fields = {
        vol.Required(CONF_ROW): vol.All(int, vol.Range(min=1, max=4)),
        vol.Required(CONF_TEXT): vol.All(str, vol.Length(max=60)),
    }
    schema = LcnServiceCall.schema.extend(extra_fields)

    async def async_call_service(self, service: ServiceCall) -> None:
        """Execute service call."""
        row_id = service.data[CONF_ROW] - 1
        text = service.data[CONF_TEXT]

        device_connection = self.get_device_connection(service)
        await device_connection.dyn_text(row_id, text)


class Pck(LcnServiceCall):
    """Send arbitrary PCK command."""

    extra_fields = {vol.Required(CONF_PCK): cv.string}
    schema = LcnServiceCall.schema.extend(extra_fields)

    async def async_call_service(self, service: ServiceCall) -> None:
        """Execute service call."""
        pck = service.data[CONF_PCK]
        device_connection = self.get_device_connection(service)
        await device_connection.pck(pck)


class LcnService(StrEnum):
    """LCN service names."""

    OUTPUT_ABS = auto()
    OUTPUT_REL = auto()
    OUTPUT_TOGGLE = auto()
    RELAYS = auto()
    VAR_ABS = auto()
    VAR_RESET = auto()
    VAR_REL = auto()
    LOCK_REGULATOR = auto()
    LED = auto()
    SEND_KEYS = auto()
    LOCK_KEYS = auto()
    DYN_TEXT = auto()
    PCK = auto()


SERVICES = (
    (LcnService.VAR_ABS, VarAbs),
    (LcnService.VAR_RESET, VarReset),
    (LcnService.VAR_REL, VarRel),
    (LcnService.LOCK_REGULATOR, LockRegulator),
    (LcnService.LED, Led),
    (LcnService.SEND_KEYS, SendKey),
    (LcnService.LOCK_KEYS, LockKey),
    (LcnService.DYN_TEXT, DynText),
    (LcnService.PCK, Pck),
)
