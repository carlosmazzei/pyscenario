"""Constants for the Scenario IFSEI."""

IFSEI_ATTR_BRIGHTNESS = "w"
IFSEI_ATTR_AVAILABLE = "available"
IFSEI_ATTR_COMMAND = "command"
IFSEI_ATTR_STATE = "state"
IFSEI_ATTR_SCENE_ACTIVE = "1"
IFSEI_ATTR_SCENE_INACTIVE = "0"
IFSEI_ATTR_RED = "r"
IFSEI_ATTR_GREEN = "g"
IFSEI_ATTR_BLUE = "b"
IFSEI_ATTR_SHADERS_UP = "address1"
IFSEI_ATTR_SHADERS_STOP = "address2"
IFSEI_ATTR_SHADERS_DOWN = "address3"

IFSEI_COVER_UP = "up"
IFSEI_COVER_DOWN = "down"
IFSEI_COVER_STOP = "stop"

LIGHT_DEVICES = "lights"
COVER_DEVICES = "covers"

RESPONSE_TERMINATOR = ">"
BUFFER_SIZE = 1024
IFSEI_RECONNECT_DELAY = 10.0  # Delay in seconds before retrying connection
IFSEI_ATTR_SEND_DELAY = 0.2  # Delay in seconds between messages
DEVICE_FILE = "scenario_device_config.yaml"

ERROR_CODES = {
    "E1": "Buffer overflow on input. Too many characters were sent without sending the <CR> character.",
    "E2": "Buffer overflow on output. Too much traffic on the Classic-NET and the IFSEI is unable to transmit the commands to the controller.",
    "E3": "Non-existent module addressed.",
    "E4": "Syntax error. The controller sent a command that was not recognized by the IFSEI.",
}
