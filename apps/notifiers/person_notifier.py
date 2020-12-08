import sys
import traceback

import voluptuous as vol
from appdaemon import adbase, adapi

from common.validation import ensure_list, email
from notifiers.notification_channel import NotificationChannel

NOTIFIER_IOS = "ios"
NOTIFIER_FCM = "fcm"
NOTIFIER_EMAIL = "email"

ARG_PEOPLE = "people"
ARG_PERSON_NAME = "name"
ARG_EMAIL_ADDRESS = "email_address"
ARG_CHANNELS = "channels"
ARG_TYPE = "type"
ARG_NAME = "name"
ARG_SERVICE = "service"

ARG_VALID_CHANNELS = [member.name for name, member in NotificationChannel.__members__.items()]
ARG_NOTIFIER = "notifier"
ARG_VALID_NOTIFIERS = [
    NOTIFIER_IOS,
    NOTIFIER_FCM,
    NOTIFIER_EMAIL
]

ATTR_IMAGE_URL = "image_url"
ATTR_IMAGE_PATH = "image_path"
ATTR_EXTENSION = "image_ext"

DEFAULT_CHANNELS = ARG_VALID_CHANNELS

SCHEMA_NOTIFIER_BASE = vol.Schema({
    vol.Required(ARG_TYPE): vol.In(ARG_VALID_NOTIFIERS),
    vol.Optional(ARG_CHANNELS, default=ARG_VALID_CHANNELS): vol.All(
        ensure_list,
        [vol.In(ARG_VALID_CHANNELS)]
    )
})

SCHEMA_SERVICE_NOTIFIER = SCHEMA_NOTIFIER_BASE.extend(
    {
        vol.Required(ARG_SERVICE): str
    }
)

SCHEMA_EMAIL_NOTIFIER = SCHEMA_NOTIFIER_BASE.extend(
    {
        vol.Optional(ARG_NAME, default="email"): str
    }
)

SCHEMA_NOTIFIER = vol.Any(
    SCHEMA_SERVICE_NOTIFIER,
    SCHEMA_EMAIL_NOTIFIER
)


def get_arg_schema(args):
    """Retrieve the validation schema."""
    return vol.Schema({
        vol.Required(ARG_PEOPLE): vol.All(
            ensure_list,
            [{
                vol.Required(ARG_PERSON_NAME): str,
                vol.Optional(ARG_EMAIL_ADDRESS): vol.All(vol.Coerce(str), email),
                vol.Required(ARG_NOTIFIER): vol.All(
                    ensure_list,
                    [SCHEMA_NOTIFIER]
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
                    if not notifier.get("app", None):
                        self.log("No app found, skipping")
                        continue

                    if notification_category.channel.name not in notifier.get(ARG_CHANNELS, ARG_VALID_CHANNELS):
                        continue
                    # noinspection PyBroadException
                    try:
                        notifier["app"].notify_person(
                            notification_category,
                            person,
                            notifier.get(ARG_SERVICE, None),
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
        for person_args in self.configs[ARG_PEOPLE]:
            if person_args[ARG_PERSON_NAME] == name:
                return await self._init_person(person_args)
        return None

    async def _init_person(self, args):
        notifiers = []
        for notifier in args[ARG_NOTIFIER]:
            notifier_name = notifier.get(ARG_NAME, notifier[ARG_TYPE]).lower()
            notifiers.append({
                "app": await self.get_app(notifier_name + "_notifier"),
                ARG_SERVICE: notifier.get(ARG_SERVICE, None),
                ARG_CHANNELS: notifier.get(ARG_CHANNELS, ARG_VALID_CHANNELS)
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
