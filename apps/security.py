import voluptuous as vol

from common.base_app import BaseApp
from common.const import (
    ARG_ENTITY_ID,
    ARG_NOTIFY_CATEGORY,
    ARG_STATE
)
from common.validation import entity_id, ensure_list
from notifiers.notification_category import NotificationCategory, VALID_NOTIFICATION_CATEGORIES

ARG_DOORBELL = 'doorbell'
ARG_PEOPLE = 'people'
ARG_LOCK = 'lock'
ARG_GPS_MAX_ACCURACY = 'gps_max_accuracy'

DEFAULT_ACCURACY = 30


class Doorbell(BaseApp):
    config_schema = vol.Schema({
        vol.Required(ARG_DOORBELL): vol.Schema({
            vol.Required(ARG_ENTITY_ID): entity_id,
            vol.Optional(ARG_STATE, default='on'): str
        }),
        vol.Optional(ARG_NOTIFY_CATEGORY): vol.In(VALID_NOTIFICATION_CATEGORIES)
    }, extra=vol.ALLOW_EXTRA)

    def initialize_app(self):
        doorbell = self.args[ARG_DOORBELL]
        self.listen_state(self._handle_doorbell,
                          entity=doorbell[ARG_ENTITY_ID],
                          new=doorbell[ARG_STATE])

    def _handle_doorbell(self, entity, attribute, old, new, kwargs):
        if old == new:
            return

        self.notifier.notify_people(
            NotificationCategory.PRESENCE_PERSON_DETECTED,
            response_entity_id="lock.front_door",
            location="the front door"
        )


class DoorLock(BaseApp):

    config_schema = vol.Schema({
        vol.Required(ARG_PEOPLE): vol.All(
            ensure_list,
            [entity_id]
        ),
        vol.Optional(ARG_GPS_MAX_ACCURACY, default=DEFAULT_ACCURACY): vol.Range(1, 100),
        vol.Required(ARG_LOCK): entity_id
    }, extra=vol.ALLOW_EXTRA)

    _lock_name = None
    _last_states = {}

    def initialize_app(self):
        self._lock_name = self.get_state(self.args[ARG_LOCK], attribute='friendly_name')
        for person in self.args[ARG_PEOPLE]:
            self._last_states[person] = None
            self.listen_state(self._handle_person_change,
                              entity=person,
                              oneshot=True)

    @property
    def is_locked(self):
        return self.get_state(self.args[ARG_LOCK]) == 'locked'

    def _handle_person_change(self, entity, attribute, old, new, kwargs):
        if old == new or new == self._last_states[entity] or 'unavailable' in [new.lower(),
                                                                               old.lower()]:
            self.listen_state(self._handle_person_change,
                              entity=entity,
                              oneshot=True)
            return

        accuracy = self.get_state(entity, attribute='gps accuracy', default=None)
        if accuracy is not None and accuracy > self.args[ARG_GPS_MAX_ACCURACY]:
            self.log('{} accuracy too high {}'.format(entity, accuracy))
            self.listen_state(self._handle_person_change,
                              entity=entity,
                              oneshot=True)
            return
        self._last_states[entity] = new
        person_name = self.get_state(entity, attribute='friendly_name')
        if new == 'home':
            self._handle_person_arrive(person_name)
        elif old == 'home':
            self._handle_person_left(person_name)

        self.listen_state(self._handle_person_change,
                          entity=entity,
                          oneshot=True)

    def _handle_person_arrive(self, person_name):
        self.log("{} arrived".format(person_name))
        if not self.is_locked:
            self.log("Notify presence")
            self._notify(
                NotificationCategory.PRESENCE_PERSON_ARRIVED,
                response_entity_id=None,
                person_name=person_name)
            return
        self.log('Unlock')
        self.publish(
            'lock',
            'unlock',
            {
                ARG_ENTITY_ID: self.args[ARG_LOCK]
            }
        )
        self.log('Notify unlock')
        self._notify(
            NotificationCategory.SECURITY_UNLOCKED,
            response_entity_id=self.args[ARG_LOCK],
            person_name=person_name)

    def _handle_person_left(self, person_name):
        self.log("{} left".format(person_name))
        if self.is_locked:
            self.log('Notify departed')
            self._notify(
                NotificationCategory.PRESENCE_PERSON_DEPARTED,
                response_entity_id=None,
                person_name=person_name)
            return
        self.log('Lock')
        self.publish(
            'lock',
            'lock',
            {
                ARG_ENTITY_ID: self.args[ARG_LOCK]
            }
        )

        self.log('Notify lock')
        self._notify(
            NotificationCategory.SECURITY_LOCKED,
            response_entity_id=self.args[ARG_LOCK],
            person_name=person_name)

    def _notify(self, category, response_entity_id, person_name):
        self.notifier.notify_people(
            category,
            response_entity_id=response_entity_id,
            person_name=person_name,
            entity_name=self._lock_name)
