"""Web socket API for Local Control Network devices."""

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_HOST,
    CONF_IP_ADDRESS,
    CONF_NAME,
    CONF_PORT,
)
from homeassistant.core import callback

from .const import CONF_PLATFORMS, DOMAIN

TYPE = "type"
ID = "id"
ATTR_HOST = "host"
ATTR_SEGMENT_ID = "segment_id"
ATTR_ADDRESS_ID = "address_id"
ATTR_IS_GROUP = "is_group"


def convert_config_entry(config_entry):
    """Convert the config entry to a format which can be transferred via websocket."""
    config = {}
    for platform_name, entity_configs in config_entry.data[CONF_PLATFORMS].items():
        for entity_config in entity_configs:
            entity_config_copy = entity_config.copy()
            address = tuple(entity_config_copy.pop(CONF_ADDRESS))

            if address not in config:
                config[address] = {}

            config[address].update(
                {
                    ATTR_SEGMENT_ID: address[0],
                    ATTR_ADDRESS_ID: address[1],
                    ATTR_IS_GROUP: address[2],
                }
            )

            if CONF_PLATFORMS not in config[address]:
                config[address][CONF_PLATFORMS] = {}

            if platform_name not in config[address][CONF_PLATFORMS]:
                config[address][CONF_PLATFORMS][platform_name] = []

            config[address][CONF_PLATFORMS][platform_name].append(entity_config_copy)

    devices_config = []
    for device_config in config.values():
        devices_config.append(device_config)
    return devices_config


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command({vol.Required(TYPE): "lcn/hosts"})
async def websocket_get_hosts(hass, connection, msg):
    """Get LCN hosts."""
    config_entries = hass.config_entries.async_entries(DOMAIN)

    hosts = [
        {
            CONF_NAME: config_entry.data[CONF_HOST],
            CONF_IP_ADDRESS: config_entry.data[CONF_IP_ADDRESS],
            CONF_PORT: config_entry.data[CONF_PORT],
        }
        for config_entry in config_entries
    ]

    connection.send_result(msg[ID], hosts)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {vol.Required(TYPE): "lcn/config", vol.Required(ATTR_HOST): str}
)
async def websocket_get_config(hass, connection, msg):
    """Get LCN modules."""
    for config_entry in hass.config_entries.async_entries(DOMAIN):
        if config_entry.data[CONF_HOST] == msg[ATTR_HOST]:
            break

    config = convert_config_entry(config_entry)
    connection.send_result(msg[ID], config)


@callback
def async_load_websocket_api(hass):
    """Set up the web socket API."""
    websocket_api.async_register_command(hass, websocket_get_hosts)
    websocket_api.async_register_command(hass, websocket_get_config)
