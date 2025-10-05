"""The Beurer BF 915 integration."""

import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .bluetooth import BeurerBF915Device
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger("Beurer")

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Beurer BF 915 from a config entry."""
    address = entry.data.get(CONF_ADDRESS)

    if not address:
        _LOGGER.error("No address found in config entry")
        return False

    # Create a minimal BLE device object
    # The BLEDevice constructor signature varies between versions
    try:
        # Try the newer version first (3 arguments)
        from bleak.backends.device import BLEDevice

        try:
            # Most common: address, name, details dict
            ble_device = BLEDevice(address, "Beurer BF 915", {})
            _LOGGER.debug("Created BLEDevice with 3 arguments")
        except TypeError:
            try:
                # Alternative: address, name, details dict, rssi
                ble_device = BLEDevice(address, "Beurer BF 915", {}, -50)
                _LOGGER.debug("Created BLEDevice with 4 arguments")
            except TypeError:
                # Fallback: just address and name
                ble_device = BLEDevice(address, "Beurer BF 915")
                _LOGGER.debug("Created BLEDevice with 2 arguments")
    except ImportError:
        # If BLEDevice is not available, create a simple object
        _LOGGER.warning("BLEDevice not available, using fallback")

        class SimpleBLEDevice:
            def __init__(self, address, name):
                self.address = address
                self.name = name
                self.details = {}
                self.rssi = -50

        ble_device = SimpleBLEDevice(address, "Beurer BF 915")
    except Exception as e:
        _LOGGER.error(f"Failed to create BLE device: {e}")

        # Last resort: just use a simple object with address
        class MinimalBLEDevice:
            def __init__(self, address):
                self.address = address

        ble_device = MinimalBLEDevice(address)

    # Create device instance
    device = BeurerBF915Device(hass, ble_device)

    # Create coordinator
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="{}_{}".format(DOMAIN, address),
        update_method=device.async_update,
        update_interval=SCAN_INTERVAL,
    )

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "device": device,
        "address": address,
    }

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start coordinator - but don't fail if first update fails
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.warning(
            f"First refresh failed (this is normal if scale is sleeping): {e}"
        )
        # Continue anyway - the coordinator will retry

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
