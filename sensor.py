"""Sensor platform for Beurer BF 915."""

import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MEASUREMENT_TYPES, MODEL, USER_PROFILES

_LOGGER = logging.getLogger("beurer_bf915")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Beurer BF 915 sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    device = data["device"]
    address = data.get("address", entry.data.get(CONF_ADDRESS, "unknown"))

    # Clean up the MAC address (remove colons for entity IDs)
    clean_address = address.replace(":", "").lower()

    sensors = []

    # Create sensors for each user and measurement type
    for user_id, user_profile in USER_PROFILES.items():
        # Clean username for entity IDs (remove spaces and special chars)
        clean_username = (
            user_profile["name"].lower().replace(" ", "_").replace("-", "_")
        )

        for measurement_key, measurement_config in MEASUREMENT_TYPES.items():
            sensor = BeurerBF915Sensor(
                coordinator,
                device,
                clean_address,
                user_id,
                measurement_key,
                measurement_config,
                user_profile["name"],
                clean_username,
            )
            sensors.append(sensor)

    async_add_entities(sensors)


class BeurerBF915Sensor(CoordinatorEntity, SensorEntity):
    """Representation of a Beurer BF 915 sensor."""

    def __init__(
        self,
        coordinator,
        device,
        clean_address,
        user_id,
        measurement_type,
        measurement_config,
        user_name,
        clean_username,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device = device
        self._clean_address = clean_address
        self._user_id = user_id
        self._measurement_type = measurement_type
        self._measurement_config = measurement_config
        self._user_name = user_name
        self._clean_username = clean_username

        # Create unique ID using clean address, user ID, and measurement type
        self._attr_unique_id = f"bf915_{clean_address}_{user_id}_{measurement_type}"

        # Set entity ID suggestion
        self._attr_has_entity_name = True
        self._attr_suggested_entity_id = (
            f"sensor.bf915_{clean_username}_{measurement_type}"
        )

        # Set name (will be combined with device name)
        self._attr_name = f"{user_name} {measurement_config['name']}"

        # Set icon
        if "icon" in measurement_config:
            self._attr_icon = measurement_config["icon"]

        # Set unit
        if "unit" in measurement_config and measurement_config["unit"]:
            self._attr_native_unit_of_measurement = measurement_config["unit"]

        # Set device class if applicable
        if measurement_type == "weight":
            self._attr_device_class = SensorDeviceClass.WEIGHT

        # Set state class for numerical measurements
        if measurement_config.get("unit") and measurement_type != "body_type":
            self._attr_state_class = SensorStateClass.MEASUREMENT

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{clean_address}")},
            name=f"{MANUFACTURER} {MODEL}",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def native_value(self) -> Optional[Any]:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        user_data = self.coordinator.data.get(self._user_id)
        if not user_data:
            return None

        value = user_data.get(self._measurement_type)

        # Return None instead of 0 for uninitialized measurements
        if value == 0 or value == 0.0:
            return None

        return value

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "user_id": self._user_id,
            "user_name": self._user_name,
        }

        if self.coordinator.data:
            user_data = self.coordinator.data.get(self._user_id)
            if user_data and user_data.get("timestamp"):
                attrs["last_measurement"] = user_data["timestamp"].isoformat()

        return attrs
