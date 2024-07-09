"""Device Manager."""

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


class Device:
    """Device class."""

    def __init__(self) -> None:
        """Device class."""
        self.unique_id: str = ""
        self.name: str = ""
        self.zone: str = ""
        self.callback_: Callable[[], None] | None = None

    def get_device_id(self) -> str:
        """Return unique id."""
        return self.unique_id

    def get_name(self) -> str:
        """Return name."""
        return self.name

    def add_subscriber(self, callback_: Callable[[], None]) -> None:
        """Set a callback function to be called when a response is received."""
        self.callback_ = callback_

    def remove_subscriber(self) -> None:
        """Remove callback function."""
        self.callback_ = None


class Light(Device):
    """Light class."""

    def __init__(
        self,
        unique_id: str,
        name: str,
        zone: str,
        is_rgb: bool,
        address: list[dict[str, str]],
    ) -> None:
        """Init light class."""
        super().__init__()
        self.unique_id = str(f"{unique_id}_{zone}").lower().replace(" ", "_")
        self.name = name
        self.zone = zone
        self.is_rgb = is_rgb
        self.address = address

    def get_is_rgb(self) -> bool:
        """Return if the light is RGB."""
        return self.is_rgb


class Cover(Device):
    """Cover class."""

    def __init__(
        self, unique_id: str, name: str, zone: str, up: str, stop: str, down: str
    ) -> None:
        """Init light class."""
        super().__init__()
        self.unique_id = str(f"{unique_id}_{zone}").lower().replace(" ", "_")
        self.name = name
        self.zone = zone
        self.up = up
        self.stop = stop
        self.down = down
        self.is_closed = False


class DeviceManager:
    """Device Manager."""

    def __init__(
        self,
        lights: list[Light],
        covers: list[Cover],
        zones: dict[str, str],
    ) -> None:
        """Device Manager."""
        self.lights = lights
        self.covers = covers
        self.zones = zones

    @classmethod
    def from_config(cls, config_file: str):
        """Create Device Manager from config file."""
        try:
            with open(config_file, encoding="utf-8") as file:
                data = yaml.safe_load(file)

            device_config_schema(data)

            zones_list = data.get("zones", [])
            zones = {zone["id"]: zone["name"] for zone in zones_list}

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

            covers = []
            for covers_data in data["shades"]:
                cover = Cover(
                    unique_id=covers_data["id"],
                    name=covers_data["name"],
                    zone=zones[covers_data["zone"]],
                    up=str(covers_data["address1"]),
                    stop=str(covers_data["address2"]),
                    down=str(covers_data["address3"]),
                )
                covers.append(cover)

            return cls(lights, covers, zones)
        except FileNotFoundError:
            return None

    def get_devices_by_type(self, device_type: str) -> list[Light] | list[Cover] | None:
        """Get devices by type."""
        if device_type == LIGHT_DEVICES:
            return self.lights

        if device_type == COVER_DEVICES:
            return self.covers

        return None

    def get_device_by_id(self, id: str) -> Device | None:
        """Get device by id."""
        for device in self.lights:
            if device.unique_id == id:
                return device
        return None

    async def async_handle_zone_state_change(
        self, module_number: int, channel: int, state: int
    ) -> None:
        """Update device intensity."""
        for light in self.lights:
            for address in light.address:
                if (
                    int(address["module"]) == module_number
                    and address["channel"] == channel
                ):
                    address["state"] = str(state)
                    address_name = address["name"]

                    if light.callback_ is not None:
                        kwargs = {address_name: state}
                        light.callback_(**kwargs)

    async def async_handle_scene_state_change(
        self, change_address: str, state: str
    ) -> None:
        """Update scene."""
        kwargs = {}
        for cover in self.covers:
            if change_address in [cover.up, cover.down, cover.stop]:
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

                if cover.callback_ is not None:
                    cover.callback_(**kwargs)

    def notify_subscriber(self, **kwargs: str) -> None:
        """Notify change."""
        for light in self.lights:
            if light.callback_ is not None:
                light.callback_(**kwargs)

        for cover in self.covers:
            if cover.callback_ is not None:
                cover.callback_(**kwargs)
