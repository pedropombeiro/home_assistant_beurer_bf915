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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MEASUREMENT_TYPES, MODEL, USER_PROFILES

# _LOGGER = logging.getLogger(**name**)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Beurer BF 915 sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    device = data["device"]
    address = data.get("address", entry.data.get(CONF_ADDRESS))

    sensors = []

    # Create sensors for each user and measurement type
    for user_id, user_profile in USER_PROFILES.items():
        for measurement_key, measurement_config in MEASUREMENT_TYPES.items():
            sensors.append(
                BeurerBF915Sensor(
                    coordinator,
                    device,
                    address,
                    user_id,
                    measurement_key,
                    measurement_config,
                    user_profile["name"],
                )
            )

            async_add_entities(sensors)


class BeurerBF915Sensor(CoordinatorEntity, SensorEntity):
    """Representation of a Beurer BF 915 sensor."""

    def __init__(
        self,
        coordinator,
        device,
        address,
        user_id,
        measurement_type,
        measurement_config,
        user_name,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device = device
        self._address = address
        self._user_id = user_id
        self._measurement_type = measurement_type
        self._measurement_config = measurement_config
        self._user_name = user_name

        # Set unique ID and entity ID
        self._attr_unique_id = "{}_{}_{}".format(address, user_id, measurement_type)

        # Create safe entity ID
        safe_user_name = user_name.lower().replace(" ", "_").replace("-", "_")
        self.entity_id = "sensor.beurer_bf915_{}_{}".format(
            safe_user_name, measurement_type
        )

        # Set name
        self._attr_name = "{} {}".format(user_name, measurement_config["name"])

        # Set icon
        self._attr_icon = measurement_config.get("icon")

        # Set unit
        unit = measurement_config.get("unit")
        if unit:
            self._attr_native_unit_of_measurement = unit

        # Set device class if applicable
        if measurement_type == "weight":
            self._attr_device_class = SensorDeviceClass.WEIGHT

        # Set state class for numerical measurements
        if unit and measurement_type != "body_type":
            self._attr_state_class = SensorStateClass.MEASUREMENT

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name="{} {}".format(MANUFACTURER, MODEL),
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

        return user_data.get(self._measurement_type)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        user_data = self.coordinator.data.get(self._user_id)
        if not user_data:
            return {}

        timestamp = user_data.get("timestamp")
        if timestamp:
            return {
                "last_measurement": timestamp.isoformat(),
                "user_id": self._user_id,
                "user_name": self._user_name,
            }

        return {}
