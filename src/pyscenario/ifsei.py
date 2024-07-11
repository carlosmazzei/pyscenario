"""
IFSEI Module.

This module contains the IFSEI class, which represents an IFSEI device. It provides methods to manage
the connection, send commands, and handle responses from the device.

Classes:
    IFSEI: Represents an IFSEI device and provides methods to interact with it.

Functions:
    from_config: Creates an IFSEI object from a configuration file.
    _load_config: Loads a configuration file and returns its content.
    load_devices: Loads the device manager from a configuration file.
    set_send_delay: Sets the delay for sending commands.
    async_connect: Asynchronously connects to the IFSEI device.
    async_close: Asynchronously closes the connection to the IFSEI device.
    _create_client: Creates a telnet client using a factory.
    on_connection_lost: Callback for lost connection.
    _async_reconnect: Asynchronously attempts to reconnect when the connection is lost.
    async_send_command: Asynchronously sends a command to the send queue.
    _async_process_responses: Asynchronously processes responses from the IFSEI device.
    _async_handle_response: Asynchronously handles a response from the IFSEI device.
    _async_handle_zone_response: Asynchronously handles a zone response from the IFSEI device.
    _async_handle_scene_response: Asynchronously handles a scene response from the IFSEI device.
    _async_handle_error: Asynchronously handles an error response from the IFSEI device.
    set_protocol: Sets the communication protocol.
    get_device_id: Returns the unique ID of the device.
    set_is_connected: Sets the connection status.
    async_get_version: Asynchronously gets the IFSEI version.
    async_get_ip: Asynchronously gets the IP address.
    async_get_gateway: Asynchronously gets the gateway.
    async_get_netmask: Asynchronously gets the netmask.
    async_get_tcp_port: Asynchronously gets the TCP port.
    async_get_udp_port: Asynchronously gets the UDP port.
    async_monitor: Asynchronously monitors the network.
    async_update_light_state: Asynchronously updates the light state.
    async_update_cover_state: Asynchronously updates the cover state.
    async_change_scene: Asynchronously changes the scene.
    async_toggle_zone: Asynchronously toggles the zone.
    async_get_scene_status: Asynchronously gets the scene status.
    async_set_zone_intensity: Asynchronously sets the zone intensity.
    async_set_shader_state: Asynchronously sets the shader state.
    async_get_zone_intensity: Asynchronously gets the zone intensity.
    async_increase_scene_intensity: Asynchronously increases the scene intensity.
    async_decrease_scene_intensity: Asynchronously decreases the scene intensity.
    async_increase_zone_intensity: Asynchronously increases the zone intensity.
    async_decrease_zone_intensity: Asynchronously decreases the zone intensity.
    async_record_scene: Asynchronously records a scene.
    async_get_module_configuration: Asynchronously gets the module configuration.
    async_execute_macro_key_press: Asynchronously executes a macro key press.
    async_execute_macro_key_release: Asynchronously executes a macro key release.
"""

import asyncio
import json
import logging
import os
import socket
from asyncio import Queue, Task
from ipaddress import IPv4Address
from typing import Any

import telnetlib3
from telnetlib3 import TelnetReader, TelnetWriter

from pyscenario import NetworkConfiguration, Protocol, QueueManager
from pyscenario.client import IFSEITelnetClient
from pyscenario.manager import DeviceManager

from .const import (
    DEVICE_FILE,
    ERROR_CODES,
    IFSEI_ATTR_BLUE,
    IFSEI_ATTR_BRIGHTNESS,
    IFSEI_ATTR_GREEN,
    IFSEI_ATTR_RED,
    IFSEI_ATTR_SEND_DELAY,
)

logger = logging.getLogger(__name__)


