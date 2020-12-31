import datetime
from builtins import int

import voluptuous as vol

from common.base_app import BaseApp
from common.const import (
    ARG_DOMAIN,
    ARG_ENTITY_ID,
    ARG_SERVICE,
    ARG_SERVICE_DATA,
    ATTR_RGB_COLOR)
from common.validation import ensure_list, entity_id, color_rgb, color_name

ARG_DUSK = "dusk"
ARG_DAWN = "dawn"
ARG_NIGHT = "night"
ARG_ENTITIES = "entities"
ARG_OFFSET = "offset"
ARG_STATIC_COLOR = "static_color"

DEFAULT_OFFSET = 0
DEFAULT_DOMAIN = "homeassistant"
DEFAULT_DUSK_SERVICE = DEFAULT_NIGHT_SERVICE = "turn_on"
DEFAULT_DAWN_SERVICE = "turn_off"

SCHEDULE_WAIT = 60 * 5  # 5 Minutes

ENTITY_SCHEMA = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_SERVICE_DATA, default={}): dict,
    vol.Optional(ARG_STATIC_COLOR): vol.All(vol.Any(color_rgb, color_name), vol.Coerce(tuple))
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
    vol.Required(ARG_SERVICE, default=DEFAULT_NIGHT_SERVICE): str,
    vol.Required(ARG_DOMAIN, default=DEFAULT_DOMAIN): str
})


class NightLights(BaseApp):
    """Fire events for dawn/dusk."""

    dawn_entities = []
    dusk_entities = []
    night_entities = []

    async def initialize_app(self):
        """Initalize the application."""
        conf_dawn = self.configs.get(ARG_DAWN)
        conf_dusk = self.configs.get(ARG_DUSK)
        self.night_entities = self.configs.get(ARG_NIGHT)

        if conf_dawn:
            if await self.sun_up():
                await self._handle_dawn(None)
            await self._schedule_dawn()

        if conf_dusk:
            if await self.sun_down():
                await self._handle_dusk(None)
            await self._schedule_dusk()

        if self.night_entities:
            now = datetime.datetime.now().time()
            if await self.sun_down() and now.hour < 12 and \
                    now > datetime.time():
                await self._handle_night(None)
            await self.run_daily(self._handle_night,
                                 datetime.time())

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

    async def _schedule_dawn(self):
        self.dawn_handle = await self.run_at_sunrise(
            self._handle_dawn,
            offset=self.configs[ARG_DAWN][ARG_OFFSET])

    async def _schedule_dusk(self):
        self.dusk_handle = await self.run_at_sunset(
            self._handle_dusk,
            offset=-self.configs[ARG_DUSK][ARG_OFFSET])

    async def _handle_dawn(self, kwargs):
        """Handle dawn event."""
        self._handle_entity_services(self.dawn_entities)

    async def _handle_dusk(self, kwargs):
        """Handle dusk event."""
        self._handle_entity_services(self.dusk_entities)

    async def _handle_night(self, kwargs):
        """Handle night event."""
        self._handle_entity_services(self.night_entities)

    def _handle_entity_services(self, entities):
        holiday_colors = [(255, 255, 255)]
        if self.holidays:
            holiday_colors = self.holidays.get_closest_holiday_colors()
            self.info("HOLIDAY COLORS: {0}".format(str(holiday_colors)))

        for i, entity in enumerate(entities):
            data = entity.get(ARG_SERVICE_DATA, {})
            data[ARG_ENTITY_ID] = entity[ARG_ENTITY_ID]
            color = entity.get(ARG_STATIC_COLOR, None)
            if color:
                data[ATTR_RGB_COLOR] = color
            elif holiday_colors and '_on' in entity[ARG_SERVICE]:
                data[ATTR_RGB_COLOR] = holiday_colors[i % len(holiday_colors)]

            self.info('Light Color: {0}'.format(data.get(ATTR_RGB_COLOR, 'n/a')))

            self.publish_service_call(
                entity[ARG_DOMAIN],
                entity[ARG_SERVICE],
                data
            )
