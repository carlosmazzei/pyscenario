"""IFSEI Module."""

import asyncio
import json
import logging
import os
import socket
from asyncio import Queue, Task
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import telnetlib3
from telnetlib3 import TelnetClient, TelnetReader, TelnetWriter

from pyscenario.manager import DeviceManager

from .const import (
    DEVICE_FILE,
    ERROR_CODES,
    IFSEI_ATTR_BLUE,
    IFSEI_ATTR_BRIGHTNESS,
    IFSEI_ATTR_GREEN,
    IFSEI_ATTR_RED,
    IFSEI_ATTR_SEND_DELAY,
    RESPONSE_TERMINATOR,
)

logger = logging.getLogger(__name__)


class Protocol(Enum):
    """An enum that represents the supported protocols."""

    TCP = 1
    UDP = 2


@dataclass
class NetworkConfiguration:
    """A class that represents the default network configuration."""

    host: str = "192.168.1.20"
    tcp_port: int = 28000
    udp_port: int = 25200
    protocol: Protocol = Protocol.TCP


@dataclass
class QueueManager:
    """A class that manages queues."""

    send_queue: Queue
    receive_queue: Queue


@dataclass
class TaskManager:
    """A class that manages tasks."""

    send_task: Task | None = None
    receive_task: Task | None = None


