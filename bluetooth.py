"""Bluetooth communication for Beurer BF 915."""

import asyncio
import logging
import struct
from datetime import datetime
from typing import Any, Dict, Optional

from .const import CHARACTERISTIC_UUID, CMD_INIT, DOMAIN, SERVICE_UUID, USER_PROFILES

_LOGGER = logging.getLogger(DOMAIN)


class BeurerBF915Device:
    """Representation of a Beurer BF 915 device."""

    def __init__(self, hass, ble_device):
        """Initialize the device."""
        self.hass = hass
        self.ble_device = ble_device
        self._measurements = {}
        self._last_update = None
        self._is_scanning = False

        # Extract address from ble_device (handle different object types)
        if hasattr(ble_device, "address"):
            self.address = ble_device.address
        elif hasattr(ble_device, "get") and callable(ble_device.get):
            self.address = ble_device.get("address", "unknown")
        else:
            self.address = str(ble_device)

        _LOGGER.info(f"Initialized Beurer BF 915 device for address: {self.address}")

        # Initialize measurements with default values
        for user_id, profile in USER_PROFILES.items():
            self._measurements[user_id] = self._get_default_measurements(user_id)

    def _get_default_measurements(self, user_id: int) -> Dict[str, Any]:
        """Get default measurements for a user."""
        profile = USER_PROFILES[user_id]
        # Calculate a reasonable default BMI
        height_m = profile["height"] / 100
        default_weight = 70 if profile["gender"] == "male" else 60
        default_bmi = default_weight / (height_m**2)

        return {
            "timestamp": datetime.now(),
            "weight": 0.0,
            "body_fat": 0.0,
            "water": 0.0,
            "muscle": 0.0,
            "bone_mass": 0.0,
            "bmi": round(default_bmi, 1),
            "bmr": 1500 if profile["gender"] == "male" else 1200,
            "amr": 2000 if profile["gender"] == "male" else 1600,
            "visceral_fat": 0,
            "metabolic_age": profile["age"],
            "body_type": "Unknown",
        }

    async def async_update(self) -> Dict[int, Dict[str, Any]]:
        """Update data from the scale."""
        if self._is_scanning:
            _LOGGER.debug("Already scanning, skipping update")
            return self._measurements

        self._is_scanning = True

        try:
            # Check if bleak is available
            try:
                from bleak import BleakClient, BleakScanner
            except ImportError:
                _LOGGER.error(
                    "Bleak library not available. Please restart Home Assistant after installation."
                )
                return self._measurements

            # Quick scan to see if scale is advertising
            _LOGGER.debug(f"Scanning for scale at {self.address}")

            scanner = BleakScanner()
            devices = []

            try:
                # Short scan with timeout
                devices = await asyncio.wait_for(scanner.discover(), timeout=5.0)
            except asyncio.TimeoutError:
                _LOGGER.debug("Scan timeout - scale might be sleeping")
            except Exception as e:
                _LOGGER.debug(f"Scan error: {e}")

            # Check if our scale was found
            scale_found = False
            for device in devices:
                if device.address.upper() == self.address.upper():
                    scale_found = True
                    _LOGGER.info(f"Found scale: {device.name} (RSSI: {getattr(device, "rssi", None)})")

                    # Try to connect
                    await self._connect_and_read()
                    break

            if not scale_found:
                _LOGGER.debug(
                    f"Scale {self.address} not found in scan (found {len(devices)} other devices)"
                )
                # Don't log as error - this is normal when scale is sleeping

        except Exception as e:
            _LOGGER.error(f"Update error: {e}", exc_info=True)
        finally:
            self._is_scanning = False

        return self._measurements

    async def _connect_and_read(self):
        """Connect to the scale and attempt to read data."""
        try:
            from bleak import BleakClient

            _LOGGER.info(f"Attempting to connect to {self.address}")

            # Create client with timeout
            client = BleakClient(self.address, timeout=10.0)

            try:
                # Connect
                connected = await client.connect()

                if not connected:
                    _LOGGER.warning("Connection failed")
                    return

                _LOGGER.info("Connected successfully!")

                # Discover services
                services = client.services
                service_found = False
                char_found = False

                for service in services:
                    _LOGGER.debug(f"Service: {service.uuid}")
                    if SERVICE_UUID.lower() in service.uuid.lower():
                        service_found = True

                        for char in service.characteristics:
                            _LOGGER.debug(f"  Characteristic: {char.uuid}")
                            if CHARACTERISTIC_UUID.lower() in char.uuid.lower():
                                char_found = True
                                _LOGGER.debug(f"    Properties: {char.properties}")

                if not service_found:
                    _LOGGER.error(f"Service {SERVICE_UUID} not found")
                    return

                if not char_found:
                    _LOGGER.error(f"Characteristic {CHARACTERISTIC_UUID} not found")
                    return

                # Setup notification handler
                self._notification_buffer = []

                def notification_handler(sender, data):
                    """Handle notifications."""
                    _LOGGER.debug(f"Notification from {sender}: {data.hex()}")
                    self._notification_buffer.append(data)

                # Start notifications
                await client.start_notify(CHARACTERISTIC_UUID, notification_handler)

                # Send init command
                _LOGGER.debug("Sending initialization command")
                await client.write_gatt_char(
                    CHARACTERISTIC_UUID, CMD_INIT, response=False
                )

                # Wait for response
                await asyncio.sleep(1)

                # Request data for each user
                for user_id, profile in USER_PROFILES.items():
                    _LOGGER.debug(
                        f"Requesting data for {profile['name']} (user {user_id})"
                    )

                    # Build command
                    gender_byte = 0x01 if profile["gender"] == "male" else 0x00
                    command = bytes([0xE7, 0x41]) + struct.pack(
                        "BBBBBBBB",
                        user_id,
                        gender_byte,
                        profile["age"],
                        profile["height"],
                        0x03,  # Activity level
                        0x00,
                        0x00,
                        0x00,  # Reserved
                    )

                    await client.write_gatt_char(
                        CHARACTERISTIC_UUID, command, response=False
                    )

                    # Wait for response
                    await asyncio.sleep(1)

                # Process any notifications received
                for data in self._notification_buffer:
                    self._process_notification(data)

                # Stop notifications
                await client.stop_notify(CHARACTERISTIC_UUID)

                _LOGGER.info("Data collection complete")

            finally:
                # Always disconnect
                if client.is_connected:
                    await client.disconnect()
                    _LOGGER.debug("Disconnected")

        except Exception as e:
            _LOGGER.error(f"Connection error: {e}", exc_info=True)

    def _process_notification(self, data: bytearray):
        """Process a notification from the scale."""
        if len(data) < 10:
            _LOGGER.debug(f"Short notification: {data.hex()}")
            return

        _LOGGER.info(f"Processing notification of {len(data)} bytes")

        # Try to parse as measurement
        # The exact format varies, but weight is usually reliable
        try:
            # Try to find weight (usually 2 bytes in 0.1 kg units)
            # Common positions: bytes 7-8, 8-9, or 6-7
            for pos in [7, 8, 6]:
                if pos + 2 <= len(data):
                    weight_raw = struct.unpack("<H", data[pos : pos + 2])[0]
                    weight = weight_raw / 10.0

                    # Validate weight
                    if 2.0 <= weight <= 300.0:
                        _LOGGER.info(
                            f"Found valid weight at position {pos}: {weight} kg"
                        )

                        # Try to identify user (usually byte 2 or 3)
                        user_id = None
                        for uid_pos in [2, 3, 1]:
                            if uid_pos < len(data) and data[uid_pos] in USER_PROFILES:
                                user_id = data[uid_pos]
                                break

                        if not user_id:
                            # Default to user 1 if can't identify
                            user_id = 1
                            _LOGGER.warning(
                                "Could not identify user, defaulting to user 1"
                            )

                        # Update measurements for this user
                        user = USER_PROFILES[user_id]
                        self._measurements[user_id]["weight"] = round(weight, 1)
                        self._measurements[user_id]["timestamp"] = datetime.now()

                        # Try to parse other measurements if data is long enough
                        if len(data) >= 20:
                            try:
                                self._measurements[user_id]["body_fat"] = (
                                    round(struct.unpack("<H", data[9:11])[0] / 10.0, 1)
                                    if data[9:11] != b"\xff\xff"
                                    else 0.0
                                )

                                self._measurements[user_id]["water"] = (
                                    round(struct.unpack("<H", data[11:13])[0] / 10.0, 1)
                                    if data[11:13] != b"\xff\xff"
                                    else 0.0
                                )

                                self._measurements[user_id]["muscle"] = (
                                    round(struct.unpack("<H", data[13:15])[0] / 10.0, 1)
                                    if data[13:15] != b"\xff\xff"
                                    else 0.0
                                )

                                self._measurements[user_id]["bone_mass"] = (
                                    round(struct.unpack("<H", data[15:17])[0] / 10.0, 1)
                                    if data[15:17] != b"\xff\xff"
                                    else 0.0
                                )

                                # Calculate BMI
                                height_m = user["height"] / 100
                                self._measurements[user_id]["bmi"] = round(
                                    weight / (height_m**2), 1
                                )

                                _LOGGER.info(
                                    f"Updated full measurements for {user['name']}"
                                )
                            except Exception as e:
                                _LOGGER.debug(
                                    f"Could not parse additional measurements: {e}"
                                )

                        _LOGGER.info(f"Updated weight for {user['name']}: {weight} kg")
                        break

        except Exception as e:
            _LOGGER.error(f"Failed to process notification: {e}")
