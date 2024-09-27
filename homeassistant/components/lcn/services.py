"""Service calls related dependencies for LCN component."""

from enum import StrEnum, auto
from typing import Any

import pypck
import voluptuous as vol

from homeassistant.const import CONF_DEVICE_ID, CONF_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_KEY_STATE,
    CONF_KEYS,
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
    KEYLOCKSTATEMODIFIERS,
    KEYS,
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
        vol.Required(CONF_VALUE): vol.Coerce(float),
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
        vol.Required(CONF_VALUE): vol.Coerce(float),
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
        vol.Required(CONF_LOCK_STATE): bool,
    }
    schema = LcnServiceCall.schema.extend(extra_fields)

    async def async_call_service(self, service: ServiceCall) -> None:
        """Execute service call."""
        setpoint = pypck.lcn_defs.Var[service.data[CONF_SETPOINT]]
        state = service.data[CONF_LOCK_STATE]

        reg_id = pypck.lcn_defs.Var.to_set_point_id(setpoint)
        device_connection = self.get_device_connection(service)
        await device_connection.lock_regulator(reg_id, state)


class SendKeys(LcnServiceCall):
    """Sends keys (which executes bound commands)."""

    extra_fields = {
        vol.Required(CONF_KEYS): [vol.All(vol.Upper, vol.In(KEYS))],
        vol.Required(CONF_KEY_STATE, default="hit"): vol.All(
            vol.Upper, vol.In(SENDKEYCOMMANDS)
        ),
        vol.Optional(CONF_TIME): cv.positive_int,
        vol.Optional(CONF_TIME_UNIT, default="seconds"): vol.All(
            vol.Upper, vol.In(TIME_UNITS)
        ),
    }
    schema = LcnServiceCall.schema.extend(extra_fields)

    async def async_call_service(self, service: ServiceCall) -> None:
        """Execute service call."""
        device_connection = self.get_device_connection(service)
        keys = [pypck.lcn_defs.Key[key] for key in service.data[CONF_KEYS]]

        if (CONF_TIME in service.data) and (delay_time := service.data[CONF_TIME]) > 0:
            hit = pypck.lcn_defs.SendKeyCommand.HIT
            if pypck.lcn_defs.SendKeyCommand[service.data[CONF_KEY_STATE]] != hit:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="only_hit_command_allowed",
                )
            delay_unit = pypck.lcn_defs.TimeUnit.parse(service.data[CONF_TIME_UNIT])
            try:
                await device_connection.send_keys_hit_deferred(
                    keys, delay_time, delay_unit
                )
            except ValueError as exception:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key=f"wrong_time_{service.data[CONF_TIME_UNIT]}",
                ) from exception
        else:
            state = pypck.lcn_defs.SendKeyCommand[service.data[CONF_KEY_STATE].upper()]
            await device_connection.send_keys(keys, state)


class LockKeys(LcnServiceCall):
    """Lock keys."""

    extra_fields = {
        vol.Required(CONF_KEYS): [vol.All(vol.Upper, vol.In(KEYS))],
        vol.Required(CONF_LOCK_STATE): vol.All(
            vol.Upper, vol.In(KEYLOCKSTATEMODIFIERS)
        ),
        vol.Optional(CONF_TIME): cv.positive_int,
        vol.Optional(CONF_TIME_UNIT, default="seconds"): vol.All(
            vol.Upper, vol.In(TIME_UNITS)
        ),
    }
    schema = LcnServiceCall.schema.extend(extra_fields)

    async def async_call_service(self, service: ServiceCall) -> None:
        """Execute service call."""
        device_connection = self.get_device_connection(service)
        keys = [pypck.lcn_defs.Key[key] for key in service.data[CONF_KEYS]]
        states = [pypck.lcn_defs.KeyLockStateModifier.NOCHANGE] * 8

        if (CONF_TIME in service.data) and (delay_time := service.data[CONF_TIME]) > 0:
            table_ids, key_ids = zip(*[key.value for key in keys], strict=True)
            if any(table_ids):
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="only_table_a_allowed",
                )
            delay_unit = pypck.lcn_defs.TimeUnit.parse(service.data[CONF_TIME_UNIT])
            for key_id in key_ids:
                states[key_id] = pypck.lcn_defs.KeyLockStateModifier[
                    service.data[CONF_LOCK_STATE]
                ]
                if pypck.lcn_defs.KeyLockStateModifier.TOGGLE in states:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN,
                        translation_key="only_lock_state_on_off_allowed",
                    )
            await device_connection.lock_keys_tab_a_temporary(
                delay_time, delay_unit, states
            )
        else:
            state = pypck.lcn_defs.KeyLockStateModifier[service.data[CONF_LOCK_STATE]]
            await device_connection.lock_keys(keys, state)

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
    (LcnService.SEND_KEYS, SendKeys),
    (LcnService.LOCK_KEYS, LockKeys),
    (LcnService.DYN_TEXT, DynText),
    (LcnService.PCK, Pck),
)
