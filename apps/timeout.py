from builtins import int, float, isinstance, str

import voluptuous as vol

from common.base_app import BaseApp
from common.validation import entity_id, service
from notifiers.notification_action import NotificationAction
from notifiers.notification_category import get_category_by_name

ARG_ENTITY_ID = "entity_id"
ARG_NOTIFY = "notify"
ARG_STATE = "state"
ARG_TIMEOUT = "timeout"
ARG_TIMEOUT_WAIT = "wait"
ARG_SERVICE = "service"
ARG_SERVICE_DATA = "service_data"
ARG_DELAY_IF = "delay_if"
ARG_DELAY_SECONDS = "seconds"
ARG_DELAY_ENTITY = "entity_id"
ARG_DELAY_STATE = "state"
ARG_DELAY_ATTRIBUTE = "attribute"
ARG_DELAY_NOTIFY = "notify"
ARG_DELAY_ACKNOWLEDGE_ID = "acknowledge_id"
ARG_DELAY_SILENCE_MINUTES = "silence_minutes"

DEFAULT_DELAY_SECONDS = 30
DEFAULT_SILENCE_MINUTES = 30

DELAY_SCHEMA = vol.Schema({
    vol.Required(ARG_DELAY_ENTITY): entity_id,
    vol.Required(ARG_DELAY_STATE): str,
    vol.Inclusive(ARG_DELAY_NOTIFY, 'notify_delay'): str,
    vol.Inclusive(ARG_DELAY_ACKNOWLEDGE_ID, 'notify_delay'): str,
    vol.Optional(
        ARG_DELAY_SILENCE_MINUTES, default=DEFAULT_SILENCE_MINUTES): int,
    vol.Optional(ARG_DELAY_ATTRIBUTE): str,
    vol.Optional(ARG_DELAY_SECONDS, default=DEFAULT_DELAY_SECONDS): int
}, extra=vol.ALLOW_EXTRA)


