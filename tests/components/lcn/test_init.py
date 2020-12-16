"""Test init of LCN integration."""
import json

from pypck.connection import (
    PchkAuthenticationError,
    PchkConnectionManager,
    PchkLicenseError,
)

from homeassistant import config_entries
from homeassistant.components import lcn
from homeassistant.components.lcn.const import CONNECTION, DOMAIN
from homeassistant.config_entries import (
    ENTRY_STATE_LOADED,
    ENTRY_STATE_NOT_LOADED,
    ENTRY_STATE_SETUP_ERROR,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from .conftest import MockPchkConnectionManager, init_integration

from tests.async_mock import patch
from tests.common import load_fixture


@patch("pypck.connection.PchkConnectionManager", MockPchkConnectionManager)
async def test_async_setup_entry(hass, entry):
    """Test a successful setup entry and unload of entry."""
    await init_integration(hass, entry)
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert entry.state == ENTRY_STATE_LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state == ENTRY_STATE_NOT_LOADED
    assert not hass.data.get(DOMAIN)


@patch("pypck.connection.PchkConnectionManager", MockPchkConnectionManager)
async def test_async_setup_entry_update(hass, entry):
    """Test a successful setup entry if entry with same id already exists."""
    # setup first entry
    entry.source = config_entries.SOURCE_IMPORT

    # create dummy entity for LCN platform as an orphan
    entity_registry = await er.async_get_registry(hass)
    dummy_entity = entity_registry.async_get_or_create(
        "switch", DOMAIN, "dummy", config_entry=entry
    )
    assert dummy_entity in entity_registry.entities.values()

    # add entity to hass and setup (should cleanup dummy entity)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert dummy_entity not in entity_registry.entities.values()


async def test_async_setup_entry_raises_authentication_error(hass, entry):
    """Test that an authentication error is handled properly."""
    with patch.object(
        PchkConnectionManager, "async_connect", side_effect=PchkAuthenticationError
    ):
        await init_integration(hass, entry)
    assert entry.state == ENTRY_STATE_SETUP_ERROR


async def test_async_setup_entry_raises_license_error(hass, entry):
    """Test that an authentication error is handled properly."""
    with patch.object(
        PchkConnectionManager, "async_connect", side_effect=PchkLicenseError
    ):
        await init_integration(hass, entry)
    assert entry.state == ENTRY_STATE_SETUP_ERROR


async def test_async_setup_entry_raises_timeout_error(hass, entry):
    """Test that an authentication error is handled properly."""
    with patch.object(PchkConnectionManager, "async_connect", side_effect=TimeoutError):
        await init_integration(hass, entry)
    assert entry.state == ENTRY_STATE_SETUP_ERROR


async def test_async_setup_from_configuration_yaml(hass):
    """Test a successful setup using data from configuration.yaml."""
    await async_setup_component(hass, "persistent_notification", {})

    config = json.loads(load_fixture("lcn/config.json"))
    with patch(
        "homeassistant.components.lcn.async_setup_entry", return_value=True
    ) as async_setup_entry:
        await lcn.async_setup(hass, config)
        await hass.async_block_till_done()

        assert async_setup_entry.await_count == 2


@patch("pypck.connection.PchkConnectionManager", MockPchkConnectionManager)
async def test_connection_name_update(hass, entry):
    """Test connection name change on update of config_entry."""
    await init_integration(hass, entry)
    assert entry.title == "pchk"
    assert hass.data[DOMAIN][entry.entry_id][CONNECTION].connection_id == "pchk"

    # rename config entry title
    hass.config_entries.async_update_entry(entry, title="foobar")
    await hass.async_block_till_done()

    assert entry.title == "foobar"
    assert hass.data[DOMAIN][entry.entry_id][CONNECTION].connection_id == "foobar"


@patch("pypck.connection.PchkConnectionManager", MockPchkConnectionManager)
async def test_unload_entry(hass, entry):
    """Test being able to unload an entry."""
    await init_integration(hass, entry)
    assert hass.data[DOMAIN]

    assert await lcn.async_unload_entry(hass, entry)
    assert entry.entry_id not in hass.data[DOMAIN]
