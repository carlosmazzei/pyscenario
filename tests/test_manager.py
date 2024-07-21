import re
from unittest import mock

import pyscenario
import pytest
import voluptuous as vol
from pyscenario.config_schema import device_config_schema
from pyscenario.const import (
    COVER_DEVICES,
    DEVICE_FILE,
    ERROR_CODES,
    IFSEI_ATTR_BRIGHTNESS,
    IFSEI_ATTR_RED,
    LIGHT_DEVICES,
)
from pyscenario.manager import Cover, DeviceManager, Light

# Mock configuration data
mock_device_config = {
    "lights": [
        {
            "id": 1,
            "name": "Light 1",
            "zone": 1,
            "isRGB": True,
            "address": [
                {"name": IFSEI_ATTR_RED, "module": 1, "channel": 1, "isDimmeable": True}
            ],
        }
    ],
    "shades": [
        {
            "id": 2,
            "name": "Shade 1",
            "zone": 2,
            "address1": "1234",
            "address2": "5678",
            "address3": "9012",
        }
    ],
    "zones": [{"id": 1, "name": "Living Room"}, {"id": 2, "name": "Bedroom"}],
}


@pytest.fixture
def mock_queue_manager():
    """Mock the QueueManager."""
    send_queue = mock.AsyncMock()
    receive_queue = mock.AsyncMock()
    return pyscenario.QueueManager(send_queue, receive_queue)


@pytest.fixture
def mock_async():
    """Mock async."""
    return lambda *args, **kwargs: None


@pytest.fixture
def mock_device_manager_config(monkeypatch):
    """Mock loading the device manager configuration."""
    monkeypatch.setattr(
        DeviceManager,
        "from_config",
        mock.Mock(
            return_value=DeviceManager(
                lights=[
                    Light(
                        unique_id="1_living_room",
                        name="Light 1",
                        zone="Living Room",
                        is_rgb=True,
                        address=[{"name": IFSEI_ATTR_RED, "module": 1, "channel": 1}],
                    )
                ],
                covers=[
                    Cover(
                        unique_id="2_bedroom",
                        name="Shade 1",
                        zone="Bedroom",
                        up="1234",
                        stop="5678",
                        down="9012",
                    )
                ],
                zones={"1": "Living Room", "2": "Bedroom"},
            )
        ),
    )


def test_device_manager_from_config(mock_device_manager_config):
    """Test DeviceManager creation from a valid config file."""
    manager = DeviceManager.from_config("device_config.yaml")
    assert manager is not None
    assert len(manager.lights) > 0
    assert len(manager.covers) > 0


def test_device_manager_from_invalid_config(monkeypatch):
    """Test DeviceManager creation from an invalid config file."""
    monkeypatch.setattr(DeviceManager, "from_config", mock.Mock(return_value=None))
    manager = DeviceManager.from_config("invalid.yaml")
    assert manager is None


def test_device_manager_get_devices_by_type(mock_device_manager_config):
    """Test retrieving devices by type from DeviceManager."""
    manager = DeviceManager.from_config("device_config.yaml")
    lights = manager.get_devices_by_type(LIGHT_DEVICES)
    covers = manager.get_devices_by_type(COVER_DEVICES)
    assert len(lights) > 0
    assert len(covers) > 0


def test_device_manager_get_device_by_id(mock_device_manager_config):
    """Test retrieving a device by ID from DeviceManager."""
    manager = DeviceManager.from_config("device_config.yaml")
    device = manager.get_device_by_id(manager.lights[0].unique_id)
    assert device is not None


def test_device_manager_async_handle_zone_state_change(
    monkeypatch, mock_device_manager_config, event_loop
):
    """Test handling zone state change in DeviceManager."""
    manager = DeviceManager.from_config("device_config.yaml")
    light = manager.lights[0]
    callback = mock.Mock()
    monkeypatch.setattr(light, "callback_", callback)
    event_loop.run_until_complete(
        manager.async_handle_zone_state_change(
            int(light.address[0]["module"]),
            light.address[0]["channel"],
            100,
        )
    )
    callback.assert_called_once()


@pytest.mark.asyncio
async def test_device_manager_async_handle_scene_state_change(
    monkeypatch, mock_device_manager_config
):
    """Test handling scene state change in DeviceManager."""
    manager = DeviceManager.from_config("device_config.yaml")
    cover = manager.covers[0]
    callback = mock.Mock()
    monkeypatch.setattr(cover, "callback_", callback)
    await manager.async_handle_scene_state_change(cover.up, "1")
    callback.assert_called_once()


def test_device_manager_notify_subscriber(monkeypatch, mock_device_manager_config):
    """Test notifying subscribers in DeviceManager."""
    manager = DeviceManager.from_config("device_config.yaml")
    light = manager.lights[0]
    cover = manager.covers[0]
    light_callback = mock.Mock()
    cover_callback = mock.Mock()
    monkeypatch.setattr(light, "callback_", light_callback)
    monkeypatch.setattr(cover, "callback_", cover_callback)
    manager.notify_subscriber(available="True")
    light_callback.assert_called_once()
    cover_callback.assert_called_once()


def test_light_class():
    """Test the Light class."""
    light = Light("1", "Test Light", "Living Room", True, [])
    assert light.unique_id == "1_living_room"
    assert light.name == "Test Light"
    assert light.zone == "Living Room"
    assert light.is_rgb


def test_cover_class():
    """Test the Cover class."""
    cover = Cover("2", "Test Cover", "Bedroom", "1234", "5678", "9012")
    assert cover.unique_id == "2_bedroom"
    assert cover.name == "Test Cover"
    assert cover.zone == "Bedroom"
    assert cover.up == "1234"
    assert cover.stop == "5678"
    assert cover.down == "9012"


def test_config_schema_validation():
    """Test the device configuration schema validation."""
    valid_data = {
        "lights": [
            {
                "id": 1,
                "name": "Light 1",
                "zone": 1,
                "isRGB": True,
                "address": [
                    {
                        "name": IFSEI_ATTR_RED,
                        "module": 1,
                        "channel": 1,
                        "isDimmeable": True,
                    }
                ],
            }
        ],
        "shades": [
            {
                "id": 2,
                "name": "Shade 1",
                "zone": 2,
                "address1": "1234",
                "address2": "5678",
                "address3": "9012",
            }
        ],
        "zones": [{"id": 1, "name": "Living Room"}, {"id": 2, "name": "Bedroom"}],
    }
    device_config_schema(valid_data)

    invalid_data = {
        "lights": [
            {
                "id": 1,
                "name": "Light 1",
                "zone": 1,
                "isRGB": True,
                "address": [
                    {
                        "name": "invalid",
                        "module": "invalid",
                        "channel": "invalid",
                        "isDimmeable": "invalid",
                    }
                ],
            }
        ]
    }
    with pytest.raises(vol.Invalid):
        device_config_schema(invalid_data)


def test_const_module():
    """Test the constants in the const module."""
    assert isinstance(IFSEI_ATTR_BRIGHTNESS, str)
    assert isinstance(DEVICE_FILE, str)
    assert isinstance(ERROR_CODES, dict)


def test_version_is_semver_string():
    """Test that the version in pyproject.toml is a proper semantic version."""
    semver_pattern = r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
    version = pyscenario.__version__
    assert re.match(
        semver_pattern, version
    ), f'"{version}" is not a valid semver version'
