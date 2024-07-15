import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pyscenario import Protocol, QueueManager
from pyscenario.client import (
    IFSEITelnetClient,  # Adjust the import based on your module's name
)
from telnetlib3 import TelnetReader, TelnetWriter

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def queue_manager():
    """Queue manager."""
    qm = MagicMock(spec=QueueManager)
    qm.send_queue = AsyncMock()
    qm.receive_queue = AsyncMock()
    return qm


@pytest.fixture
def telnet_client(queue_manager):
    """Telnet client fixture."""
    cb = MagicMock(response=None)
    client = IFSEITelnetClient(
        queue_manager=queue_manager,
        on_connection_lost_callback=cb,
        encoding="utf-8",  # Pass the encoding argument
    )
    client.writer = AsyncMock(spec=TelnetWriter)
    client.reader = AsyncMock(spec=TelnetReader)
    client.protocol = Protocol.TCP
    return client


@pytest.mark.asyncio
async def test_async_run_shell(telnet_client):
    """Test async run shell."""
    with patch.object(
        telnet_client, "_async_start_tasks", new=AsyncMock()
    ) as mock_start_tasks:
        await telnet_client._async_run_shell(telnet_client.reader, telnet_client.writer)
        mock_start_tasks.assert_called_once()


@pytest.mark.asyncio
async def test_async_start_tasks(telnet_client):
    """Test start tasks."""
    telnet_client.task_manager.send_task = None
    telnet_client.task_manager.receive_task = None

    with patch.object(
        asyncio,
        "create_task",
        side_effect=[AsyncMock(spec=asyncio.Task), AsyncMock(spec=asyncio.Task)],
    ) as mock_create_task:
        await telnet_client._async_start_tasks()
        assert telnet_client.task_manager.send_task is not None
        assert telnet_client.task_manager.receive_task is not None

        # Capture the actual calls to create_task
        calls = mock_create_task.call_args_list
        assert len(calls) == 2  # Ensure create_task was called twice

        # Extract the coroutines from the calls
        send_data_coro = calls[0][0][0]
        receive_data_coro = calls[1][0][0]

        # Check that the correct coroutines were passed to create_task
        assert isinstance(send_data_coro, type(telnet_client._async_send_data()))
        assert isinstance(receive_data_coro, type(telnet_client._async_receive_data()))


def test_stop_tasks(telnet_client):
    """Test stop taks."""
    send_task = AsyncMock(spec=asyncio.Task)
    receive_task = AsyncMock(spec=asyncio.Task)
    telnet_client.task_manager.send_task = send_task
    telnet_client.task_manager.receive_task = receive_task

    telnet_client._stop_tasks()

    send_task.cancel.assert_called_once()
    receive_task.cancel.assert_called_once()
    assert telnet_client.task_manager.send_task is None
    assert telnet_client.task_manager.receive_task is None


@pytest.mark.asyncio
async def test_async_send_data_tcp(telnet_client, queue_manager, monkeypatch):
    """Test send data."""
    command = "TEST_COMMAND"
    telnet_client.protocol = Protocol.TCP

    monkeypatch.setattr(telnet_client, "_async_send_command_tcp", AsyncMock())

    mock_get_generator = AsyncMock()
    mock_get_generator.side_effect = [command, asyncio.CancelledError]

    monkeypatch.setattr(
        telnet_client.queue_manager.send_queue, "get", mock_get_generator
    )

    await telnet_client._async_send_data()

    # Verify an item is read from the queue
    queue_manager.send_queue.get.assert_called()

    # Ensure the command is sent over TCP
    telnet_client._async_send_command_tcp.assert_called_once_with(command)


@pytest.mark.asyncio
async def test_async_send_command_tcp(telnet_client):
    """Test send command over TCP."""
    command = "TEST_COMMAND"

    # Mock the write and drain methods
    telnet_client.writer.write = AsyncMock()
    telnet_client.writer.drain = AsyncMock()

    # Test the normal execution
    await telnet_client._async_send_command_tcp(command)
    telnet_client.writer.write.assert_called_once_with(command + "\r")
    telnet_client.writer.drain.assert_awaited_once()

    # Reset the mocks for the next test
    telnet_client.writer.write.reset_mock()
    telnet_client.writer.drain.reset_mock()

    # Simulate ConnectionResetError
    telnet_client.writer.drain.side_effect = ConnectionResetError

    with pytest.raises(ConnectionResetError):
        await telnet_client._async_send_command_tcp(command)

    telnet_client.writer.write.assert_called_once_with(command + "\r")
    telnet_client.writer.drain.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_receive_data(telnet_client, monkeypatch):
    """Test receive data."""
    response = "TEST_RESPONSE"
    telnet_client.queue_manager.receive_queue = asyncio.Queue()
    telnet_client.reader.connection_closed = True

    # Replace _async_read_until_prompt using monkeypatch
    mock_read_until_prompt = AsyncMock(return_value=response)
    monkeypatch.setattr(
        telnet_client, "_async_read_until_prompt", mock_read_until_prompt
    )

    # Create a task for receiving data
    receive_task = asyncio.create_task(telnet_client._async_receive_data())

    try:
        await receive_task
    except asyncio.CancelledError:
        pass

    # Ensure _async_read_until_prompt was called
    mock_read_until_prompt.assert_called_once()

    # Check that the item is put into the queue
    assert not telnet_client.queue_manager.receive_queue.empty()
    queued_response = await telnet_client.queue_manager.receive_queue.get()
    assert queued_response == response

    # Ensure reader.connection_closed is correctly tested
    assert telnet_client.reader.connection_closed is True


def test_connection_lost(telnet_client, monkeypatch):
    """Test connection lost with callback."""
    exc = Exception("Connection lost")

    # Mock _stop_tasks method
    mock_stop_tasks = MagicMock()
    monkeypatch.setattr(telnet_client, "_stop_tasks", mock_stop_tasks)

    # Mock _transport.close method
    mock_transport_close = MagicMock()
    telnet_client._transport = MagicMock()
    monkeypatch.setattr(telnet_client._transport, "close", mock_transport_close)

    telnet_client.connection_lost(exc)

    # Assert that _stop_tasks was called
    mock_stop_tasks.assert_called_once()

    # Assert that the on_connection_lost_callback was called
    telnet_client.on_connection_lost_callback.assert_called_once()


def test_connection_lost_no_callback(telnet_client, monkeypatch):
    """Test connection lost without callback."""
    exc = Exception("Connection lost")

    telnet_client.on_connection_lost_callback = None

    # Mock _stop_tasks method
    mock_stop_tasks = MagicMock()
    monkeypatch.setattr(telnet_client, "_stop_tasks", mock_stop_tasks)

    # Mock _transport.close method
    mock_transport_close = MagicMock()
    telnet_client._transport = MagicMock()
    monkeypatch.setattr(telnet_client._transport, "close", mock_transport_close)

    telnet_client.connection_lost(exc)


@pytest.mark.asyncio
async def test_async_close(telnet_client):
    """Test async close."""
    await telnet_client.async_close()
    telnet_client.writer.close.assert_called_once()
    telnet_client.reader.close.assert_called_once()
    assert telnet_client.task_manager.send_task is None
    assert telnet_client.task_manager.receive_task is None
