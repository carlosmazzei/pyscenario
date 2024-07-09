"""Validation schema for config file."""

from voluptuous import All, Any, Coerce, Length, Optional, Required, Schema

from .const import (
    IFSEI_ATTR_BLUE,
    IFSEI_ATTR_BRIGHTNESS,
    IFSEI_ATTR_GREEN,
    IFSEI_ATTR_RED,
)

# Define the schema for address in lights
address_schema = Schema(
    {
        Required("name"): Any(
            IFSEI_ATTR_RED, IFSEI_ATTR_GREEN, IFSEI_ATTR_BLUE, IFSEI_ATTR_BRIGHTNESS
        ),
        Required("module"): Coerce(int),
        Required("channel"): Coerce(int),
        Required("isDimmeable"): Coerce(bool),
    }
)

# Define the schema for lights
lights_schema = Schema(
    {
        Required("id"): Coerce(int),
        Required("name"): str,
        Required("zone"): Coerce(int),
        Required("isRGB"): Coerce(bool),
        Required("address"): All([address_schema], Length(min=1)),
    }
)

# Define the schema for shades
shades_schema = Schema(
    {
        Required("id"): Coerce(int),
        Required("name"): str,
        Required("zone"): Coerce(int),
        Required("address1"): Coerce(str),
        Required("address2"): Coerce(str),
        Required("address3"): Coerce(str),
    }
)

# Define the schema for zones
zones_schema = Schema({Required("id"): Coerce(int), Required("name"): str})

# Define the main schema for the YAML configuration
device_config_schema = Schema(
    {
        Optional("zones"): [zones_schema],
        Optional("lights"): [lights_schema],
        Optional("shades"): [shades_schema],
    }
)
