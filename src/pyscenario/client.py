"""
IFSEI Telnet Client Module.

This module contains the IFSEITelnetClient class, a custom TelnetClient for handling
communication with IFSEI devices over Telnet. It manages the connection, sending,
and receiving of data, and handles connection loss gracefully.

"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from telnetlib3 import TelnetClient, TelnetReader, TelnetWriter

from pyscenario import Protocol, QueueManager, TaskManager
from pyscenario.const import IFSEI_ATTR_SEND_DELAY, RESPONSE_TERMINATOR

logger = logging.getLogger(__name__)


class IFSEITelnetClient(TelnetClient):
    """
    Custom TelnetClient for handling IFSEI device communication.

    This client handles the connection, sending, and receiving of data
    to and from an IFSEI device over a Telnet connection. It manages
    tasks for sending and receiving data, and can handle connection
    loss gracefully.

    Attributes
    ----------
    protocol : Protocol
        The communication protocol (TCP/UDP).
    task_manager : TaskManager
        Manager for send and receive tasks.
    queue_manager : QueueManager
        Manager for send and receive queues.
    send_delay : float
        Delay between sending commands.
    shell : Callable
        Shell function to run asynchronously.
    on_connection_lost_callback : Callable | None
        Callback when connection is lost.
    """

    def __init__(
        self,
        queue_manager: QueueManager,
        on_connection_lost_callback: Callable[[], None] | None,
        *args: tuple,
        **kwds: Any,
    ) -> None:
        """
        Initialize the IFSEITelnetClient.

        Parameters
        ----------
        queue_manager : QueueManager
            Manager for send and receive queues.
        on_connection_lost_callback : Callable | None
            Callback when connection is lost.
        *args : tuple
            Additional arguments for the TelnetClient.
        **kwds : Any
            Additional keyword arguments for the TelnetClient.
        """
        super().__init__(*args, **kwds)
        self.protocol: Protocol = Protocol.TCP
        self.task_manager = TaskManager()
        self.queue_manager = queue_manager
        self.send_delay = IFSEI_ATTR_SEND_DELAY
        self.shell = self._async_run_shell
        self.on_connection_lost_callback: Callable[[], None] | None = (
            on_connection_lost_callback
        )

    async def _async_run_shell(self, reader: TelnetReader, writer: TelnetWriter):
        """
        Run the asynchronous shell for communication.

        Parameters
        ----------
        reader : TelnetReader
            Telnet reader object.
        writer : TelnetWriter
            Telnet writer object.
        """
        await self._async_start_tasks()

    async def _async_start_tasks(self):
        """Start the asynchronous tasks for sending and receiving data."""
        self._stop_tasks()
        logger.info("Starting tasks.")
        self.task_manager.send_task = asyncio.create_task(self._async_send_data())
        self.task_manager.receive_task = asyncio.create_task(self._async_receive_data())

    def _stop_tasks(self):
        """Stop the currently running asynchronous tasks."""
        try:
            if self.task_manager.send_task is not None:
                self.task_manager.send_task.cancel()
                self.task_manager.send_task = None
                logger.info("Send task cancel requested")
        except asyncio.CancelledError:
            logger.info("Send task already cancelled.")

        try:
            if self.task_manager.receive_task is not None:
                self.task_manager.receive_task.cancel()
                self.task_manager.receive_task = None
                logger.info("Receive task cancel requested")
        except asyncio.CancelledError:
            logger.info("Receive task already cancelled.")

    async def _async_send_data(self):
        """Send data to the IFSEI device from the queue."""
        try:
            logger.info("Starting data sending loop")
            while True:
                command = await self.queue_manager.send_queue.get()
                if self.protocol == Protocol.TCP:
                    await self._async_send_command_tcp(command)
                elif self.protocol == Protocol.UDP:
                    raise NotImplementedError
                if self.writer.connection_closed:
                    logger.info("Closed connection, send data ending")
                    break
                await asyncio.sleep(self.send_delay)
        except asyncio.CancelledError:
            logger.info("Send task cancelled")

    async def _async_send_command_tcp(self, command: str) -> None:
        """
        Send a command using TCP.

        Parameters
        ----------
        command : str
            Command to be sent.
        """
        try:
            self.writer.write(command + "\r")
            await self.writer.drain()
        except ConnectionResetError:
            logger.error("Connection reset")
            raise
        except Exception as e:
            logger.error("Failed to send command %s over TCP: %s", command, e)
            raise
        else:
            logger.info("Command sent (TCP): %s", command)

    def _send_command_udp(self, command: str) -> None:
        """
        Send a command using UDP.

        Parameters
        ----------
        command : str
            Command to be sent.

        Raises
        ------
        NotImplementedError
            UDP protocol is not implemented.
        """
        raise NotImplementedError

    async def _async_receive_data(self):
        """Receive data from the IFSEI device."""
        try:
            logger.info("Starting data receiving loop")
            while True:
                response = await self._async_read_until_prompt()
                if response:
                    await self.queue_manager.receive_queue.put(response)
                if self.reader.connection_closed:
                    logger.info("Closed connection, receive data ending")
                    break
        except Exception as e:
            logger.error("Error receiving data: %s", e)
            raise

    async def _async_read_until_prompt(self) -> str:
        """
        Read data from the IFSEI device until a prompt is received.

        Returns
        -------
        str
            The response received from the device.
        """
        try:
            response = ""
            while True:
                if self.protocol == Protocol.TCP:
                    char = await self.reader.read(1)
                elif self.protocol == Protocol.UDP:
                    raise NotImplementedError
                response += char
                if (
                    response.endswith(RESPONSE_TERMINATOR)
                    or self.reader.connection_closed
                ):
                    break
            return response.strip()[:-2]
        except asyncio.exceptions.CancelledError:
            logger.info("Data receiving loop cancelled")
            raise
        except Exception as e:
            logger.error("Error reading data: %s", e)
            raise

    def connection_lost(self, exc: None | Exception, /) -> None:
        """
        Handle connection loss.

        Parameters
        ----------
        exc : None | Exception
            Exception that caused the connection loss.
        """
        super().connection_lost(exc)
        self._stop_tasks()
        if self.on_connection_lost_callback is not None:
            self.on_connection_lost_callback()

    async def async_close(self) -> None:
        """Disconnect from the IFSEI device."""
        try:
            self._stop_tasks()
            self.writer.close()
            self.reader.close()
            logger.info("Disconnected from IFSEI")
        except Exception as e:
            logger.error("Failed to disconnect: %s", e)
            raise
