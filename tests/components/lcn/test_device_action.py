"""The tests for LCN device actions."""

import pytest
from pytest_unordered import unordered

from homeassistant.components import automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.components.lcn import DOMAIN
from homeassistant.components.lcn.const import (
    CONF_KEY_STATE,
    CONF_KEYS,
    CONF_LED,
    CONF_LED_STATE,
    CONF_LOCK_STATE,
    CONF_PCK,
    CONF_ROW,
    CONF_SETPOINT,
    CONF_TEXT,
    CONF_VALUE,
    CONF_VARIABLE,
)
from homeassistant.components.lcn.device_action import ACTION_TYPES
from homeassistant.components.lcn.services import LcnService
from homeassistant.const import CONF_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from .conftest import MockConfigEntry, get_device, init_integration

from tests.common import async_get_device_automations, async_mock_service

action_data = {
    LcnService.LED: {
        CONF_LED: "LED1",
        CONF_LED_STATE: "ON",
    },
    LcnService.VAR_ABS: {
        CONF_VARIABLE: "var1",
        CONF_VALUE: 100,
        CONF_UNIT_OF_MEASUREMENT: "native",
    },
    LcnService.VAR_RESET: {CONF_VARIABLE: "var5"},
    LcnService.VAR_REL: {
        CONF_VARIABLE: "var2",
        CONF_VALUE: 50,
        CONF_UNIT_OF_MEASUREMENT: "percent",
    },
    LcnService.LOCK_REGULATOR: {CONF_SETPOINT: "r1varsetpoint", CONF_LOCK_STATE: True},
    LcnService.SEND_KEYS: {CONF_KEYS: ["a1", "a4", "b1", "c4"], CONF_KEY_STATE: "hit"},
    LcnService.LOCK_KEYS: {CONF_KEYS: ["a1", "a4", "b1", "c4"], CONF_LOCK_STATE: "on"},
    LcnService.DYN_TEXT: {CONF_ROW: 1, CONF_TEXT: "Hello world!"},
    LcnService.PCK: {CONF_PCK: "PIN001"},
}


async def test_get_actions(
    hass: HomeAssistant,
    entry: MockConfigEntry,
) -> None:
    """Test we get the expected actions from a lcn."""
    await init_integration(hass, entry)
    device_entry = get_device(hass, entry, (0, 7, False))

    expected_actions = [
        {
            "domain": DOMAIN,
            "type": action,
            "device_id": device_entry.id,
            "metadata": {},
        }
        for action in ACTION_TYPES
    ]
    actions = await async_get_device_automations(
        hass, DeviceAutomationType.ACTION, device_entry.id
    )

    assert actions == unordered(expected_actions)


@pytest.mark.parametrize("action_type", ACTION_TYPES)
async def test_action(
    hass: HomeAssistant, entry: MockConfigEntry, action_type: str
) -> None:
    """Test for trigger actions."""
    await init_integration(hass, entry)
    device_entry = get_device(hass, entry, (0, 7, False))
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        "platform": "event",
                        "event_type": f"test_event_{action_type}",
                    },
                    "action": {
                        "domain": DOMAIN,
                        "device_id": device_entry.id,
                        "type": action_type,
                        **action_data.get(action_type, {}),
                    },
                }
            ]
        },
    )

    action_calls = async_mock_service(hass, "lcn", action_type)

    hass.bus.async_fire(f"test_event_{action_type}")
    await hass.async_block_till_done()
    assert len(action_calls) == 1
