"""Config flow for Beurer BF 915 integration."""

import logging
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

_LOGGER = logging.getLogger("beurer_bf915")

# Add CONF_NAME if not imported
CONF_NAME = "BeurerBF"


class BeurerBF915ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Beurer BF 915."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._discovery_info = None  # type: Optional[BluetoothServiceInfoBleak]
        self._discovered_devices = {}  # type: Dict[str, str]

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input=None  # type: Optional[Dict[str, Any]]
    ) -> FlowResult:
        """Confirm discovery."""
        if user_input is not None:
            return self.async_create_entry(
                title="Beurer BF 915",
                data={
                    CONF_ADDRESS: self._discovery_info.address,
                    CONF_NAME: self._discovery_info.name,
                },
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": (
                    self._discovery_info.name
                    if self._discovery_info
                    else "Beurer BF 915"
                ),
            },
        )

    async def async_step_user(
        self, user_input=None  # type: Optional[Dict[str, Any]]
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}  # type: Dict[str, str]

        if user_input is not None:
            address = user_input[CONF_ADDRESS]

            # Check if already configured
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()

            # Get device name if available
            name = self._discovered_devices.get(address, "Beurer BF 915")

            # Create entry
            return self.async_create_entry(
                title=name,
                data={
                    CONF_ADDRESS: address,
                    CONF_NAME: name,
                },
            )

        # Discover devices
        discovered = await self._async_discover_devices()

        if not discovered:
            # No devices found, show manual entry
            return self.async_show_form(
                step_id="manual",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_ADDRESS): str,
                    }
                ),
                errors={"base": "no_devices_found"},
            )

        # Show selection form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(discovered),
                }
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input=None  # type: Optional[Dict[str, Any]]
    ) -> FlowResult:
        """Handle manual address entry."""
        errors = {}  # type: Dict[str, str]

        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper()

            # Validate MAC address format
            if not self._validate_mac_address(address):
                errors["base"] = "invalid_mac"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Beurer BF 915",
                    data={
                        CONF_ADDRESS: address,
                        CONF_NAME: "Beurer BF 915",
                    },
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                }
            ),
            errors=errors,
        )

    async def _async_discover_devices(self) -> Dict[str, str]:
        """Discover nearby Beurer scales."""
        discovered = {}

        try:
            # Get all discovered bluetooth devices
            discovered_devices = async_discovered_service_info(self.hass)

            for info in discovered_devices:
                # Check if this is a Beurer BF915 scale
                if info.name and "BF915" in info.name:
                    # Add to discovered devices
                    discovered[info.address] = "{} ({})".format(
                        info.name, info.address[-5:]
                    )
                    self._discovered_devices[info.address] = info.name
                # Also check for the service UUID
                elif (
                    info.service_uuids
                    and "0000ffe0-0000-1000-8000-00805f9b34fb" in info.service_uuids
                ):
                    # This might be a Beurer scale even without the name
                    name = info.name or "Beurer Scale"
                    discovered[info.address] = "{} ({})".format(name, info.address[-5:])
                    self._discovered_devices[info.address] = name
        except Exception as e:
            _LOGGER.error("Error discovering devices: %s", e)

        return discovered

    def _validate_mac_address(self, address: str) -> bool:
        """Validate MAC address format."""
        parts = address.split(":")
        if len(parts) != 6:
            return False

        for part in parts:
            if len(part) != 2:
                return False
            try:
                int(part, 16)
            except ValueError:
                return False

        return True
