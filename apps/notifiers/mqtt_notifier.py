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
        "id": NotificationChannel.SECURITY.name,
        "name": str(NotificationChannel.SECURITY).title(),
        "visibility": PRIVATE,
        "description": "Security event notifications",
        "importance": "HIGH"
    },
    NotificationChannel.PRESENCE: {
        "id": NotificationChannel.PRESENCE.name,
        "name": str(NotificationChannel.PRESENCE).title(),
        "visibility": PUBLIC,
        "description": "Presence detection notifications",
        "importance": MID_IMPORTANCE
    },
    NotificationChannel.TRAINING: {
        "id": NotificationChannel.TRAINING.name,
        "name": str(NotificationChannel.TRAINING).title(),
        "visibility": PRIVATE,
        "description": "Reinforcement training",
        "importance": LOW_IMPORTANCE
    },
    NotificationChannel.WARNING: {
        "id": NotificationChannel.WARNING.name,
        "name": str(NotificationChannel.WARNING).title(),
        "visibility": PUBLIC,
        "description": "Warning messages",
        "importance": MID_IMPORTANCE
    },
}


def _build_payload(category, response_entity_id, **kwargs):
    payload = {
        "channel": CHANNEL_PAYLOADS[category.channel],
        "title": str(category.channel.name).title(),
        "body": KWArgFormatter().format(str(category.body), **kwargs),
        "imageUrl": kwargs.get(ATTR_IMAGE_URL, None),
        "actions":
            list(map((lambda action:
                      {
                          "text": action.text,
                          "topic": TOPIC_ACTION,
                          "payload": {
                              "actionName": str(action),
                              "action_data": {
                                  "category": str(category),
                                  "entity_id": response_entity_id or ""
                              }
                          }
                      }
                      ),
                     category.actions))
    }
    for action in payload['actions']:
        for key, value in kwargs.items():
            if key == ATTR_IMAGE_URL:
                continue
            action['payload']['action_data'][key] = value
        action['payload'] = json.dumps(action['payload'])


def _build_topic(person):
    return TOPIC_FORMAT.format(person.name)


class MqttNotifier(hass.Hass):

    def initialize(self):
        self.log("Initialized")

    def notify_person(self, notification_category, person, service, response_entity_id, **kwargs):
        if notification_category.channel.name in person.notification_channels:
            self.log("Notifying {}".format(person.name))
            extra_args = {}

            for key, value in kwargs.items():
                extra_args[key] = value

            payload = json.dumps(
                _build_payload(notification_category, response_entity_id,
                               **extra_args)).replace('"', '\"')

            self.log("Notifying {} on channel {} with args {} service {} payload {}".format(
                person.name,
                notification_category.channel.name,
                str(extra_args),
                service,
                payload
            ))
            self.call_service(
                service,
                topic=TOPIC_FORMAT.format(str(person.name).lower()),
                payload=payload,
                qos=0,
                retain=False
            )
