"""Support for LCN lights."""
from typing import Any, Callable, List, Optional

import pypck

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    DOMAIN as DOMAIN_LIGHT,
    SUPPORT_BRIGHTNESS,
    SUPPORT_TRANSITION,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DOMAIN, CONF_ENTITIES
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from .const import (
    CONF_DIMMABLE,
    CONF_DOMAIN_DATA,
    CONF_OUTPUT,
    CONF_TRANSITION,
    CONF_UNIQUE_DEVICE_ID,
    OUTPUT_PORTS,
)
from .helpers import DeviceConnectionType, InputType, get_device_connection
from .lcn_entity import LcnEntity


def create_lcn_light_entity(
    hass: HomeAssistantType, entity_config: ConfigType, config_entry: ConfigEntry
) -> LcnEntity:
    """Set up an entity for this domain."""
    host_name = config_entry.entry_id
    device_connection = get_device_connection(
        hass, entity_config[CONF_UNIQUE_DEVICE_ID], config_entry
    )

    if entity_config[CONF_DOMAIN_DATA][CONF_OUTPUT] in OUTPUT_PORTS:
        return LcnOutputLight(entity_config, host_name, device_connection)
    else:  # in RELAY_PORTS
        return LcnRelayLight(entity_config, host_name, device_connection)


async def async_setup_entry(
    hass: HomeAssistantType,
    config_entry: ConfigEntry,
    async_add_entities: Callable[[List[LcnEntity]], None],
) -> None:
    """Set up LCN light entities from a config entry."""
    entities = []

    for entity_config in config_entry.data[CONF_ENTITIES]:
        if entity_config[CONF_DOMAIN] == DOMAIN_LIGHT:
            entities.append(create_lcn_light_entity(hass, entity_config, config_entry))

    async_add_entities(entities)


class LcnOutputLight(LcnEntity, LightEntity):
    """Representation of a LCN light for output ports."""

    def __init__(
        self, config: ConfigType, host_id: str, device_connection: DeviceConnectionType
    ) -> None:
        """Initialize the LCN light."""
        super().__init__(config, host_id, device_connection)

        self.output = pypck.lcn_defs.OutputPort[config[CONF_DOMAIN_DATA][CONF_OUTPUT]]

        self._transition = pypck.lcn_defs.time_to_ramp_value(
            config[CONF_DOMAIN_DATA][CONF_TRANSITION]
        )
        self.dimmable = config[CONF_DOMAIN_DATA][CONF_DIMMABLE]

        self._brightness = 255
        self._is_on = False
        self._is_dimming_to_zero = False

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        if not self.device_connection.is_group():
            await self.device_connection.activate_status_request_handler(self.output)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        await super().async_will_remove_from_hass()
        if not self.device_connection.is_group():
            await self.device_connection.cancel_status_request_handler(self.output)

    @property
    def supported_features(self) -> Optional[int]:
        """Flag supported features."""
        features = SUPPORT_TRANSITION
        if self.dimmable:
            features |= SUPPORT_BRIGHTNESS
        return features

    @property
    def brightness(self) -> float:
        """Return the brightness of this light between 0..255."""
        return self._brightness

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        self._is_on = True
        self._is_dimming_to_zero = False
        if ATTR_BRIGHTNESS in kwargs:
            percent = int(kwargs[ATTR_BRIGHTNESS] / 255.0 * 100)
        else:
            percent = 100
        if ATTR_TRANSITION in kwargs:
            transition = pypck.lcn_defs.time_to_ramp_value(
                kwargs[ATTR_TRANSITION] * 1000
            )
        else:
            transition = self._transition

        self.device_connection.dim_output(self.output.value, percent, transition)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        self._is_on = False
        if ATTR_TRANSITION in kwargs:
            transition = pypck.lcn_defs.time_to_ramp_value(
                kwargs[ATTR_TRANSITION] * 1000
            )
        else:
            transition = self._transition

        self._is_dimming_to_zero = bool(transition)

        self.device_connection.dim_output(self.output.value, 0, transition)
        self.async_write_ha_state()

    def input_received(self, input_obj: InputType) -> None:
        """Set light state when LCN input object (command) is received."""
        if (
            not isinstance(input_obj, pypck.inputs.ModStatusOutput)
            or input_obj.get_output_id() != self.output.value
        ):
            return

        self._brightness = int(input_obj.get_percent() / 100.0 * 255)
        if self.brightness == 0:
            self._is_dimming_to_zero = False
        if not self._is_dimming_to_zero:
            self._is_on = self.brightness > 0
        self.async_write_ha_state()


class LcnRelayLight(LcnEntity, LightEntity):
    """Representation of a LCN light for relay ports."""

    def __init__(
        self, config: ConfigType, host_id: str, device_connection: DeviceConnectionType
    ) -> None:
        """Initialize the LCN light."""
        super().__init__(config, host_id, device_connection)

        self.output = pypck.lcn_defs.RelayPort[config[CONF_DOMAIN_DATA][CONF_OUTPUT]]

        self._is_on = False

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        if not self.device_connection.is_group():
            await self.device_connection.activate_status_request_handler(self.output)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        await super().async_will_remove_from_hass()
        if not self.device_connection.is_group():
            await self.device_connection.cancel_status_request_handler(self.output)

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        self._is_on = True

        states = [pypck.lcn_defs.RelayStateModifier.NOCHANGE] * 8
        states[self.output.value] = pypck.lcn_defs.RelayStateModifier.ON
        self.device_connection.control_relays(states)

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        self._is_on = False

        states = [pypck.lcn_defs.RelayStateModifier.NOCHANGE] * 8
        states[self.output.value] = pypck.lcn_defs.RelayStateModifier.OFF
        self.device_connection.control_relays(states)

        self.async_write_ha_state()

    def input_received(self, input_obj: InputType) -> None:
        """Set light state when LCN input object (command) is received."""
        if not isinstance(input_obj, pypck.inputs.ModStatusRelays):
            return

        self._is_on = input_obj.get_state(self.output.value)
        self.async_write_ha_state()
