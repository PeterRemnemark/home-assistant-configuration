import logging
import asyncio

from homeassistant.components.light import (
    ATTR_BRIGHTNESS, ATTR_COLOR_TEMP, ATTR_RGB_COLOR, ATTR_XY_COLOR, SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR_TEMP, SUPPORT_RGB_COLOR, SUPPORT_XY_COLOR, Light)
from homeassistant.components.light import \
    PLATFORM_SCHEMA as LIGHT_PLATFORM_SCHEMA
from custom_components.dcz import (
    ATTR_DISCOVER_DEVICES, DATA_REGISTRY, DATA_API)

from homeassistant.util import color as color_util

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ['dcz']

DCZ_TYPE_TO_DEVICE_CLASS = {'Color temperature light': 'ikea_light',
                            'Dimmable light': 'ikea_light',
                            'LightGroup': 'lightgroup',
                            'Extended color light': 'osram_light'}


SUPPORT_DIMMABLE_LIGHT = (SUPPORT_BRIGHTNESS)
SUPPORT_IKEA_DIMMABLE_LIGHT = (SUPPORT_DIMMABLE_LIGHT)
SUPPORT_WHITE_SPECTRUM_LIGHT = (SUPPORT_DIMMABLE_LIGHT|SUPPORT_COLOR_TEMP)
SUPPORT_IKEA_WHITE_SPECTRUM_LIGHT = (SUPPORT_WHITE_SPECTRUM_LIGHT)
SUPPORT_EXTENDED_LIGHT = (SUPPORT_DIMMABLE_LIGHT|SUPPORT_XY_COLOR|SUPPORT_RGB_COLOR)
SUPPORT_OSRAM_LIGHTIFY = (SUPPORT_EXTENDED_LIGHT)

SUPPORT_DCZ = {
    'Extended color light': SUPPORT_OSRAM_LIGHTIFY,
    'Dimmable light': SUPPORT_IKEA_DIMMABLE_LIGHT,
    'Color temperature light': SUPPORT_IKEA_WHITE_SPECTRUM_LIGHT
    }


def _get_device_class(dcz_type):
    return DCZ_TYPE_TO_DEVICE_CLASS.get(dcz_type, None)

PLATFORM_SCHEMA = LIGHT_PLATFORM_SCHEMA

