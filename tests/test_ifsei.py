import asyncio
import json
from unittest import mock

import pytest
import telnetlib3
from pyscenario import NetworkConfiguration, Protocol, QueueManager
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


@pytest.fixture
def mock_config_data():
    """Mock configuration data."""
    return {
        "host": "192.168.1.1",
        "tcp_port": 2300,
        "udp_port": 2301,
        "protocol": "TCP",
    }


@pytest.fixture
def mock_config_file(tmp_path, mock_config_data):
    """Create a mock configuration file."""
    config_file = tmp_path / "config.json"
    with open(config_file, "w") as f:
        json.dump(mock_config_data, f)
    return config_file


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
    invalid_host_config = NetworkConfiguration(host="invalid", tcp_port=-1)
    with pytest.raises(ValueError):
        IFSEI(invalid_host_config)

    invalid_port_config = NetworkConfiguration(host="192.168.1.20", tcp_port=-1)
    with pytest.raises(ValueError):
        IFSEI(invalid_port_config)

    invalid_protocol_config = NetworkConfiguration(
        host="192.168.1.20", tcp_port=100, protocol="X"
    )
    with pytest.raises(ValueError):
        IFSEI(invalid_protocol_config)


def test_ifsei_set_reconnect_options_default_config():
    """Test setting reconnect options with default configuration."""
    ifsei = IFSEI()

    # Set reconnect options
    ifsei.set_reconnect_options(reconnect=True, delay=5.0)

    # Verify the changes
    assert ifsei.network_config.reconnect is True
    assert ifsei.network_config.reconnect_delay == pytest.approx(5.0, 0.1)


def test_ifsei_set_reconnect_options_custom_config():
    """Test setting reconnect options with a custom configuration."""
    custom_config = NetworkConfiguration(
        host="192.168.1.1", tcp_port=2300, udp_port=2301, protocol=Protocol.TCP
    )
    ifsei = IFSEI(network_config=custom_config)

    # Set reconnect options
    ifsei.set_reconnect_options(reconnect=False, delay=10.0)

    # Verify the changes
    assert ifsei.network_config.reconnect is False
    assert ifsei.network_config.reconnect_delay == pytest.approx(10.0, 0.1)


def test_ifsei_set_reconnect_options_logging(monkeypatch):
    """Test the logging in set_reconnect_options method."""
    ifsei = IFSEI()
    mock_logger = mock.Mock()
    monkeypatch.setattr("pyscenario.ifsei.logger", mock_logger)

    # Set reconnect options
    ifsei.set_reconnect_options(reconnect=True, delay=15.0)

    # Verify the log message
    mock_logger.info.assert_any_call(
        "Reconnect options set: reconnect=%s, delay=%s", True, 15.0
    )


def test_set_send_delay_no_telnetclient(monkeypatch):
    """Test setting send delay when _telnetclient is None."""
    ifsei = IFSEI()
    mock_logger = mock.Mock()
    monkeypatch.setattr("pyscenario.ifsei.logger", mock_logger)

    # Set send delay
    delay = 5.0
    ifsei.set_send_delay(delay)

    # Verify that the logger was called with the correct message
    mock_logger.info.assert_called_once_with(
        "Cannot set send delay without telnetclient"
    )


def test_set_send_delay_with_telnetclient(monkeypatch):
    """Test setting send delay when _telnetclient is not None."""
    ifsei = IFSEI()
    mock_telnetclient = mock.Mock(spec=IFSEITelnetClient)
    ifsei._telnetclient = mock_telnetclient
    mock_logger = mock.Mock()
    monkeypatch.setattr("pyscenario.ifsei.logger", mock_logger)

    # Set send delay
    delay = 10.0
    ifsei.set_send_delay(delay)

    # Verify that the send_delay attribute of _telnetclient was set
    assert mock_telnetclient.send_delay == pytest.approx(delay, 0.1)

    # Verify that the logger was called with the correct message
    mock_logger.info.assert_called_once_with("Send delay set to: %s", delay)


def test_set_send_delay_logging(monkeypatch):
    """Test logging in set_send_delay method."""
    ifsei = IFSEI()
    mock_logger = mock.Mock()
    monkeypatch.setattr("pyscenario.ifsei.logger", mock_logger)

    # Set send delay
    delay = 15.0
    ifsei.set_send_delay(delay)

    # Verify the log message
    if ifsei._telnetclient is None:
        mock_logger.info.assert_called_once_with(
            "Cannot set send delay without telnetclient"
        )
    else:
        mock_logger.info.assert_called_once_with("Send delay set to: %s", delay)


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
    ifsei._reconnect_task = mock.AsyncMock()

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
    mock_get_generator.side_effect = [
        response,
        asyncio.CancelledError,
    ]

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


def test_ifsei_load_config(monkeypatch, mock_config_file, mock_config_data):
    """Test the _load_config method of the IFSEI class."""
    mock_logger = mock.Mock()
    monkeypatch.setattr("pyscenario.ifsei.logger", mock_logger)

    config = IFSEI._load_config(mock_config_file)
    assert config == mock_config_data

    mock_logger.info.assert_called_once_with(
        "Reading from log file: %s", mock_config_file
    )


def test_ifsei_from_config(mock_config_file, mock_config_data):
    """Test the from_config method of the IFSEI class."""
    ifsei = IFSEI.from_config(mock_config_file)

    assert ifsei.network_config.host == mock_config_data["host"]
    assert ifsei.network_config.tcp_port == mock_config_data["tcp_port"]
    assert ifsei.network_config.udp_port == mock_config_data["udp_port"]
    assert ifsei.network_config.protocol == Protocol[mock_config_data["protocol"]]