class EntityTimeout(BaseApp):
    config_schema = vol.Schema({
        vol.Required(ARG_ENTITY_ID): entity_id,
        vol.Required(ARG_STATE): str,
        vol.Optional(ARG_TIMEOUT_WAIT, default=1): vol.Coerce(int),
        vol.Required(ARG_TIMEOUT): vol.Any(
            vol.Coerce(int),
            entity_id
        ),
        vol.Required(ARG_SERVICE): service,
        vol.Optional(ARG_SERVICE_DATA): dict,
        vol.Optional(ARG_DELAY_IF): DELAY_SCHEMA,
        vol.Optional(ARG_NOTIFY): str
    }, extra=vol.ALLOW_EXTRA)

    timer_handle = None
    state_handle = None
    delay_handle = None
    silence_handle = None
    timeout = 0
    _notifiers = None
    _acknowledged = False

    def initialize_app(self):
        self._notifiers = self.get_app("notifiers")

        arg = self.args[ARG_TIMEOUT]
        if isinstance(arg, int):
            self.timeout = arg
        elif isinstance(arg, str):
            self.timeout = int(float(self.get_state(arg)))
            self.listen_state(self.handle_duration_change,
                              entity=arg)

        if self.get_state(self.args[ARG_ENTITY_ID]) == self.args[ARG_STATE]:
            self.handle_start_timeout(
                entity=self.args[ARG_ENTITY_ID],
                new=self.get_state(self.args[ARG_ENTITY_ID])
            )

        self.state_handle = self.listen_state(
            self.handle_start_timeout,
            entity=self.args[ARG_ENTITY_ID],
            new=self.args[ARG_STATE],
            duration=self.args[ARG_TIMEOUT_WAIT]
        )
        self.listen_state(
            self.handle_stop_timeout,
            entity=self.args[ARG_ENTITY_ID],
            old=self.args[ARG_STATE],
            duration=self.args[ARG_TIMEOUT_WAIT]
        )

        if self.args.get(ARG_DELAY_IF, {}).get(ARG_DELAY_ACKNOWLEDGE_ID, None):
            self.get_app('notification_action_processor').add_acknowledge_listener(
                self.handle_delay_acknowledge)

        self.log("Initialized")

    def handle_delay_acknowledge(self, acknowledge_id, action):
        if not action:
            self.log("Wrong action {}".format(str(action)))
            return

        if acknowledge_id != self.args[ARG_DELAY_IF][ARG_DELAY_ACKNOWLEDGE_ID]:
            self.log("Invalid ack id {}".format(str(acknowledge_id)))
            return

        if action == NotificationAction.ACTION_TIMEOUT_DELAY_ACKNOWLEDGE:
            self._acknowledged = True
        elif action == NotificationAction.ACTION_TIMEOUT_DELAY_SILENCE:
            self.stop_delay()
            minutes = self.args[ARG_DELAY_IF][ARG_DELAY_SILENCE_MINUTES]
            self.silence_handle = self.run_in(self.handle_timed_out,
                                              minutes)

    def handle_duration_change(self, entity, attribute, old, new, kwargs):
        if not new or old == new or self.timeout == int(float(new)):
            return

        self.timeout = int(float(new))
        if self.timer_handle:
            self.log("Restarting for new duration")
            self.start_timer()

    def handle_start_timeout(self, entity=None, attribute=None, old=None, new=None, kwargs={}):
        self.log("{} went from {} to {}".format(entity, old, new))
        if old == new:
            return
        elif new == self.args[ARG_STATE]:
            self.start_timer()
        else:
            self.log("Not starting timer")

    def handle_stop_timeout(self, entity=None, attribute=None, old=None, new=None, kwargs={}):
        self.log("{} went from {} to {}".format(entity, old, new))
        if old == new:
            return
        elif new != self.args[ARG_STATE]:
            self.log("Canceling timer")
            self.stop_delay()
            self.stop_timer()
        else:
            self.log("Not correct state {} {}".format(new, old))

    def handle_timed_out(self, kwargs):
        self.log("Entity timed out")

        self.stop_timer()

        if self.should_delay():
            self.log("Delaying")
            self.delay()
            return

        self._acknowledged = False
        self.stop_delay()
        self.stop_timer()

        service_data = self.args.get(ARG_SERVICE_DATA, None)
        if not service_data:
            service_data = {
                'entity_id': self.args[ARG_ENTITY_ID]
            }
        self.publish(service=self.args[ARG_SERVICE],
                     **service_data)

        if self.args.get(ARG_NOTIFY, None):
            self._notify(
                get_category_by_name(self.args[ARG_NOTIFY]),
                self.args[ARG_ENTITY_ID],
                entity_name=self.friendly_name(self.args[ARG_ENTITY_ID])
            )

    def delay(self):
        seconds = self.args[ARG_DELAY_IF].get(ARG_DELAY_SECONDS, DEFAULT_DELAY_SECONDS)
        self.delay_handle = self.run_in(self.handle_timed_out,
                                        seconds)
        self.log("Delaying for {}".format(seconds))

        if not self._acknowledged and self.args[ARG_DELAY_IF].get(ARG_DELAY_NOTIFY, None):
            self._notify(
                get_category_by_name(self.args[ARG_DELAY_IF][ARG_DELAY_NOTIFY]),
                self.args[ARG_ENTITY_ID],
                entity_name=self.friendly_name(self.args[ARG_ENTITY_ID]),
                acknowledge_id=self.args[ARG_DELAY_IF][ARG_DELAY_ACKNOWLEDGE_ID]
            )

    def stop_delay(self):
        if self.delay_handle:
            self.cancel_timer(self.delay_handle)

    def stop_timer(self):
        if self.timer_handle:
            self.cancel_timer(self.timer_handle)

    def stop_silence(self):
        if self.silence_handle:
            self.cancel_timer(self.silence_handle)

    def start_timer(self):
        self.log("Starting timer")
        self.stop_delay()
        self.stop_timer()
        self.timer_handle = self.run_in(self.handle_timed_out,
                                        self.timeout * 60,
                                        immediate=True)

    def should_delay(self):
        if self.args.get(ARG_DELAY_IF, None) is None:
            return False

        condition = self.args[ARG_DELAY_IF]
        if condition.get(ARG_DELAY_ATTRIBUTE, None) is None:
            value = self.get_state(condition[ARG_DELAY_ENTITY])
        else:
            value = self.get_state(condition[ARG_DELAY_ENTITY],
                                   attribute=condition[ARG_DELAY_ATTRIBUTE])

        return value == condition[ARG_DELAY_STATE]

    def _notify(self, category, response_entity_id, **kwargs):
        self._notifiers.notify_people(
            category,
            response_entity_id,
            **kwargs
        )
