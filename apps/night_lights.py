import datetime
from builtins import int
from time import sleep

import voluptuous as vol

from common.base_app import BaseApp
from common.const import (
    ARG_DOMAIN,
    ARG_ENTITY_ID,
    ARG_SERVICE,
    ARG_SERVICE_DATA)
from common.utils import minutes_to_seconds
from common.validation import ensure_list, entity_id

ARG_DUSK = "dusk"
ARG_DAWN = "dawn"
ARG_NIGHT = "night"
ARG_ENTITIES = "entities"
ARG_OFFSET = "offset"

ATTR_RGB_COLOR = "rgb_color"

DEFAULT_OFFSET = 0
DEFAULT_DOMAIN = "homeassistant"
DEFAULT_DUSK_SERVICE = "turn_on"
DEFAULT_DAWN_SERVICE = "turn_off"

SCHEDULE_WAIT = 60 * 10  # 10 Minutes

ENTITY_SCHEMA = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_SERVICE_DATA, default={}): dict
})

DUSK_ENTITY_SCHEMA = ENTITY_SCHEMA.extend({
    vol.Optional(ARG_DOMAIN, default=DEFAULT_DOMAIN): str,
    vol.Optional(ARG_SERVICE, default=DEFAULT_DUSK_SERVICE): str
})

DAWN_ENTITY_SCHEMA = ENTITY_SCHEMA.extend({
    vol.Optional(ARG_DOMAIN, default=DEFAULT_DOMAIN): str,
    vol.Optional(ARG_SERVICE, default=DEFAULT_DAWN_SERVICE): str
})

NIGHT_ENTITY_SCHEMA = ENTITY_SCHEMA.extend({
    vol.Required(ARG_SERVICE): str,
    vol.Required(ARG_DOMAIN): str
})


class NightLights(BaseApp):
    """Fire events for dawn/dusk."""

    dawn_entities = []
    dusk_entities = []
    night_entities = []

    def initialize_app(self):
        """Initalize the application."""
        conf_dawn = self.configs.get(ARG_DAWN)
        conf_dusk = self.configs.get(ARG_DUSK)
        self.night_entities = self.configs.get(ARG_NIGHT)

        if conf_dawn:
            self.dawn_entities = conf_dawn[ARG_ENTITIES]
            self._schedule_dawn()
            if self.sun_up():
                self._handle_dawn(None)

        if conf_dusk:
            self.dusk_entities = conf_dusk[ARG_ENTITIES]
            self._schedule_dusk()
            if self.sun_down():
                self._handle_dusk(None)

        if self.night_entities:
            self.run_daily(self._handle_night,
                           datetime.time())
            now = datetime.datetime.now().time()
            if self.sun_down() and now.hour < 12 and \
                    now > datetime.time():
                self._handle_night(None)

    @property
    def app_schema(self):
        return vol.Schema({
            vol.Optional(ARG_DAWN): {
                vol.Optional(ARG_OFFSET, default=DEFAULT_OFFSET): vol.Coerce(int),
                vol.Optional(ARG_ENTITIES, default=[]): vol.All(
                    ensure_list,
                    [DAWN_ENTITY_SCHEMA]
                )
            },
            vol.Optional(ARG_DUSK): {
                vol.Optional(ARG_OFFSET, default=DEFAULT_OFFSET): vol.Coerce(int),
                vol.Optional(ARG_ENTITIES, default=[]): vol.All(
                    ensure_list,
                    [DUSK_ENTITY_SCHEMA]
                )
            },
            vol.Optional(ARG_NIGHT, default=[]): vol.All(
                ensure_list,
                [NIGHT_ENTITY_SCHEMA]
            )
        }, extra=vol.ALLOW_EXTRA)

    def _schedule_dawn(self, wait_seconds=0):
        self._schedule(
            'run_at_sunrise',
            self._handle_dawn,
            offset=self.configs[ARG_DAWN][ARG_OFFSET],
            wait_seconds=wait_seconds)

    def _schedule_dusk(self, wait_seconds=0):
        self._schedule(
            'run_at_sunset',
            self._handle_dusk,
            offset=-self.configs[ARG_DUSK][ARG_OFFSET],
            wait_seconds=wait_seconds)

    def _handle_dawn(self, kwargs):
        """Handle dawn event."""
        self._handle_entity_services(self.dawn_entities)
        self._schedule_dawn(SCHEDULE_WAIT)

    def _handle_dusk(self, kwargs):
        """Handle dusk event."""
        self._handle_entity_services(self.dusk_entities)
        self._schedule_dusk(SCHEDULE_WAIT)

    def _handle_night(self, kwargs):
        """Handle night event."""
        self._handle_entity_services(self.night_entities)

    def _handle_entity_services(self, entity_services):
        holiday_colors = [(255, 255, 255)]
        if self.holidays:
            holiday_colors = self.holidays.get_closest_holiday_colors()

        for i, entity_service in enumerate(entity_services):
            data = entity_service.get(ARG_SERVICE_DATA, {})
            data[ARG_ENTITY_ID] = entity_service[ARG_ENTITY_ID]
            if holiday_colors and '_on' in entity_service[ARG_SERVICE]:
                data[ATTR_RGB_COLOR] = holiday_colors[i % len(holiday_colors)]

            self.publish_service_call(
                entity_service[ARG_DOMAIN],
                entity_service[ARG_SERVICE],
                data
            )
            sleep(1.5)

    def _schedule(self, event, handler, offset, wait_seconds=0):
        """Schedule handler."""
        sleep(wait_seconds)
        self.__getattribute__(event)(handler, offset=offset)
