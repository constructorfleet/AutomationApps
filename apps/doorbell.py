import datetime
from builtins import int
from time import sleep

import voluptuous as vol

from common.const import (
    ARG_DOMAIN,
    ARG_ENTITY_ID,
    ARG_SERVICE,
    ARG_SERVICE_DATA
)
from common.base_app import BaseApp
from common.utils import minutes_to_seconds
from common.validation import entity_id, ensure_list, service
from notifiers.notification_category import NotificationCategory


class Doorbell(BaseApp):

    def initialize_app(self):
        kwargs = {}
        self.get_app("notifiers").notify_people(
            NotificationCategory.PRESENCE_PERSON_DETECTED,
            response_entity_id="group.all_locks",
            location="the front door",
            **kwargs
        )
