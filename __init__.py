"""The BreatheAudio 6-Zone Amplifier integration."""
import asyncio
import logging

from .pybreatheaudio import get_breatheaudio
from serial import SerialException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

PLATFORMS = ["media_player"]

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the BreatheAudio 6-Zone Amplifier component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up BreatheAudio 6-Zone Amplifier from a config entry."""
    port = entry.data[CONF_PORT]

    try:
        breatheaudio = await hass.async_add_executor_job(get_breatheaudio, port)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = breatheaudio
    except SerialException:
        _LOGGER.error("Error connecting to BreatheAudio controller at %s", port)
        raise ConfigEntryNotReady

    entry.add_update_listener(_update_listener)

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )

    return unload_ok


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
