from builtins import int, isinstance

import voluptuous as vol

from common.base_app import BaseApp
from common.const import (
    ARG_ENTITY_ID,
    ARG_COMPARATOR,
    ARG_STATE,
    ARG_VALUE,
    ARG_DOMAIN,
    ARG_SERVICE,
    ARG_SERVICE_DATA,
    EQUALS, VALID_COMPARATORS)
from common.validation import (
    entity_id,
    ensure_list,
    any_value
)

ARG_TRIGGER = 'trigger'
ARG_CONDITION = 'condition'
ARG_CALL = 'call'

SCHEMA_TRIGGER = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_STATE, default='on'): any_value
})

SCHEMA_CONDITION_STATE = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_COMPARATOR, default=EQUALS): vol.In(VALID_COMPARATORS),
    vol.Required(ARG_VALUE): any_value
})

# SCHEMA_CONDITION_TIME = vol.Schema({
#     vol.Exclusive(ARG_BEFORE, 'time_condition'): time,
#     vol.Exclusive(ARG_AFTER, 'time_condition'): time
# })

SCHEMA_CONDITION = vol.Any(SCHEMA_CONDITION_STATE)  # , SCHEMA_CONDITION_TIME)

SCHEMA_CALL = vol.Schema({
    vol.Required(ARG_DOMAIN): str,
    vol.Required(ARG_SERVICE): str,
    vol.Optional(ARG_SERVICE_DATA, default={}): dict
})


class CallWhen(BaseApp):
    config_schema = vol.Schema({
        vol.Required(ARG_TRIGGER): vol.All(
            ensure_list,
            [SCHEMA_TRIGGER]
        ),
        vol.Optional(ARG_CONDITION, default=[]): vol.All(
            ensure_list,
            [SCHEMA_CONDITION]
        ),
        vol.Required(ARG_CALL): vol.All(
            ensure_list,
            [SCHEMA_CALL]
        )
    }, extra=vol.ALLOW_EXTRA)

    _conditions = {}

    def initialize_app(self):
        for trigger in self.args[ARG_TRIGGER]:
            new_state = self.get_state(entity_id=trigger[ARG_ENTITY_ID])
            if new_state == trigger[ARG_STATE]:
                self._handle_trigger(
                    trigger[ARG_ENTITY_ID],
                    None,
                    None,
                    new_state,
                    {}
                )
            self.listen_state(self._handle_trigger,
                              entity=trigger[ARG_ENTITY_ID],
                              new=trigger[ARG_STATE])

    @property
    def conditions_met(self):
        for condition in self.args[ARG_CONDITION]:
            if not self.condition_met(condition):
                return False

        return True

    def _handle_trigger(self, entity, attribute, old, new, kwargs):
        if not self.conditions_met:
            self.log("Conditions no met")
            return

        events = self.args[ARG_CALL]
        for event in events:
            self.publish_service_call(event[ARG_DOMAIN], event[ARG_SERVICE], event[ARG_SERVICE_DATA])
