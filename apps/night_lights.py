import datetime
from builtins import int
from time import sleep

import voluptuous as vol

from common.base_app import BaseApp
from common.utils import minutes_to_seconds
from common.validation import entity_id, ensure_list, service

ARG_DUSK = "dusk"
ARG_DAWN = "dawn"
ARG_NIGHT = "night"
ARG_ENTITIES = "entities"
ARG_ENTITY_ID = "entity_id"
ARG_SERVICE = "service"
ARG_SERVICE_DATA = "service_data"
ARG_OFFSET = "offset"

DEFAULT_OFFSET = 0
DEFAULT_DUSK_SERVICE = "homeassistant/turn_on"
DEFAULT_DAWN_SERVICE = "homeassistant/turn_off"

MIDNIGHT = datetime.time(0, 0, 0)

ENTITY_SCHEMA = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_SERVICE_DATA, default={}): dict
})

DUSK_ENTITY_SCHEMA = ENTITY_SCHEMA.extend({
    vol.Optional(ARG_SERVICE, default=DEFAULT_DUSK_SERVICE): service
})

DAWN_ENTITY_SCHEMA = ENTITY_SCHEMA.extend({
    vol.Optional(ARG_SERVICE, default=DEFAULT_DAWN_SERVICE): service
})

NIGHT_ENTITY_SCHEMA = ENTITY_SCHEMA.extend({
    vol.Required(ARG_SERVICE): service
})


class NightLights(BaseApp):
    """Fire events for dawn/dusk."""

    config_schema = vol.Schema({
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

    dawn_entities = []
    dusk_entities = []
    night_entities = []

    def initialize_app(self):
        """Iniitalize the application."""
        conf_dawn = self.args.get(ARG_DAWN)
        conf_dusk = self.args.get(ARG_DUSK)
        self.night_entities = self.args.get(ARG_NIGHT)

        if conf_dawn:
            self.dawn_entities = conf_dawn[ARG_ENTITIES]
            self.run_at_sunrise(self._handle_dawn,
                                offset=minutes_to_seconds(conf_dawn[ARG_OFFSET]))
            if self.sun_up():
                self._handle_dawn(None)

        if conf_dusk:
            self.dusk_entities = conf_dusk[ARG_ENTITIES]
            self.run_at_sunset(self._handle_dusk,
                               offset=-minutes_to_seconds(conf_dusk[ARG_OFFSET]))
            if self.sun_down():
                self._handle_dusk(None)

        if self.night_entities:
            self.run_daily(self._handle_night,
                           MIDNIGHT)
            if self.sun_down() and datetime.datetime.now().time() > MIDNIGHT:
                self._handle_night(None)

    def _handle_dawn(self, kwargs):
        """Handle dawn event."""
        self._handle_entity_services(self.dawn_entities)

    def _handle_dusk(self, kwargs):
        """Handle dusk event."""
        self._handle_entity_services(self.dusk_entities)

    def _handle_night(self, kwargs):
        """Handle night event."""
        self._handle_entity_services(self.night_entities)

    def _handle_entity_services(self, entity_services):
        for entity_service in entity_services:
            data = entity_service.get(ARG_SERVICE_DATA, {})
            data[ARG_ENTITY_ID] = entity_service[ARG_ENTITY_ID]

            self.publish(
                entity_service[ARG_SERVICE],
                **data
            )
            sleep(1)
