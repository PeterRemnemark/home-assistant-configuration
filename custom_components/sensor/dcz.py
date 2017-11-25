import logging
import asyncio

from custom_components.dcz import (
    ATTR_DISCOVER_DEVICES, DATA_REGISTRY)

from homeassistant.const import TEMP_CELSIUS, ATTR_BATTERY_LEVEL
from homeassistant.helpers.entity import Entity
from custom_components.dcz import EventType

_LOGGER = logging.getLogger(__name__)

ICON = 'mdi:battery'

DCZ_TYPE_TO_DEVICE_CLASS = {'ZHATemperature': 'temperature',
                            'ZHALightLevel': 'lux',
                            'ZHASwitch': 'switch',
                            'CLIPSwitch': 'switch'}

def _get_device_class(dcz_type):
    return DCZ_TYPE_TO_DEVICE_CLASS.get(dcz_type, None)

@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices,
                         discovery_info=None):
    """Initialize the platform."""
    if discovery_info is None or discovery_info is False:
        return

    #Let's add sensors first
    temperatureSensors = {k: v for k, v in discovery_info.items() if v['type'] == 'ZHATemperature'}
    lightSensors = {k: v for k, v in discovery_info.items() if v['type'] == 'ZHALightLevel'}
    switches = {k: v for k, v in discovery_info.items() if v['type'] == 'ZHASwitch'}
    clipSwitches = {k: v for k, v in discovery_info.items() if v['type'] == 'CLIPSwitch'}
    #this is here so we can create battery sensors only, rest is in binary sensors
    motionSensors = {k: v for k, v in discovery_info.items() if v['type'] == 'ZHAPresence'}
    doorSensors = {k: v for k, v in discovery_info.items() if v['type'] == 'ZHAOpenClose'}

    #Temperature entities
    tempEntities = [DczSensor(sensor_id=k+"sensor",
                           name=v['name'],
                           state=v['state']['temperature']/float(100),
                           device_class=_get_device_class(v['type']),
                           dcz_registry=hass.data[DATA_REGISTRY])
                for k, v in temperatureSensors.items()]

    #Let's create the light entities
    lightEntities = [DczSensor(sensor_id=k+"sensor",
                           name=v['name'],
                           state=round(10 ** (float(v['state']['lightlevel'] - 1) / 10000),1),
                           device_class=_get_device_class(v['type']),
                           dcz_registry=hass.data[DATA_REGISTRY])
                for k, v in lightSensors.items()]

    #Let's create the light entities
    switchEntities = [DczSensor(sensor_id=k+"sensor",
                           name=v['name'],
                           state=v['state']['buttonevent'],
                           device_class=_get_device_class(v['type']),
                           dcz_registry=hass.data[DATA_REGISTRY])
                for k, v in switches.items()]

    #battery entities (let's try)
    switchBatteryEntities = [DczBatterySensor(sensor_id=k+"battSensor",
                           name="Battery "+v['name'],
                           state=v['config']['battery'],
                           device_class=_get_device_class(v['type']),
                           dcz_registry=hass.data[DATA_REGISTRY])
                for k, v in switches.items()]

    #battery entities (let's try)
    clipSwitchBatteryEntities = [DczBatterySensor(sensor_id=k+"battSensor",
                           name="Battery "+v['name'],
                           state=v['config']['battery'],
                           device_class=_get_device_class(v['type']),
                           dcz_registry=hass.data[DATA_REGISTRY])
                for k, v in clipSwitches.items()]

    #battery entities (let's try)
    motionSensorBatteryEntities = [DczBatterySensor(sensor_id=k+"battSensor",
                           name="Battery "+v['name'],
                           state=v['config']['battery'],
                           device_class=_get_device_class(v['type']),
                           dcz_registry=hass.data[DATA_REGISTRY])
                for k, v in motionSensors.items()]

    #battery entities (let's try)
    doorSensorBatteryEntities = [DczBatterySensor(sensor_id=k+"battSensor",
                           name="Battery "+v['name'],
                           state=v['config']['battery'] if "battery" in v['config'] else "unkown",
                           device_class=_get_device_class(v['type']),
                           dcz_registry=hass.data[DATA_REGISTRY])
                for k, v in doorSensors.items()]

#Let's create the light entities
    clipSwitchEntities = [DczSensor(sensor_id=k+"sensor",
                           name=v['name'],
                           state=v['state']['buttonevent'],
                           device_class=_get_device_class(v['type']),
                           dcz_registry=hass.data[DATA_REGISTRY])
                for k, v in clipSwitches.items()]

    async_add_devices(tempEntities)
    async_add_devices(lightEntities)
    async_add_devices(switchEntities)
    async_add_devices(clipSwitchEntities)
    async_add_devices(switchBatteryEntities)
    async_add_devices(clipSwitchBatteryEntities)
    async_add_devices(motionSensorBatteryEntities)
    async_add_devices(doorSensorBatteryEntities)

class DczSensor(Entity):
    """Represents a sensor based on an DeConz Sensor."""

    def __init__(self, sensor_id, name, state, device_class, dcz_registry):
        """Initialize the sensor device."""
        self._sensor_id = sensor_id
        self._name = name
        self._state = state
        self._device_class = device_class
        self._unit_of_measurement = None

        if self._device_class=="temperature":
            self._unit_of_measurement = TEMP_CELSIUS
        elif self._device_class=="lux":
            self._unit_of_measurement = "lux"

        dcz_registry.register_sensor_device(sensor_id, self)

    @asyncio.coroutine
    def async_update_from_dcz(self, state):
        """Update the state of the device."""
        self._state = state
        _LOGGER.error("The value is %s", state)
        yield from self.async_update_ha_state()

    @property
    def state(self):
        return self._state

    @property
    def name(self):
        """The name of the device."""
        return self._name

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def device_class(self):
        """The device class."""
        return self._device_class

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

class DczBatterySensor(DczSensor):
    """Represents a sensor based on an DeConz Sensor."""

    def __init__(self, sensor_id, name, state, device_class, dcz_registry):
        """Initialize the sensor device."""
        self._sensor_id = sensor_id
        self._name = name
        self._state = state
        self._device_class = device_class

        self._unit_of_measurement = "%"

        dcz_registry.register_sensor_device(sensor_id, self)

    @asyncio.coroutine
    def async_update_from_dcz(self, state, type):
        _LOGGER.error("Event was battery level")
        self._state = state
        yield from self.async_update_ha_state()

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return ICON
