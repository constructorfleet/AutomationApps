from builtins import int, isinstance

import voluptuous as vol

from common.base_app import BaseApp
from common.const import (
    ARG_ENTITY_ID,
    ARG_STATE,
    ARG_VALUE,
    ARG_DOMAIN,
    ARG_SERVICE,
    ARG_SERVICE_DATA,
    ARG_COMPARATOR, EQUALS, VALID_COMPARATORS)
from common.validation import (
    entity_id,
    ensure_list,
    any_value
)

ARG_TRIGGER = 'trigger'
ARG_RESET_WHEN = 'reset_when'
ARG_DURATION = 'duration'
ARG_ON_TIMEOUT = 'on_timeout'

SCHEMA_TRIGGER = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_STATE, default='on'): any_value
})

SCHEMA_RESET_WHEN = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_COMPARATOR, default=EQUALS): vol.In(VALID_COMPARATORS),
    vol.Required(ARG_VALUE): any_value
})

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
        vol.Optional(ARG_RESET_WHEN, default=[]): vol.All(
            ensure_list,
            [SCHEMA_RESET_WHEN]
        ),
        vol.Required(ARG_DURATION): vol.Any(
            entity_id,
            vol.Coerce(int)
        ),
        vol.Required(ARG_ON_TIMEOUT): vol.All(
            ensure_list,
            [SCHEMA_ON_TIMEOUT]
        )
    }, extra=vol.ALLOW_EXTRA)

    _reset_when = {}
    _when_handlers = set()
    _triggers = set()
    _timeout_handler = None

    def initialize_app(self):
        for when in self.args[ARG_RESET_WHEN]:
            self._reset_when[when[ARG_ENTITY_ID]] = when

        for trigger in self.args[ARG_TRIGGER]:
            if self.get_state(trigger[ARG_ENTITY_ID]) == trigger[ARG_STATE]:
                self._trigger_met_handler(trigger[ARG_ENTITY_ID],
                                          None,
                                          None,
                                          trigger[ARG_STATE],
                                          None)

            self.listen_state(self._trigger_met_handler,
                              entity=trigger[ARG_ENTITY_ID],
                              new=trigger[ARG_STATE])
            self.listen_state(self._trigger_unmet_handler,
                              entity=trigger[ARG_ENTITY_ID],
                              old=trigger[ARG_STATE])

    @property
    def duration(self):
        return self.args[ARG_DURATION] \
            if isinstance(self.args[ARG_DURATION], int) \
            else self.get_state(self.args[ARG_DURATION])

    def _trigger_met_handler(self, entity, attribute, old, new, kwargs):
        if new == old:
            return
        self._triggers.add(entity)
        for reset_when in self.args[ARG_RESET_WHEN]:
            self._when_handlers.add(self.listen_state(self._handle_reset_when,
                                                      entity=reset_when[ARG_ENTITY_ID]))

        self._reset_timer()

    def _handle_reset_when(self, entity, attribute, old, new, kwargs):
        if old == new:
            return
        if self.condition_met(self._reset_when[entity]):
            self._reset_timer()

    def _trigger_unmet_handler(self, entity, attribute, old, new, kwargs):
        if new == old:
            return
        if entity in self._triggers:
            self._triggers.remove(entity)
        if len(self._triggers) == 0:
            self._cancel_timer()
            self._cancel_handlers()
            return

    def _handle_timeout(self, kwargs):
        self._triggers.clear()
        self._cancel_timer()
        self._cancel_handlers()

        self.log("Firing on time out events")
        events = self.args.get(ARG_ON_TIMEOUT, [])
        for event in events:
            self.publish(event[ARG_DOMAIN], event[ARG_SERVICE], event[ARG_SERVICE_DATA])

    def _cancel_handlers(self):
        for handler in self._when_handlers:
            if handler is not None:
                self.cancel_listen_state(handler)
        self._when_handlers.clear()

    def _cancel_timer(self):
        if self._timeout_handler is not None:
            self.cancel_timer(self._timeout_handler)

    def _reset_timer(self):
        self._cancel_timer()
        self._timeout_handler = self.run_in(self._handle_timeout,
                                            self.duration * 60)
