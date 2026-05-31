# Specification: Home Assistant Custom Integration Update for Cover Position Tracking

This specification details the changes required in the Home Assistant custom integration (`custom_components/scenario`) to support accurate cover position tracking using the physical relay feedback signals now provided by the `pyscenario` library.

---

## 1. Objective

By utilizing physical relay feedback (Module and Channels representing the UP and DOWN relays), the Home Assistant integration will track the real-time position of the curtain (`CoverEntity`). This calculation will work seamlessly whether the curtain is commanded via:
- The Home Assistant UI or Automations.
- Physical keypads or wall switches (bypassing Home Assistant).
- The Scenario central controller's automatic safety timeout (e.g., 30-second relay shutoff).

---

## 2. Configuration Schema Update

The custom integration's platform configuration schema (usually defined in `cover.py` or `config_flow.py` using `voluptuous`) must be updated to accept the new optional configuration parameters from `scenario_device_config.yaml`:

```python
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

# Example addition to the platform schema if handled locally
COVER_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.positive_int,
        vol.Required("name"): cv.string,
        vol.Required("zone"): cv.positive_int,
        vol.Required("address1"): cv.string,
        vol.Required("address2"): cv.string,
        vol.Required("address3"): cv.string,
        vol.Optional("module"): cv.positive_int,
        vol.Optional("open_channel"): cv.positive_int,
        vol.Optional("close_channel"): cv.positive_int,
    }
)
```

---

## 3. Position Calculation Logic

To calculate the cover position, the integration needs to know the **full travel duration** (the time it takes for the cover to go from 100% open to 100% closed).

### Configuration parameters:
- **`travel_time`**: The total duration in seconds for a complete opening or closing course. (Recommended default: `30` seconds, matching the physical module safety timer).

### Tracking State Variables (Instance level):
- `self._current_position` (int, `0` to `100`): `0` represents fully closed, `100` represents fully open.
- `self._is_opening` (bool): Tracking if the open relay is active.
- `self._is_closing` (bool): Tracking if the close relay is active.
- `self._last_relay_on_time` (float | None): Timestamp when the active relay turned ON (`100`).

---

## 4. Signal Mapping & Callbacks

The `pyscenario` library dispatches two new parameters in the shade update callback:
*   `open_relay`: `100` (relay turned ON), `0` (relay turned OFF).
*   `close_relay`: `100` (relay turned ON), `0` (relay turned OFF).

### Callback Flow Diagram

```mermaid
graph TD
    A[pyscenario Callback Received] --> B{Relay Parameter?}
    B -- open_relay --0 or 100--> C[Handle Open Relay State]
    B -- close_relay --0 or 100--> D[Handle Close Relay State]
    B -- regular command/state --> E[Handle Legacy Scene State]
    C --> F[Calculate Position Delta & Update HA State]
    D --> F
    F --> G[async_write_ha_state]
```

### State Transitions & Math:

1. **Relay Turns ON (`100`)**:
   - Save the current time: `self._last_relay_on_time = time.time()`
   - Set the moving direction flags: `self._is_opening = True` (or `self._is_closing = True`).
   - Trigger Home Assistant state update to show "Opening" or "Closing".

2. **Relay Turns OFF (`0`)**:
   - Verify if the cover was actively moving in that direction.
   - Calculate elapsed active time: `elapsed = time.time() - self._last_relay_on_time`
   - Calculate the percentage of movement: `delta_pct = (elapsed / travel_time) * 100`
   - Update the virtual position:
     - **If Opening:** `self._current_position = min(100, self._current_position + delta_pct)`
     - **If Closing:** `self._current_position = max(0, self._current_position - delta_pct)`
   - Reset flags: `self._is_opening = False`, `self._is_closing = False`, `self._last_relay_on_time = None`.

---

## 5. Reference Implementation (`cover.py`)

Below is the blueprint for the custom component's updated callback and property methods:

