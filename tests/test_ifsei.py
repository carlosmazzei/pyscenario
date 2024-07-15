import asyncio
from unittest import mock

import pytest
import telnetlib3
from pyscenario import NetworkConfiguration, Protocol
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


@pytest.fixture
def ifsei_instance():
    """Fixture to provide a default IFSEI instance."""
    return IFSEI()


@pytest.mark.asyncio
async def test_ifsei_async_connect(mock_telnet_connection, ifsei_instance):
    """Test the async_connect method of the IFSEI class."""
    ifsei = ifsei_instance
    assert not ifsei.is_connected
    mock_reader, mock_writer = mock_telnet_connection
    result = await ifsei.async_connect()
    assert ifsei.connection == (mock_reader, mock_writer)
    assert ifsei.process_task is not None
    assert result


def test_ifsei_valid_config():
    """Test the ifsei init method with valid configuration."""
    valid_config = NetworkConfiguration(
        host="192.168.15.1", tcp_port=2300, protocol=Protocol.TCP
    )
    ifsei = IFSEI(valid_config)
    assert ifsei.network_config == valid_config


@pytest.mark.asyncio
async def test_ifsei_async_connect_invalid_config():
    """Test the async_connect method with invalid configuration."""
    invalid_config = NetworkConfiguration(host="invalid", tcp_port=-1)
    with pytest.raises(ValueError):
        IFSEI(invalid_config)


@pytest.mark.asyncio
async def test_ifsei_async_close(mock_telnet_connection, monkeypatch, ifsei_instance):
    """Test the async_close method of the IFSEI class."""
    ifsei = ifsei_instance
    mock_reader, mock_writer = mock_telnet_connection
    await ifsei.async_connect()
    assert ifsei.connection == (mock_reader, mock_writer)

    # Manually set the _telnetclient attribute to a mock
    mock_telnetclient = mock.AsyncMock(spec=IFSEITelnetClient)
    ifsei._telnetclient = mock_telnetclient

    await ifsei.async_close()
    assert ifsei.is_closing
    assert ifsei.connection is None
    assert ifsei.process_task is None
    assert ifsei._reconnect_task is None

    mock_telnetclient.async_close.assert_called_once()


@pytest.mark.asyncio
async def test_ifsei_async_send_command(mock_telnet_connection, ifsei_instance):
    """Test the async_send_command method of the IFSEI class."""
    ifsei = ifsei_instance
    mock_reader, mock_writer = mock_telnet_connection
    await ifsei.async_connect()
    assert ifsei.connection == (mock_reader, mock_writer)
    command = "$VER"
    await ifsei.async_send_command(command)
    assert not ifsei.queue_manager.send_queue.empty()
    assert await ifsei.queue_manager.send_queue.get() == command


@pytest.mark.asyncio
async def test_ifsei_async_monitor(mock_telnet_connection, ifsei_instance):
    """Test the async_monitor method of the IFSEI class."""
    ifsei = ifsei_instance
    mock_reader, mock_writer = mock_telnet_connection
    await ifsei.async_connect()
    assert ifsei.connection == (mock_reader, mock_writer)
    await ifsei.async_monitor(5)
    with pytest.raises(ValueError):
        await ifsei.async_monitor(8)


@pytest.mark.asyncio
async def test_ifsei_async_update_light_state(
    monkeypatch, mock_telnet_connection, mock_device_manager_config, ifsei_instance
):
    """Test the async_update_light_state method of the IFSEI class."""
    ifsei = ifsei_instance
    ifsei.load_devices("scenario_device_config.yaml")
    monkeypatch.setattr(ifsei, "async_set_zone_intensity", mock.AsyncMock())
    device_id = ifsei.device_manager.lights[0].unique_id
    await ifsei.async_update_light_state(device_id, [255, 0, 0, 100])
    ifsei.async_set_zone_intensity.assert_called()


