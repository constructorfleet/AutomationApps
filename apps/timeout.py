from builtins import int, isinstance

import voluptuous as vol

from common.base_app import BaseApp
from common.const import (
    ARG_ENTITY_ID,
    ARG_STATE,
    ARG_VALUE,
    ARG_DOMAIN,
    ARG_SERVICE,
    ARG_SERVICE_DATA
)
from common.validation import (
    entity_id,
    ensure_list,
    any_value
)

ARG_TRIGGER = 'trigger'
ARG_CONDITION = 'condition'
ARG_CONDITION_COMPARATOR = 'comparator'
ARG_DURATION = 'duration'
ARG_ON_TRIGGER = 'on_trigger'
ARG_ON_TIMEOUT = 'on_timeout'

EQUALS = '='
LESS_THAN = '<'
LESS_THAN_EQUAL_TO = '<='
GREATER_THAN = '>'
GREATER_THAN_EQUAL_TO = '>='
NOT_EQUAL = '!='

VALID_COMPARATORS = [
    EQUALS,
    LESS_THAN,
    LESS_THAN_EQUAL_TO,
    GREATER_THAN,
    GREATER_THAN_EQUAL_TO,
    NOT_EQUAL
]

SCHEMA_TRIGGER = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_STATE, default='on'): any_value
})

SCHEMA_CONDITION_STATE = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_CONDITION_COMPARATOR, default=EQUALS): vol.In(VALID_COMPARATORS),
    vol.Required(ARG_VALUE): any_value
})

# SCHEMA_CONDITION_TIME = vol.Schema({
#     vol.Exclusive(ARG_BEFORE, 'time_condition'): time,
#     vol.Exclusive(ARG_AFTER, 'time_condition'): time
# })

SCHEMA_CONDITION = vol.Any(SCHEMA_CONDITION_STATE)  # , SCHEMA_CONDITION_TIME)

SCHEMA_ON_TIMEOUT = SCHEMA_ON_TRIGGER = vol.Schema({
    vol.Required(ARG_DOMAIN): str,
    vol.Required(ARG_SERVICE): str,
    vol.Optional(ARG_SERVICE_DATA, default={}): dict
})


class Timeout(BaseApp):
    config_schema = vol.Schema({
        vol.Required(ARG_TRIGGER): vol.All(
            ensure_list,
            [SCHEMA_TRIGGER]
        ),
        vol.Optional(ARG_CONDITION, default=[]): vol.All(
            ensure_list,
            [SCHEMA_CONDITION]
        ),
        vol.Required(ARG_DURATION): vol.Any(
            entity_id,
            vol.Coerce(int)
        ),
        vol.Required(ARG_ON_TIMEOUT): vol.All(
            ensure_list,
            [SCHEMA_ON_TIMEOUT]
        ),
        vol.Optional(ARG_ON_TRIGGER): vol.All(
            ensure_list,
            [SCHEMA_ON_TRIGGER]
        )
    }, extra=vol.ALLOW_EXTRA)

    _triggers = set()
    _timeout_handler = None

    def initialize_app(self):
        for trigger in self.args[ARG_TRIGGER]:
            self.listen_state(self._trigger_met_handler,
                              entity=trigger[ARG_ENTITY_ID],
                              new=trigger[ARG_STATE])
            self.listen_state(self._trigger_unmet_handler,
                              entity=trigger[ARG_ENTITY_ID],
                              old=trigger[ARG_STATE])
        pass

    @property
    def duration(self):
        return self.args[ARG_DURATION] \
            if isinstance(self.args[ARG_DURATION], int) \
            else self.get_state(self.args[ARG_DURATION])

    @property
    def conditions_met(self):
        for condition in self.args[ARG_CONDITION]:
            # TODO: Other conditions
            if not self._state_condition_met(condition):
                return False

        return True

    def _state_condition_met(self, condition):
        entity_state = self.get_state(condition[ARG_ENTITY_ID])
        value = condition[ARG_VALUE]
        comparator = condition[ARG_CONDITION_COMPARATOR]
        if comparator == EQUALS:
            return entity_state == value
        elif comparator == NOT_EQUAL:
            return entity_state != value
        elif comparator == LESS_THAN:
            return entity_state < value
        elif comparator == LESS_THAN_EQUAL_TO:
            return entity_state <= value
        elif comparator == GREATER_THAN:
            return entity_state > value
        elif comparator == GREATER_THAN_EQUAL_TO:
            return entity_state >= value
        else:
            self.log('Invalid comparator %s' % comparator)
            return False

    def _trigger_met_handler(self, entity, attribute, old, new, kwargs):
        if new == old:
            return
        self.log("Adding %s from triggers" % entity)
        self._triggers.add(entity)
        if self._timeout_handler is None:
            self.log("New run")
            if not self.conditions_met:
                self.log("Conditions not met")
                return
            self._handle_triggered()

    def _trigger_unmet_handler(self, entity, attribute, old, new, kwargs):
        if new == old:
            return
        if len(self._triggers) == 0:
            return
        self.log("Removing %s from triggers" % entity)
        if entity in self._triggers:
            self._triggers.remove(entity)
        if len(self._triggers) == 0:
            self._start_timer()

    def _start_timer(self):
        self.log("Starting timer")
        if self._timeout_handler is not None:
            self.cancel_timer(self._timeout_handler)
        self._timeout_handler = self.run_in(self._handle_timeout,
                                            self.duration * 60)

    def _handle_triggered(self):
        self.log("Handling triggered")
        events = self.args.get(ARG_ON_TRIGGER, [])
        for event in events:
            self.publish(event[ARG_DOMAIN], event[ARG_SERVICE], event[ARG_SERVICE_DATA])

    def _handle_timeout(self, kwargs):
        self._triggers.clear()
        self.log("Handling timeout")
        if self._timeout_handler is not None:
            self.log("Killing timer")
            self.cancel_timer(self._timeout_handler)

        self.log("Firing on time out events")
        events = self.args.get(ARG_ON_TIMEOUT, [])
        for event in events:
            self.publish(event[ARG_DOMAIN], event[ARG_SERVICE], event[ARG_SERVICE_DATA])
