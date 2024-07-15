from unittest import mock

import pyscenario
import pytest
import telnetlib3
from pyscenario import NetworkConfiguration
from pyscenario.client import IFSEITelnetClient
from pyscenario.const import IFSEI_ATTR_RED
from pyscenario.ifsei import IFSEI
from pyscenario.manager import Cover, DeviceManager, Light


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


@pytest.fixture
def mock_telnet_connection(monkeypatch):
    """Mock the telnet connection over TCP."""
    mock_reader = mock.AsyncMock()
    mock_writer = mock.AsyncMock()
    mock_writer.get_extra_info = mock.Mock(return_value="utf-8")
    monkeypatch.setattr(
        telnetlib3,
        "open_connection",
        mock.AsyncMock(return_value=(mock_reader, mock_writer)),
    )
    return mock_reader, mock_writer


def test_ifsei_async_connect(mock_telnet_connection, event_loop):
    """Test the async_connect method of the IFSEI class."""
    ifsei = IFSEI()
    assert not ifsei.is_connected
    mock_reader, mock_writer = mock_telnet_connection
    result = event_loop.run_until_complete(ifsei.async_connect())
    assert ifsei.connection == (mock_reader, mock_writer)
    assert ifsei.process_task is not None
    assert result


def test_ifsei_valid_config():
    """Test the ifsei init method with valid configuration."""
    valid_config = NetworkConfiguration(
        host="192.168.15.1", tcp_port=2300, protocol=pyscenario.Protocol.TCP
    )
    IFSEI(valid_config)
    assert valid_config


def test_ifsei_async_connect_invalid_config():
    """Test the async_connect method with invalid configuration."""
    invalid_config = NetworkConfiguration(host="invalid", tcp_port=-1)
    with pytest.raises(ValueError):
        IFSEI(invalid_config)


def test_ifsei_async_close(mock_telnet_connection, event_loop, monkeypatch):
    """Test the async_close method of the IFSEI class."""
    ifsei = IFSEI()
    mock_reader, mock_writer = mock_telnet_connection
    event_loop.run_until_complete(ifsei.async_connect())
    assert ifsei.connection == (mock_reader, mock_writer)

    # Manually set the _telnetclient attribute to a mock
    mock_telnetclient = mock.AsyncMock(spec=IFSEITelnetClient)
    mock_telnetclient.async_close = mock.AsyncMock()
    ifsei._telnetclient = mock_telnetclient

    assert ifsei._telnetclient is not None  # Ensure _telnetclient is initialized
    event_loop.run_until_complete(ifsei.async_close())
    assert ifsei.is_closing
    assert ifsei.connection is None

    mock_telnetclient.async_close.assert_called_once()


def test_ifsei_async_send_command(mock_telnet_connection, event_loop):
    """Test the async_send_command method of the IFSEI class."""
    ifsei = IFSEI()
    mock_reader, mock_writer = mock_telnet_connection
    event_loop.run_until_complete(ifsei.async_connect())
    assert ifsei.connection == (mock_reader, mock_writer)
    command = "$VER"
    event_loop.run_until_complete(ifsei.async_send_command(command))
    assert not ifsei.queue_manager.send_queue.empty()


def test_ifsei_async_monitor(mock_telnet_connection, event_loop):
    """Test the async_monitor method of the IFSEI class."""
    ifsei = IFSEI()
    mock_reader, mock_writer = mock_telnet_connection
    event_loop.run_until_complete(ifsei.async_connect())
    assert ifsei.connection == (mock_reader, mock_writer)
    event_loop.run_until_complete(ifsei.async_monitor(5))
    with pytest.raises(ValueError):
        event_loop.run_until_complete(ifsei.async_monitor(8))


def test_ifsei_async_update_light_state(
    monkeypatch, mock_telnet_connection, mock_device_manager_config, event_loop
):
    """Test the async_update_light_state method of the IFSEI class."""
    ifsei = IFSEI()
    ifsei.load_devices("scenario_device_config.yaml")
    monkeypatch.setattr(ifsei, "async_set_zone_intensity", mock.AsyncMock())
    device_id = ifsei.device_manager.lights[0].unique_id
    event_loop.run_until_complete(
        ifsei.async_update_light_state(device_id, [255, 0, 0, 100])
    )


def test_ifsei_async_update_cover_state(
    monkeypatch, mock_telnet_connection, mock_device_manager_config, event_loop
):
    """Test the async_update_cover_state method of the IFSEI class."""
    ifsei = IFSEI()
    ifsei.load_devices("scenario_device_config.yaml")
    monkeypatch.setattr(ifsei, "async_set_shader_state", mock.AsyncMock())
    device_id = ifsei.device_manager.covers[0].unique_id
    event_loop.run_until_complete(ifsei.async_update_cover_state(device_id, "1234"))


def test_ifsei_async_get_version(monkeypatch, mock_telnet_connection, event_loop):
    """Test the async_get_version method of the IFSEI class."""
    ifsei = IFSEI()
    monkeypatch.setattr(ifsei, "async_send_command", mock.AsyncMock())
    event_loop.run_until_complete(ifsei.async_get_version())
    ifsei.async_send_command.assert_called_with("$VER")


def test_ifsei_async_get_ip(monkeypatch, mock_telnet_connection, event_loop):
    """Test the async_get_ip method of the IFSEI class."""
    ifsei = IFSEI()
    monkeypatch.setattr(ifsei, "async_send_command", mock.AsyncMock())
    event_loop.run_until_complete(ifsei.async_get_ip())
    ifsei.async_send_command.assert_called_with("$IP")