@pytest.mark.asyncio
async def test_reconnect_when_closing(monkeypatch, ifsei_instance):
    """Test _reconnect method when is_closing is True."""
    ifsei_instance.is_closing = True
    mock_logger = mock.Mock()
    monkeypatch.setattr("pyscenario.ifsei.logger", mock_logger)

    ifsei_instance._reconnect()

    # Ensure no reconnect task is started
    assert ifsei_instance._reconnect_task is None
    mock_logger.info.assert_any_call("Closing, do not start reconnect thread")


@pytest.mark.asyncio
async def test_reconnect_when_not_closing_and_task_running(monkeypatch, ifsei_instance):
    """Test _reconnect method when is_closing is False and _reconnect_task is running."""
    ifsei_instance.is_closing = False
    mock_reconnect_task = mock.Mock()
    ifsei_instance._reconnect_task = mock_reconnect_task
    mock_logger = mock.Mock()
    monkeypatch.setattr("pyscenario.ifsei.logger", mock_logger)
    monkeypatch.setattr(ifsei_instance._reconnect_task, "done", mock.Mock())

    ifsei_instance._reconnect()

    # Ensure no new reconnect task is started
    assert ifsei_instance._reconnect_task == mock_reconnect_task
    ifsei_instance._reconnect_task.done.assert_called_once()


@pytest.mark.asyncio
async def test_reconnect_when_not_closing_and_no_task_running(
    monkeypatch, ifsei_instance
):
    """Test _reconnect method when is_closing is False and _reconnect_task is not running."""
    ifsei_instance.is_closing = False
    ifsei_instance._reconnect_task = None
    mock_logger = mock.Mock()
    monkeypatch.setattr("pyscenario.ifsei.logger", mock_logger)
    monkeypatch.setattr(ifsei_instance, "set_is_connected", mock.Mock())
    mock_create_task = mock.Mock()
    monkeypatch.setattr(asyncio, "create_task", mock_create_task)

    ifsei_instance._reconnect()

    # Ensure reconnect task is started
    assert ifsei_instance._reconnect_task is not None
    mock_logger.info.assert_any_call("Reconnect loop not running")
    mock_create_task.assert_called_once()
    assert mock_create_task.call_args[0][0].__name__ == "_async_reconnect"
    ifsei_instance.set_is_connected.assert_called_once_with(False)


def test_create_client(ifsei_instance):
    """Test the create_client method of the IFSEI class."""
    mock_queue_manager = mock.Mock(spec=QueueManager)
    mock_callback = mock.Mock()
    ifsei_instance.queue_manager = mock_queue_manager
    ifsei_instance.on_connection_lost = mock_callback
    kwds = {"encoding": "utf-8"}

    client = ifsei_instance._create_client(**kwds)
    assert isinstance(client, IFSEITelnetClient)


@pytest.mark.asyncio
async def test_async_handle_zone_response_with_device_manager(ifsei_instance):
    """Test _async_handle_zone_response with a valid device manager."""
    response = "*Z0101L100"
    ifsei_instance.device_manager = mock.MagicMock(spec=DeviceManager)
    ifsei_instance.device_manager.async_handle_zone_state_change = mock.AsyncMock()

    with mock.patch("pyscenario.ifsei.logger") as mock_logger:
        await ifsei_instance._async_handle_zone_response(response)

        # Assert the correct log message
        mock_logger.info.assert_any_call("Zone %s state: %s intensity: %s", 1, 1, 100)

        # Assert that async_handle_zone_state_change was called with correct parameters
        ifsei_instance.device_manager.async_handle_zone_state_change.assert_awaited_once_with(
            1, 1, 100
        )


@pytest.mark.asyncio
async def test_async_handle_zone_response_without_device_manager(ifsei_instance):
    """Test _async_handle_zone_response without a device manager."""
    response = "*Z0202L050"
    ifsei_instance.device_manager = None

    with mock.patch("pyscenario.ifsei.logger") as mock_logger:
        await ifsei_instance._async_handle_zone_response(response)

        # Assert the correct log message for the zone state
        mock_logger.info.assert_any_call("Zone %s state: %s intensity: %s", 2, 2, 50)

        # Assert the log message for missing device manager
        mock_logger.info.assert_any_call(
            "Cannot handle zone response (no device manager found)"
        )


@pytest.mark.asyncio
async def test_async_handle_scene_response_with_device_manager(ifsei_instance):
    """Test _async_handle_scene_response with a valid device manager."""
    response = "*C12341"
    ifsei_instance.device_manager = mock.MagicMock(spec=DeviceManager)
    ifsei_instance.device_manager.async_handle_scene_state_change = mock.AsyncMock()

    with mock.patch("pyscenario.ifsei.logger") as mock_logger:
        await ifsei_instance._async_handle_scene_response(response)

        # Assert the correct log message
        mock_logger.info.assert_any_call(
            "Scene response: %s, address: %s, state: %s", response, "1234", "1"
        )

        # Assert that async_handle_scene_state_change was called with correct parameters
        ifsei_instance.device_manager.async_handle_scene_state_change.assert_awaited_once_with(
            "1234", "1"
        )


@pytest.mark.asyncio
async def test_async_handle_scene_response_without_device_manager(ifsei_instance):
    """Test _async_handle_scene_response without a device manager."""
    response = "*C56780"
    ifsei_instance.device_manager = None

    with mock.patch("pyscenario.ifsei.logger") as mock_logger:
        await ifsei_instance._async_handle_scene_response(response)

        # Assert the correct log message for the scene response
        mock_logger.info.assert_any_call(
            "Scene response: %s, address: %s, state: %s", response, "5678", "0"
        )

        # Assert the log message for missing device manager
        mock_logger.info.assert_any_call(
            "Cannot handle scene response (no device manager found)"
        )
