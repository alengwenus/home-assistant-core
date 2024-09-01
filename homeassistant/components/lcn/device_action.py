"""Provides device actions for LCN."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType, TemplateVarsType

from . import DOMAIN

ACTION_TYPES = {"pck"}

PCK_EXTRA_FIELDS = {
    vol.Required("pck"): cv.string,
}


PCK_ACTION_SCHEMA = cv.DEVICE_ACTION_BASE_SCHEMA.extend(
    {vol.Required(CONF_TYPE): "pck", **PCK_EXTRA_FIELDS}
)

ACTION_SCHEMA = vol.Any(PCK_ACTION_SCHEMA)


async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List device actions for LCN devices."""
    actions: list[dict[str, str]] = []

    registry = dr.async_get(hass)
    device = registry.async_get(device_id)
    if not device:
        return actions

    identifiers = next(iter(device.identifiers))
    if len(identifiers[1].split("-")) != 2:
        return actions

    base_action = {CONF_DEVICE_ID: device_id, CONF_DOMAIN: DOMAIN}
    actions.append({**base_action, CONF_TYPE: "pck"})

    return actions


async def async_get_action_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """List action capabilities."""
    match config[CONF_TYPE]:
        case "pck":
            return {"extra_fields": vol.Schema(PCK_EXTRA_FIELDS)}
        case _:
            return {}


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: ConfigType,
    variables: TemplateVarsType,
    context: Context | None,
) -> None:
    """Execute a device action."""
    # print(config)
    # print(variables)
    # print(context)

    # service_data = {ATTR_ENTITY_ID: config[CONF_ENTITY_ID]}

    # if config[CONF_TYPE] == "turn_on":
    #     service = SERVICE_TURN_ON
    # elif config[CONF_TYPE] == "turn_off":
    #     service = SERVICE_TURN_OFF

    # await hass.services.async_call(
    #     DOMAIN, service, service_data, blocking=True, context=context
    # )
