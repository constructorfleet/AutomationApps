import json

import appdaemon.plugins.hass.hassapi as hass

from notifiers.notification_channel import NotificationChannel
from notifiers.person_notifier import ATTR_IMAGE_URL
from common.utils import KWArgFormatter

TOPIC_FORMAT = "/notify/{}"
TOPIC_ACTION = "/service/call"

PRIVATE = "PRIVATE"
PUBLIC = "PUBLIC"
HIGH_IMPORTANCE = "HIGH"
MID_IMPORTANCE = "MID"
LOW_IMPORTANCE = "LOW"

CHANNEL_PAYLOADS = {
    NotificationChannel.SECURITY: {
        "title": str(NotificationChannel.SECURITY).title(),
        "priority": "high",
        "silent": False
    },
    NotificationChannel.PRESENCE: {
        "title": str(NotificationChannel.PRESENCE).title(),
        "priority": "normal",
        "silent": False
    },
    NotificationChannel.TRAINING: {
        "title": str(NotificationChannel.TRAINING).title(),
        "priority": "normal",
        "silent": True
    },
    NotificationChannel.WARNING: {
        "title": str(NotificationChannel.WARNING).title(),
        "priority": "high",
        "silent": False
    }
}


def _build_payload(
        category,
        target,
        response_entity_id,
        **kwargs
):
    payload = {
        "title": str(category.channel.name).title(),
        "message": KWArgFormatter().format(str(category.body), **kwargs),
        "target": target,
        "data": {
            "image": kwargs.get(ATTR_IMAGE_URL, None),
            "priority":
                category.importance_override if category.importance_override is not None else
                CHANNEL_PAYLOADS[category.channel].get("priority", "normal"),
            "silent": CHANNEL_PAYLOADS[category.channel].get("silent", False),
            "action_data": {
                "category": str(category),
                "entity_id": response_entity_id or ""
            },
            "actions":
                list(map((lambda action:
                          {
                              "action": str(action),
                              "title": action.text
                          }
                          ), category.actions))
        }
    }

    for key, value in kwargs.items():
        if key == ATTR_IMAGE_URL:
            continue
        payload['data']['action_data'][key] = value

    return payload


class FcmNotifier(hass.Hass):

    def initialize(self):
        self.log("Initialized")

    def notify_person(self, notification_category, person, service, response_entity_id, **kwargs):
        if notification_category.channel.name in person.notification_channels:
            self.log("Notifying {}".format(person.name))
            extra_args = {}

            for key, value in kwargs.items():
                extra_args[key] = value

            payload = _build_payload(notification_category,
                                     str(person.name).lower(),
                                     response_entity_id,
                                     **extra_args)

            self.log("Notifying {} on channel {} with args {} service {} payload {}".format(
                person.name,
                notification_category.channel.name,
                str(extra_args),
                service,
                json.dumps(payload)
            ))
            self.call_service(
                service,
                **payload
            )
