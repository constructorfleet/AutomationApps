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
    ARG_COMPARATOR,
    EQUALS,
    VALID_COMPARATORS,
    ARG_NOTIFY,
    ARG_NOTIFY_CATEGORY,
    ARG_NOTIFY_REPLACERS,
    ARG_NOTIFY_ENTITY_ID)
from common.validation import (
    entity_id,
    ensure_list,
    any_value,
)
from notifiers.notification_category import (
    VALID_NOTIFICATION_CATEGORIES,
    get_category_by_name
)

ARG_TRIGGER = 'trigger'
ARG_PAUSE_WHEN = 'pause_when'
ARG_DURATION = 'duration'
ARG_EXCEPT_IF = 'except_if'
ARG_ON_TIMEOUT = 'on_timeout'

SCHEMA_TRIGGER = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_STATE, default='on'): any_value
})

SCHEMA_EXCEPT_IF = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Required(ARG_STATE): any_value
})

SCHEMA_PAUSE_WHEN = vol.Schema({
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
        vol.Required(ARG_TRIGGER): SCHEMA_TRIGGER,
        vol.Optional(ARG_PAUSE_WHEN, default=[]): vol.All(
            ensure_list,
            [SCHEMA_PAUSE_WHEN]
        ),
        vol.Required(ARG_DURATION): vol.Any(
            entity_id,
            int
        ),
        vol.Required(ARG_ON_TIMEOUT): vol.All(
            ensure_list,
            [SCHEMA_ON_TIMEOUT]
        ),
        vol.Optional(ARG_EXCEPT_IF): SCHEMA_EXCEPT_IF,
        vol.Optional(ARG_NOTIFY): vol.Schema({
            vol.Required(ARG_NOTIFY_CATEGORY): vol.In(VALID_NOTIFICATION_CATEGORIES),
            vol.Optional(ARG_NOTIFY_REPLACERS, default={}): dict
        }, extra=vol.ALLOW_EXTRA)
    }, extra=vol.ALLOW_EXTRA)

    _pause_when = {}
    _when_handlers = set()
    _timeout_handler = None
    _notification_category = None

    def initialize_app(self):
        if ARG_NOTIFY in self.config:
            self._notification_category = \
                get_category_by_name(self.config[ARG_NOTIFY][ARG_NOTIFY_CATEGORY])

        for when in self.config[ARG_PAUSE_WHEN]:
            self._pause_when[when[ARG_ENTITY_ID]] = when

        self.warning('When lenght: {}', len(self._pause_when))

        trigger = self.config[ARG_TRIGGER]

        self.listen_state(self._trigger_met_handler,
                          entity=trigger[ARG_ENTITY_ID],
                          new=trigger[ARG_STATE],
                          immediate=True)
        self.listen_state(self._trigger_unmet_handler,
                          entity=trigger[ARG_ENTITY_ID],
                          old=trigger[ARG_STATE],
                          immediate=True)

    @property
    def duration(self):
        if isinstance(self.config[ARG_DURATION], str):
            return self.get_state(self.config[ARG_DURATION])
        else:
            return self.config[ARG_DURATION]

    def _trigger_met_handler(self, entity, attribute, old, new, kwargs):
        if new == old:
            return
        self.debug("Triggered!")
        if self._timeout_handler is None:
            self.debug("Setting up pause handlers")
            for pause_when in self.config[ARG_PAUSE_WHEN]:
                self._when_handlers.add(
                    self.listen_state(self._handle_pause_when,
                                      entity=pause_when[ARG_ENTITY_ID],
                                      immediate=True))
        self.debug('Triggered - resetting timer')
        self._reset_timer()

    def _handle_pause_when(self, entity, attribute, old, new, kwargs):
        if old == new:
            return
        self.warning('When lenght: {}', len(self._pause_when))
        if self._timeout_handler is not None and self.condition_met(self._pause_when[entity]):
            self.debug("Pause time because {} is {}".format(entity, new))
            self._cancel_timer()
        elif self._timeout_handler is None:
            for entity, condition in self._pause_when.items():
                if self.condition_met(condition):
                    return
            self.debug("Starting timer")
            self._reset_timer()

    def _trigger_unmet_handler(self, entity, attribute, old, new, kwargs):
        self._cancel_timer()
        self._cancel_handlers()

    def _handle_timeout(self, kwargs):
        self._cancel_timer()
        self._cancel_handlers()

        self.debug("Firing on time out events")
        events = self.config.get(ARG_ON_TIMEOUT, [])
        for event in events:
            self.publish_service_call(event[ARG_DOMAIN], event[ARG_SERVICE],
                                      event[ARG_SERVICE_DATA])

        if self._notification_category is not None:
            self.notifier.notify_people(
                self._notification_category,
                response_entity_id=self.config[ARG_NOTIFY].get(ARG_NOTIFY_ENTITY_ID, None),
                **self.config[ARG_NOTIFY][ARG_NOTIFY_REPLACERS]
            )

    def _cancel_handlers(self):
        handlers = self._when_handlers.copy()
        self._when_handlers.clear()
        for handler in handlers:
            self.cancel_listen_state(handler)

    def _cancel_timer(self):
        self._timeout_handler = self.cancel_timer(self._timeout_handler)

    def _reset_timer(self):
        self.debug("Resetting timer")
        self._cancel_timer()
        self._timeout_handler = self.run_in(self._handle_timeout,
                                            self.duration * 60)
