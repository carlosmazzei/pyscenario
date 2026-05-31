"""
Device Manager Module.

This module contains classes for managing devices, including lights and covers. It provides methods
for handling device states and configurations.

"""

import logging
from collections.abc import Callable

import yaml

from .config_schema import device_config_schema
from .const import (
    COVER_DEVICES,
    IFSEI_ATTR_COMMAND,
    IFSEI_ATTR_STATE,
    IFSEI_COVER_DOWN,
    IFSEI_COVER_STOP,
    IFSEI_COVER_UP,
    LIGHT_DEVICES,
)

logger = logging.getLogger(__name__)


class Device:
    """
    Base class for all devices.

    Attributes
    ----------
        unique_id (str): Unique identifier for the device.
        name (str): Name of the device.
        zone (str): Zone where the device is located.
        callback_ (Callable[[], None] | None): Callback function for updates.
    """

    def __init__(self) -> None:
        """Initialize a Device object."""
        self.unique_id: str = ""
        self.name: str = ""
        self.zone: str = ""
        self.callback_: Callable[[], None] | None = None

    def get_device_id(self) -> str:
        """
        Return the unique ID of the device.

        Returns
        -------
            str: Unique ID of the device.
        """
        return self.unique_id

    def get_name(self) -> str:
        """
        Return the name of the device.

        Returns
        -------
            str: Name of the device.
        """
        return self.name

    def add_subscriber(self, callback_: Callable[[], None]) -> None:
        """
        Set a callback function to be called when a response is received.

        Args:
            callback_ (Callable[[], None]): The callback function.
        """
        if self.callback_ is not None:
            logger.debug(
                "[device_id=%s name=%s] replacing existing subscriber",
                self.unique_id,
                self.name,
            )
        else:
            logger.debug(
                "[device_id=%s name=%s] subscriber added",
                self.unique_id,
                self.name,
            )
        self.callback_ = callback_

    def remove_subscriber(self) -> None:
        """Remove the callback function."""
        logger.debug(
            "[device_id=%s name=%s] subscriber removed",
            self.unique_id,
            self.name,
        )
        self.callback_ = None


class Light(Device):
    """
    Class representing a light device.

    Attributes
    ----------
        unique_id (str): Unique identifier for the light.
        name (str): Name of the light.
        zone (str): Zone where the light is located.
        is_rgb (bool): Indicates if the light supports RGB.
        address (list[dict[str, str]]): List of addresses for the light.
    """

    def __init__(
        self,
        unique_id: str,
        name: str,
        zone: str,
        is_rgb: bool,
        address: list[dict[str, str]],
    ) -> None:
        """
        Initialize a Light object.

        Args:
            unique_id (str): Unique identifier for the light.
            name (str): Name of the light.
            zone (str): Zone where the light is located.
            is_rgb (bool): Indicates if the light supports RGB.
            address (list[dict[str, str]]): List of addresses for the light.
        """
        super().__init__()
        self.unique_id = str(f"{unique_id}_{zone}").lower().replace(" ", "_")
        self.name = name
        self.zone = zone
        self.is_rgb = is_rgb
        self.address = address

    def get_is_rgb(self) -> bool:
        """
        Return if the light supports RGB.

        Returns
        -------
            bool: True if the light supports RGB, False otherwise.
        """
        return self.is_rgb


class Cover(Device):
    """
    Class representing a cover device.

    Attributes
    ----------
        unique_id (str): Unique identifier for the cover.
        name (str): Name of the cover.
        zone (str): Zone where the cover is located.
        up (str): Address for the up command.
        stop (str): Address for the stop command.
        down (str): Address for the down command.
        is_closed (bool): Indicates if the cover is closed.
    """

    def __init__(
        self,
        unique_id: str,
        name: str,
        zone: str,
        up: str,
        stop: str,
        down: str,
        module: int | None = None,
        open_channel: int | None = None,
        close_channel: int | None = None,
    ) -> None:
        """
        Initialize a Cover object.

        Args:
            unique_id (str): Unique identifier for the cover.
            name (str): Name of the cover.
            zone (str): Zone where the cover is located.
            up (str): Address for the up command.
            stop (str): Address for the stop command.
            down (str): Address for the down command.
            module (int | None): Opcional module address of the physical relay.
            open_channel (int | None): Opcional channel of the opening physical relay.
            close_channel (int | None): Opcional channel of the closing physical relay.
        """
        super().__init__()
        self.unique_id = str(f"{unique_id}_{zone}").lower().replace(" ", "_")
        self.name = name
        self.zone = zone
        self.up = up
        self.stop = stop
        self.down = down
        self.module = module
        self.open_channel = open_channel
        self.close_channel = close_channel
        self.is_closed = False


