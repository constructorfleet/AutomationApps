import re
from builtins import isinstance, dict, str, bool, int, property

import voluptuous as vol

#
# Movie mode
#
# Args:
#  media_player: Entity id of the media player
#  reset_on_pause: Whether to reset on pause
#  media_types: Media content types to respond to
#  turn_on_between_episodes: List of entities to turn on between tv episodes
#  turn_off: List of entities to turn off
#  turn_on: List of entities to turn on
#  tv: Entity id  of the television
from common.base_app import BaseApp
from common.const import DOMAIN_HOMEASSISTANT, SERVICE_TURN_ON, ARG_ENTITY_ID, SERVICE_TURN_OFF
from common.validation import entity_id, ensure_list

ARG_MEDIA_PLAYER = "media_player"
ARG_RESET_ON_PAUSE = "reset_on_pause"
ARG_TV_DELAY = "tv_delay"
ARG_MEDIA_TYPES = "media_types"
ARG_TURN_OFF = "turn_off"
ARG_TURN_OFF_ENTITY_ID = "entity_id"
ARG_TURN_OFF_RESET = "reset"
ARG_ON_BETWEEN_EPISODES = "turn_on_between_episodes"
ARG_TURN_ON = "turn_on"
ARG_REMEMBER = "remember"
ARG_STAY_OFF = "stay_off"
ARG_CHECK_SUN = "check_sun"
ARG_TV = "tv"
ARG_ENABLE_TOGGLE = "toggle"

DEFAULT_RESET = False
DEFAULT_REMEMBER = False
DEFAULT_STAY_OFF = True
DEFAULT_SUN_CHECK = False
DEFAULT_MEDIA_TYPES = ["movie"]
DEFAULT_TV_DELAY = 60

MEDIA_TYPE_MUSIC = "music"
MEDIA_TYPE_MOVIE = "movie"
MEDIA_TYPE_VIDEO = "video"
MEDIA_TYPE_TV_SHOW = "tvshow"

MOVIE_MEDIA_TYPES = [
    MEDIA_TYPE_MOVIE,
    MEDIA_TYPE_VIDEO
]

STATE_PAUSED = "paused"
STATE_PLAYING = "playing"
STATE_IDLE = "idle"
STATE_ON = "on"
STATE_UNKNOWN = "unknown"

PLEX_TVSHOW_REGEX = re.compile(r'^S\d+\s.\sE\d+.*$')

ATTR_MEDIA_TYPE = "media_content_type"
ATTR_TITLE = "media_title"
ATTR_DURATION = "media_duration"
ATTR_IGNORE_ENABLED = "ignore_enabled"

SCHEMA_TURN_OFF = vol.Any(
    entity_id,
    vol.Schema({
        vol.Required(ARG_TURN_OFF_ENTITY_ID): entity_id,
        vol.Optional(ARG_REMEMBER, default=DEFAULT_REMEMBER): vol.Coerce(bool),
        vol.Optional(ARG_STAY_OFF, default=DEFAULT_STAY_OFF): vol.Coerce(bool)
    }))


def _plex_media_content_type(
        media_type,
        title,
        duration
):
    """Content type hack for Plex which always shows as music."""
    if media_type == MEDIA_TYPE_MUSIC:
        title = title
        if PLEX_TVSHOW_REGEX.search(title):
            return MEDIA_TYPE_TV_SHOW
        elif duration and int(duration) > 1000:
            return MEDIA_TYPE_VIDEO
        else:
            return MEDIA_TYPE_MUSIC

    return media_type


def is_movie(media_type):
    return media_type in MOVIE_MEDIA_TYPES


