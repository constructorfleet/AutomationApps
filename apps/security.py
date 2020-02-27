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


class UnlockDoor(BaseApp):

    config_schema = vol.Schema({
        vol.Required(ARG_PEOPLE): vol.All(
            ensure_list,
            [entity_id]
        ),
        vol.Required(ARG_LOCK): entity_id
    }, extra=vol.ALLOW_EXTRA)

    def initialize_app(self):
        for person in self.args[ARG_PEOPLE]:
            self.listen_state(self._handle_person_arrive,
                              entity=person,
                              new='home',
                              oneshot=True)

    @property
    def is_locked(self):
        return self.get_state(self.args[ARG_LOCK]) == 'locked'

    def _handle_person_arrive(self, entity, attribute, old, new, kwargs):
        if old == new:
            self.listen_state(self._handle_person_arrive,
                              entity=entity,
                              new='home',
                              oneshot=True)
            return

        person_name = self.get_state(entity, attribute='friendly_name')
        if not self.is_locked:
            self.notifier.notify_people(
                NotificationCategory.PRESENCE_PERSON_ARRIVED,
                response_entity_id=None,
                **{
                    'person_name': person_name
                  }
            )
            return
        self.publish(
            'lock',
            'unlock',
            {
                ARG_ENTITY_ID: self.args[ARG_LOCK]
            }
        )

        lock_name = self.get_state(self.args[ARG_LOCK], attribute='friendly_name')
        self.notifier.notify_people(
            NotificationCategory.SECURITY_UNLOCKED,
            response_entity_id=self.args[ARG_LOCK],
            person_name=person_name,
            entity_name=lock_name)
