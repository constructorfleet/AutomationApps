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
    ARG_ENABLED_FLAG,
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
    _notification_category = None
    _pause_when = {}
    _when_handlers = set()
    _timeout_handler = None
    _enabled_flag = True

    def initialize_app(self):
        if ARG_ENABLED_FLAG in self.configs:
            self.listen_state(self._flag_handler,
                              entity_id=self.configs[ARG_ENABLED_FLAG],
                              immediate=True)

        if ARG_NOTIFY in self.configs:
            self._notification_category = \
                get_category_by_name(self.configs[ARG_NOTIFY][ARG_NOTIFY_CATEGORY])

        for when in self.configs[ARG_PAUSE_WHEN]:
            self._pause_when[when[ARG_ENTITY_ID]] = when

        trigger = self.configs[ARG_TRIGGER]
        self.listen_state(self._trigger_met_handler,
                          entity=trigger[ARG_ENTITY_ID],
                          new=trigger[ARG_STATE],
                          immediate=True)
        self.listen_state(self._trigger_unmet_handler,
                          entity=trigger[ARG_ENTITY_ID],
                          old=trigger[ARG_STATE],
                          immediate=True)

    @property
    def app_schema(self):
        return vol.Schema({
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
            vol.Optional(ARG_ENABLED_FLAG): entity_id,
            vol.Optional(ARG_NOTIFY): vol.Schema({
                vol.Required(ARG_NOTIFY_CATEGORY): vol.In(VALID_NOTIFICATION_CATEGORIES),
                vol.Optional(ARG_NOTIFY_REPLACERS, default={}): dict
            }, extra=vol.ALLOW_EXTRA)
        }, extra=vol.ALLOW_EXTRA)

    @property
    def duration(self):
        if isinstance(self.configs[ARG_DURATION], str):
            return self.get_state(self.configs[ARG_DURATION])
        else:
            return self.configs[ARG_DURATION]

    def _flag_handler(self, entity, attribute, old, new, kwargs):
        self._enabled_flag = new is None or new

        if not self._enabled_flag:
            self._cancel_timer('Automation disabled')
            self._cancel_handlers('Automation disabled')
        else:
            trigger = self.configs[ARG_TRIGGER]
            state = self.get_state(trigger[ARG_ENTITY_ID])
            if state == trigger[ARG_STATE]:
                self._trigger_met_handler(
                    trigger[ARG_ENTITY_ID],
                    None,
                    '',
                    state,
                    {}
                )
            else:
                self._trigger_unmet_handler(
                    trigger[ARG_ENTITY_ID],
                    None,
                    '',
                    state,
                    {}
                )

    def _trigger_met_handler(self, entity, attribute, old, new, kwargs):
        if new == old and new != self.configs[ARG_TRIGGER][ARG_STATE]:
            return
        self.debug("Triggered!")
        if self._timeout_handler is None:
            self.debug("Setting up pause handlers")
            for pause_when in self.configs[ARG_PAUSE_WHEN]:
                self._when_handlers.add(
                    self.listen_state(self._handle_pause_when,
                                      entity=pause_when[ARG_ENTITY_ID],
                                      immediate=True))
        self._reset_timer('Triggered')

    def _handle_pause_when(self, entity, attribute, old, new, kwargs):
        if old == new:
            return

        if self._timeout_handler is not None and self.condition_met(self._pause_when[entity]):
            self.debug("Pause time because {} is {}".format(entity, new))
            self._cancel_timer('Pause condition met')
        elif self._timeout_handler is None:
            for entity, condition in self._pause_when.items():
                if self.condition_met(condition):
                    return
            self._reset_timer('Initiating timer')

    def _trigger_unmet_handler(self, entity, attribute, old, new, kwargs):
        if old == new or new == self.configs[ARG_TRIGGER][ARG_STATE]:
            return
        self._cancel_timer('Trigger no longer met')
        self._cancel_handlers('Trigger no longer met')

    def _handle_timeout(self, kwargs):
        self._cancel_timer('Timed out')
        self._cancel_handlers('Timed out')

        self.debug("Firing on time out events")
        events = self.configs.get(ARG_ON_TIMEOUT, [])
        for event in events:
            self.publish_service_call(event[ARG_DOMAIN], event[ARG_SERVICE],
                                      event[ARG_SERVICE_DATA])

        if self._notification_category is not None:
            self.notifier.notify_people(
                self._notification_category,
                response_entity_id=self.configs[ARG_NOTIFY].get(ARG_NOTIFY_ENTITY_ID, None),
                **self.configs[ARG_NOTIFY][ARG_NOTIFY_REPLACERS]
            )

    def _cancel_handlers(self, message):
        self.debug('Cancelling when handlers %s', message)
        handlers = self._when_handlers.copy()
        self._when_handlers = set()
        for handler in [handler for handler in handlers if handler is not None]:
            self.cancel_listen_state(handler)

    def _cancel_timer(self, message):
        self.debug('Canceling Timer %s', message)
        if self._timeout_handler is not None:
            self.cancel_timer(self._timeout_handler)
        self._timeout_handler = None

    def _reset_timer(self, message):
        self._cancel_timer('Resetting')
        self._timeout_handler = self.run_in(self._handle_timeout,
                                            self.duration * 60)