@pytest.mark.asyncio
async def test_ifsei_async_update_cover_state(
    monkeypatch, mock_telnet_connection, mock_device_manager_config, ifsei_instance
):
    """Test the async_update_cover_state method of the IFSEI class."""
    ifsei = ifsei_instance
    ifsei.load_devices("scenario_device_config.yaml")
    monkeypatch.setattr(ifsei, "async_set_shader_state", mock.AsyncMock())
    device_id = ifsei.device_manager.covers[0].unique_id
    await ifsei.async_update_cover_state(device_id, "1234")
    ifsei.async_set_shader_state.assert_called()


@pytest.mark.asyncio
async def test_ifsei_async_get_version(
    monkeypatch, mock_telnet_connection, ifsei_instance
):
    """Test the async_get_version method of the IFSEI class."""
    ifsei = ifsei_instance
    monkeypatch.setattr(ifsei, "async_send_command", mock.AsyncMock())
    await ifsei.async_get_version()
    ifsei.async_send_command.assert_called_with("$VER")


@pytest.mark.asyncio
async def test_ifsei_async_get_ip(monkeypatch, mock_telnet_connection, ifsei_instance):
    """Test the async_get_ip method of the IFSEI class."""
    ifsei = ifsei_instance
    monkeypatch.setattr(ifsei, "async_send_command", mock.AsyncMock())
    await ifsei.async_get_ip()
    ifsei.async_send_command.assert_called_with("$IP")


@pytest.mark.asyncio
async def test_ifsei_async_process_responses(
    mock_telnet_connection, monkeypatch, ifsei_instance
):
    """Test the _async_process_responses method of the IFSEI class."""
    ifsei = ifsei_instance
    mock_reader, mock_writer = mock_telnet_connection
    await ifsei.async_connect()
    assert ifsei.connection == (mock_reader, mock_writer)

    response = "TEST_RESPONSE"

    mock_get_generator = mock.AsyncMock()
    mock_get_generator.side_effect = [response, asyncio.CancelledError]

    monkeypatch.setattr(ifsei.queue_manager.receive_queue, "get", mock_get_generator)
    monkeypatch.setattr(ifsei, "_async_handle_response", mock.AsyncMock())

    await ifsei._async_process_responses()

    ifsei._async_handle_response.assert_called_once_with(response)


@pytest.mark.asyncio
async def test_ifsei_async_handle_response(
    mock_telnet_connection, monkeypatch, ifsei_instance
):
    """Test the _async_handle_response method of the IFSEI class."""
    ifsei = ifsei_instance
    mock_reader, mock_writer = mock_telnet_connection
    await ifsei.async_connect()
    assert ifsei.connection == (mock_reader, mock_writer)

    response = "*IFSEION"
    monkeypatch.setattr(ifsei, "set_is_connected", mock.Mock())
    monkeypatch.setattr(ifsei, "async_monitor", mock.AsyncMock())

    await ifsei._async_handle_response(response)

    ifsei.set_is_connected.assert_called_once_with(True)
    ifsei.async_monitor.assert_called_once_with(7)

    response = "*Z0101L100"
    monkeypatch.setattr(ifsei, "_async_handle_zone_response", mock.AsyncMock())
    await ifsei._async_handle_response(response)
    ifsei._async_handle_zone_response.assert_called_once_with(response)


@pytest.mark.asyncio
async def test_ifsei_async_handle_error(mock_telnet_connection, ifsei_instance):
    """Test the _async_handle_error method of the IFSEI class."""
    ifsei = ifsei_instance
    mock_reader, mock_writer = mock_telnet_connection
    await ifsei.async_connect()
    assert ifsei.connection == (mock_reader, mock_writer)

    response = "E01"
    await ifsei._async_handle_error(response)

    response = "E31"
    await ifsei._async_handle_error(response)


def test_ifsei_set_protocol(ifsei_instance):
    """Test the set_protocol method of the IFSEI class."""
    ifsei = ifsei_instance
    ifsei.set_protocol(Protocol.UDP)
    assert ifsei.network_config.protocol == Protocol.UDP


def test_ifsei_get_device_id(ifsei_instance):
    """Test the get_device_id method of the IFSEI class."""
    ifsei = ifsei_instance
    assert ifsei.get_device_id() == f"ifsei-scenario-{ifsei.network_config.host}"
