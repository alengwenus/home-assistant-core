"""Config flow to configure the LCN integration."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import logging
from types import MappingProxyType
from typing import Any

import pypck
from pypck import lcn_defs
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_BASE,
    CONF_DEVICE,
    CONF_DEVICES,
    CONF_ENTITIES,
    CONF_HOST,
    CONF_IP_ADDRESS,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.typing import ConfigType

from . import PchkConnectionManager
from .const import (
    CONF_ACKNOWLEDGE,
    CONF_DIM_MODE,
    CONF_HARDWARE_SERIAL,
    CONF_HARDWARE_TYPE,
    CONF_SK_NUM_TRIES,
    CONF_SOFTWARE_SERIAL,
    DIM_MODES,
    DOMAIN,
)
from .helpers import (
    AddressType,
    LcnConfigEntry,
    async_update_device_config,
    get_device_connection,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_DATA = {
    vol.Required(CONF_IP_ADDRESS, default=""): str,
    vol.Required(CONF_PORT, default=4114): cv.positive_int,
    vol.Required(CONF_USERNAME, default=""): str,
    vol.Required(CONF_PASSWORD, default=""): str,
    vol.Required(CONF_SK_NUM_TRIES, default=0): cv.positive_int,
    vol.Required(CONF_DIM_MODE, default="STEPS200"): vol.In(DIM_MODES),
    vol.Required(CONF_ACKNOWLEDGE, default=False): cv.boolean,
}

USER_DATA = {vol.Required(CONF_HOST, default="pchk"): str, **CONFIG_DATA}

CONFIG_SCHEMA = vol.Schema(CONFIG_DATA)
USER_SCHEMA = vol.Schema(USER_DATA)


DEVICE_DATA = {
    vol.Required("segment_id", default=0): cv.positive_int,
    vol.Required("id", default=0): cv.positive_int,
    vol.Optional("is_group", default=False): cv.boolean,
}

DEVICE_SCHEMA = vol.Schema(DEVICE_DATA)


async def validate_connection(data: ConfigType) -> str | None:
    """Validate if a connection to LCN can be established."""
    error = None
    host_name = data[CONF_HOST]
    host = data[CONF_IP_ADDRESS]
    port = data[CONF_PORT]
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]
    sk_num_tries = data[CONF_SK_NUM_TRIES]
    dim_mode = data[CONF_DIM_MODE]
    acknowledge = data[CONF_ACKNOWLEDGE]

    settings = {
        "SK_NUM_TRIES": sk_num_tries,
        "DIM_MODE": pypck.lcn_defs.OutputPortDimMode[dim_mode],
        "ACKNOWLEDGE": acknowledge,
    }

    _LOGGER.debug("Validating connection parameters to PCHK host '%s'", host_name)

    connection = PchkConnectionManager(
        host, port, username, password, settings=settings
    )

    try:
        await connection.async_connect(timeout=5)
        _LOGGER.debug("LCN connection validated")
    except pypck.connection.PchkAuthenticationError:
        _LOGGER.warning('Authentication on PCHK "%s" failed', host_name)
        error = "authentication_error"
    except pypck.connection.PchkLicenseError:
        _LOGGER.warning(
            'Maximum number of connections on PCHK "%s" was '
            "reached. An additional license key is required",
            host_name,
        )
        error = "license_error"
    except (
        pypck.connection.PchkConnectionFailedError,
        pypck.connection.PchkConnectionRefusedError,
    ):
        _LOGGER.warning('Connection to PCHK "%s" failed', host_name)
        error = "connection_refused"

    await connection.async_close()
    return error


class LcnFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a LCN config flow."""

    VERSION = 3
    MINOR_VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """Return subentries supported by this handler."""
        return {
            CONF_DEVICE: LcnDeviceSubentryFlowHandler,
            "scan_devices": LcnScanDeviceSubentryFlowHandler,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initiated by the user."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

        self._async_abort_entries_match(
            {
                CONF_IP_ADDRESS: user_input[CONF_IP_ADDRESS],
                CONF_PORT: user_input[CONF_PORT],
            }
        )

        if (error := await validate_connection(user_input)) is not None:
            return self.async_show_form(
                step_id="user",
                data_schema=self.add_suggested_values_to_schema(
                    USER_SCHEMA, user_input
                ),
                errors={CONF_BASE: error},
            )

        data: dict[str, Any] = {
            **user_input,
            CONF_DEVICES: [],
            CONF_ENTITIES: [],
        }

        return self.async_create_entry(title=data[CONF_HOST], data=data)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Reconfigure LCN configuration."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors = None
        if user_input is not None:
            user_input[CONF_HOST] = reconfigure_entry.data[CONF_HOST]

            self._async_abort_entries_match(
                {
                    CONF_IP_ADDRESS: user_input[CONF_IP_ADDRESS],
                    CONF_PORT: user_input[CONF_PORT],
                }
            )

            await self.hass.config_entries.async_unload(reconfigure_entry.entry_id)

            if (error := await validate_connection(user_input)) is None:
                return self.async_update_reload_and_abort(
                    reconfigure_entry, data_updates=user_input
                )

            errors = {CONF_BASE: error}
            await self.hass.config_entries.async_setup(reconfigure_entry.entry_id)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                CONFIG_SCHEMA, reconfigure_entry.data
            ),
            errors=errors,
        )


