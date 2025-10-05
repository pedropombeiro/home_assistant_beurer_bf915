"""Bluetooth communication for Beurer BF 915 - ESPHome Proxy Version."""

import asyncio
import logging
import struct
from datetime import datetime
from typing import Any, Dict, Optional

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
)

from .const import CHARACTERISTIC_UUID, CMD_INIT, SERVICE_UUID, USER_PROFILES

_LOGGER = logging.getLogger("beurer_bf915")


class BeurerBF915Device:
    """Beurer BF 915 device for ESPHome Bluetooth Proxy."""

    def __init__(self, hass, ble_device):
        """Initialize the device."""
        self.hass = hass
        self._measurements = {}
        self._is_updating = False
        self._last_error = None

        # Extract address
        if hasattr(ble_device, "address"):
            self.address = ble_device.address.upper()
        else:
            self.address = str(ble_device).upper()

        _LOGGER.info(f"BF 915 ESPHome Proxy version initialized for: {self.address}")

        # Initialize measurements
        for user_id, profile in USER_PROFILES.items():
            self._measurements[user_id] = self._create_empty_measurement(user_id)

    def _create_empty_measurement(self, user_id: int) -> Dict[str, Any]:
        """Create empty measurement dict."""
        profile = USER_PROFILES[user_id]
        return {
            "timestamp": datetime.now(),
            "weight": 0.0,
            "body_fat": 0.0,
            "water": 0.0,
            "muscle": 0.0,
            "bone_mass": 0.0,
            "bmi": 0.0,
            "bmr": 0,
            "amr": 0,
            "visceral_fat": 0,
            "metabolic_age": profile["age"],
            "body_type": "Unknown",
        }

    async def async_update(self) -> Dict[int, Dict[str, Any]]:
        """Update data from scale via ESPHome proxy."""
        if self._is_updating:
            _LOGGER.debug("Already updating, skipping")
            return self._measurements

        self._is_updating = True

        try:
            # Get device via Home Assistant's Bluetooth system
            # This ensures we use the proxy that can reach the device
            device = async_ble_device_from_address(
                self.hass,
                self.address,
                connectable=True,  # We need a connectable device
            )

            if not device:
                _LOGGER.debug(f"Device {self.address} not found via proxy")
                return self._measurements

            _LOGGER.info(f"Found device via proxy: {device}")

            # Try to connect using bleak with ESPHome backend
            await self._connect_via_proxy(device)

        except Exception as e:
            _LOGGER.error(f"Update error: {e}")
            self._last_error = str(e)
        finally:
            self._is_updating = False

        return self._measurements

    async def _connect_via_proxy(self, device):
        """Connect to device via ESPHome proxy."""
        from bleak import BleakClient
        from bleak_retry_connector import establish_connection

        client = None

        try:
            _LOGGER.info(f"Attempting proxy connection to {self.address}")

            client = await establish_connection(
                BleakClient,
                device,
                name=self.address,
                disconnected_callback=lambda _: _LOGGER.debug("Device disconnected"),
                use_services_cache=True,  # Add this
                ble_device_callback=lambda: device,  # Add this
            )

            _LOGGER.info("✓ Connected via proxy!")

            # Skip the service discovery section entirely
            # Go straight to communication
            await self._communicate_simple(client)

        except asyncio.TimeoutError:
            _LOGGER.error("Proxy connection timeout")
        except Exception as e:
            _LOGGER.error(f"Proxy connection error: {e}", exc_info=True)
        finally:
            if client and client.is_connected:
                await client.disconnect()

    async def _communicate_simple(self, client):
        """Simple communication without complex service checking."""
        try:
            # Send init command
            try:
                # Verify characteristic exists
                services = await client.get_services()
                char = services.get_characteristic(CHARACTERISTIC_UUID)
                if not char:
                    _LOGGER.error(f"Characteristic {CHARACTERISTIC_UUID} not found")
                    return

                _LOGGER.debug("Sending init command")
                await client.write_gatt_char(
                    CHARACTERISTIC_UUID, CMD_INIT, response=True
                )
                _LOGGER.info("Init command sent")
            except Exception as e:
                _LOGGER.warning(f"Init command failed: {e}")
                # Continue anyway

            await asyncio.sleep(1)

            # Setup notifications
            received_data = []

            def notification_handler(sender, data):
                """Handle notifications from scale."""
                _LOGGER.info(f"✓ Data received: {len(data)} bytes")
                received_data.append(data)
                # Parse immediately
                self._parse_measurement(data)

            # Start notifications
            try:
                await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
                _LOGGER.info("Notifications enabled")
            except Exception as e:
                _LOGGER.error(f"Failed to start notifications: {e}")
                return

            # Request measurements for each user
            for user_id, profile in USER_PROFILES.items():
                try:
                    gender_byte = 0x01 if profile["gender"] == "male" else 0x00

                    # Build user command
                    user_cmd = bytes(
                        [
                            0xE7,
                            0x41,  # Command
                            user_id,  # User ID
                            gender_byte,  # Gender
                            profile["age"],  # Age
                            profile["height"],  # Height in cm
                            0x03,  # Activity level
                            0x00,
                            0x00,
                            0x00,  # Reserved
                        ]
                    )

                    _LOGGER.debug(
                        f"Requesting data for user {user_id}: {profile['name']}"
                    )
                    await client.write_gatt_char(
                        CHARACTERISTIC_UUID, user_cmd, response=False
                    )

                    # Wait for response
                    await asyncio.sleep(1.5)

                except Exception as e:
                    _LOGGER.error(f"Failed to request user {user_id} data: {e}")

            # Extra wait for any delayed responses
            await asyncio.sleep(2)

            # Stop notifications
            try:
                await client.stop_notify(CHARACTERISTIC_UUID)
                _LOGGER.debug("Notifications stopped")
            except:
                pass

            if received_data:
                _LOGGER.info(
                    f"✓ Successfully received {len(received_data)} data packets"
                )
            else:
                _LOGGER.warning("No data received from scale")

                # Try a direct read as fallback
                try:
                    data = await client.read_gatt_char(CHARACTERISTIC_UUID)
                    _LOGGER.info(f"Direct read succeeded: {data.hex()}")
                    self._parse_measurement(data)
                except Exception as e:
                    _LOGGER.debug(f"Direct read also failed: {e}")

        except Exception as e:
            _LOGGER.error(f"Communication error: {e}")

    def _parse_measurement(self, data: bytes):
        """Parse measurement data from scale."""
        if not data or len(data) < 10:
            _LOGGER.debug(f"Data too short: {len(data) if data else 0} bytes")
            return

        _LOGGER.info(f"Parsing measurement: {data.hex()}")

        # Try to extract weight from common positions
        weight_found = False

        for position in [7, 8, 6, 4, 5, 9]:
            if position + 2 <= len(data):
                try:
                    # Parse as little-endian unsigned short, divide by 10
                    weight_raw = struct.unpack("<H", data[position : position + 2])[0]
                    weight = weight_raw / 10.0

                    # Validate weight range
                    if 2.0 <= weight <= 300.0:
                        _LOGGER.info(
                            f"✓✓✓ WEIGHT FOUND: {weight} kg at byte {position}"
                        )

                        # Try to identify user
                        user_id = 1  # Default
                        for uid_pos in [2, 3, 1, 0]:
                            if uid_pos < len(data) and data[uid_pos] in USER_PROFILES:
                                user_id = data[uid_pos]
                                _LOGGER.debug(
                                    f"User ID {user_id} found at byte {uid_pos}"
                                )
                                break

                        # Update measurements
                        self._measurements[user_id]["weight"] = round(weight, 1)
                        self._measurements[user_id]["timestamp"] = datetime.now()

                        # Calculate BMI
                        profile = USER_PROFILES[user_id]
                        height_m = profile["height"] / 100
                        bmi = weight / (height_m**2)
                        self._measurements[user_id]["bmi"] = round(bmi, 1)

                        # Try to parse additional measurements if available
                        if len(data) >= position + 10:
                            self._parse_extended(data, position + 2, user_id)

                        weight_found = True
                        _LOGGER.info(
                            f"Updated {profile['name']}: {weight} kg, BMI: {round(bmi, 1)}"
                        )
                        break

                except Exception as e:
                    _LOGGER.debug(f"Parse error at position {position}: {e}")

        if not weight_found:
            _LOGGER.warning(f"No valid weight found in {len(data)} bytes")
            # Log raw bytes for debugging
            hex_str = " ".join([f"{b:02x}" for b in data[:20]])
            _LOGGER.debug(f"First 20 bytes: {hex_str}")

    def _parse_extended(self, data: bytes, start_pos: int, user_id: int):
        """Parse extended measurements."""
        try:
            # Body fat
            if start_pos + 2 <= len(data):
                body_fat = (
                    struct.unpack("<H", data[start_pos : start_pos + 2])[0] / 10.0
                )
                if 0.1 <= body_fat <= 80.0:
                    self._measurements[user_id]["body_fat"] = round(body_fat, 1)
                    _LOGGER.debug(f"Body fat: {body_fat}%")

            # Water
            if start_pos + 4 <= len(data):
                water = (
                    struct.unpack("<H", data[start_pos + 2 : start_pos + 4])[0] / 10.0
                )
                if 0.1 <= water <= 80.0:
                    self._measurements[user_id]["water"] = round(water, 1)
                    _LOGGER.debug(f"Water: {water}%")

            # Muscle
            if start_pos + 6 <= len(data):
                muscle = (
                    struct.unpack("<H", data[start_pos + 4 : start_pos + 6])[0] / 10.0
                )
                if 0.1 <= muscle <= 80.0:
                    self._measurements[user_id]["muscle"] = round(muscle, 1)
                    _LOGGER.debug(f"Muscle: {muscle}%")

        except Exception as e:
            _LOGGER.debug(f"Extended parse error: {e}")
