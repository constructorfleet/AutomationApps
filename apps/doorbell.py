import datetime
from builtins import int
from time import sleep

import voluptuous as vol

from common.const import (
    ARG_DOMAIN,
    ARG_ENTITY_ID,
    ARG_NOTIFY_CATEGORY,
    ARG_STATE,
    ARG_SERVICE,
    ARG_SERVICE_DATA
)
from common.base_app import BaseApp
from common.utils import minutes_to_seconds
from common.validation import entity_id, ensure_list, service
from notifiers.notification_category import NotificationCategory, VALID_NOTIFICATION_CATEGORIES

ARG_DOORBELL = 'doorbell'


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