class LcnDeviceSubentryFlowHandler(config_entries.ConfigSubentryFlow):
    """Handle LCN subentry flow."""

    add_device_task: asyncio.Task
    lcn_connection: pypck.connection.PchkConnectionManager
    _subentry_data: dict[str, Any]
    _entity_data: dict[str, Any]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Add a subentry."""
        self.lcn_connection = self._get_entry().runtime_data.connection
        return await self.async_step_add_device()

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Add a new LCN device."""
        errors: dict[str, Any] = {}
        data_schema = DEVICE_SCHEMA
        config_entry = self._get_entry()

        if user_input is None:
            return self.async_show_form(
                step_id="add_device",
                data_schema=data_schema,
                errors=errors,
                last_step=True,
            )

        address = (
            user_input["segment_id"],
            user_input["id"],
            user_input["is_group"],
        )

        if check_already_configured(address, config_entry):
            return self.async_show_form(
                step_id="add_device",
                data_schema=self.add_suggested_values_to_schema(
                    data_schema, user_input
                ),
                errors={CONF_BASE: "device_exists"},
                last_step=True,
            )

        self.add_device_task = self.hass.async_create_task(
            async_get_device_config(self.hass, config_entry, address)
        )

        return await self.async_step_add_device_progress()

    async def async_step_add_device_progress(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Add device progress."""
        if not self.add_device_task.done():
            return self.async_show_progress(
                step_id="add_device_progress",
                progress_action="add_device_progress",
                progress_task=self.add_device_task,
            )

        return self.async_show_progress_done(
            next_step_id="add_device_progress_completed"
        )

    async def async_step_add_device_progress_completed(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.SubentryFlowResult:
        """Add device completed."""
        device_config = self.add_device_task.result()
        # device_config |= {
        #     CONF_ENTITIES: [
        #         {
        #             "name": "Switch_Relay1",
        #             "domain": "switch",
        #             "domain_data": {
        #                 "output": "RELAY1",
        #             },
        #         },
        #     ],
        # }
        return self.async_create_entry(
            title=device_config[CONF_NAME], data=device_config
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Reconfigure a subentry."""
        reconfigure_subentry = self._get_reconfigure_subentry()
        self._subentry_data = deepcopy(dict(reconfigure_subentry.data))
        return await self.async_step_summary_menu()

    async def async_step_summary_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Show summary menu and decide to add more entities or to finish the flow."""
        menu_options = ["add_entity", "delete_entity", "save_changes"]
        return self.async_show_menu(
            step_id="summary_menu",
            menu_options=menu_options,
            description_placeholders={
                "lcn_device": self._subentry_data[CONF_NAME],
            },
        )

    async def async_step_add_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Show entity platform menu."""
        self._entity_data = {"domain": "", "domain_data": {}}
        menu_options = [
            "add_binary_sensor",
            "add_climate",
            "add_cover",
            "add_light",
            "add_scene",
            "add_sensor",
            "add_switch",
        ]
        return self.async_show_menu(
            step_id="add_entity",
            menu_options=menu_options,
            description_placeholders={
                "lcn_device": self._subentry_data[CONF_NAME],
            },
        )

    async def async_step_add_switch(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Add a switch entity."""
        if user_input is not None:
            self._entity_data["domain"] = "switch"
            self._entity_data["target_type"] = user_input["target_type"]
            return await self.async_step_add_switch_target()

        options = [
            SelectOptionDict(value="output", label="Output"),
            SelectOptionDict(value="relay", label="Relay"),
            SelectOptionDict(value="regulator", label="Regulator lock"),
            SelectOptionDict(value="key", label="Key lock"),
        ]
        data_schema = vol.Schema(
            {
                vol.Required("target_type"): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.LIST,
                        translation_key="target_type",
                    )
                )
            }
        )

        return self.async_show_form(
            step_id="add_switch",
            data_schema=data_schema,
            description_placeholders={
                "lcn_device": self._subentry_data[CONF_NAME],
            },
            last_step=False,
        )

    async def async_step_add_switch_target(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Configure switch target."""
        target_type = self._entity_data["target_type"]
        match target_type:
            case "output":
                options = [
                    SelectOptionDict(value=output.name.lower(), label=output.name)
                    for output in lcn_defs.OutputPort
                ]
            case "relay":
                options = [
                    SelectOptionDict(value=relay.name.lower(), label=relay.name)
                    for relay in lcn_defs.RelayPort
                ]
            case "regulator":
                options = [
                    SelectOptionDict(value=set_point.name.lower(), label=set_point.name)
                    for set_point in lcn_defs.Var.set_points()
                ]
            case "key":
                options = [
                    SelectOptionDict(value=key.name, label=key.name)
                    for key in lcn_defs.Key
                ]

        data_schema = vol.Schema(
            {
                vol.Required("target"): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key=target_type,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="add_switch_target",
            data_schema=data_schema,
            description_placeholders={
                "lcn_device": self._subentry_data[CONF_NAME],
            },
            last_step=True,
        )


class LcnScanDeviceSubentryFlowHandler(config_entries.ConfigSubentryFlow):
    """Handle LCN subentry flow."""

    _subentry_data: dict[str, Any]
    scan_devices_task: asyncio.Task
    lcn_connection: pypck.connection.PchkConnectionManager

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Add a subentry."""
        self.lcn_connection = self._get_entry().runtime_data.connection
        return await self.async_step_scan_devices(user_input)

    async def async_step_scan_devices(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.SubentryFlowResult:
        """Scan for new devices."""
        self.scan_devices_task = self.hass.async_create_task(
            self.lcn_connection.scan_modules()
        )

        if self.scan_devices_task.done():
            return self.async_show_progress_done(next_step_id="scan_completed")

        return self.async_show_progress(
            progress_action="scan_devices",
            progress_task=self.scan_devices_task,
        )

    async def async_step_scan_completed(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.SubentryFlowResult:
        """Scan completed."""
        # Add new devices as subentries
        config_entry = self._get_entry()
        for device_connection in self.lcn_connection.device_connections.values():
            if device_connection.is_group:
                continue

            address: AddressType = (
                device_connection.seg_id,
                device_connection.addr_id,
                False,
            )

            if check_already_configured(address, config_entry):
                continue

            device_config = await async_get_device_config(
                self.hass, config_entry, address
            )
            subentry = config_entries.ConfigSubentry(
                data=MappingProxyType(device_config),
                subentry_type=CONF_DEVICE,
                title=device_config[CONF_NAME],
                unique_id=None,
            )

            self.hass.config_entries.async_add_subentry(self._get_entry(), subentry)

        return self.async_abort(reason="scan_completed")


async def async_get_device_config(
    hass: HomeAssistant,
    config_entry: LcnConfigEntry,
    address: AddressType,
) -> ConfigType:
    """Add device and update the config entry."""
    device_connection = get_device_connection(hass, address, config_entry)
    device_config = {
        CONF_ADDRESS: address,
        CONF_NAME: "",
        CONF_HARDWARE_SERIAL: -1,
        CONF_SOFTWARE_SERIAL: -1,
        CONF_HARDWARE_TYPE: -1,
    }

    # update device info from LCN
    await async_update_device_config(device_connection, device_config)
    return device_config


def check_already_configured(
    address: AddressType, config_entry: LcnConfigEntry
) -> bool:
    """Check if device is already configured in the config entry."""
    for subentry in config_entry.subentries.values():
        if tuple(subentry.data[CONF_ADDRESS]) == address:
            _LOGGER.debug("Device %s already exists in config entry", address)
            return True
    return False
