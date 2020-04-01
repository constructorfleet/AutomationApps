import copy

import voluptuous as vol

from common.base_app import BaseApp
from common.const import (
    ARG_ENTITY_ID,
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
    config_schema = vol.Schema({
        vol.Required(ARG_ENTITY_ID): vol.All(
            ensure_list,
            [entity_id]),
        vol.Required(ARG_FROM): SCHEMA_CONDITION,
        vol.Required(ARG_TO): SCHEMA_CONDITION,
        vol.Required(ARG_NOTIFY): SCHEMA_NOTIFY
    }, extra=vol.ALLOW_EXTRA)

    _notification_category = None

    def initialize_app(self):
        self._notification_category = \
            get_category_by_name(self.args[ARG_NOTIFY][ARG_NOTIFY_CATEGORY])
        for entity in self.args[ARG_ENTITY_ID]:
            self.listen_state(self._handle_state_change,
                              entity=entity)

    def _condition_to(self, value):
        condition_to = copy.deepcopy(self.args[ARG_TO])
        condition_to[ARG_ENTITY_ID] = value
        return condition_to

    def _condition_from(self, value):
        condition_to = copy.deepcopy(self.args[ARG_FROM])
        condition_to[ARG_ENTITY_ID] = value
        return condition_to

    def _handle_state_change(self, entity, attribute, old, new, kwargs):
        if old == new or old is None or new is None:
            return

        if self.condition_met(self._condition_from(old)) and \
                self.condition_met(self._condition_to(new)):
            self._notify(entity)

    def _notify(self, entity):
        replacers = copy.copy(self.args[ARG_NOTIFY][ARG_NOTIFY_REPLACERS])
        for key, value in [(key, value) for key, value in
                           self.args[ARG_NOTIFY][ARG_NOTIFY_REPLACERS].items() if
                           value == ATTR_ENTITY_NAME]:
            replacers[key] = self.get_state(entity_id=entity, attribute='friendly_name')
        self.notifier.notify_people(
            self._notification_category,
            response_entity_id=self.args[ARG_NOTIFY].get(ARG_NOTIFY_ENTITY_ID, None),
            **replacers)
