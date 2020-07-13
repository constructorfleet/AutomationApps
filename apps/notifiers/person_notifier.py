import sys
import traceback

import voluptuous as vol
from appdaemon import adbase, adapi

from common.validation import ensure_list
from notifiers.notification_channel import NotificationChannel

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
    NOTIFIER_IOS,
    NOTIFIER_FCM
]

ATTR_IMAGE_URL = "image_url"
ATTR_EXTENSION = "image_ext"

DEFAULT_CHANNELS = ARG_VALID_CHANNELS


def get_arg_schema(args):
    """Retrieve the validation schema."""
    return vol.Schema({
        vol.Required(ARG_PEOPLE): vol.All(
            ensure_list,
            [{
                vol.Required(ARG_PERSON_NAME): str,
                vol.Required(ARG_NOTIFIER): vol.All(
                    ensure_list,
                    [vol.Schema({
                        vol.Required(ARG_NAME): vol.In(ARG_VALID_NOTIFIERS),
                        vol.Required(ARG_SERVICE): str
                    })]
                ),
                vol.Optional(ARG_CHANNELS, default=DEFAULT_CHANNELS):
                    vol.All(ensure_list,
                            [vol.In(
                                ARG_VALID_CHANNELS)])
            }]
        )
    }, extra=vol.ALLOW_EXTRA)(args)


class PersonNotifier(adbase.ADBase, adapi.ADAPI):
    async def initialize(self):
        self._notifier = None
        self._service = None
        self.configs = get_arg_schema(self.args)

    async def notify_people(self, notification_category, response_entity_id=None, **kwargs):
        for person_args in self.configs.get(ARG_PEOPLE, []):
            self.log(
                "Notifying {} on {}".format(person_args[ARG_PERSON_NAME], notification_category))
            await self.notify_person(
                person_args[ARG_PERSON_NAME],
                notification_category,
                response_entity_id,
                **kwargs
            )

    async def notify_person(self, name, notification_category, response_entity_id=None, **kwargs):
        self.log("Notifying {} on channel {} and category {}".format(
            name,
            notification_category.channel.name,
            notification_category.name)
        )
        person = await self._get_person(name)
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
                        self.error(''.join('!! ' + line for line in lines))
                        continue
                return
        else:
            self.log("Not found {}".format(name))

    async def _get_person(self, name):
        for person_args in  self.configs[ARG_PEOPLE]:
            if person_args[ARG_PERSON_NAME] == name:
                return await self._init_person(person_args)
        return None

    async def _init_person(self, args):
        notifiers = []
        for notifier in args[ARG_NOTIFIER]:
            notifiers.append({
                "app": await self.get_app(str(notifier[ARG_NAME]).lower() + "_notifier"),
                ARG_SERVICE: notifier[ARG_SERVICE]
            })
        return self.Person(
            args[ARG_PERSON_NAME],
            notifiers,
            args.get(ARG_CHANNELS, DEFAULT_CHANNELS))

    class Person(object):
        def __init__(self, name, notifiers, channels):
            self.name = name
            self.notifiers = notifiers
            self.notification_channels = channels
