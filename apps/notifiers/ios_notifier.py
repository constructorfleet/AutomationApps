import os.path

from appdaemon import utils

from common.base_app import (BaseApp)
from common.utils import KWArgFormatter
from common.const import DOMAIN_NOTIFY
from notifiers.person_notifier import ATTR_IMAGE_URL, ATTR_EXTENSION

ARG_SERVICE = "service"


class iOSNotifier(BaseApp):

    async def initialize_app(self):
        return

    @property
    def service(self):
        return ""

    async def notify_person(self, notification_category, person, service, response_entity_id, **kwargs):
        critical = notification_category.critical
        if notification_category.channel.name in person.notification_channels:
            service_data = {
                "title": str(notification_category.channel.name).title(),
                "message": self.kw_formatter.format(str(notification_category.body), **kwargs),
                "data": {
                    "push": {
                        "category": str(notification_category),
                        "thread-id": str(notification_category),
                        "sound": {
                            "name": "default",
                            "critical": 1 if critical else 0,
                            "volume": 1.0 if critical else 0.0
                        }
                    },
                    "presentation_options": ['alert', 'sound'] if critical else ['alert'],
                    "action_data": {
                        "entity_id": response_entity_id or "",
                        "category": str(notification_category)
                    }
                }
            }
            if ATTR_IMAGE_URL in kwargs:
                image_url = kwargs[ATTR_IMAGE_URL]
                content_type = kwargs.get(ATTR_EXTENSION, os.path.splitext(image_url)[1][1:])
                service_data["data"]["attachment"] = {
                    "url": image_url,
                    "content-type": content_type
                }
            for key, value in kwargs.items():
                if key == ATTR_IMAGE_URL:
                    continue
                if 'action_data' in service_data['data']:
                    service_data['data']['action_data'][key] = value

            self.log("Invoking service {} with {}".format(service, service_data))
            self.call_service(
                "notify/{0}".format(service),
                **service_data
            )