```python
import logging
import time
from typing import Any
from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
    ATTR_POSITION,
)

_LOGGER = logging.getLogger(__name__)

# Default total travel time in seconds
DEFAULT_TRAVEL_TIME = 30.0

class ScenarioCover(CoverEntity):
    """Representation of a Scenario Shade/Cover in Home Assistant."""

    def __init__(self, shade_device: Any, travel_time: float = DEFAULT_TRAVEL_TIME) -> None:
        """Initialize the cover."""
        self._device = shade_device
        self._travel_time = travel_time
        
        # Position state tracking
        self._current_position: int = 50  # Start at middle if unknown, or restore state
        self._is_opening: bool = False
        self._is_closing: bool = False
        self._last_relay_on_time: float | None = None

        # Subscribe to pyscenario device callbacks
        self._device.add_subscriber(self.async_update_callback)

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Flag supported features."""
        return (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        return self._is_opening

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        return self._is_closing

    @property
    def is_closed(self) -> bool:
        """Return if the cover is closed."""
        return self._current_position == 0

    @property
    def current_cover_position(self) -> int:
        """Return current position of cover. 0 is closed, 100 is open."""
        return self._current_position

    def async_update_callback(self, **kwargs: Any) -> None:
        """Callback received from pyscenario when states change."""
        open_relay = kwargs.get("open_relay")
        close_relay = kwargs.get("close_relay")
        now = time.time()
        state_changed = False

        # Handle physical OPEN relay feedback
        if open_relay is not None:
            if open_relay == 100:
                _LOGGER.debug("%s: Open relay energised (started opening)", self.name)
                self._is_opening = True
                self._is_closing = False
                self._last_relay_on_time = now
                state_changed = True
            elif open_relay == 0:
                _LOGGER.debug("%s: Open relay de-energised", self.name)
                if self._is_opening and self._last_relay_on_time:
                    elapsed = now - self._last_relay_on_time
                    delta = (elapsed / self._travel_time) * 100
                    self._current_position = min(100, int(self._current_position + delta))
                    _LOGGER.info(
                        "%s: Moved up for %.2fs (+%d%%). New position: %d%%",
                        self.name, elapsed, delta, self._current_position
                    )
                self._is_opening = False
                self._last_relay_on_time = None
                state_changed = True

        # Handle physical CLOSE relay feedback
        if close_relay is not None:
            if close_relay == 100:
                _LOGGER.debug("%s: Close relay energised (started closing)", self.name)
                self._is_closing = True
                self._is_opening = False
                self._last_relay_on_time = now
                state_changed = True
            elif close_relay == 0:
                _LOGGER.debug("%s: Close relay de-energised", self.name)
                if self._is_closing and self._last_relay_on_time:
                    elapsed = now - self._last_relay_on_time
                    delta = (elapsed / self._travel_time) * 100
                    self._current_position = max(0, int(self._current_position - delta))
                    _LOGGER.info(
                        "%s: Moved down for %.2fs (-%d%%). New position: %d%%",
                        self.name, elapsed, delta, self._current_position
                    )
                self._is_closing = False
                self._last_relay_on_time = None
                state_changed = True

        if state_changed:
            self.async_write_ha_state()

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Write open command (legacy scenes remain unchanged)."""
        await self._device.async_update_cover_state(self._device.unique_id, int(self._device.up))

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Write close command."""
        await self._device.async_update_cover_state(self._device.unique_id, int(self._device.down))

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Write stop command."""
        await self._device.async_update_cover_state(self._device.unique_id, int(self._device.stop))

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set cover position by calculating target difference and executing command."""
        target_position = kwargs[ATTR_POSITION]
        current_position = self._current_position
        
        if target_position == current_position:
            return

        # Calculate time needed to travel to target
        diff = target_position - current_position
        travel_duration = abs(diff) / 100.0 * self._travel_time

        if diff > 0:
            # We need to open the cover
            await self.async_open_cover()
            # Stop the cover after travel_duration seconds
            self.hass.loop.call_later(
                travel_duration,
                lambda: self.hass.async_create_task(self.async_stop_cover())
            )
        else:
            # We need to close the cover
            await self.async_close_cover()
            # Stop the cover after travel_duration seconds
            self.hass.loop.call_later(
                travel_duration,
                lambda: self.hass.async_create_task(self.async_stop_cover())
            )