class IFSEI:
    """A class that represents an IFSEI device."""

    def __init__(self, network_config: NetworkConfiguration | None = None) -> None:
        """Initialize ifsei device."""
        if network_config is None:
            self.network_config = NetworkConfiguration()
        else:
            self.network_config = network_config
        self.name = "Scenario IFSEI"
        self.connection: tuple[TelnetReader, TelnetWriter] | None = None
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Adding queues
        send_queue: Queue = Queue(100)
        receive_queue: Queue = Queue(100)
        self.queue_manager = QueueManager(send_queue, receive_queue)

        # Adding tasks
        self.process_task: Task | None = None
        self.device_manager: DeviceManager | None = None

        # Other attributes
        self.is_connected: bool = False
        self.is_closing: bool = False
        self._send_delay: float = IFSEI_ATTR_SEND_DELAY
        self._reconnect_task: Task | None = None
        self._telnetclient: IFSEITelnetClient | None = None

    @classmethod
    def from_config(cls, config_file: str):
        """Create an IFSEI object from a configuration file."""
        config = cls._load_config(config_file)
        network_config = NetworkConfiguration(
            config.get("host"),
            config.get("tcp_port"),
            config.get("udp_port"),
            Protocol[config.get("protocol", "TCP").upper()],
        )
        return cls(network_config=network_config)

    @staticmethod
    def _load_config(config_file: str) -> Any:
        """Load config file and return it."""
        logger.info("Reading from log file: %s", config_file)
        with open(config_file, encoding="utf-8") as file:
            return json.load(file)

    def load_devices(self) -> None:
        """Load device manager from config file."""
        current_module_path = __file__
        absolute_module_path = os.path.abspath(current_module_path)
        current_directory = os.path.dirname(absolute_module_path)
        target_file_name = DEVICE_FILE
        target_file_path = os.path.join(current_directory, target_file_name)
        self.device_manager = DeviceManager.from_config(target_file_path)

    def set_send_delay(self, delay: float) -> None:
        """Set send delay."""
        if self._telnetclient is not None:
            self._telnetclient.send_delay = delay
        logger.info("Send delay set to: %s", delay)

    async def async_connect(self) -> bool:
        """Connect to the IFSEI device."""
        try:
            logger.info(
                "Trying to connect to %s:%s",
                self.network_config.host,
                self.network_config.tcp_port,
            )

            if self.connection is not None:
                logger.info("Ifsei already connected")
                return True

            reader, writer = await telnetlib3.open_connection(
                self.network_config.host,
                self.network_config.tcp_port,
                client_factory=self._create_client,
            )

        except (ConnectionRefusedError, TimeoutError) as e:
            logger.error(
                "Failed to connect to %s:%s: %s.",
                self.network_config.host,
                self.network_config.tcp_port,
                e,
            )
            return False
        else:
            self.connection = (reader, writer)
            self.process_task = asyncio.create_task(self._async_process_responses())
            return True

    async def async_close(self) -> None:
        """Close client connection."""
        self.is_closing = True
        if self._telnetclient is not None:
            await self._telnetclient.async_close()

    def _create_client(self, **kwds: dict[str, Any]):
        """Create a telnet client using the factory."""
        self._telnetclient = telnetclient = IFSEITelnetClient(
            self.queue_manager, self.on_connection_lost, **kwds
        )
        return telnetclient

    def on_connection_lost(self) -> None:
        """Lost connection callback."""
        logger.info("Lost connection to ifsei")
        if self.is_closing:
            logger.info("Closing, do not start reconnect thread")
            return

        if self._reconnect_task is None:
            self.connection = None
            self._reconnect_task = asyncio.create_task(self._async_reconnect())
            self.set_is_connected(False)

    async def _async_reconnect(self) -> None:
        """Reconnect when connection is lost."""
        logger.info("Start reconnect loop")
        while True:
            try:
                await self.async_connect()
            except (TimeoutError, ConnectionError):
                logger.error("Reconnection attempt failed. Waiting for 10s")
                await asyncio.sleep(10)
            else:
                logger.info("Connection reestablished to ifsei")
                self._reconnect_task = None
                break

    async def async_send_command(self, command: str) -> None:
        """Send a command to the send queue."""
        await self.queue_manager.send_queue.put(command)

    async def _async_process_responses(self):
        """Process responses from the IFSEI device."""
        try:
            logger.info("Starting response processing loop")
            while True:
                response = await self.queue_manager.receive_queue.get()
                await self._async_handle_response(response)
        except asyncio.CancelledError:
            logger.info("Process responses task cancelled")
        except Exception as e:
            logger.error("Error processing responses: %s", e)
            raise

    async def _async_handle_response(self, response: str) -> None:
        """Handle a response from the IFSEI device."""
        logger.info("Received response: %s", response)

        if response == "*IFSEION":
            self.set_is_connected(True)
            await self.async_monitor(7)

        elif response.startswith("*Z"):
            await self._async_handle_zone_response(response)

        elif response.startswith("*C"):
            await self._async_handle_scene_response(response)

        if response.startswith("E"):
            await self._async_handle_error(response)

    async def _async_handle_zone_response(self, response: str) -> None:
        """Handle a zone response from the IFSEI device."""
        # Dimmer Status: *Z{module_number:2}{channel:2}L{level:3}
        module_number = int(response[2:4])
        channel = int(response[4:6])
        intensity = int(response[7:10])
        logger.info(
            "Zone %s state: %s intensity: %s", module_number, channel, intensity
        )

        if self.device_manager is not None:
            await self.device_manager.async_handle_zone_state_change(
                module_number, channel, intensity
            )
        else:
            logger.info("Cannot handle zone response (no device manager found)")

    async def _async_handle_scene_response(self, response: str):
        """Handle a scene response from the IFSEI device."""
        # Scene status: *C{address:4}{state:1} 1/0
        address = str(response[2:6])
        state = str(response[6:7])
        logger.info(
            "Scene response: %s, address: %s, state: %s", response, address, state
        )

        if self.device_manager is not None:
            await self.device_manager.async_handle_scene_state_change(address, state)
        else:
            logger.info("Cannot handle scene response (no device manager found)")

    async def _async_handle_error(self, response: str):
        """Handle an error response from the IFSEI device."""
        error_code = response.strip().split(" ")[0]
        error_message = ERROR_CODES.get(error_code, f"Unknown error code: {error_code}")
        if error_code.startswith("E3"):
            module_address = error_code[2:]
            error_message += f" Module Address: {module_address}"
        logger.error(error_message)

    def set_protocol(self, protocol: Protocol = Protocol.TCP) -> None:
        """Set the protocol to use for communication."""
        self.network_config.protocol = protocol

    def get_device_id(self) -> str:
        """Get device unique id."""
        return f"ifsei-scenario-{self.network_config.host}"

    def set_is_connected(self, is_available: bool = False) -> None:
        """Set connection status."""
        self.is_connected = is_available
        if self.device_manager is not None:
            logger.info("Set ifsei availability to: %s", is_available)
            kwargs = {"available": str(is_available)}
            self.device_manager.notify_subscriber(**kwargs)
        else:
            logger.info("Cannot set device availability (no device manager found)")

    # Commands for control/configuration
    async def async_get_version(self) -> None:
        """Get the IFSEI version."""
        await self.async_send_command("$VER")

    async def async_get_ip(self) -> None:
        """Get the IP address."""
        await self.async_send_command("$IP")

    async def async_get_gateway(self) -> None:
        """Get the gateway."""
        await self.async_send_command("$GATEWAY")

    async def async_get_netmask(self) -> None:
        """Get the netmask."""
        await self.async_send_command("$NETMASK")

    async def async_get_tcp_port(self) -> None:
        """Get the TCP port."""
        await self.async_send_command("$PORT TCP")

    async def async_get_udp_port(self) -> None:
        """Get UDP port."""
        await self.async_send_command("$PORT UDP")

    async def async_monitor(self, level: int) -> None:
        """Monitor the network."""
        if level < 1 or level > 7:
            raise ValueError("Monitor level must be between 1 and 7")
        await self.async_send_command(f"MON{level}")

    async def async_update_light_state(self, device_id: str, colors: list) -> None:
        """Update light state."""
        if len(colors) != 4:
            raise ValueError("List must have exactly 4 elements")

        if self.device_manager is None:
            logger.error("Cannot update light state (no device manager found)")
            return

        for device in self.device_manager.lights:
            if device.unique_id == device_id:
                # Propagate changes to every address
                for address in device.address:
                    value = 0
                    if address["name"] == IFSEI_ATTR_RED:
                        value = colors[0]
                    elif address["name"] == IFSEI_ATTR_GREEN:
                        value = colors[1]
                    elif address["name"] == IFSEI_ATTR_BLUE:
                        value = colors[2]
                    elif address["name"] == IFSEI_ATTR_BRIGHTNESS:
                        value = colors[3]

                    await self.async_set_zone_intensity(
                        address["module"],
                        address["channel"],
                        value,
                    )
                return

    async def async_update_cover_state(self, device_id: str, address: str) -> None:
        """Update cover state."""
        if self.device_manager is None:
            logger.error("Cannot update cover state (no device manager found)")
            return

        for device in self.device_manager.covers:
            if device.unique_id == device_id:
                await self.async_set_shader_state(address)

    # Commands for the Scenario Classic-NET network
    async def async_change_scene(self, module_address: str, scene_number: str) -> None:
        """Change the scene."""
        await self.async_send_command(f"D{module_address:02}C{scene_number:02}")

    async def async_toggle_zone(
        self, module_address: str, zone_number: str, state: str
    ) -> None:
        """Toggle the zone."""
        return await self.async_send_command(
            f"$D{module_address:02}Z{zone_number}{state}"
        )

    async def async_get_scene_status(self, module_address: str) -> None:
        """Get scene status."""
        return await self.async_send_command(f"$D{module_address:02}ST")

    async def async_set_zone_intensity(
        self, module_address: str, channel: str, intensity: int
    ) -> None:
        """Set zone intensity."""
        return await self.async_send_command(
            f"Z{module_address:02}{channel:01}L{intensity:03}T1"
        )

    async def async_set_shader_state(self, module_address: str) -> None:
        """Set shader state."""
        return await self.async_send_command(f"C{module_address:04}")

    async def async_get_zone_intensity(
        self, module_address: str, zone_number: str
    ) -> None:
        """Get zone intensity."""
        return await self.async_send_command(f"$D{module_address:02}Z{zone_number}I")

    async def async_increase_scene_intensity(self, module_address: str) -> None:
        """Increase scene intensity."""
        return await self.async_send_command(f"$D{module_address:02}C+")

    async def async_decrease_scene_intensity(self, module_address: str) -> None:
        """Decrease scene intensity."""
        return await self.async_send_command(f"$D{module_address:02}C-")

    async def async_increase_zone_intensity(
        self, module_address: str, zone_number: str
    ) -> None:
        """Increase zone intensity."""
        return await self.async_send_command(f"$D{module_address:02}Z{zone_number}+")

    async def async_decrease_zone_intensity(
        self, module_address: str, zone_number: str
    ) -> None:
        """Decrease zone intensity."""
        return await self.async_send_command(f"$D{module_address:02}Z{zone_number}-")

    async def async_record_scene(self, module_address: str) -> None:
        """Record scene.

        Command: $D{module_address:02}GRAVA"
        """
        raise NotImplementedError

    async def async_get_module_configuration(
        self, module_address: str, setup_number: str
    ) -> None:
        """Get module configuration."""
        return await self.async_send_command(f"$D{module_address:02}P{setup_number}ST")

    async def async_execute_macro_key_press(self, prid: str, key_number: str) -> None:
        """Execute macro key press."""
        return await self.async_send_command(f"I{prid}{key_number}P")

    async def async_execute_macro_key_release(self, prid: str, key_number: str) -> None:
        """Execute macro key release."""
        return await self.async_send_command(f"I{prid}{key_number}R")


