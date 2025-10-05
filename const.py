"""Constants for the Beurer BF 915 integration."""

from datetime import timedelta

# Integration domain
DOMAIN = "beurer_bf915"

# Device info
MANUFACTURER = "Beurer"
MODEL = "BF 915"

# Bluetooth UUIDs
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# Update interval
SCAN_INTERVAL = timedelta(seconds=30)

# Commands
CMD_INIT = bytes([0xE6, 0x01])
CMD_GET_STORED_MEASUREMENTS = 0xE7
CMD_LIVE_MEASUREMENT = 0xE7

# User configuration
MAX_USERS = 8
MEASUREMENTS_PER_USER = 30

# Measurement types with all their properties
MEASUREMENT_TYPES = {
    "weight": {"unit": "kg", "icon": "mdi:weight-kilogram", "name": "Weight"},
    "body_fat": {"unit": "%", "icon": "mdi:water-percent", "name": "Body Fat"},
    "water": {"unit": "%", "icon": "mdi:water", "name": "Body Water"},
    "muscle": {"unit": "%", "icon": "mdi:arm-flex", "name": "Muscle Mass"},
    "bone_mass": {"unit": "kg", "icon": "mdi:bone", "name": "Bone Mass"},
    "bmi": {"unit": "", "icon": "mdi:human", "name": "BMI"},
    "bmr": {"unit": "kcal", "icon": "mdi:fire", "name": "Basal Metabolic Rate"},
    "amr": {"unit": "kcal", "icon": "mdi:run", "name": "Active Metabolic Rate"},
    "visceral_fat": {"unit": "", "icon": "mdi:numeric", "name": "Visceral Fat"},
    "metabolic_age": {
        "unit": "years",
        "icon": "mdi:calendar-clock",
        "name": "Metabolic Age",
    },
    "body_type": {"unit": "", "icon": "mdi:human-male", "name": "Body Type"},
}

# Default user profiles - MODIFY THESE FOR YOUR FAMILY

USER_PROFILES = {
    1: {"name": "Pedro", "gender": "male", "age": 50, "height": 181},
    2: {"name": "Sofia", "gender": "female", "age": 53, "height": 167},
    3: {"name": "Diogo", "gender": "male", "age": 21, "height": 184},
    4: {"name": "Mariana", "gender": "female", "age": 19, "height": 165},
}