@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up the DeConz Light platform."""
    if discovery_info is None or discovery_info is False:
        return

    lights = {k: v for k, v in discovery_info.items() if v['type'] == 'Color temperature light'}
    lightsNC = {k: v for k, v in discovery_info.items() if v['type'] == 'Dimmable light'}
    lightsOsram = {k: v for k, v in discovery_info.items() if v['type'] == 'Extended color light'}
    groups = {k: v for k, v in discovery_info.items() if v['type'] == 'LightGroup' and len(v['lights'])>0}

    #Let's create the lights entities
    lightsEntities = [DeConzLight(id=k,
                           sensor_id=k+'lights',
                           name=v['name'],
                           state=v['state']['on'],
                           device_class=_get_device_class(v['type']),
                           reachable=v['state']['reachable'],
                           dimmer=v['state']['bri'],
                           ct_color=v['state']['ct'],
                           xy_color=None,
                           dcz_registry=hass.data[DATA_REGISTRY],
                           api=hass.data[DATA_API],
                           isGroup=False)
                for k, v in lights.items()]

    lightsEntitiesNC = [DeConzLight(id=k,
                           sensor_id=k+'lights',
                           name=v['name'],
                           state=v['state']['on'],
                           device_class=_get_device_class(v['type']),
                           reachable=v['state']['reachable'],
                           dimmer=v['state']['bri'],
                           ct_color=None,
                           xy_color=None,
                           dcz_registry=hass.data[DATA_REGISTRY],
                           api=hass.data[DATA_API],
                           isGroup=False)
                for k, v in lightsNC.items()]

    groupEntities = [DeConzLight(id=k,
                           sensor_id=k+'group',
                           name=v['name'],
                           state=v['action']['on'],
                           device_class=_get_device_class(v['type']),
                           reachable=True,
                           dimmer=v['action']['bri'],
                           ct_color=v['action']['ct'],
                           xy_color=None,
                           dcz_registry=hass.data[DATA_REGISTRY],
                           api=hass.data[DATA_API],
                           isGroup=True)
                for k, v in groups.items()]

    osramLightsEntities = [DeConzLight(id=k,
                           sensor_id=k+'lights',
                           name=v['name'],
                           state=v['state']['on'],
                           device_class=_get_device_class(v['type']),
                           reachable=v['state']['reachable'],
                           dimmer=v['state']['bri'],
                           ct_color=None,
                           xy_color=v['state']['xy'],
                           dcz_registry=hass.data[DATA_REGISTRY],
                           api=hass.data[DATA_API],
                           isGroup=False)
                for k, v in lightsOsram.items()]

    if osramLightsEntities:
        async_add_devices(osramLightsEntities)

    if lightsEntities:
        async_add_devices(lightsEntities)

    if lightsEntitiesNC:
        async_add_devices(lightsEntitiesNC)

    if groupEntities:
        async_add_devices(groupEntities)

class DeConzLight(Light):
    """The platform class required by Home Asisstant."""

    def __init__(self, id, sensor_id, name, state, device_class, reachable, dimmer, ct_color, xy_color, dcz_registry, api, isGroup):
        """Initialize a Light."""
        self._isGroup = isGroup
        self._features = SUPPORT_BRIGHTNESS

        # we have colors
        if xy_color is not None:
            self._features |= SUPPORT_XY_COLOR
            self._features |= SUPPORT_RGB_COLOR
            self._xy_color = xy_color

        if ct_color is not None:
            self._features |= SUPPORT_COLOR_TEMP
            self._features |= SUPPORT_XY_COLOR
            self._ct_color = ct_color

        self._id = id
        self._sensor_id = sensor_id
        self._name = name
        self._state = state
        self._device_class = device_class
        self._reachable = reachable
        self._dimmer = dimmer
        self._api = api

        dcz_registry.register_sensor_device(sensor_id, self)

    @asyncio.coroutine
    def async_update_from_dcz(self, state, bri, ct, x, y):
        """Update the state of the device."""

        if x:
            color_util.color_xy_brightness_to_RGB(self._xy_color[0], 1, 0)
            self._xy_color = self._xy_color[0],x
        elif y:
            self._xy_color = x,self._xy_color[1]
        if bri:
            self.brightness = bri
        elif ct:
            self.color_temp = ct
        elif state is not None:
            self._state = state

        self.hass.async_add_job(self.async_update_ha_state())

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._features

    @property
    def xy_color(self):
        """Return the XY color value."""
        if self.supported_features == (SUPPORT_BRIGHTNESS|SUPPORT_XY_COLOR|SUPPORT_RGB_COLOR):
            return self._xy_color


    @xy_color.setter
    def xy_color(self, value):
        self._xy_color = value

    @property
    def color_temp(self):
        if self.supported_features == (SUPPORT_COLOR_TEMP|SUPPORT_BRIGHTNESS|SUPPORT_XY_COLOR):
            return self._ct_color

    @color_temp.setter
    def color_temp(self, value):
        self._ct_color = value

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self._dimmer

    @brightness.setter
    def brightness(self, value):
        self._dimmer = value

    @property
    def isGroup(self):
        """Return the isGroup of the light."""
        return self._isGroup

    @isGroup.setter
    def isGroup(self, value):
        self._isGroup = value

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state

    @property
    def id(self):
        """Return the ID"""
        return self._id

    @property
    def device_class(self):
        """The device class."""
        return self._device_class

    @asyncio.coroutine
    def async_turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        self._state = False
        self.hass.async_add_job(self.async_update_ha_state())
        if self.isGroup:
            yield from self._api.set_lights('groups',False,self)
        else:
            yield from self._api.set_lights('lights',False,self)

    @asyncio.coroutine
    def async_turn_on(self, **kwargs):
        if ATTR_BRIGHTNESS in kwargs:
           self._dimmer = kwargs[ATTR_BRIGHTNESS]

        if ATTR_COLOR_TEMP in kwargs:
            self._ct_color = kwargs[ATTR_COLOR_TEMP]

        if ATTR_RGB_COLOR in kwargs:
            xyb = color_util.color_RGB_to_xy(
                    *(int(val) for val in kwargs[ATTR_RGB_COLOR]))
            self.xy_color = xyb[0], xyb[1]
            self.brightness = xyb[2]

        if ATTR_XY_COLOR in kwargs:
            self.xy_color = kwargs[ATTR_XY_COLOR]

        self._state = True
        self.hass.async_add_job(self.async_update_ha_state())
        if self.isGroup:
            yield from self._api.set_lights('groups',True,self)
        else:
            yield from self._api.set_lights('lights',True,self)