class IFSEITelnetClient(TelnetClient):
    """Protocol to have the base client."""

    def __init__(
        self,
        queue_manager: QueueManager,
        on_connection_lost_callback: Callable[[], None] | None,
        *args: tuple,
        **kwds: Any,
    ) -> None:
        """Initialize protocol to handle connection errors."""
        super().__init__(*args, **kwds)
        self.protocol: Protocol = Protocol.TCP
        self.task_manager = TaskManager()
        self.queue_manager = queue_manager
        self.send_delay = IFSEI_ATTR_SEND_DELAY
        self.shell = self._async_run_shell
        self.on_connection_lost_callback: Callable[[], None] | None = (
            on_connection_lost_callback
        )

    async def _async_start_tasks(self):
        """Start tasks."""
        self._stop_tasks()
        logger.info("Starting tasks.")
        self.task_manager.send_task = asyncio.create_task(self._async_send_data())
        self.task_manager.receive_task = asyncio.create_task(self._async_receive_data())

    def _stop_tasks(self):
        """Stop tasks."""
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
        """Send command using TCP."""
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
        """Send command using UDP."""
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

    async def _async_read_until_prompt(self):
        """Read data from the IFSEI device until a prompt is received."""
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
        """Call when connection is lost."""
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
            logger.info("Disconnected from ifsei")
        except Exception as e:
            logger.error("Failed to disconnect: %s", e)
            raise
