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
    ARG_NOTIFY)
from common.validation import (
    entity_id,
    any_value
)
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
    vol.Optional(ARG_NOTIFY_ENTITY_ID, default=None): entity_id,
    vol.Optional(ARG_NOTIFY_REPLACERS, default={}): dict
})


class NotifyWhen(BaseApp):
    config_schema = vol.Schema({
        vol.Required(ARG_ENTITY_ID): entity_id,
        vol.Required(ARG_FROM): SCHEMA_CONDITION,
        vol.Required(ARG_TO): SCHEMA_CONDITION,
        vol.Required(ARG_NOTIFY): SCHEMA_NOTIFY
    }, extra=vol.ALLOW_EXTRA)

    _notification_category = None

    def initialize_app(self):
        self._notification_category = \
            get_category_by_name(self.args[ARG_NOTIFY][ARG_NOTIFY_CATEGORY])
        self.listen_state(self._handle_state_change,
                          entity=self.args[ARG_ENTITY_ID])

    def _condition_to(self, value):
        condition_to = copy.deepcopy(self.args[ARG_TO])
        condition_to[ARG_ENTITY_ID] = value
        return condition_to

    def _condition_from(self, value):
        condition_to = copy.deepcopy(self.args[ARG_FROM])
        condition_to[ARG_ENTITY_ID] = value
        return condition_to

    def _handle_state_change(self, entity, attribute, old, new, kwargs):
        if old == new:
            return

        if self.condition_met(self._condition_from(old)) and \
                self.condition_met(self._condition_to(new)):
            self._notify()

    def _notify(self):
        self.notifier.notify_people(
            self._notification_category,
            response_entity_id=self.args[ARG_NOTIFY][ARG_NOTIFY_ENTITY_ID],
            **self.args[ARG_NOTIFY][ARG_NOTIFY_REPLACERS])
