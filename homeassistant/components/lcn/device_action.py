"""Provides device actions for LCN."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType, TemplateVarsType

from . import DOMAIN
from .services import SERVICES

ACTION_TYPES, _ = zip(*SERVICES, strict=True)

ACTION_SCHEMA = vol.Any(
    *(
        cv.DEVICE_ACTION_BASE_SCHEMA.extend(
            {vol.Required(CONF_TYPE): str(service[0]), **service[1].extra_fields}
        )
        for service in SERVICES
    )
)


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
    actions.extend(
        {**base_action, CONF_TYPE: action_type} for action_type in ACTION_TYPES
    )

    return actions


async def async_get_action_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """List action capabilities."""
    schemas = {service[0]: vol.Schema(service[1].extra_fields) for service in SERVICES}

    return {"extra_fields": schemas[config[CONF_TYPE]]}


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: ConfigType,
    variables: TemplateVarsType,
    context: Context | None,
) -> None:
    """Execute a device action."""
    service = config[CONF_TYPE]
    service_data = {
        key: value
        for key, value in config.items()
        if key not in (CONF_DOMAIN, CONF_TYPE)
    }

    await hass.services.async_call(
        DOMAIN, service, service_data, blocking=True, context=context
    )
