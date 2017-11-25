import asyncio
import logging

from homeassistant.const import ATTR_BATTERY_LEVEL
from homeassistant.components.binary_sensor import BinarySensorDevice
from homeassistant.helpers.entity import Entity
from custom_components.dcz import (
    ATTR_DISCOVER_DEVICES, DATA_REGISTRY, EventType)

DCZ_TYPE_TO_DEVICE_CLASS = {'ZHAPresence': 'motion',
                            'ZHAOpenClose': 'opening'}

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ['dcz']

def _get_device_class(dcz_type):
    return DCZ_TYPE_TO_DEVICE_CLASS.get(dcz_type, None)

@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices,
                         discovery_info=None):
    """Initialize the platform."""
    if discovery_info is None or discovery_info is False:
        return

    motionSensors = {k: v for k, v in discovery_info.items() if v['type'] == 'ZHAPresence'}
    doorSensors = {k: v for k, v in discovery_info.items() if v['type'] == 'ZHAOpenClose'}

    _LOGGER.error("Presensce sensors: %s", motionSensors)
    _LOGGER.error("Door sensors: %s", doorSensors)

    #Let's create the motion entities
    motionEntities = [DczBinarySensor(sensor_id=k+"sensor",
                           name=v['name'],
                           state=v['state']['presence'],
                           device_class=_get_device_class(v['type']),
                           dcz_registry=hass.data[DATA_REGISTRY])
                for k, v in motionSensors.items()]

    #Let's create the motion entities
    doorEntities = [DczBinarySensor(sensor_id=k+"sensor",
                           name=v['name'],
                           state=v['state']['open'],
                           device_class=_get_device_class(v['type']),
                           dcz_registry=hass.data[DATA_REGISTRY])
                for k, v in doorSensors.items()]

    async_add_devices(motionEntities)
    async_add_devices(doorEntities)

class DczBinarySensor(BinarySensorDevice):
    """representation of a Dcz binary sensor."""

    def __init__(self, sensor_id, name, state, device_class, dcz_registry):
        """Initialize the dcz sensor."""
        self._sensor_id = sensor_id
        self._name = name
        self._state = state
        self._sensor_type = device_class

        dcz_registry.register_sensor_device(sensor_id, self)

    @asyncio.coroutine
    def async_update_from_dcz(self, state):
        """Update the state of the device."""
        self._state = state
        yield from self.async_update_ha_state()

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return self._sensor_type

    @property
    def should_poll(self):
        """No polling needed for binary sensor."""
        return False

    @property
    def name(self):
        """Return the name of the binary sensor."""
        return self._name

    @property
    def is_on(self):
        """Return true if sensor is on."""
        return self._state
