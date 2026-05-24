"""
IFSEI Module.

This module contains the IFSEI class, which represents an IFSEI device. It provides methods to manage
the connection, send commands, and handle responses from the device.

"""

import asyncio
import json
import logging
import os
from asyncio import Queue, Task
from ipaddress import IPv4Address
from typing import Any, List, Optional, Tuple

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
    QUEUE_MAX_SIZE,
)

logger = logging.getLogger(__name__)


class IFSEI:
    """
    A class that represents an IFSEI device.

    Attributes
    ----------
    network_config (NetworkConfiguration): Configuration for network settings.
    name (str): Name of the IFSEI device.
    connection (Optional[Tuple[TelnetReader, TelnetWriter]]): Connection tuple for telnet.
    queue_manager (QueueManager): Manages send and receive queues.
    process_task (Optional[Task]): Task for processing responses.
    device_manager (Optional[DeviceManager]): Manages the devices.
    is_connected (bool): Connection status.
    is_closing (bool): Closing status.
    _send_delay (float): Delay for sending commands.
    _reconnect_task (Optional[Task]): Task for reconnecting.
    _telnetclient (Optional[IFSEITelnetClient]): Telnet client.
    """

    def __init__(self, network_config: Optional[NetworkConfiguration] = None) -> None:
        """
        Initialize an IFSEI device.

        Args:
            network_config (Optional[NetworkConfiguration]): Configuration for network settings.
                If None, a default configuration is used.
        """
        if network_config is None:
            self.network_config = NetworkConfiguration()
        else:
            self._validate_network_config(network_config)
            self.network_config = network_config

        self.name = "Scenario IFSEI"
        self.connection: Optional[Tuple[TelnetReader, TelnetWriter]] = None

        # Adding queues
        send_queue: Queue = Queue(QUEUE_MAX_SIZE)
        receive_queue: Queue = Queue(QUEUE_MAX_SIZE)
        self.queue_manager = QueueManager(send_queue, receive_queue)

        # Adding tasks
        self.process_task: Optional[Task] = None
        self.device_manager: Optional[DeviceManager] = None

        # Other attributes
        self.is_connected: bool = False
        self.is_closing: bool = False
        self._send_delay: float = IFSEI_ATTR_SEND_DELAY
        self._reconnect_task: Optional[Task] = None
        self._telnetclient: Optional[IFSEITelnetClient] = None

        logger.debug(
            "[host=%s:%s protocol=%s reconnect=%s send_delay=%s] IFSEI instance created",
            self.network_config.host,
            self.network_config.tcp_port,
            self.network_config.protocol.name,
            self.network_config.reconnect,
            self._send_delay,
        )

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
        protocol = Protocol[config.get("protocol", "TCP").upper()]
        network_config = NetworkConfiguration(
            host=config.get("host"),
            tcp_port=int(config.get("tcp_port", 23)),
            udp_port=int(config.get("udp_port", 23)),
            protocol=protocol,
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
        logger.debug("[config=%s] reading from config file", config_file)
        with open(config_file, encoding="utf-8") as file:
            return json.load(file)

    def load_devices(self, file: Optional[str] = None) -> None:
        """
        Load the device manager from the configuration file.

        Args:
            file (Optional[str]): Path to the configuration file. If None,
                it will be loaded from the current directory.

        This method loads the device manager using the DEVICE_FILE constant.
        """
        if file is None:
            current_directory = os.path.dirname(os.path.abspath(__file__))
            file = os.path.join(current_directory, DEVICE_FILE)

        logger.debug("[file=%s] loading devices", file)
        self.device_manager = DeviceManager.from_config(file)

    def _validate_network_config(self, network_config: NetworkConfiguration) -> bool:
        """Validate the network configuration."""
        try:
            IPv4Address(network_config.host)
            if not (0 <= int(network_config.tcp_port) <= 65535):
                raise ValueError("Invalid TCP port")
            if network_config.protocol not in [Protocol.TCP, Protocol.UDP]:
                raise ValueError("Invalid protocol")
        except ValueError as e:
            logger.error(
                "[host=%s tcp_port=%s protocol=%s] invalid network configuration: %s",
                network_config.host,
                network_config.tcp_port,
                network_config.protocol,
                e,
            )
            raise
        return True

    def set_reconnect_options(self, reconnect: bool, delay: float) -> None:
        """
        Set the reconnect options for the IFSEI device.

        Args:
            reconnect (bool): Whether to reconnect or not.
            delay (float): Delay in seconds between reconnect attempts.
        """
        self.network_config.reconnect = reconnect
        self.network_config.reconnect_delay = delay
        logger.info("[reconnect=%s delay=%s] reconnect options set", reconnect, delay)

    def set_send_delay(self, delay: float) -> None:
        """
        Set the delay for sending commands.

        Args:
            delay (float): Delay in seconds.
        """
        self._send_delay = delay
        if self._telnetclient is not None:
            self._telnetclient.send_delay = delay
            logger.info("[delay=%s] send delay updated", delay)
        else:
            logger.warning(
                "[delay=%s] cannot set send delay: telnetclient not initialized",
                delay,
            )

    async def async_connect(self) -> bool:
        """
        Asynchronously connect to the IFSEI device.

        Returns
        -------
            bool: True if connection is successful, False otherwise.
        """
        try:
            logger.info(
                "[host=%s:%s] connecting",
                self.network_config.host,
                self.network_config.tcp_port,
            )

            if self.connection is not None:
                logger.debug(
                    "[host=%s:%s] already connected, skipping",
                    self.network_config.host,
                    self.network_config.tcp_port,
                )
                return True

            reader, writer = await telnetlib3.open_connection(
                self.network_config.host,
                self.network_config.tcp_port,
                client_factory=self._create_client,
            )

            self.connection = (reader, writer)
            self.process_task = asyncio.create_task(self._async_process_responses())
            logger.info(
                "[host=%s:%s] connected",
                self.network_config.host,
                self.network_config.tcp_port,
            )
            return True

        except (ConnectionRefusedError, TimeoutError) as e:
            logger.error(
                "[host=%s:%s] failed to connect: %s",
                self.network_config.host,
                self.network_config.tcp_port,
                e,
            )

            if self.network_config.reconnect:
                self._reconnect()

            return False

    def _reconnect(self) -> None:
        """Start reconnect task."""
        if self.is_closing:
            logger.debug(
                "[host=%s:%s] is_closing=True, not starting reconnect task",
                self.network_config.host,
                self.network_config.tcp_port,
            )
            return

        if self._reconnect_task is None or self._reconnect_task.done():
            logger.debug(
                "[host=%s:%s delay=%s] starting reconnect task",
                self.network_config.host,
                self.network_config.tcp_port,
                self.network_config.reconnect_delay,
            )
            self.connection = None
            self._reconnect_task = asyncio.create_task(self._async_reconnect())
            self.set_is_connected(False)
        else:
            logger.debug(
                "[host=%s:%s] reconnect task already running",
                self.network_config.host,
                self.network_config.tcp_port,
            )

    async def async_close(self) -> None:
        """Asynchronously close the client connection."""
        logger.info(
            "[host=%s:%s] closing IFSEI connection",
            self.network_config.host,
            self.network_config.tcp_port,
        )
        self.is_closing = True
        if self._telnetclient is not None:
            await self._telnetclient.async_close()
            self.connection = None

        if self.process_task is not None:
            self.process_task.cancel()
            try:
                await self.process_task
            except asyncio.CancelledError:
                pass
            self.process_task = None
            logger.debug("process task cancelled")

        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None
            logger.debug("reconnect task cancelled")

    def _create_client(self, **kwargs: Any):
        """
        Create a telnet client using the factory.

        Args:
            **kwargs (Any): Keyword arguments for the client.

        Returns
        -------
            IFSEITelnetClient: The created telnet client.
        """
        self._telnetclient = IFSEITelnetClient(
            self.queue_manager, self.on_connection_lost, **kwargs
        )
        self._telnetclient.protocol = self.network_config.protocol
        self._telnetclient.send_delay = self._send_delay
        logger.debug(
            "[protocol=%s send_delay=%s] telnet client created",
            self.network_config.protocol.name,
            self._send_delay,
        )
        return self._telnetclient

    def on_connection_lost(self) -> None:
        """Handle connection lost event."""
        logger.warning(
            "[host=%s:%s] connection to IFSEI lost",
            self.network_config.host,
            self.network_config.tcp_port,
        )
        self.set_is_connected(False)
        self._reconnect()

    async def _async_reconnect(self) -> None:
        """Asynchronously attempt to reconnect when the connection is lost."""
        logger.debug(
            "[host=%s:%s delay=%s] starting reconnect loop",
            self.network_config.host,
            self.network_config.tcp_port,
            self.network_config.reconnect_delay,
        )
        while not self.is_closing:
            try:
                if await self.async_connect():
                    logger.info(
                        "[host=%s:%s] reconnected to IFSEI",
                        self.network_config.host,
                        self.network_config.tcp_port,
                    )
                    self._reconnect_task = None
                    break
                else:
                    logger.error(
                        "[host=%s:%s delay=%s] reconnection attempt failed, waiting",
                        self.network_config.host,
                        self.network_config.tcp_port,
                        self.network_config.reconnect_delay,
                    )
                    await asyncio.sleep(self.network_config.reconnect_delay)
            except asyncio.CancelledError:
                logger.debug("reconnect task cancelled inside loop")
                break
            except Exception as e:
                logger.error(
                    "[host=%s:%s] unexpected reconnect error: %s",
                    self.network_config.host,
                    self.network_config.tcp_port,
                    e,
                )
                await asyncio.sleep(self.network_config.reconnect_delay)
        logger.debug("reconnect loop ended")

    async def async_send_command(self, command: str) -> None:
        """
        Asynchronously send a command to the send queue.

        Args:
            command (str): The command to send.
        """
        logger.debug("[cmd=%s] enqueued for send", command)
        await self.queue_manager.send_queue.put(command)

    async def _async_process_responses(self) -> None:
        """Asynchronously process responses from the IFSEI device."""
        logger.debug("starting response processing loop")
        while True:
            try:
                response = await self.queue_manager.receive_queue.get()
                await self._async_handle_response(response)
            except asyncio.CancelledError:
                logger.debug("process responses task cancelled")
                break
            except Exception as e:
                logger.error("error processing responses: %s", e)
                break

    async def _async_handle_response(self, response: str) -> None:
        """
        Asynchronously handle a response from the IFSEI device.

        Args:
            response (str): The response to handle.
        """
        logger.debug("[response=%s] dispatching", response)

        if response == "*IFSEION":
            logger.debug("[response=%s] IFSEI ready signal received", response)
            self.set_is_connected(True)
            await self.async_monitor(7)

        elif response.startswith("*Z"):
            await self._async_handle_zone_response(response)

        elif response.startswith("*C"):
            await self._async_handle_scene_response(response)

        elif response.startswith("E"):
            await self._async_handle_error(response)
        else:
            logger.debug("[response=%s] unknown response, ignored", response)

    async def _async_handle_zone_response(self, response: str) -> None:
        """
        Asynchronously handle a zone response from the IFSEI device.

        Args:
            response (str): The zone response to handle.
        """
        try:
            # Dimmer Status: *Z{module_number:2}{channel:2}L{level:3}
            module_number = int(response[2:4])
            channel = int(response[4:6])
            intensity = int(response[7:10])
            logger.debug(
                "[module=%02d channel=%02d intensity=%d] zone response parsed",
                module_number,
                channel,
                intensity,
            )

            if self.device_manager is not None:
                await self.device_manager.async_handle_zone_state_change(
                    module_number, channel, intensity
                )
            else:
                logger.warning(
                    "[module=%02d channel=%02d] cannot handle zone response: device_manager not loaded",
                    module_number,
                    channel,
                )
        except ValueError as e:
            logger.error("[response=%s] error parsing zone response: %s", response, e)

    async def _async_handle_scene_response(self, response: str) -> None:
        """
        Asynchronously handle a scene response from the IFSEI device.

        Args:
            response (str): The scene response to handle.
        """
        try:
            # Scene status: *C{address:4}{state:1} 1/0
            address = response[2:6]
            state = response[6:7]
            logger.debug("[address=%s state=%s] scene response parsed", address, state)

            if self.device_manager is not None:
                await self.device_manager.async_handle_scene_state_change(
                    address, state
                )
            else:
                logger.warning(
                    "[address=%s state=%s] cannot handle scene response: device_manager not loaded",
                    address,
                    state,
                )
        except Exception as e:
            logger.error("[response=%s] error parsing scene response: %s", response, e)

    async def _async_handle_error(self, response: str) -> None:
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
        logger.error(
            "[error_code=%s] device reported error: %s", error_code, error_message
        )

    def set_protocol(self, protocol: Protocol = Protocol.TCP) -> None:
        """
        Set the protocol to use for communication.

        Args:
            protocol (Protocol): The protocol to use (default is TCP).
        """
        previous = self.network_config.protocol
        self.network_config.protocol = protocol
        logger.info(
            "[protocol=%s previous=%s] protocol updated",
            protocol.name,
            previous.name,
        )

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
            logger.info(
                "[available=%s host=%s:%s] IFSEI availability changed",
                is_available,
                self.network_config.host,
                self.network_config.tcp_port,
            )
            kwargs = {"available": str(is_available)}
            self.device_manager.notify_subscriber(**kwargs)
        else:
            logger.warning(
                "[available=%s] cannot propagate availability: device_manager not loaded",
                is_available,
            )

    # Commands for control/configuration
    async def async_get_version(self) -> None:
        """Asynchronously get the IFSEI version."""
        logger.debug("requesting IFSEI version")
        await self.async_send_command("$VER")

    async def async_get_ip(self) -> None:
        """Asynchronously get the IP address."""
        logger.debug("requesting IP address")
        await self.async_send_command("$IP")

    async def async_get_gateway(self) -> None:
        """Asynchronously get the gateway."""
        logger.debug("requesting gateway")
        await self.async_send_command("$GATEWAY")

    async def async_get_netmask(self) -> None:
        """Asynchronously get the netmask."""
        logger.debug("requesting netmask")
        await self.async_send_command("$NETMASK")

    async def async_get_tcp_port(self) -> None:
        """Asynchronously get the TCP port."""
        logger.debug("requesting TCP port")
        await self.async_send_command("$PORT TCP")

    async def async_get_udp_port(self) -> None:
        """Asynchronously get the UDP port."""
        logger.debug("requesting UDP port")
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
        if not 1 <= level <= 7:
            raise ValueError("Monitor level must be between 1 and 7")
        logger.debug("[level=%d] enabling monitor", level)
        await self.async_send_command(f"MON{level}")

    async def async_update_light_state(self, device_id: str, colors: List[int]) -> None:
        """
        Asynchronously update the light state.

        Args:
            device_id (str): The device ID.
            colors (List[int]): List of colors (must have exactly 4 elements).

        Raises
        ------
            ValueError: If the list does not have exactly 4 elements.
        """
        if len(colors) != 4:
            raise ValueError("Colors list must have exactly 4 elements")

        if self.device_manager is None:
            logger.error(
                "[device_id=%s] cannot update light state: device_manager not loaded",
                device_id,
            )
            return

        logger.debug(
            "[device_id=%s rgbw=%s] update_light_state requested", device_id, colors
        )
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

                    logger.debug(
                        "[device_id=%s module=%s channel=%s name=%s value=%s] propagating address change",
                        device_id,
                        address["module"],
                        address["channel"],
                        address["name"],
                        value,
                    )
                    await self.async_set_zone_intensity(
                        int(address["module"]),
                        int(address["channel"]),
                        value,
                    )
                return
        logger.warning(
            "[device_id=%s] update_light_state: no matching light found",
            device_id,
        )

    async def async_update_cover_state(self, device_id: str, address: int) -> None:
        """
        Asynchronously update the cover state.

        Args:
            device_id (str): The device ID.
            address (int): The address to update.
        """
        if self.device_manager is None:
            logger.error(
                "[device_id=%s] cannot update cover state: device_manager not loaded",
                device_id,
            )
            return

        logger.debug(
            "[device_id=%s address=%s] update_cover_state requested",
            device_id,
            address,
        )
        for device in self.device_manager.covers:
            if device.unique_id == device_id:
                await self.async_set_shader_state(address)
                return
        logger.warning(
            "[device_id=%s] update_cover_state: no matching cover found",
            device_id,
        )

    # Commands for the Scenario Classic-NET network
    async def async_change_scene(self, module_address: int, scene_number: int) -> None:
        """
        Asynchronously change the scene.

        Args:
            module_address (int): The module address.
            scene_number (int): The scene number.
        """
        logger.debug(
            "[module=%02d scene=%02d] change_scene",
            module_address,
            scene_number,
        )
        await self.async_send_command(f"D{module_address:02}C{scene_number:02}")

    async def async_toggle_zone(
        self, module_address: int, zone_number: int, state: int
    ) -> None:
        """
        Asynchronously toggle the zone.

        Args:
            module_address (int): The module address.
            zone_number (int): The zone number.
            state (int): The state to set (1 or 0).

        Raises
        ------
            ValueError: If state is not 0 or 1.
        """
        if state not in [0, 1]:
            raise ValueError("State must be 0 or 1")
        logger.debug(
            "[module=%02d zone=%d state=%d] toggle_zone",
            module_address,
            zone_number,
            state,
        )
        await self.async_send_command(f"$D{module_address:02}Z{zone_number}{state}")

    async def async_get_scene_status(self, module_address: int) -> None:
        """
        Asynchronously get the scene status.

        Args:
            module_address (int): The module address.
        """
        logger.debug("[module=%02d] requesting scene status", module_address)
        await self.async_send_command(f"$D{module_address:02}ST")

    async def async_set_zone_intensity(
        self, module_address: int, channel: int, intensity: int
    ) -> None:
        """
        Asynchronously set the zone intensity.

        Args:
            module_address (int): The module address.
            channel (int): The channel number.
            intensity (int): The intensity to set (0-100).

        Raises
        ------
            ValueError: If intensity is not between 0 and 100.
        """
        if not 0 <= intensity <= 100:
            raise ValueError("Intensity must be between 0 and 100")
        logger.debug(
            "[module=%02d channel=%d intensity=%d] set_zone_intensity",
            module_address,
            channel,
            intensity,
        )
        await self.async_send_command(
            f"Z{module_address:02}{channel:01}L{intensity:03}T1"
        )

    async def async_set_shader_state(self, module_address: int) -> None:
        """
        Asynchronously set the shader state.

        Args:
            module_address (int): The module address.
        """
        logger.debug("[address=%04d] set_shader_state", module_address)
        await self.async_send_command(f"C{module_address:04}")

    async def async_get_zone_intensity(
        self, module_address: int, zone_number: int
    ) -> None:
        """
        Asynchronously get the zone intensity.

        Args:
            module_address (int): The module address.
            zone_number (int): The zone number.
        """
        logger.debug(
            "[module=%02d zone=%d] requesting zone intensity",
            module_address,
            zone_number,
        )
        await self.async_send_command(f"$D{module_address:02}Z{zone_number}I")

    async def async_increase_scene_intensity(self, module_address: int) -> None:
        """
        Asynchronously increase the scene intensity.

        Args:
            module_address (int): The module address.
        """
        logger.debug("[module=%02d] increase_scene_intensity", module_address)
        await self.async_send_command(f"$D{module_address:02}C+")

    async def async_decrease_scene_intensity(self, module_address: int) -> None:
        """
        Asynchronously decrease the scene intensity.

        Args:
            module_address (int): The module address.
        """
        logger.debug("[module=%02d] decrease_scene_intensity", module_address)
        await self.async_send_command(f"$D{module_address:02}C-")

    async def async_increase_zone_intensity(
        self, module_address: int, zone_number: int
    ) -> None:
        """
        Asynchronously increase the zone intensity.

        Args:
            module_address (int): The module address.
            zone_number (int): The zone number.
        """
        logger.debug(
            "[module=%02d zone=%d] increase_zone_intensity",
            module_address,
            zone_number,
        )
        await self.async_send_command(f"$D{module_address:02}Z{zone_number}+")

    async def async_decrease_zone_intensity(
        self, module_address: int, zone_number: int
    ) -> None:
        """
        Asynchronously decrease the zone intensity.

        Args:
            module_address (int): The module address.
            zone_number (int): The zone number.
        """
        logger.debug(
            "[module=%02d zone=%d] decrease_zone_intensity",
            module_address,
            zone_number,
        )
        await self.async_send_command(f"$D{module_address:02}Z{zone_number}-")

    async def async_record_scene(self, module_address: int) -> None:
        """
        Asynchronously record a scene.

        Args:
            module_address (int): The module address.

        Raises
        ------
            NotImplementedError: This method is not yet implemented.
        """
        raise NotImplementedError("Scene recording is not implemented yet.")

    async def async_get_module_configuration(
        self, module_address: int, setup_number: int
    ) -> None:
        """
        Asynchronously get the module configuration.

        Args:
            module_address (int): The module address.
            setup_number (int): The setup number.
        """
        logger.debug(
            "[module=%02d setup=%d] requesting module configuration",
            module_address,
            setup_number,
        )
        await self.async_send_command(f"$D{module_address:02}P{setup_number}ST")

    async def async_execute_macro_key_press(self, prid: str, key_number: int) -> None:
        """
        Asynchronously execute a macro key press.

        Args:
            prid (str): The PRID.
            key_number (int): The key number.
        """
        logger.debug("[prid=%s key=%d] execute_macro_key_press", prid, key_number)
        await self.async_send_command(f"I{prid}{key_number}P")

    async def async_execute_macro_key_release(self, prid: str, key_number: int) -> None:
        """
        Asynchronously execute a macro key release.

        Args:
            prid (str): The PRID.
            key_number (int): The key number.
        """
        logger.debug("[prid=%s key=%d] execute_macro_key_release", prid, key_number)
        await self.async_send_command(f"I{prid}{key_number}R")
