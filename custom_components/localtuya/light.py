"""
Simple platform to control LOCALLY Tuya light devices.

Sample config yaml

light:
  - platform: localtuya
    host: 192.168.0.1
    local_key: 1234567891234567
    device_id: 12345678912345671234
    name: tuya_01
    protocol_version: 3.3
"""
import voluptuous as vol
from homeassistant.const import (CONF_HOST, CONF_ID, CONF_SWITCHES, CONF_FRIENDLY_NAME, CONF_ICON, CONF_NAME)
import homeassistant.helpers.config_validation as cv
from time import time, sleep
from threading import Lock
import logging
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    ENTITY_ID_FORMAT,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_COLOR_TEMP,
    Light,
    PLATFORM_SCHEMA
)
from homeassistant.util import color as colorutil

REQUIREMENTS = ['pytuya==7.0.4']

CONF_DEVICE_ID = 'device_id'
CONF_LOCAL_KEY = 'local_key'
CONF_PROTOCOL_VERSION = 'protocol_version'
# IMPORTANT, id is used as key for state and turning on and off, 1 was fine switched apparently but my bulbs need 20, other feature attributes count up from this, e.g. 21 mode, 22 brightnes etc, see my pytuya modification.
DEFAULT_ID = '20'
DEFAULT_PROTOCOL_VERSION = 3.3

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_ICON): cv.icon,
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_DEVICE_ID): cv.string,
    vol.Required(CONF_LOCAL_KEY): cv.string,
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_PROTOCOL_VERSION, default=DEFAULT_PROTOCOL_VERSION): vol.Coerce(float),
    vol.Optional(CONF_ID, default=DEFAULT_ID): cv.string,
})
log = logging.getLogger(__name__)
log.setLevel(level=logging.DEBUG)  # Debug hack!


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up of the Tuya switch."""
    from . import pytuya

    lights = []
    pytuyadevice = pytuya.BulbDevice(config.get(CONF_DEVICE_ID), config.get(CONF_HOST), config.get(CONF_LOCAL_KEY))
    pytuyadevice.set_version(float(config.get(CONF_PROTOCOL_VERSION)))

    bulb_device = TuyaCache(pytuyadevice)
    lights.append(
            TuyaDevice(
                bulb_device,
                config.get(CONF_NAME),
                config.get(CONF_ICON),
                config.get(CONF_ID)
            )
    )

    add_devices(lights)

class TuyaCache:
    """Cache wrapper for pytuya.BulbDevice"""

    def __init__(self, device):
        """Initialize the cache."""
        self._cached_status = ''
        self._cached_status_time = 0
        self._device = device
        self._lock = Lock()

    def __get_status(self, switchid):
        for i in range(20):
            try:
                status = self._device.status()['dps'][switchid]
                return status
            except ConnectionError:
                if i+1 == 5:
                    raise ConnectionError("Failed to update status.")

    def set_status(self, state, switchid):
        """Change the Tuya switch status and clear the cache."""
        self._cached_status = ''
        self._cached_status_time = 0
        for i in range(20):
            try:
                return self._device.set_status(state, switchid)
            except ConnectionError:
                if i+1 == 5:
                    raise ConnectionError("Failed to set status.")

    def status(self, switchid):
        """Get state of Tuya switch and cache the results."""
        self._lock.acquire()
        try:
            now = time()
            if not self._cached_status or now - self._cached_status_time > 30:
                sleep(0.5)
                self._cached_status = self.__get_status(switchid)
                self._cached_status_time = time()
            return self._cached_status
        finally:
            self._lock.release()

    def cached_status(self):
        return self._cached_status

    def support_color(self):
        return self._device.support_color()

    def support_color_temp(self):
        return self._device.support_color_temp()

    def brightness(self):
        return self._device.brightness()

    def color_temp(self):
        return self._device.colourtemp()

    def set_brightness(self, brightness):
        self._device.set_brightness(brightness)

    def set_color_temp(self, color_temp):
        self._device.set_colourtemp(color_temp)
    def state(self):
        self._device.state();

    def turn_on(self):
        self._device.turn_on();

    def turn_off(self):
        self._device.turn_off();

class TuyaDevice(Light):
    """Representation of a Tuya switch."""

    def __init__(self, device, name, icon, bulbid):
        """Initialize the Tuya switch."""
        self._device = device
        self._name = name
        self._state = False
        self._icon = icon
        self._bulb_id = bulbid

    @property
    def name(self):
        """Get name of Tuya switch."""
        return self._name

    @property
    def is_on(self):
        """Check if Tuya switch is on."""
        return self._state

    @property
    def icon(self):
        """Return the icon."""
        return self._icon

    def update(self):
        """Get state of Tuya switch."""
        status = self._device.status(self._bulb_id)
        self._state = status

    @property
    def brightness(self):
        """Return the brightness of the light."""
        """Pytuya uses 25 - 255 for color temp, use same convention elsewhere 153 to 500"""
        if self._device.brightness() is None:
            return None
        brightness = (self._device.brightness()/1000) * 255
        if brightness > 254:
           brightness = 255
        if brightness < 1:
           brightness = 1

        return int(brightness)

#    @property
#    def hs_color(self):
#        """Return the hs_color of the light."""
#        return (self._device.color_hsv()[0],self._device.color_hsv()[1])

    @property
    def color_temp(self):
        """Return the color_temp of the light."""
        """Pytuya uses 0 - 1000 for color temp, use same convention elsewhere 153 to 500"""
        color_temp = self._device.color_temp()
        if color_temp is None:
            return None
        return int(500 - ( ( (500-153)/1000) * color_temp))

    @property
    def min_mireds(self):
        """Return color temperature min mireds."""
        return 153

    @property
    def max_mireds(self):
        """Return color temperature max mireds."""
        return 500

    def turn_on(self, **kwargs):
        """Turn on or control the light."""
        log.debug("Turning on, state: " + str(self._device.cached_status()))
        if  not self._device.cached_status():
            self._device.set_status(True, self._bulb_id)
        if ATTR_BRIGHTNESS in kwargs:
            converted_brightness = int( (1000 / 255) * (int(kwargs[ATTR_BRIGHTNESS]) ))
            if converted_brightness <= 10:
                converted_brightness = 10
            self._device.set_brightness(converted_brightness)
        if ATTR_HS_COLOR in kwargs:
            raise ValueError(" TODO implement RGB from HS")
        if ATTR_COLOR_TEMP in kwargs:
            color_temp = 1000 - (1000 / (500 - 153)) * (int(kwargs[ATTR_COLOR_TEMP]) - 153)
            self._device.set_color_temp(int(color_temp))

    def turn_off(self, **kwargs):
        """Turn Tuya switch off."""
        self._device.set_status(False, self._bulb_id)

    @property
    def supported_features(self):
        """Flag supported features."""
        supports = SUPPORT_BRIGHTNESS
        #if self._device.support_color():
        #    supports = supports | SUPPORT_COLOR
        #if self._device.support_color_temp():
        #    supports = supports | SUPPORT_COLOR_TEMP
        supports = supports | SUPPORT_COLOR_TEMP
        return supports
