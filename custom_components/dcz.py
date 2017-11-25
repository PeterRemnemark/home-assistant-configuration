import logging
import asyncio
import json
from urllib.parse import urljoin

import aiohttp
import async_timeout
import voluptuous as vol

import homeassistant.core as ha
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.const import (CONF_HOST, CONF_API_KEY)
from homeassistant.components.light import (SUPPORT_COLOR_TEMP,SUPPORT_BRIGHTNESS,SUPPORT_RGB_COLOR,SUPPORT_XY_COLOR)

DOMAIN = 'dcz'
REQUIREMENTS = ['websockets==3.2']

_LOGGER = logging.getLogger(__name__)

ATTR_DISCOVER_DEVICES = 'devices'

CONF_WS_URL = 'ws_url'

DATA_REGISTRY = 'dcz_registry'
DATA_API = 'dcz_api'

from enum import Enum
class EventType(Enum):
    STATE = 1
    BATTERY_LEVEL = 2

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_WS_URL): cv.string,
        vol.Required(CONF_API_KEY): cv.string,
    }),
}, extra=vol.ALLOW_EXTRA)

@asyncio.coroutine
def async_setup(hass, config):
    """Setup the DCZ platform."""
    hass.data[DATA_REGISTRY] = DczRegistry()
    api = DczWebGateway(hass,
                        config[DOMAIN].get(CONF_WS_URL),
                        config[DOMAIN].get(CONF_HOST),
                        config[DOMAIN].get(CONF_API_KEY),
                        )

    hass.data[DATA_API] = api

    # add sensor devices
    sensors = yield from api.get_sensors('sensors')
    lights = yield from api.get_sensors('lights')
    groups = yield from api.get_sensors('groups')
    if sensors:
        hass.async_add_job(discovery.async_load_platform(
            hass, 'sensor', DOMAIN,
            sensors, config))
        hass.async_add_job(discovery.async_load_platform(
            hass, 'binary_sensor', DOMAIN,
            sensors, config))
        hass.async_add_job(discovery.async_load_platform(
            hass, 'light', DOMAIN,
            lights, config))
        hass.async_add_job(discovery.async_load_platform(
            hass, 'light', DOMAIN,
            groups, config))

	 # start listening for incoming events over websocket
    api.start_listener(_async_process_message, hass)

    return True