class IFSEI:
    """
    A class that represents an IFSEI device.

    Attributes
    ----------
        network_config (NetworkConfiguration): Configuration for network settings.
        name (str): Name of the IFSEI device.
        connection (tuple[TelnetReader, TelnetWriter] | None): Connection tuple for telnet.
        udp_socket (socket.socket): UDP socket for communication.
        queue_manager (QueueManager): Manages send and receive queues.
        process_task (Task | None): Task for processing responses.
        device_manager (DeviceManager | None): Manages the devices.
        is_connected (bool): Connection status.
        is_closing (bool): Closing status.
        _send_delay (float): Delay for sending commands.
        _reconnect_task (Task | None): Task for reconnecting.
        _telnetclient (IFSEITelnetClient | None): Telnet client.
    """

    def __init__(self, network_config: NetworkConfiguration | None = None) -> None:
        """
        Initialize an IFSEI device.

        Args:
            network_config (NetworkConfiguration | None): Configuration for network settings.
                If None, a default configuration is used.
        """
        if network_config is None:
            self.network_config = NetworkConfiguration()
        else:
            self._validate_network_config(network_config)
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
        """
        Create an IFSEI object from a configuration file.

        Args:
            config_file (str): Path to the configuration file.

        Returns
        -------
            IFSEI: An instance of the IFSEI class.
        """
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
        """
        Load a configuration file and return its content.

        Args:
            config_file (str): Path to the configuration file.

        Returns
        -------
            dict: Configuration data.
        """
        logger.info("Reading from log file: %s", config_file)
        with open(config_file, encoding="utf-8") as file:
            return json.load(file)

    def load_devices(self, file: str | None) -> None:
        """Load the device manager from the configuration file.

        Args:
            file (str | None): Path to the configuration file. If None,
            it will be loaded from the current directory.

        This method loads the device manager using the DEVICE_FILE constant.
        """
        if file is None:
            current_module_path = __file__
            absolute_module_path = os.path.abspath(current_module_path)
            current_directory = os.path.dirname(absolute_module_path)
            target_file_name = DEVICE_FILE
            file = os.path.join(current_directory, target_file_name)

        self.device_manager = DeviceManager.from_config(file)

    def _validate_network_config(self, network_config: NetworkConfiguration) -> bool:
        """Validate the network configuration."""
        IPv4Address(network_config)
        if not (0 <= network_config.tcp_port <= 65535):
            raise ValueError("Invalid TCP port") from None
        if network_config.protocol not in [Protocol.TCP, Protocol.UDP]:
            raise ValueError("Invalid protocol") from None
        return True

    def set_send_delay(self, delay: float) -> None:
        """
        Set the delay for sending commands.

        Args:
            delay (float): Delay in seconds.
        """
        if self._telnetclient is not None:
            self._telnetclient.send_delay = delay
        logger.info("Send delay set to: %s", delay)

    async def async_connect(self) -> bool:
        """
        Asynchronously connect to the IFSEI device.

        Returns
        -------
            bool: True if connection is successful, False otherwise.
        """
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
        """Asynchronously close the client connection."""
        self.is_closing = True
        if self._telnetclient is not None:
            await self._telnetclient.async_close()
            self.connection = None

    def _create_client(self, **kwds: dict[str, Any]):
        """
        Create a telnet client using the factory.

        Args:
            **kwds (dict[str, Any]): Keyword arguments for the client.

        Returns
        -------
            IFSEITelnetClient: The created telnet client.
        """
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
        """Asynchronously attempt to reconnect when the connection is lost."""
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
        """
        Asynchronously send a command to the send queue.

        Args:
            command (str): The command to send.
        """
        await self.queue_manager.send_queue.put(command)

    async def _async_process_responses(self):
        """Asynchronously process responses from the IFSEI device."""
        try:
            logger.info("Starting response processing loop")
            while True:
                response = await self.queue_manager.receive_queue.get()
                await self._async_handle_response(response)
        except asyncio.CancelledError:
            logger.info("Process responses task cancelled")
        except RuntimeError:
            logger.info("Runtime error in response processing loop")
        except Exception as e:
            logger.error("Error processing responses: %s", e)
            raise

    async def _async_handle_response(self, response: str) -> None:
        """
        Asynchronously handle a response from the IFSEI device.

        Args:
            response (str): The response to handle.
        """
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
        """
        Asynchronously handle a zone response from the IFSEI device.

        Args:
            response (str): The zone response to handle.
        """
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
        """
        Asynchronously handle a scene response from the IFSEI device.

        Args:
            response (str): The scene response to handle.
        """
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
        """
        Asynchronously handle an error response from the IFSEI device.

        Args:
            response (str): The error response to handle.
        """
        error_code = response.strip().split(" ")[0]
        error_message = ERROR_CODES.get(error_code, f"Unknown error code: {error_code}")
        if error_code.startswith("E3"):
            module_address = error_code[2:]
            error_message += f" Module Address: {module_address}"
        logger.error(error_message)

    def set_protocol(self, protocol: Protocol = Protocol.TCP) -> None:
        """
        Set the protocol to use for communication.

        Args:
            protocol (Protocol): The protocol to use (default is TCP).
        """
        self.network_config.protocol = protocol

    def get_device_id(self) -> str:
        """
        Get the unique ID of the device.

        Returns
        -------
            str: The unique ID of the device.
        """
        return f"ifsei-scenario-{self.network_config.host}"

    def set_is_connected(self, is_available: bool = False) -> None:
        """
        Set the connection status.

        Args:
            is_available (bool): Connection status (default is False).
        """
        self.is_connected = is_available
        if self.device_manager is not None:
            logger.info("Set ifsei availability to: %s", is_available)
            kwargs = {"available": str(is_available)}
            self.device_manager.notify_subscriber(**kwargs)
        else:
            logger.info("Cannot set device availability (no device manager found)")

    # Commands for control/configuration
    async def async_get_version(self) -> None:
        """Asynchronously get the IFSEI version."""
        await self.async_send_command("$VER")

    async def async_get_ip(self) -> None:
        """Asynchronously get the IP address."""
        await self.async_send_command("$IP")

    async def async_get_gateway(self) -> None:
        """Asynchronously get the gateway."""
        await self.async_send_command("$GATEWAY")

    async def async_get_netmask(self) -> None:
        """Asynchronously get the netmask."""
        await self.async_send_command("$NETMASK")

    async def async_get_tcp_port(self) -> None:
        """Asynchronously get the TCP port."""
        await self.async_send_command("$PORT TCP")

    async def async_get_udp_port(self) -> None:
        """Asynchronously get the UDP port."""
        await self.async_send_command("$PORT UDP")

    async def async_monitor(self, level: int) -> None:
        """
        Asynchronously monitor the network.

        Args:
            level (int): Monitoring level (must be between 1 and 7).

        Raises
        ------
            ValueError: If the monitoring level is not between 1 and 7.
        """
        if level < 1 or level > 7:
            raise ValueError("Monitor level must be between 1 and 7")
        await self.async_send_command(f"MON{level}")

    async def async_update_light_state(self, device_id: str, colors: list) -> None:
        """
        Asynchronously update the light state.

        Args:
            device_id (str): The device ID.
            colors (list): List of colors (must have exactly 4 elements).

        Raises
        ------
            ValueError: If the list does not have exactly 4 elements.
        """
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
        """
        Asynchronously update the cover state.

        Args:
            device_id (str): The device ID.
            address (str): The address to update.

        Raises
        ------
            logger.error: If no device manager is found.
        """
        if self.device_manager is None:
            logger.error("Cannot update cover state (no device manager found)")
            return

        for device in self.device_manager.covers:
            if device.unique_id == device_id:
                await self.async_set_shader_state(address)

    # Commands for the Scenario Classic-NET network
    async def async_change_scene(self, module_address: str, scene_number: str) -> None:
        """
        Asynchronously change the scene.

        Args:
            module_address (str): The module address.
            scene_number (str): The scene number.
        """
        await self.async_send_command(f"D{module_address:02}C{scene_number:02}")

    async def async_toggle_zone(
        self, module_address: str, zone_number: str, state: str
    ) -> None:
        """
        Asynchronously toggle the zone.

        Args:
            module_address (str): The module address.
            zone_number (str): The zone number.
            state (str): The state to set (1 or 0).
        """
        return await self.async_send_command(
            f"$D{module_address:02}Z{zone_number}{state}"
        )

    async def async_get_scene_status(self, module_address: str) -> None:
        """
               Asynchronously get the scene status.

               Args:


        module_address (str): The module address.
        """
        return await self.async_send_command(f"$D{module_address:02}ST")

    async def async_set_zone_intensity(
        self, module_address: str, channel: str, intensity: int
    ) -> None:
        """
        Asynchronously set the zone intensity.

        Args:
            module_address (str): The module address.
            channel (str): The channel.
            intensity (int): The intensity to set.
        """
        return await self.async_send_command(
            f"Z{module_address:02}{channel:01}L{intensity:03}T1"
        )

    async def async_set_shader_state(self, module_address: str) -> None:
        """
        Asynchronously set the shader state.

        Args:
            module_address (str): The module address.
        """
        return await self.async_send_command(f"C{module_address:04}")

    async def async_get_zone_intensity(
        self, module_address: str, zone_number: str
    ) -> None:
        """
        Asynchronously get the zone intensity.

        Args:
            module_address (str): The module address.
            zone_number (str): The zone number.
        """
        return await self.async_send_command(f"$D{module_address:02}Z{zone_number}I")

    async def async_increase_scene_intensity(self, module_address: str) -> None:
        """
        Asynchronously increase the scene intensity.

        Args:
            module_address (str): The module address.
        """
        return await self.async_send_command(f"$D{module_address:02}C+")

    async def async_decrease_scene_intensity(self, module_address: str) -> None:
        """
        Asynchronously decrease the scene intensity.

        Args:
            module_address (str): The module address.
        """
        return await self.async_send_command(f"$D{module_address:02}C-")

    async def async_increase_zone_intensity(
        self, module_address: str, zone_number: str
    ) -> None:
        """
        Asynchronously increase the zone intensity.

        Args:
            module_address (str): The module address.
            zone_number (str): The zone number.
        """
        return await self.async_send_command(f"$D{module_address:02}Z{zone_number}+")

    async def async_decrease_zone_intensity(
        self, module_address: str, zone_number: str
    ) -> None:
        """
        Asynchronously decrease the zone intensity.

        Args:
            module_address (str): The module address.
            zone_number (str): The zone number.
        """
        return await self.async_send_command(f"$D{module_address:02}Z{zone_number}-")

    async def async_record_scene(self, module_address: str) -> None:
        """
        Asynchronously record a scene.

        Args:
            module_address (str): The module address.

        Raises
        ------
            NotImplementedError: This feature is not yet implemented.
        """
        raise NotImplementedError

    async def async_get_module_configuration(
        self, module_address: str, setup_number: str
    ) -> None:
        """
        Asynchronously get the module configuration.

        Args:
            module_address (str): The module address.
            setup_number (str): The setup number.
        """
        return await self.async_send_command(f"$D{module_address:02}P{setup_number}ST")

    async def async_execute_macro_key_press(self, prid: str, key_number: str) -> None:
        """
        Asynchronously execute a macro key press.

        Args:
            prid (str): The PRID.
            key_number (str): The key number.
        """
        return await self.async_send_command(f"I{prid}{key_number}P")

    async def async_execute_macro_key_release(self, prid: str, key_number: str) -> None:
        """
        Asynchronously execute a macro key release.

        Args:
            prid (str): The PRID.
            key_number (str): The key number.
        """
        return await self.async_send_command(f"I{prid}{key_number}R")
