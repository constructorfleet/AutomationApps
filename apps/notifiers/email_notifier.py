from os.path import exists, isfile
import imghdr

import voluptuous as vol
from appdaemon import utils

from common.base_app import (BaseApp)
import common.validation as validate
from common.const import DOMAIN_NOTIFY
from common.utils import (KWArgFormatter,
                          send_email)
from notifiers.person_notifier import ARG_EMAIL_ADDRESS, ATTR_IMAGE_PATH, ATTR_EXTENSION

ARG_NAME = "name"
ARG_USERNAME = "username"
ARG_PASSWORD = "password"
ARG_CC = "cc"
ARG_BCC = "bcc"


class EmailNotifier(BaseApp):

    async def initialize_app(self):
        self._username = self.configs[ARG_USERNAME]
        self._password = self.configs[ARG_PASSWORD]
        self._cc = self.configs.get(ARG_CC, None)
        self._bcc = self.configs.get(ARG_BCC, None)

    @property
    def app_schema(self):
        return vol.Schema({
            vol.Optional(ARG_NAME, default='email'): str,
            vol.Required(ARG_USERNAME): validate.email,
            vol.Required(ARG_PASSWORD): str,
            vol.Optional(ARG_CC, default=[]): vol.All(
                validate.ensure_list,
                [validate.email]
            ),
            vol.Optional(ARG_BCC, default=[]): vol.All(
                validate.ensure_list,
                [validate.email]
            ),
        }, extra=vol.ALLOW_EXTRA)

    @property
    def service(self):
        return ""

    async def notify_person(self, notification_category, person, service, response_entity_id, **kwargs):
        to = person.email
        if not to:
            self.error("No email address for {0}".format(person[ARG_NAME]))
        if notification_category.channel.name not in person.notification_channels:
            return
        critical = notification_category.critical
        subject = str(notification_category.channel.name).title()
        content = KWArgFormatter().format(str(notification_category.body), **kwargs)
        image_path = kwargs.get(ATTR_IMAGE_PATH, None)
        img_data = None
        if image_path and exists(image_path) and isfile(image_path):
            with open(kwargs[ATTR_IMAGE_PATH], 'rb') as fp:
                img_data = fp.read()

        for to in person.email:
            self.log("Sending email {0} to {1}".format(subject, to))
            await send_email(
                to=to,
                subject=subject,
                content=content,
                important=critical,
                attach_img=img_data,
                username=self.configs[ARG_USERNAME],
                password=self.configs[ARG_PASSWORD],
            )