class DeviceManager:
    """
    Class for managing a collection of devices.

    Attributes
    ----------
        lights (list[Light]): List of light devices.
        covers (list[Cover]): List of cover devices.
        zones (dict[str, str]): Dictionary mapping zone IDs to zone names.
    """

    def __init__(
        self,
        lights: list[Light],
        covers: list[Cover],
        zones: dict[str, str],
    ) -> None:
        """
        Initialize a DeviceManager object.

        Args:
            lights (list[Light]): List of light devices.
            covers (list[Cover]): List of cover devices.
            zones (dict[str, str]): Dictionary mapping zone IDs to zone names.
        """
        self.lights = lights
        self.covers = covers
        self.zones = zones

    @classmethod
    def from_config(cls, config_file: str):
        """
        Create a DeviceManager object from a configuration file.

        Args:
            config_file (str): Path to the configuration file.

        Returns
        -------
            DeviceManager | None: An instance of the DeviceManager class, or None if the file is not found.
        """
        try:
            logger.debug("[config=%s] loading device configuration", config_file)
            with open(config_file, encoding="utf-8") as file:
                data = yaml.safe_load(file)

            device_config_schema(data)

            zones_list = data.get("zones", [])
            zones = {zone["id"]: zone["name"] for zone in zones_list}
            logger.debug("[zones=%d] parsed zones", len(zones))

            lights = []
            for light_data in data["lights"]:
                addresses = light_data.get("address", [])
                for address in addresses:
                    address["state"] = 0
                light = Light(
                    unique_id=light_data["id"],
                    name=light_data["name"],
                    zone=zones[light_data["zone"]],
                    is_rgb=light_data["isRGB"],
                    address=addresses,
                )
                lights.append(light)
                logger.debug(
                    "[device_id=%s type=light zone=%s is_rgb=%s addresses=%d] parsed",
                    light.unique_id,
                    light.zone,
                    light.is_rgb,
                    len(addresses),
                )

            covers = []
            for covers_data in data["shades"]:
                cover = Cover(
                    unique_id=covers_data["id"],
                    name=covers_data["name"],
                    zone=zones[covers_data["zone"]],
                    up=str(covers_data["address1"]),
                    stop=str(covers_data["address2"]),
                    down=str(covers_data["address3"]),
                    module=covers_data.get("module"),
                    open_channel=covers_data.get("open_channel"),
                    close_channel=covers_data.get("close_channel"),
                )
                covers.append(cover)
                logger.debug(
                    "[device_id=%s type=cover zone=%s up=%s stop=%s down=%s module=%s open_channel=%s close_channel=%s] parsed",
                    cover.unique_id,
                    cover.zone,
                    cover.up,
                    cover.stop,
                    cover.down,
                    cover.module,
                    cover.open_channel,
                    cover.close_channel,
                )

            logger.info(
                "[config=%s lights=%d covers=%d zones=%d] devices loaded",
                config_file,
                len(lights),
                len(covers),
                len(zones),
            )

            return cls(lights, covers, zones)
        except FileNotFoundError:
            logger.error("[config=%s] config file not found", config_file)
            return None

    def get_devices_by_type(self, device_type: str) -> list[Light] | list[Cover] | None:
        """
        Get devices by type.

        Args:
            device_type (str): The type of device to retrieve (LIGHT_DEVICES or COVER_DEVICES).

        Returns
        -------
            list[Light] | list[Cover] | None: List of devices of the specified type, or None if the type is invalid.
        """
        if device_type == LIGHT_DEVICES:
            return self.lights

        if device_type == COVER_DEVICES:
            return self.covers

        return None

    def get_device_by_id(self, id: str) -> Device | None:
        """
        Get a device by its unique ID.

        Args:
            id (str): The unique ID of the device.

        Returns
        -------
            Device | None: The device with the specified ID, or None if not found.
        """
        logger.debug("[device_id=%s] lookup", id)
        for light in self.lights:
            if light.unique_id == id:
                logger.debug("[device_id=%s type=light] found", id)
                return light
        for cover in self.covers:
            if cover.unique_id == id:
                logger.debug("[device_id=%s type=cover] found", id)
                return cover
        logger.debug("[device_id=%s] not found", id)
        return None

    async def async_handle_zone_state_change(
        self, module_number: int, channel: int, state: int
    ) -> None:
        """
        Asynchronously update the intensity of a device.

        Args:
            module_number (int): The module number.
            channel (int): The channel number.
            state (int): The new state to set.
        """
        matched = False
        for light in self.lights:
            for address in light.address:
                if (
                    int(address["module"]) == module_number
                    and int(address["channel"]) == channel
                ):
                    matched = True
                    address["state"] = str(state)
                    address_name = address["name"]
                    logger.debug(
                        "[device_id=%s name=%s module=%02d channel=%02d attr=%s state=%s] zone state updated",
                        light.unique_id,
                        light.name,
                        module_number,
                        channel,
                        address_name,
                        state,
                    )

                    if light.callback_ is not None:
                        kwargs = {address_name: state}
                        logger.debug(
                            "[device_id=%s kwargs=%s] dispatching callback",
                            light.unique_id,
                            kwargs,
                        )
                        light.callback_(**kwargs)
                    else:
                        logger.debug(
                            "[device_id=%s] no subscriber registered, skipping callback",
                            light.unique_id,
                        )

        # Match covers/shades physical relay zone state changes
        for cover in self.covers:
            if cover.module == module_number:
                if cover.open_channel == channel:
                    matched = True
                    if cover.callback_ is not None:
                        kwargs = {"open_relay": state}
                        logger.debug(
                            "[device_id=%s name=%s module=%02d channel=%02d open_relay=%s] cover physical relay state updated",
                            cover.unique_id,
                            cover.name,
                            module_number,
                            channel,
                            state,
                        )
                        cover.callback_(**kwargs)
                    else:
                        logger.debug(
                            "[device_id=%s] no subscriber registered, skipping callback",
                            cover.unique_id,
                        )
                elif cover.close_channel == channel:
                    matched = True
                    if cover.callback_ is not None:
                        kwargs = {"close_relay": state}
                        logger.debug(
                            "[device_id=%s name=%s module=%02d channel=%02d close_relay=%s] cover physical relay state updated",
                            cover.unique_id,
                            cover.name,
                            module_number,
                            channel,
                            state,
                        )
                        cover.callback_(**kwargs)
                    else:
                        logger.debug(
                            "[device_id=%s] no subscriber registered, skipping callback",
                            cover.unique_id,
                        )

        if not matched:
            logger.warning(
                "[module=%02d channel=%02d state=%s] zone state change has no matching light/cover",
                module_number,
                channel,
                state,
            )

    async def async_handle_scene_state_change(
        self, change_address: str, state: str
    ) -> None:
        """
        Asynchronously update the state of a scene.

        Args:
            change_address (str): The address to change.
            state (str): The new state to set.
        """
        kwargs = {}
        matched = False
        for cover in self.covers:
            if change_address in [cover.up, cover.down, cover.stop]:
                matched = True
                if change_address == cover.up:
                    kwargs = {
                        IFSEI_ATTR_COMMAND: IFSEI_COVER_UP,
                        IFSEI_ATTR_STATE: state,
                    }
                elif change_address == cover.down:
                    kwargs = {
                        IFSEI_ATTR_COMMAND: IFSEI_COVER_DOWN,
                        IFSEI_ATTR_STATE: state,
                    }
                elif change_address == cover.stop:
                    kwargs = {
                        IFSEI_ATTR_COMMAND: IFSEI_COVER_STOP,
                        IFSEI_ATTR_STATE: state,
                    }

                logger.debug(
                    "[device_id=%s name=%s address=%s state=%s command=%s] scene state matched cover",
                    cover.unique_id,
                    cover.name,
                    change_address,
                    state,
                    kwargs.get(IFSEI_ATTR_COMMAND),
                )

                if cover.callback_ is not None:
                    logger.debug(
                        "[device_id=%s kwargs=%s] dispatching callback",
                        cover.unique_id,
                        kwargs,
                    )
                    cover.callback_(**kwargs)
                else:
                    logger.debug(
                        "[device_id=%s] no subscriber registered, skipping callback",
                        cover.unique_id,
                    )
        if not matched:
            logger.warning(
                "[address=%s state=%s] scene state change has no matching cover",
                change_address,
                state,
            )

    def notify_subscriber(self, **kwargs: str) -> None:
        """
        Notify subscribers about changes.

        Args:
            **kwargs (str): Keyword arguments containing the state changes.
        """
        notified_lights = sum(1 for light in self.lights if light.callback_ is not None)
        notified_covers = sum(1 for cover in self.covers if cover.callback_ is not None)
        logger.debug(
            "[lights=%d covers=%d kwargs=%s] notifying subscribers",
            notified_lights,
            notified_covers,
            kwargs,
        )
        for light in self.lights:
            if light.callback_ is not None:
                light.callback_(**kwargs)

        for cover in self.covers:
            if cover.callback_ is not None:
                cover.callback_(**kwargs)
