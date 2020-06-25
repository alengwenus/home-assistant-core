"""Support for LCN lights."""
import pypck

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    DOMAIN as DOMAIN_LIGHT,
    SUPPORT_BRIGHTNESS,
    SUPPORT_TRANSITION,
    LightEntity,
)
from homeassistant.const import CONF_DOMAIN, CONF_ENTITIES, CONF_HOST

from .const import (
    CONF_CONNECTIONS,
    CONF_DIMMABLE,
    CONF_DOMAIN_DATA,
    CONF_OUTPUT,
    CONF_TRANSITION,
    CONF_UNIQUE_DEVICE_ID,
    DATA_LCN,
    OUTPUT_PORTS,
)
from .helpers import get_device_address, get_device_config
from .lcn_entity import LcnEntity


def create_lcn_light_entity(hass, entity_config, config_entry):
    """Set up an entity for this domain."""
    host_name = config_entry.data[CONF_HOST]
    host = hass.data[DATA_LCN][CONF_CONNECTIONS][host_name]
    device_config = get_device_config(
        entity_config[CONF_UNIQUE_DEVICE_ID], config_entry
    )
    addr = pypck.lcn_addr.LcnAddr(*get_device_address(device_config))
    device_connection = host.get_address_conn(addr)
    if entity_config[CONF_DOMAIN_DATA][CONF_OUTPUT] in OUTPUT_PORTS:
        entity = LcnOutputLight(entity_config, device_connection)
    else:  # in RELAY_PORTS
        entity = LcnRelayLight(entity_config, device_connection)
    return entity


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up LCN light entities from a config entry."""
    entities = []

    for entity_config in config_entry.data[CONF_ENTITIES]:
        if entity_config[CONF_DOMAIN] == DOMAIN_LIGHT:
            entities.append(create_lcn_light_entity(hass, entity_config, config_entry))

    async_add_entities(entities)


class LcnOutputLight(LcnEntity, LightEntity):
    """Representation of a LCN light for output ports."""

    def __init__(self, config, address_connection):
        """Initialize the LCN light."""
        super().__init__(config, address_connection)

        self.output = pypck.lcn_defs.OutputPort[config[CONF_DOMAIN_DATA][CONF_OUTPUT]]

        self._transition = pypck.lcn_defs.time_to_ramp_value(
            config[CONF_DOMAIN_DATA][CONF_TRANSITION]
        )
        self.dimmable = config[CONF_DOMAIN_DATA][CONF_DIMMABLE]

        self._brightness = 255
        self._is_on = None
        self._is_dimming_to_zero = False

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        if not self.address_connection.is_group():
            await self.address_connection.activate_status_request_handler(self.output)

    async def async_will_remove_from_hass(self):
        """Run when entity will be removed from hass."""
        await super().async_will_remove_from_hass()
        if not self.address_connection.is_group():
            await self.address_connection.cancel_status_request_handler(self.output)

    @property
    def supported_features(self):
        """Flag supported features."""
        if self.dimmable:
            return SUPPORT_TRANSITION | SUPPORT_BRIGHTNESS
        return SUPPORT_TRANSITION

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        return self._brightness

    @property
    def is_on(self):
        """Return True if entity is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs):
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

        self.address_connection.dim_output(self.output.value, percent, transition)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        self._is_on = False
        if ATTR_TRANSITION in kwargs:
            transition = pypck.lcn_defs.time_to_ramp_value(
                kwargs[ATTR_TRANSITION] * 1000
            )
        else:
            transition = self._transition

        self._is_dimming_to_zero = bool(transition)

        self.address_connection.dim_output(self.output.value, 0, transition)
        self.async_write_ha_state()

    def input_received(self, input_obj):
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

    def __init__(self, config, address_connection):
        """Initialize the LCN light."""
        super().__init__(config, address_connection)

        self.output = pypck.lcn_defs.RelayPort[config[CONF_DOMAIN_DATA][CONF_OUTPUT]]

        self._is_on = None

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        if not self.address_connection.is_group():
            await self.address_connection.activate_status_request_handler(self.output)

    async def async_will_remove_from_hass(self):
        """Run when entity will be removed from hass."""
        await super().async_will_remove_from_hass()
        if not self.address_connection.is_group():
            await self.address_connection.cancel_status_request_handler(self.output)

    @property
    def is_on(self):
        """Return True if entity is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        self._is_on = True

        states = [pypck.lcn_defs.RelayStateModifier.NOCHANGE] * 8
        states[self.output.value] = pypck.lcn_defs.RelayStateModifier.ON
        self.address_connection.control_relays(states)

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        self._is_on = False

        states = [pypck.lcn_defs.RelayStateModifier.NOCHANGE] * 8
        states[self.output.value] = pypck.lcn_defs.RelayStateModifier.OFF
        self.address_connection.control_relays(states)

        self.async_write_ha_state()

    def input_received(self, input_obj):
        """Set light state when LCN input object (command) is received."""
        if not isinstance(input_obj, pypck.inputs.ModStatusRelays):
            return

        self._is_on = input_obj.get_state(self.output.value)
        self.async_write_ha_state()
