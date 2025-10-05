"""The Beurer BF 915 integration."""

import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .bluetooth import BeurerBF915Device
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger("beurer_bf915")

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Beurer BF 915 from a config entry."""
    address = entry.data.get(CONF_ADDRESS, "").upper()

    _LOGGER.info(f"Setting up Beurer BF 915 integration for address: {address}")

    if not address:
        _LOGGER.error("No address found in config entry")
        return False

    # Create a simple device object
    class SimpleDevice:
        def __init__(self, addr):
            self.address = addr

    ble_device = SimpleDevice(address)

    # Create device instance
    device = BeurerBF915Device(hass, ble_device)

    # Create update method that logs
    async def update_with_logging():
        """Update method with logging."""
        _LOGGER.debug(f"Running update for {address}")
        try:
            result = await device.async_update()
            _LOGGER.debug(f"Update complete, got {len(result)} user measurements")
            return result
        except Exception as e:
            _LOGGER.error(f"Update failed: {e}")
            raise UpdateFailed(f"Failed to update: {e}")

    # Create coordinator
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"beurer_{address.replace(':', '')}",
        update_method=update_with_logging,
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

    # Try first update but don't fail if it doesn't work
    try:
        _LOGGER.info("Attempting first update...")
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.info("First update completed")
    except Exception as e:
        _LOGGER.warning(
            f"First update failed (this is normal if scale is sleeping): {e}"
        )

    _LOGGER.info(f"Beurer BF 915 setup complete for {address}")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Beurer BF 915 integration")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
