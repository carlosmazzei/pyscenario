# Scenario IFSEI Interface

[![Tests](https://github.com/carlosmazzei/pyscenario/actions/workflows/cicd.yaml/badge.svg)](https://github.com/carlosmazzei/pyscenario/actions/workflows/cicd.yaml)
[![codecov](https://codecov.io/gh/carlosmazzei/pyscenario/graph/badge.svg)](https://codecov.io/gh/carlosmazzei/pyscenario)
[![PyPI version](https://badge.fury.io/py/pyscenario.svg)](https://pypi.org/project/pyscenario/)
[![Documentation Status](https://readthedocs.org/projects/pyscenario/badge/?version=latest)](https://pyscenario.readthedocs.io/en/latest/?badge=latest)

Python Scenario Automation contains a library to interface with Scenario IFSEI Classic for home automation.

> **NOTE:** This library was designed and tested with IFSEI version *Ver 04.12.15 - NS 00.00.00 - DS 05.02*.

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
  - [Supported devices](#supported-devices)
  - [Devices config file](#devices-config-file)
    - [Light](#light)
    - [Shades / Covers](#shades--covers)
- [Message reception and processing](#message-reception-and-processing)
  - [Connection handling](#connection-handling)
  - [Device updates](#device-updates)
- [Example](#example)
- [Contributing](#contributing)
- [Contact](#contact)

## Installation

To install the package, use pip, which is the package installer for Python:

```bash
pip install pyscenario
```

This command will download and install the latest version of pyscenario from the Python Package Index (PyPI).

## Usage

To use the package, first import the necessary modules:

```python
import pyscenario
from pyscenario.ifsei import IFSEI
from pyscenario.network import NetworkConfiguration, Protocol
```

To connect to an IFSEI device, you need to create an IFSEI instance with the appropriate network configuration. Here’s how you can do that:

```python

# Create a NetworkConfiguration object with the IP address, and port numbers for 
# command and data channels, and protocol
network_configuration = NetworkConfiguration("192.168.1.20", 28000, 23000, Protocol.TCP)

# Create an IFSEI instance with the network configuration
ifsei = IFSEI(network_config=network_configuration)

# Load devices from a device configuration file
ifsei.load_devices("device_config.yaml")

# Connect to the IFSEI device asynchronously
await ifsei.async_connect()

```

### Supported devices

The `IFSEI.load_devices()` function will populate three entities: zones, lights, and shades (covers). Each of these entities represents a different type of device that can be managed by the IFSEI interface. All entities are optional, but they provide a structure to the configuration and management of the home automation system.

> Device Manager supports only Light and Shade/Cover devices.

The file `config_schema.py` contains the valid schema for the yaml file. This file gets validated using Voluptuous lib.

### Devices config file

To properly load and interact with devices, they must be defined in a YAML configuration file. Without this configuration, the integration will have no devices to interact with. The default file name is `scenario_device_config.yaml`.

**Example of device config file:**

```yaml
# Zone config
zones:
  - id: 1
    name: Area de Servico
  - id: 2
    name: Banho

# Lights config
lights:
  - id: 1
    name: Bancada
    zone: 2
    isRGB: false
    address:
      - name: w
        module: 4
        channel: 5
        isDimmeable: false
  - id: 2
    name: Sanca
    zone: 1
    isRGB: false
    address:
      - name: w
        module: 3
        channel: 8
        isDimmeable: false
# Shades config
shades:
  - id: 1
    name: Cortina
    zone: 2
    address1: "0002"
    address2: "0003"
    address3: "0004"
  - id: 2
    name: Persiana LD
    zone: 1
    address1: "0005"
    address2: "0006"
    address3: "0007"
```

#### Light

Light devices support both dimmable `(isDimmeable: bool)` and RGB `(isRGB: bool)` configurations. Each light should have at least one address, usually the `w` for the white channel. RGB lights should also have `r`, `g`, and `b` addresses.

The update callback should support `**kwargs` with the following parameters:

- IFSEI_ATTR_AVAILABLE: availability of the device
- IFSEI_ATTR_BRIGHTNESS: white channel with value from 0 (off) to 100 (max brightness)
- IFSEI_ATTR_RED: red channel with value from 0 (off) to 100 (max brightness)
- IFSEI_ATTR_GREEN: green channel with value from 0 (off) to 100 (max brightness)
- IFSEI_ATTR_BLUE: blue channel with value from 0 (off) to 100 (max brightness)

```python
def light_update_callback(self, **kwargs: Any):
    brightness = kwargs.pop(IFSEI_ATTR_BRIGHTNESS, None)
    available = kwargs.pop(IFSEI_ATTR_AVAILABLE, None)
    red = kwargs.pop(IFSEI_ATTR_RED, None)
    green = kwargs.pop(IFSEI_ATTR_GREEN, None)
    blue = kwargs.pop(IFSEI_ATTR_BLUE, None)
    print(f"Light Update - Brightness: {brightness}, Available: {available}, Red: {red}, Green: {green}, Blue: {blue}")
```

#### Shades / Covers

Shade devices typically have three addresses. The first corresponds to the up command, the second to stop, and the third to down.

The update callback should support **kwargs with the following parameters:

- IFSEI_ATTR_AVAILABLE: Availability of the device
- IFSEI_ATTR_COMMAND: Command for the device (IFSEI_COVER_DOWN, IFSEI_COVER_UP, or IFSEI_COVER_STOP)
- IFSEI_ATTR_STATE: State of the scene (IFSEI_ATTR_SCENE_ACTIVE or IFSEI_ATTR_SCENE_INACTIVE)

```python
def shade_update_callback(self, **kwargs: Any):
    available = kwargs.pop(IFSEI_ATTR_AVAILABLE, None)
    command = kwargs.pop(IFSEI_ATTR_COMMAND, None)
    state = kwargs.pop(IFSEI_ATTR_STATE, None)
    print(f"Shade Update - Available: {available}, Command: {command}, State: {state}")
```

## Message reception and processing

The IFSEI class creates two queues: one for receiving messages and another for sending messages. These queues are also used by the telnet client to process incoming and outgoing messages. All messages are processed by the IFSEI class, and the IFSEITelnetClient puts and gets messages from these queues.

It is possible to set a delay between messages to be sent. This can be done by calling the set_send_delay function with a time in seconds:

```python
ifsei.set_send_delay(0.2)
```

### Connection handling

After the first connection is established, the IFSEI instance will try to reconnect in a separate monitoring thread if the connection is lost. This thread is created after the `on_connection_lost` is called.

Upon the first connection, the device should respond with `*IFSEION`, indicating that it is available. All devices in the device manager with registered callbacks will be notified.

To close the connection and stop all read, send, and processing tasks, call:

```python
await ifsei.async_close()
```

### Device updates

It is possible to add subscribers to each device so that they can be notified when specific state changes occur. Device availability and state status are sent to the callback when received by the IFSEI instance.

**Example of adding a subscriber:**

```python
light.add_subscriber(self.update_callback)

def async_update_callback(self, **kwargs: Any):
  """Update callback."""
  brightness = kwargs.pop(IFSEI_ATTR_BRIGHTNESS, None)
  available = kwargs.pop(IFSEI_ATTR_AVAILABLE, None)
  red = kwargs.pop(IFSEI_ATTR_RED, None)
  green = kwargs.pop(IFSEI_ATTR_GREEN, None)
  blue = kwargs.pop(IFSEI_ATTR_BLUE, None)

  if available is not None:
      self._attr_available = available
      _LOGGER.debug("Set device %s availability to %s", self.name, available)

```

## Example

This library is used in Home Assistant custom integration for Scenario Automation.

## Contributing

If you feel you can contribute to the project, please read the contribution guide at [CONTRIBUTING](CONTRIBUTING.md).

## Contact

Carlos Mazzei
  ([carlos.mazzei@gmail.com](mailto:carlos.mazzei@gmail.com))
