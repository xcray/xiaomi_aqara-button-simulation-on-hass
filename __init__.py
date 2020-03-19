"""Support for Xiaomi Gateways."""
from datetime import timedelta
import logging

import voluptuous as vol
from xiaomi_gateway import XiaomiGatewayDiscovery

from homeassistant.components.discovery import SERVICE_XIAOMI_GW
from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    ATTR_VOLTAGE,
    CONF_HOST,
    CONF_MAC,
    CONF_PORT,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import callback
from homeassistant.helpers import discovery
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util.dt import utcnow

_LOGGER = logging.getLogger(__name__)

ATTR_GW_MAC = "gw_mac"
ATTR_RINGTONE_ID = "ringtone_id"
ATTR_RINGTONE_VOL = "ringtone_vol"
ATTR_DEVICE_ID = "device_id"

CONF_DISCOVERY_RETRY = "discovery_retry"
CONF_GATEWAYS = "gateways"
CONF_INTERFACE = "interface"
CONF_KEY = "key"
CONF_DISABLE = "disable"

DOMAIN = "xiaomi_aqara"

PY_XIAOMI_GATEWAY = "xiaomi_gw"

TIME_TILL_UNAVAILABLE = timedelta(minutes=150)

SERVICE_PLAY_RINGTONE = "play_ringtone"
SERVICE_STOP_RINGTONE = "stop_ringtone"
SERVICE_ADD_DEVICE = "add_device"
SERVICE_REMOVE_DEVICE = "remove_device"
SERVICE_SIMULATE_BUTTON = 'simulate_button'

GW_MAC = vol.All(
    cv.string, lambda value: value.replace(":", "").lower(), vol.Length(min=12, max=12)
)

SERVICE_SCHEMA_PLAY_RINGTONE = vol.Schema(
    {
        vol.Required(ATTR_RINGTONE_ID): vol.All(
            vol.Coerce(int), vol.NotIn([9, 14, 15, 16, 17, 18, 19])
        ),
        vol.Optional(ATTR_RINGTONE_VOL): vol.All(
            vol.Coerce(int), vol.Clamp(min=0, max=100)
        ),
    }
)

SERVICE_SCHEMA_REMOVE_DEVICE = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): vol.All(cv.string, vol.Length(min=14, max=14))}
)

SERVICE_SCHEMA_SIMULATE_BUTTON = vol.Schema({
   vol.Required(ATTR_DEVICE_ID):
      vol.All(cv.string, vol.Length(min=14, max=14)),
   vol.Required('status'):
      vol.All(cv.string, vol.Length(min=5, max=14)) #click/double_click
})

GATEWAY_CONFIG = vol.Schema(
    {
        vol.Optional(CONF_KEY): vol.All(cv.string, vol.Length(min=16, max=16)),
        vol.Optional(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=9898): cv.port,
        vol.Optional(CONF_DISABLE, default=False): cv.boolean,
    }
)

GATEWAY_CONFIG_MAC_OPTIONAL = GATEWAY_CONFIG.extend({vol.Optional(CONF_MAC): GW_MAC})

GATEWAY_CONFIG_MAC_REQUIRED = GATEWAY_CONFIG.extend({vol.Required(CONF_MAC): GW_MAC})