@asyncio.coroutine
def _async_process_message(message, hass):
    _LOGGER.error(message)

    dcz_registry = hass.data[DATA_REGISTRY]

    if message['r']=='sensors':
        #we assume battery event
        if 'config' in message:
            additional = 'battSensor'
        else:
            additional = 'sensor'
    elif message['r']=='lights':
        additional = 'lights'
    elif message ['r']=='groups':
        additional = 'group'
    else:
        additional = ''

    device = dcz_registry.get_sensor_device(message['id']+additional)
    if device:
        if device.device_class=="temperature":
            if 'config' in message:
                _LOGGER.error("We got an battery update")
                yield from device.async_update_from_dcz(message['config']['battery'],EventType.BATTERY_LEVEL)
            else:
                yield from device.async_update_from_dcz(message['state']['temperature']/float(100))
        elif device.device_class=="lux":
            if 'lightlevel' in message['state']:
                yield from device.async_update_from_dcz(round(10 ** (float(message['state']['lightlevel'] - 1) / 10000),1))
            elif 'config' in message:
                _LOGGER.error("We got an battery update")
                yield from device.async_update_from_dcz(message['config']['battery'],EventType.BATTERY_LEVEL)
        elif device.device_class=="motion":
            if 'config' in message:
                yield from device.async_update_from_dcz(message['config']['battery'],EventType.BATTERY_LEVEL)
            else:
                yield from device.async_update_from_dcz(message['state']['presence'])
                hass.bus.async_fire('dcz_event_motion', {'id': device.name,'presence': message['state']['presence']}, ha.EventOrigin.remote)
        elif device.device_class=="opening":
            if 'config' in message:
                yield from device.async_update_from_dcz(message['config']['battery'],EventType.BATTERY_LEVEL)
            else:
                yield from device.async_update_from_dcz(message['state']['open'])
                hass.bus.async_fire('dcz_event_open', {'id': device.name,'open': message['state']['open']}, ha.EventOrigin.remote)
        elif device.device_class=="switch":
            if 'config' in message:
                _LOGGER.error("We got an battery update")
                yield from device.async_update_from_dcz(message['config']['battery'],EventType.BATTERY_LEVEL)
            else:
                hass.bus.async_fire('dcz_event', {'id': device.name,'button' : message['state']['buttonevent']}, ha.EventOrigin.remote)
        elif device.device_class=="battSensor":
            _LOGGER.error("We got an battery update")
            yield from device.async_update_from_dcz(message['config']['battery'],EventType.BATTERY_LEVEL)
        elif device.device_class=="ikea_light" or device.device_class=="lightgroup" or device.device_class=="osram_light":
            if 'on' in message['state'] and device.device_class=="ikea_light":
                yield from device.async_update_from_dcz(message['state']['on'], None, None, None, None)
            elif 'any_on' in message['state'] and device.device_class=="lightgroup":
                yield from device.async_update_from_dcz(message['state']['any_on'], None, None, None, None)
            elif 'bri' in message['state']:
                yield from device.async_update_from_dcz(None,message['state']['bri'],None, None, None)
            elif 'ct' in message['state']:
                yield from device.async_update_from_dcz(None,None,message['state']['ct'],None,None)
            #elif 'x' in message['state']:
            #    yield from device.async_update_from_dcz(None,None,None,message['state']['x'],None)
            #elif 'y' in message['state']:
            #    yield from device.async_update_from_dcz(None,None,None,None,message['state']['y'])

    # todo, parse message and make event on the hass.bus
    #hass.bus.async_fire('dcz_event', {'id': 1,'button' : 1002}, ha.EventOrigin.remote)

class DczRegistry:
    """Maintains mappings between DeConz and HA entities."""

    def __init__(self):
        """Initialize the registry."""
        self._sensor_id_to_sensor_map = {}

    def register_sensor_device(self, sensor_id, device):
        """Add a sensor device to the registry."""
        self._sensor_id_to_sensor_map[sensor_id] = device

    def get_sensor_device(self, sensor_id):
        """Retrieve a sensor device for a specific id."""
        return self._sensor_id_to_sensor_map.get(sensor_id, None)

@asyncio.coroutine
def _ws_process_message(message, async_callback, *args):
    if message.get('status', '') != 'success':
        _LOGGER.warning("Unsuccessful websocket message "
                        "delivered, ignoring: %s", message)
    try:
        yield from async_callback(message, *args)
    except:    # pylint: disable=bare-except
        _LOGGER.exception("Exception in callback, ignoring.")