class MovieMode(BaseApp):
    """Movie mode app."""

    delay_handle = None
    media_type = None
    state = None
    memory = {}

    def initialize_app(self):
        self.debug("Configs %s", str(self.configs))
        self.listen_state(
            self.player_state_changed,
            entity=self.configs[ARG_MEDIA_PLAYER]
        )

        self.player_state_changed(
            self.configs[ARG_MEDIA_PLAYER],
            None,
            None,
            self.get_state(self.configs[ARG_MEDIA_PLAYER]),
            None
        )

        if self.configs.get(ARG_ENABLE_TOGGLE, None):
            self.listen_state(self.handle_toggle_changed,
                              entity=self.configs[ARG_ENABLE_TOGGLE])

        if ARG_TV in self.configs:
            self.listen_state(self.handle_toggle_changed,
                              entity=self.configs[ARG_TV])

    @property
    def app_schema(self):
        return vol.Schema({
            vol.Required(ARG_MEDIA_PLAYER): entity_id,
            vol.Optional(ARG_MEDIA_TYPES, default=DEFAULT_MEDIA_TYPES): vol.All(
                ensure_list,
                [str]
            ),
            vol.Optional(ARG_TV_DELAY, default=DEFAULT_TV_DELAY): int,
            vol.Optional(ARG_RESET_ON_PAUSE, default=DEFAULT_RESET): vol.Any(
                str,
                bool
            ),
            vol.Required(ARG_TURN_OFF): vol.All(
                ensure_list,
                [SCHEMA_TURN_OFF]
            ),
            vol.Optional(ARG_TURN_ON, default=[]): vol.All(
                ensure_list,
                [entity_id]
            ),
            vol.Optional(ARG_ON_BETWEEN_EPISODES, default=[]): vol.All(
                ensure_list,
                [entity_id]
            ),
            vol.Optional(ARG_CHECK_SUN, default=DEFAULT_SUN_CHECK): bool,
            vol.Optional(ARG_TV): entity_id
        }, extra=vol.ALLOW_EXTRA)

    @property
    def is_playing(self):
        return self.state == STATE_PLAYING

    @property
    def should_turn_on(self):
        return not self.configs[ARG_CHECK_SUN] or self.sun_down()

    @property
    def is_enabled(self):
        is_enabled = self.configs.get(ARG_ENABLE_TOGGLE, None) is None \
                     or self.get_state(self.configs[ARG_ENABLE_TOGGLE]) == "on"
        self.debug('Is enabled? %s', str(is_enabled))
        return is_enabled

    def player_state_changed(self, entity, attribute, old, new, kwargs):
        if not new or new == "" or self.state == new:
            return
        self.state = new
        if new != STATE_IDLE and new != STATE_UNKNOWN:
            self.media_type = _plex_media_content_type(
                self.get_state(
                    self.configs[ARG_MEDIA_PLAYER],
                    attribute=ATTR_MEDIA_TYPE
                ),
                self.get_state(
                    self.configs[ARG_MEDIA_PLAYER],
                    attribute=ATTR_TITLE
                ),
                self.get_state(
                    self.configs[ARG_MEDIA_PLAYER],
                    attribute=ATTR_DURATION
                )
            )
        self.debug("New state {} {}".format(
            self.state,
            self.media_type
        ))
        self.process()

    def pause_media_player(self):
        self.call_service(
            "media_player/media_pause",
            entity_id=self.configs[ARG_MEDIA_PLAYER]
        )

    def process(self):
        self.cancel_delay_timer()

        if self.state == STATE_PLAYING:
            self.handle_playing()
        elif self.state == STATE_PAUSED:
            self.handle_paused()
        elif self.state == STATE_IDLE:
            self.handle_stopped()

    def handle_stopped(self):
        if not self.is_enabled:
            return
        if self.media_type and not is_movie(self.media_type):
            self.debug("Delaying stop")
            self.delay_handle = \
                self.run_in(self.handle_player_stopped,
                            delay=self.configs[ARG_TV_DELAY])
            if self.should_turn_on:
                devices = []
                for device in self.configs[ARG_ON_BETWEEN_EPISODES]:
                    if self.get_state(device) == "on":
                        continue
                    self.debug("Turning on {}".format(device))
                    devices.append(device)

                if len(devices) > 0:
                    self.publish_service_call(
                        DOMAIN_HOMEASSISTANT,
                        SERVICE_TURN_ON,
                        {
                            ARG_ENTITY_ID: devices
                        }
                    )
        else:
            self.handle_player_stopped({})

    def handle_paused(self):
        if not self.is_enabled or not self.configs[ARG_RESET_ON_PAUSE]:
            return

        if isinstance(self.configs[ARG_RESET_ON_PAUSE], bool):
            self.handle_stopped()
        elif self.should_turn_on and self.configs[ARG_RESET_ON_PAUSE] in self.configs:
            devices = []
            for device in self.configs[self.configs[ARG_RESET_ON_PAUSE]]:
                if isinstance(device, str):
                    device_id = device
                else:
                    device_id = device[ARG_TURN_OFF_ENTITY_ID]
                    if device_id not in self.memory:
                        continue
                if self.get_state(device_id) == "on":
                    continue
                self.debug("Turning on {}".format(device_id))
                devices.append(device_id)

            if len(devices) > 0:
                self.publish_service_call(
                    DOMAIN_HOMEASSISTANT,
                    SERVICE_TURN_ON,
                    {
                        ARG_ENTITY_ID: devices
                    }
                )

    def handle_playing(self):
        if not self.is_enabled:
            return
        self.debug("Playing")
        devices = []
        for device in self.configs[ARG_TURN_OFF]:
            if isinstance(device, dict):
                device_id = device[ARG_TURN_OFF_ENTITY_ID]
                self.memory[device_id] = self.get_state(device_id) == STATE_ON
            else:
                device_id = device
            if self.get_state(device_id) == "off":
                continue
            self.debug("Turning off {}".format(device_id))
            devices.append(device_id)
        if len(devices) > 0:
            self.publish_service_call(
                DOMAIN_HOMEASSISTANT,
                SERVICE_TURN_OFF,
                {
                    ARG_ENTITY_ID: devices
                }
            )

        if not self.should_turn_on:
            return

        devices_on = self.configs.get(ARG_TURN_ON, [])
        if len(devices_on) > 0:
            self.publish_service_call(
                DOMAIN_HOMEASSISTANT,
                SERVICE_TURN_ON,
                {
                    ARG_ENTITY_ID: devices_on
                })

    def handle_player_stopped(self, kwargs):
        if not self.is_enabled and not (kwargs or {}).get(ATTR_IGNORE_ENABLED, False):
            return

        if (kwargs or {}).get(ATTR_IGNORE_ENABLED, False):
            self.debug('Ignoring enabled flag')

        self.debug("STOPPED")
        self.cancel_delay_timer()
        self.media_type = None

        devices_on = self.configs.get(ARG_TURN_ON, [])
        if len(devices_on) > 0:
            self.publish_service_call(
                DOMAIN_HOMEASSISTANT,
                SERVICE_TURN_OFF,
                {
                    ARG_ENTITY_ID: devices_on
                }
            )

        if self.should_turn_on:
            devices = []
            for device in self.configs[ARG_TURN_OFF]:
                if isinstance(device, str) and DEFAULT_STAY_OFF:
                    device_id = device
                else:
                    device_id = device[ARG_TURN_OFF_ENTITY_ID]
                    if device_id not in self.memory or device[ARG_STAY_OFF]:
                        continue
                if self.get_state(device_id) == "on":
                    continue
                self.debug("Turning on {}".format(device_id))
                devices.append(device_id)
            if len(devices) > 0:
                self.publish_service_call(
                    DOMAIN_HOMEASSISTANT,
                    SERVICE_TURN_ON,
                    {
                        ARG_ENTITY_ID: devices
                    }
                )

    def handle_tv_off(self, entity, attribute, old, new, kwargs):
        if new != "off":
            return
        self.debug("TV off")
        self.handle_player_stopped(None)
        self.pause_media_player()

    def cancel_delay_timer(self):
        if self.delay_handle:
            self.cancel_timer(self.delay_handle)

        self.delay_handle = None

    def handle_toggle_changed(self, entity, attribute, old, new, kwargs):
        if new == old:
            return
        if new == "on":
            self.debug('Enabling movie mode')
            self.process()
        else:
            self.debug('Disabling movie mode')
            self.handle_player_stopped({
                ATTR_IGNORE_ENABLED: True
            })
