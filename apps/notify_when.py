import copy

import voluptuous as vol

from common.base_app import BaseApp
from common.const import (
    ARG_ENTITY_ID,
    ARG_STATE,
    ARG_COMPARATOR,
    ARG_VALUE,
    ARG_NOTIFY_CATEGORY,
    EQUALS, VALID_COMPARATORS,
    ARG_NOTIFY_ENTITY_ID,
    ARG_NOTIFY_REPLACERS,
    ARG_NOTIFY,
    ATTR_ENTITY_NAME)
from common.validation import (
    entity_id,
    any_value,
    ensure_list)
from notifiers.notification_category import (
    VALID_NOTIFICATION_CATEGORIES,
    get_category_by_name
)

ARG_FROM = 'from'
ARG_TO = 'to'

SCHEMA_CONDITION = vol.Schema({
    vol.Optional(ARG_COMPARATOR, default=EQUALS): vol.In(VALID_COMPARATORS),
    vol.Required(ARG_VALUE): any_value
})

SCHEMA_NOTIFY = vol.Schema({
    vol.Required(ARG_NOTIFY_CATEGORY): vol.In(VALID_NOTIFICATION_CATEGORIES),
    vol.Optional(ARG_NOTIFY_ENTITY_ID): entity_id,
    vol.Optional(ARG_NOTIFY_REPLACERS, default={}): dict
})


class NotifyWhen(BaseApp):
    async def initialize_app(self):
        self._notification_category = \
            get_category_by_name(self.configs[ARG_NOTIFY][ARG_NOTIFY_CATEGORY])
        for entity in self.configs[ARG_ENTITY_ID]:
            await self.listen_state(self._handle_state_change,
                                    entity=entity)

    @property
    def app_schema(self):
        return vol.Schema({
            vol.Required(ARG_ENTITY_ID): vol.All(
                ensure_list,
                [entity_id]),
            vol.Required(ARG_FROM): SCHEMA_CONDITION,
            vol.Required(ARG_TO): SCHEMA_CONDITION,
            vol.Required(ARG_NOTIFY): SCHEMA_NOTIFY
        }, extra=vol.ALLOW_EXTRA)

    def _condition_to(self, entity, state):
        condition_to = copy.deepcopy(self.configs[ARG_TO])
        condition_to[ARG_ENTITY_ID] = entity
        condition_to[ARG_STATE] = state
        return condition_to

    def _condition_from(self, entity, state):
        condition_to = copy.deepcopy(self.configs[ARG_FROM])
        condition_to[ARG_ENTITY_ID] = entity
        condition_to[ARG_STATE] = state
        return condition_to

    async def _handle_state_change(self, entity, attribute, old, new, kwargs):
        if old == new or old is None or new is None:
            self.debug(f'Old {old} new {new} entity {entity}')
            return

        if await self.condition_met(self._condition_from(entity, old)) and \
                await self.condition_met(self._condition_to(entity, new)):
            await self._notify(entity)

    async def _notify(self, entity):
        replacers = copy.copy(self.configs[ARG_NOTIFY][ARG_NOTIFY_REPLACERS])
        for key, value in [(key, value) for key, value in
                           self.configs[ARG_NOTIFY][ARG_NOTIFY_REPLACERS].items() if
                           value == ATTR_ENTITY_NAME]:
            replacers[key] = await self.get_state(entity_id=entity, attribute='friendly_name')
        await self.notifier.notify_people(
            self._notification_category,
            response_entity_id=self.configs[ARG_NOTIFY].get(ARG_NOTIFY_ENTITY_ID, None),
            **replacers)