class DczWebGateway:
    """Simple binding for the Lundix SPC Web Gateway REST API."""
    def __init__(self, hass, ws_host, host, api_key):
        """Initialize the web gateway client."""
        self._hass = hass
        self._ws_host = ws_host
        self._host = host
        self._api_key = api_key
        self._ws = None

    @asyncio.coroutine
    def get_sensors(self, resource):
        """Retrieve all available sensors."""
        return (yield from self._get_data(resource))

    @asyncio.coroutine
    def set_lights(self, resource, state, light):
        """Retrieve all available sensors."""
        return (yield from self._set_state(resource, state, light))

    def start_listener(self, async_callback, *args):
        """Start the websocket listener."""
        try:
            from asyncio import ensure_future
        except ImportError:
            from asyncio import async as ensure_future

        ensure_future(self._ws_listen(async_callback, *args))

    @asyncio.coroutine
    def _get_data(self, resource):
        data = yield from self._call_web_gateway(resource)
        if not data:
            return False

        return data

    @asyncio.coroutine
    def _set_state(self, resource, state, light):
        actionString = None
        if light.isGroup:
            actionString = 'action'
        else:
            actionString = 'state'
        url = 'http://{a}/api/{b}/{c}/{d}/{e}'.format(a=self._host, b=self._api_key, c=resource, d=light.id, e=actionString)

        dt = {}
        dt['on'] = state
        dt['transitiontime'] = 0

        if state==True: #turn on lights
            dt['bri'] = light.brightness
            if light.supported_features == (SUPPORT_COLOR_TEMP|SUPPORT_BRIGHTNESS|SUPPORT_XY_COLOR):
                dt['ct'] = light.color_temp
            elif light.supported_features == (SUPPORT_XY_COLOR|SUPPORT_BRIGHTNESS|SUPPORT_RGB_COLOR):
                dt['xy'] = light.xy_color

        jsonData = json.dumps(dt)
        try:
           session = aiohttp.ClientSession()
           with async_timeout.timeout(10, loop=self._hass.loop):
               action = session.put
               response = yield from action(url,data=jsonData)
           if response.status != 200:
               _LOGGER.error("DeConz Gateway returned http "
                             "status %d, response %s.",
                             response.status, (yield from response.text()))
               return False
           result = yield from response.json()
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout getting DeConz data from %s.", url)
            return False
        except aiohttp.ClientError:
            _LOGGER.exception("Error getting DeConz data from %s.", url)
            return False
        finally:
            if session:
                yield from session.close()
            if response:
                yield from response.release()
        return result

    @asyncio.coroutine
    def _call_web_gateway(self, resource, use_get=True):
        response = None
        session = None
        url = 'http://{a}/api/{b}/{c}'.format(a=self._host, b=self._api_key, c=resource)
        try:
            _LOGGER.debug("Attempting to retrieve DeConz data from %s.", url)
            session = aiohttp.ClientSession()
            with async_timeout.timeout(10, loop=self._hass.loop):
                action = session.get if use_get else session.put
                response = yield from action(url)
            if response.status != 200:
                _LOGGER.error("DeConz Gateway returned http "
                              "status %d, response %s.",
                              response.status, (yield from response.text()))
                return False
            result = yield from response.json()
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout getting DeConz data from %s.", url)
            return False
        except aiohttp.ClientError:
            _LOGGER.exception("Error getting DeConz data from %s.", url)
            return False
        finally:
            if session:
                yield from session.close()
            if response:
                yield from response.release()
        _LOGGER.debug("Data from Deconz: %s", result)
        return result

    @asyncio.coroutine
    def _ws_read(self):
        import websockets as wslib

        try:
            if not self._ws:
                self._ws = yield from wslib.connect(self._ws_host)
                _LOGGER.info("Connected to websocket at %s.", self._ws_host)
        except Exception as ws_exc:    # pylint: disable=broad-except
            _LOGGER.error("Failed to connect to websocket: %s", ws_exc)
            _LOGGER.error("Failed to connect to websocket: %s", self._ws_host)
            return

        result = None

        try:
            result = yield from self._ws.recv()
            _LOGGER.debug("Data from websocket: %s", result)
        except Exception as ws_exc:    # pylint: disable=broad-except
            _LOGGER.error("Failed to read from websocket: %s", ws_exc)
            try:
                yield from self._ws.close()
            finally:
                self._ws = None

        return result

    @asyncio.coroutine
    def _ws_listen(self, async_callback, *args):
        try:
            while True:
                result = yield from self._ws_read()

                if result:
                    yield from _ws_process_message(json.loads(result),
                                                   async_callback, *args)
                else:
                    _LOGGER.info("Trying again in 30 seconds.")
                    yield from asyncio.sleep(30)

        finally:
            if self._ws:
                yield from self._ws.close()