def _fix_conf_defaults(config):
    """Update some configuration defaults."""
    config["sid"] = config.pop(CONF_MAC, None)

    if config.get(CONF_KEY) is None:
        _LOGGER.warning(
            "Key is not provided for gateway %s. Controlling the gateway "
            "will not be possible",
            config["sid"],
        )

    if config.get(CONF_HOST) is None:
        config.pop(CONF_PORT)

    return config


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_GATEWAYS, default={}): vol.All(
                    cv.ensure_list,
                    vol.Any(
                        vol.All([GATEWAY_CONFIG_MAC_OPTIONAL], vol.Length(max=1)),
                        vol.All([GATEWAY_CONFIG_MAC_REQUIRED], vol.Length(min=2)),
                    ),
                    [_fix_conf_defaults],
                ),
                vol.Optional(CONF_INTERFACE, default="any"): cv.string,
                vol.Optional(CONF_DISCOVERY_RETRY, default=3): cv.positive_int,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def setup(hass, config):
    """Set up the Xiaomi component."""
    gateways = []
    interface = "any"
    discovery_retry = 3
    if DOMAIN in config:
        gateways = config[DOMAIN][CONF_GATEWAYS]
        interface = config[DOMAIN][CONF_INTERFACE]
        discovery_retry = config[DOMAIN][CONF_DISCOVERY_RETRY]

    async def xiaomi_gw_discovered(service, discovery_info):
        """Perform action when Xiaomi Gateway device(s) has been found."""
        # We don't need to do anything here, the purpose of Home Assistant's
        # discovery service is to just trigger loading of this
        # component, and then its own discovery process kicks in.

    discovery.listen(hass, SERVICE_XIAOMI_GW, xiaomi_gw_discovered)

    xiaomi = hass.data[PY_XIAOMI_GATEWAY] = XiaomiGatewayDiscovery(
        hass.add_job, gateways, interface
    )

    _LOGGER.debug("Expecting %s gateways", len(gateways))
    for k in range(discovery_retry):
        _LOGGER.info("Discovering Xiaomi Gateways (Try %s)", k + 1)
        xiaomi.discover_gateways()
        if len(xiaomi.gateways) >= len(gateways):
            break

    if not xiaomi.gateways:
        _LOGGER.error("No gateway discovered")
        return False
    xiaomi.listen()
    _LOGGER.debug("Gateways discovered. Listening for broadcasts")

    for component in ["binary_sensor", "sensor", "switch", "cover", "lock"]:
        discovery.load_platform(hass, component, DOMAIN, {}, config) #"light" deleted by XCray

    def stop_xiaomi(event):
        """Stop Xiaomi Socket."""
        _LOGGER.info("Shutting down Xiaomi Hub")
        xiaomi.stop_listen()

    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, stop_xiaomi)

    def play_ringtone_service(call):
        """Service to play ringtone through Gateway."""
        ring_id = call.data.get(ATTR_RINGTONE_ID)
        gateway = call.data.get(ATTR_GW_MAC)

        kwargs = {"mid": ring_id}

        ring_vol = call.data.get(ATTR_RINGTONE_VOL)
        if ring_vol is not None:
            kwargs["vol"] = ring_vol

        gateway.write_to_hub(gateway.sid, **kwargs)

    def stop_ringtone_service(call):
        """Service to stop playing ringtone on Gateway."""
        gateway = call.data.get(ATTR_GW_MAC)
        gateway.write_to_hub(gateway.sid, mid=10000)

    def add_device_service(call):
        """Service to add a new sub-device within the next 30 seconds."""
        gateway = call.data.get(ATTR_GW_MAC)
        gateway.write_to_hub(gateway.sid, join_permission="yes")
        hass.components.persistent_notification.async_create(
            "Join permission enabled for 30 seconds! "
            "Please press the pairing button of the new device once.",
            title="Xiaomi Aqara Gateway",
        )

    def remove_device_service(call):
        """Service to remove a sub-device from the gateway."""
        device_id = call.data.get(ATTR_DEVICE_ID)
        gateway = call.data.get(ATTR_GW_MAC)
        gateway.write_to_hub(gateway.sid, remove_device=device_id)
    def simulate_button_service(call):
        '''Service to simulate click/double_click of the wireless button'''
        device_id = call.data.get(ATTR_DEVICE_ID)
        gateway = call.data.get(ATTR_GW_MAC)
        simu_status = call.data.get('status')
        gateway.write_to_hub(device_id, status=simu_status)

    gateway_only_schema = _add_gateway_to_schema(xiaomi, vol.Schema({}))

    hass.services.register(
        DOMAIN,
        SERVICE_PLAY_RINGTONE,
        play_ringtone_service,
        schema=_add_gateway_to_schema(xiaomi, SERVICE_SCHEMA_PLAY_RINGTONE),
    )

    hass.services.register(
        DOMAIN, SERVICE_STOP_RINGTONE, stop_ringtone_service, schema=gateway_only_schema
    )

    hass.services.register(
        DOMAIN, SERVICE_ADD_DEVICE, add_device_service, schema=gateway_only_schema
    )

    hass.services.register(
        DOMAIN,
        SERVICE_REMOVE_DEVICE,
        remove_device_service,
        schema=_add_gateway_to_schema(xiaomi, SERVICE_SCHEMA_REMOVE_DEVICE),
    )

    hass.services.register(
        DOMAIN, SERVICE_SIMULATE_BUTTON, simulate_button_service,
        schema=_add_gateway_to_schema(xiaomi, SERVICE_SCHEMA_SIMULATE_BUTTON))

    return True

