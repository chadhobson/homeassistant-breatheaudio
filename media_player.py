"""Support for interfacing with BreatheAudio 6-Zone amplifier."""
import logging
import math

from serial import SerialException
from datetime import timedelta

from homeassistant import core
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.components.media_player.const import (
    SUPPORT_SELECT_SOURCE,
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
)
from homeassistant.const import CONF_PORT, STATE_OFF, STATE_ON
from homeassistant.helpers import config_validation as cv, entity_platform, service

from .const import CONF_SOURCES, DOMAIN, SERVICE_RESTORE, SERVICE_SNAPSHOT

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1
SCAN_INTERVAL = timedelta(seconds=10)

SUPPORT_BREATHEAUDIO = (
    SUPPORT_VOLUME_MUTE
    | SUPPORT_VOLUME_SET
    | SUPPORT_VOLUME_STEP
    | SUPPORT_TURN_ON
    | SUPPORT_TURN_OFF
    | SUPPORT_SELECT_SOURCE
)


@core.callback
def _get_sources_from_dict(data):
    sources_config = data[CONF_SOURCES]

    source_id_name = {int(index): name for index, name in sources_config.items()}

    source_name_id = {v: k for k, v in source_id_name.items()}

    source_names = sorted(source_name_id.keys(), key=lambda v: source_name_id[v])

    return [source_id_name, source_name_id, source_names]


@core.callback
def _get_sources(config_entry):
    if CONF_SOURCES in config_entry.options:
        data = config_entry.options
    else:
        data = config_entry.data
    return _get_sources_from_dict(data)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the BreatheAudio 6-zone amplifier platform."""
    port = config_entry.data[CONF_PORT]

    breatheaudio = hass.data[DOMAIN][config_entry.entry_id]

    sources = _get_sources(config_entry)

    entities = []
    for i in range(1, 7):
        zone_id = i
        _LOGGER.debug("Adding zone %d for port %s", zone_id, port)
        entities.append(
            BreatheAudioZone(breatheaudio, sources, config_entry.entry_id, zone_id)
        )

    async_add_entities(entities, False)

    platform = entity_platform.current_platform.get()

    def _call_service(entities, service_call):
        for entity in entities:
            if service_call.service == SERVICE_SNAPSHOT:
                entity.snapshot()
            elif service_call.service == SERVICE_RESTORE:
                entity.restore()

    @service.verify_domain_control(hass, DOMAIN)
    async def async_service_handle(service_call):
        """Handle for services."""
        entities = await platform.async_extract_from_service(service_call)

        if not entities:
            return

        hass.async_add_executor_job(_call_service, entities, service_call)

    # hass.services.async_register(
    #     DOMAIN,
    #     SERVICE_SNAPSHOT,
    #     async_service_handle,
    #     schema=cv.make_entity_service_schema({}),
    # )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESTORE,
        async_service_handle,
        schema=cv.make_entity_service_schema({}),
    )


class BreatheAudioZone(MediaPlayerEntity):
    """Representation of a BreatheAudio amplifier zone."""

    def __init__(self, breatheaudio, sources, namespace, zone_id):
        """Initialize new zone."""
        self._breatheaudio = breatheaudio
        # dict source_id -> source name
        self._source_id_name = sources[0]
        # dict source name -> source_id
        self._source_name_id = sources[1]
        # ordered list of all source names
        self._source_names = sources[2]
        self._zone_id = zone_id
        self._unique_id = f"{namespace}_{self._zone_id}"
        self._name = f"Zone {self._zone_id}"

        self._snapshot = None
        self._state = None
        self._volume = None
        self._source = None
        self._mute = None

    def update(self):
        """Retrieve latest state."""
        try:
            state = self._breatheaudio.zone_status(self._zone_id)
        except SerialException:
            _LOGGER.debug('Could not update zone %d', self._zone_id)
            _LOGGER.error(SerialException)
            return

        self._state = STATE_ON if state.power else STATE_OFF
        self._volume = state.volume / 100
        self._mute = state.mute
        idx = state.source
        if idx in self._source_id_name:
            self._source = self._source_id_name[idx]
        else:
            self._source = None

    @property
    def device_info(self):
        """Return device info for this device."""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": "BreatheAudio",
            "model": "6-Zone Amplifier",
        }

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the zone."""
        return self._name

    @property
    def state(self):
        """Return the state of the zone."""
        return self._state

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        if self._volume is None:
            return None
        return self._volume

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._mute

    @property
    def supported_features(self):
        """Return flag of media commands that are supported."""
        return SUPPORT_BREATHEAUDIO

    @property
    def media_title(self):
        """Return the current source as media title."""
        return self._source

    @property
    def source(self):
        """Return the current input source of the device."""
        return self._source

    @property
    def source_list(self):
        """List of available input sources."""
        return self._source_names

    def snapshot(self):
        """Save zone's current state."""
        self._snapshot = self._breatheaudio.zone_status(self._zone_id)

    def restore(self):
        """Restore saved state."""
        if self._snapshot:
            self._breatheaudio.restore_zone(self._snapshot)
            self.schedule_update_ha_state(True)

    def select_source(self, source):
        """Set input source."""
        if source not in self._source_name_id:
            return
        idx = self._source_name_id[source]
        self._breatheaudio.set_source(self._zone_id, idx)

    def turn_on(self):
        """Turn the media player on."""
        self._breatheaudio.set_power(self._zone_id, True)

    def turn_off(self):
        """Turn the media player off."""
        self._breatheaudio.set_power(self._zone_id, False)

    def mute_volume(self, mute):
        """Mute (true) or unmute (false) media player."""
        self._breatheaudio.set_mute(self._zone_id, mute)

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        volume = int(volume * 100)
        _LOGGER.debug('VOL SET: Current volume: %d, New volume: %d', self._volume * 100, volume)
        self._breatheaudio.set_volume(self._zone_id, volume)
    def volume_up(self):
        """Volume up the media player. 0..100"""
        if self._volume is None:
            return
        else:
            volume = (self._volume * 100) + 10
            self._breatheaudio.set_volume(self._zone_id, min(volume, 100))
    def volume_down(self):
        """Volume down media player. 0..100"""
        if self._volume is None:
            return
        else:
            volume = (self._volume * 100) - 10
            self._breatheaudio.set_volume(self._zone_id, max(volume, 0))
