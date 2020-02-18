import sys
import traceback

import voluptuous as vol

from common.base_app import BaseApp
from common.validation import ensure_list, service
from notifiers.notification_channel import NotificationChannel

NOTIFIER_MQTT = "mqtt"
NOTIFIER_IOS = "ios"
NOTIFIER_FCM = "fcm"

ARG_PEOPLE = "people"
ARG_PERSON_NAME = "name"
ARG_CHANNELS = "channels"
ARG_NAME = "name"
ARG_SERVICE = "service"
ARG_VALID_CHANNELS = [member.name for name, member in NotificationChannel.__members__.items()]
ARG_NOTIFIER = "notifier"
ARG_VALID_NOTIFIERS = [
    NOTIFIER_MQTT,
    NOTIFIER_IOS,
    NOTIFIER_FCM
]

ATTR_IMAGE_URL = "image_url"
ATTR_EXTENSION = "image_ext"

DEFAULT_CHANNELS = ARG_VALID_CHANNELS


def get_arg_schema(args):
    """Retrieve the validation schema."""
    return vol.Schema({
        vol.Required(ARG_PEOPLE): vol.All(ensure_list, [{
            vol.Required(ARG_PERSON_NAME): str,
            vol.Required(ARG_NOTIFIER): vol.All(
                ensure_list,
                [vol.Schema({
                    vol.Required(ARG_NAME): vol.In(ARG_VALID_NOTIFIERS),
                    vol.Required(ARG_SERVICE): str
                })]
            ),
            vol.Optional(ARG_CHANNELS, default=DEFAULT_CHANNELS): vol.All(ensure_list,
                                                                          [vol.In(
                                                                              ARG_VALID_CHANNELS)])
        }])
    }, extra=vol.ALLOW_EXTRA)(args)


class PersonNotifier(BaseApp):
    _notifier = None
    _service = None

    def initialize(self):
        self.args = get_arg_schema(self.args)

    def notify_people(self, notification_category, response_entity_id=None, **kwargs):
        for person_args in self.args[ARG_PEOPLE]:
            self.log(
                "Notifying {} on {}".format(person_args[ARG_PERSON_NAME], notification_category))
            self.notify_person(
                person_args[ARG_PERSON_NAME],
                notification_category,
                response_entity_id,
                **kwargs
            )

    def notify_person(self, name, notification_category, response_entity_id=None, **kwargs):
        self.log("Notifying {} on channel {} and category {}".format(
            name,
            notification_category.channel.name,
            notification_category.name)
        )
        person = self._get_person(name)
        if person:
            self.log("Checking {} is in {}".format(notification_category.channel.name,
                                                   str(person.notification_channels)))
            if notification_category.channel.name in person.notification_channels:
                for notifier in person.notifiers:
                    # noinspection PyBroadException
                    try:
                        notifier["app"].notify_person(
                            notification_category,
                            person,
                            notifier[ARG_SERVICE],
                            response_entity_id,
                            **kwargs)
                    except Exception:
                        exc_type, exc_value, exc_traceback = sys.exc_info()
                        lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                        self.log(''.join('!! ' + line for line in lines))
                        continue
                return
        else:
            self.log("Not found {}".format(name))

    def _get_person(self, name):
        return next((self.Person(self, person_args) for person_args in self.args[ARG_PEOPLE] if
                     person_args[ARG_PERSON_NAME] == name), None)

    class Person(object):
        def __init__(self, app, args):
            self.name = args[ARG_PERSON_NAME]
            self.notifiers = []
            for notifer in args[ARG_NOTIFIER]:
                self.notifiers.append({
                    "app": app.get_app(str(notifer[ARG_NAME]).lower() + "_notifier"),
                    ARG_SERVICE: notifer[ARG_SERVICE]
                })
            self.notification_channels = args.get(ARG_CHANNELS, DEFAULT_CHANNELS)