class XiaomiDevice(Entity):
    """Representation a base Xiaomi device."""

    def __init__(self, device, device_type, xiaomi_hub):
        """Initialize the Xiaomi device."""
        self._state = None
        self._is_available = True
        self._sid = device["sid"]
        self._name = f"{device_type}_{self._sid}"
        self._type = device_type
        self._write_to_hub = xiaomi_hub.write_to_hub
        self._get_from_hub = xiaomi_hub.get_from_hub
        self._device_state_attributes = {}
        self._remove_unavailability_tracker = None
        self._xiaomi_hub = xiaomi_hub
        self.parse_data(device["data"], device["raw_data"])
        self.parse_voltage(device["data"])

        if hasattr(self, "_data_key") and self._data_key:  # pylint: disable=no-member
            self._unique_id = "{}{}".format(
                self._data_key, self._sid  # pylint: disable=no-member
            )
        else:
            self._unique_id = f"{self._type}{self._sid}"

    def _add_push_data_job(self, *args):
        self.hass.add_job(self.push_data, *args)

    async def async_added_to_hass(self):
        """Start unavailability tracking."""
        self._xiaomi_hub.callbacks[self._sid].append(self._add_push_data_job)
        self._async_track_unavailable()

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._unique_id

    @property
    def available(self):
        """Return True if entity is available."""
        return self._is_available

    @property
    def should_poll(self):
        """Return the polling state. No polling needed."""
        return False

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._device_state_attributes

    @callback
    def _async_set_unavailable(self, now):
        """Set state to UNAVAILABLE."""
        self._remove_unavailability_tracker = None
        self._is_available = False
        self.async_schedule_update_ha_state()

    @callback
    def _async_track_unavailable(self):
        if self._remove_unavailability_tracker:
            self._remove_unavailability_tracker()
        self._remove_unavailability_tracker = async_track_point_in_utc_time(
            self.hass, self._async_set_unavailable, utcnow() + TIME_TILL_UNAVAILABLE
        )
        if not self._is_available:
            self._is_available = True
            return True
        return False

    @callback
    def push_data(self, data, raw_data):
        """Push from Hub."""
        _LOGGER.debug("PUSH >> %s: %s", self, data)
        was_unavailable = self._async_track_unavailable()
        is_data = self.parse_data(data, raw_data)
        is_voltage = self.parse_voltage(data)
        if is_data or is_voltage or was_unavailable:
            self.async_schedule_update_ha_state()

    def parse_voltage(self, data):
        """Parse battery level data sent by gateway."""
        if "voltage" in data:
            voltage_key = "voltage"
        elif "battery_voltage" in data:
            voltage_key = "battery_voltage"
        else:
            return False

        max_volt = 3300
        min_volt = 2800
        voltage = data[voltage_key]
        self._device_state_attributes[ATTR_VOLTAGE] = round(voltage / 1000.0, 2)
        voltage = min(voltage, max_volt)
        voltage = max(voltage, min_volt)
        percent = ((voltage - min_volt) / (max_volt - min_volt)) * 100
        self._device_state_attributes[ATTR_BATTERY_LEVEL] = round(percent, 1)
        return True

    def parse_data(self, data, raw_data):
        """Parse data sent by gateway."""
        raise NotImplementedError()


def _add_gateway_to_schema(xiaomi, schema):
    """Extend a voluptuous schema with a gateway validator."""

    def gateway(sid):
        """Convert sid to a gateway."""
        sid = str(sid).replace(":", "").lower()

        for gateway in xiaomi.gateways.values():
            if gateway.sid == sid:
                return gateway

        raise vol.Invalid(f"Unknown gateway sid {sid}")

    gateways = list(xiaomi.gateways.values())
    kwargs = {}

    # If the user has only 1 gateway, make it the default for services.
    if len(gateways) == 1:
        kwargs["default"] = gateways[0].sid

    return schema.extend({vol.Required(ATTR_GW_MAC, **kwargs): gateway})
