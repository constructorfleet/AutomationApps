import os

import voluptuous as vol

from call_when import ARG_CONDITION
from common.base_app import BaseApp
from common.const import (
    ARG_ENTITY_ID,
    ARG_NOTIFY_CATEGORY,
    ARG_STATE,
    ARG_SENSOR,
    ARG_COMPARATOR, EQUALS, VALID_COMPARATORS, ARG_VALUE, ATTR_SCORE, DOMAIN_CAMERA,
    SERVICE_SNAPSHOT, ARG_FILENAME)
from common.validation import entity_id, ensure_list, any_value, url
from notifiers.notification_category import (
    NotificationCategory,
    VALID_NOTIFICATION_CATEGORIES,
    get_category_by_name
)
from notifiers.person_notifier import ATTR_IMAGE_URL, ATTR_EXTENSION

ARG_DOORBELL = 'doorbell'
ARG_IMAGE_PROCESSING = 'image_processing'
ARG_PEOPLE = 'people'
ARG_LOCK = 'lock'
ARG_GPS_MAX_ACCURACY = 'gps_max_accuracy'
ARG_CLASS = "class"
ARG_CONFIDENCE = "confidence"
ARG_CAMERA = 'camera'
ARG_IMAGE_URL = 'image_url'
ARG_NOTIFY_INTERVAL = 'notify_interval'

SCHEMA_CONDITION_STATE = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_COMPARATOR, default=EQUALS): vol.In(VALID_COMPARATORS),
    vol.Required(ARG_VALUE): any_value
})

# SCHEMA_CONDITION_TIME = vol.Schema({
#     vol.Exclusive(ARG_BEFORE, 'time_condition'): time,
#     vol.Exclusive(ARG_AFTER, 'time_condition'): time
# })

SCHEMA_CONDITION = vol.Any(SCHEMA_CONDITION_STATE)  # , SCHEMA_CONDITION_TIME)

DEFAULT_ACCURACY = 30
DEFAULT_CONFIDENCE = 70
DEFAULT_NOTIFY_INTERVAL = 2
DEFAULT_CLASS = 'person'

REPLACER_CAMERA = "{CAM}"

FILE_NAME_TEMPLATE = "{}_snapshot.jpg".format(REPLACER_CAMERA)
FILE_PATH = "/config/www/camera_snapshot/"

ATTR_MATCHES = 'matches'


def _get_image_url(url_base, file_name):
    return os.path.join(url_base, file_name)


def _get_file_name(camera):
    return FILE_NAME_TEMPLATE \
        .replace(REPLACER_CAMERA, camera)


def _get_file_path(camera, file_name=None):
    file_name = _get_file_name(camera) if file_name is None else file_name
    return os.path.join(FILE_PATH, file_name)


class Doorbell(BaseApp):
    config_schema = vol.Schema({
        vol.Required(ARG_DOORBELL): vol.Schema({
            vol.Required(ARG_ENTITY_ID): entity_id,
            vol.Optional(ARG_STATE, default='on'): str
        }),
        vol.Optional(ARG_IMAGE_PROCESSING): vol.Schema({
            vol.Required(ARG_SENSOR): entity_id,
            vol.Optional(ARG_CONFIDENCE, default=DEFAULT_CONFIDENCE): vol.Coerce(int),
            vol.Optional(ARG_CLASS, default=DEFAULT_CLASS): vol.All(vol.Coerce(str), vol.Lower),
            vol.Optional(ARG_CONDITION): vol.All(
                ensure_list,
                [SCHEMA_CONDITION]),
            vol.Optional(ARG_NOTIFY_INTERVAL, default=DEFAULT_NOTIFY_INTERVAL): vol.All(
                vol.Coerce(int),
                vol.Range(1, 10)
            )
        }),
        vol.Inclusive(ARG_CAMERA, 'snapshot'): entity_id,
        vol.Inclusive(ARG_IMAGE_URL, 'snapshot'): url,
        vol.Optional(ARG_NOTIFY_CATEGORY,
                     default=NotificationCategory.PRESENCE_PERSON_DETECTED.name): vol.In(
            VALID_NOTIFICATION_CATEGORIES)
    }, extra=vol.ALLOW_EXTRA)

    _image_processor_handle = None
    _pause_handle = None
    _notification_category = None

    def initialize_app(self):
        self._notification_category = get_category_by_name(self.args[ARG_NOTIFY_CATEGORY])
        doorbell = self.args[ARG_DOORBELL]
        self.listen_state(self._handle_doorbell,
                          entity=doorbell[ARG_ENTITY_ID],
                          new=doorbell[ARG_STATE])
        if ARG_IMAGE_PROCESSING in self.args:
            self._start_image_processing(None)

    def _start_image_processing(self, kwargs):
        if self._pause_handle is not None:
            self.cancel_timer(self._pause_handle)

        self._image_processor_handle = self.listen_state(
            self._handle_image_processor,
            entity=self.args[ARG_IMAGE_PROCESSING][ARG_SENSOR],
            attribute=ATTR_MATCHES)

    def _pause_image_processing(self):
        if self._image_processor_handle is not None:
            self.cancel_listen_state(self._image_processor_handle)
        self._pause_handle = self.run_in(self._start_image_processing,
                                         self.args[ARG_IMAGE_PROCESSING][ARG_NOTIFY_INTERVAL] * 60)

    def _handle_image_processor(self, entity, attribute, old, new, kwargs):
        if old == new or self._should_ignore_processor:
            return

        matches = new.get(self.args[ARG_IMAGE_PROCESSING][ARG_CLASS], None)
        if not matches:
            return

        for match in matches:
            if match.get(ATTR_SCORE, 0.0) >= self.args[ARG_IMAGE_PROCESSING][ARG_CONFIDENCE]:
                'Got a match'
                self._pause_image_processing()
                self._notify()
                return

    def _handle_doorbell(self, entity, attribute, old, new, kwargs):
        if old == new:
            return

        self._notify()

    def _notify(self):
        self.notifier.notify_people(
            self._notification_category,
            response_entity_id="lock.front_door",
            location="the front door",
            **self._get_notify_args()
        )

    def _get_notify_args(self):
        if ARG_CAMERA not in self.args:
            self.log('No camera specified')
            return {}

        camera_id = self.args[ARG_CAMERA]
        self.log('Camera %s' % camera_id)
        file_name = _get_file_name(camera_id)
        self.log('Filename %s' % file_name)
        file_path = _get_file_path(camera_id, file_name)
        self.log('Filepath %s' % file_path)
        self.publish(
            DOMAIN_CAMERA,
            SERVICE_SNAPSHOT,
            {
                ARG_ENTITY_ID: camera_id,
                ARG_FILENAME: file_path
            }
        )

        return {
            ATTR_IMAGE_URL: _get_image_url(self.args[ARG_IMAGE_URL], file_name),
            ATTR_EXTENSION: "jpg"
        }

    @property
    def _should_ignore_processor(self):
        if ARG_IMAGE_PROCESSING not in self.args \
                or ARG_CONDITION not in self.args[ARG_IMAGE_PROCESSING]:
            return False
        for condition in self.args[ARG_IMAGE_PROCESSING][ARG_CONDITION]:
            if self.condition_met(condition):
                return True
        return False


class DoorLock(BaseApp):
    config_schema = vol.Schema({
        vol.Required(ARG_PEOPLE): vol.All(
            ensure_list,
            [entity_id]
        ),
        vol.Optional(ARG_GPS_MAX_ACCURACY, default=DEFAULT_ACCURACY): vol.Range(1, 100),
        vol.Required(ARG_LOCK): entity_id
    }, extra=vol.ALLOW_EXTRA)

    _lock_name = None
    _last_states = {}

    def initialize_app(self):
        self._lock_name = self.get_state(self.args[ARG_LOCK], attribute='friendly_name')
        for person in self.args[ARG_PEOPLE]:
            self._last_states[person] = None
            self.listen_state(self._handle_person_change,
                              entity=person,
                              oneshot=True)

    @property
    def is_locked(self):
        return self.get_state(self.args[ARG_LOCK]) == 'locked'

    def _handle_person_change(self, entity, attribute, old, new, kwargs):
        if old == new or new == self._last_states[entity] or 'unavailable' in [new.lower(),
                                                                               old.lower()]:
            self.listen_state(self._handle_person_change,
                              entity=entity,
                              oneshot=True)
            return

        accuracy = self.get_state(entity, attribute='gps accuracy', default=None)
        if accuracy is not None and accuracy > self.args[ARG_GPS_MAX_ACCURACY]:
            self.log('{} accuracy too high {}'.format(entity, accuracy))
            self.listen_state(self._handle_person_change,
                              entity=entity,
                              oneshot=True)
            return
        self._last_states[entity] = new
        person_name = self.get_state(entity, attribute='friendly_name')
        if new == 'home':
            self._handle_person_arrive(person_name)
        elif old == 'home':
            self._handle_person_left(person_name)

        self.listen_state(self._handle_person_change,
                          entity=entity,
                          oneshot=True)

    def _handle_person_arrive(self, person_name):
        self.log("{} arrived".format(person_name))
        if not self.is_locked:
            self.log("Notify presence")
            self._notify(
                NotificationCategory.PRESENCE_PERSON_ARRIVED,
                response_entity_id=None,
                person_name=person_name)
            return
        self.log('Unlock')
        self.publish(
            'lock',
            'unlock',
            {
                ARG_ENTITY_ID: self.args[ARG_LOCK]
            }
        )
        self.log('Notify unlock')
        self._notify(
            NotificationCategory.SECURITY_UNLOCKED,
            response_entity_id=self.args[ARG_LOCK],
            person_name=person_name)

    def _handle_person_left(self, person_name):
        self.log("{} left".format(person_name))
        if self.is_locked:
            self.log('Notify departed')
            self._notify(
                NotificationCategory.PRESENCE_PERSON_DEPARTED,
                response_entity_id=None,
                person_name=person_name)
            return
        self.log('Lock')
        self.publish(
            'lock',
            'lock',
            {
                ARG_ENTITY_ID: self.args[ARG_LOCK]
            }
        )

        self.log('Notify lock')
        self._notify(
            NotificationCategory.SECURITY_LOCKED,
            response_entity_id=self.args[ARG_LOCK],
            person_name=person_name)

    def _notify(self, category, response_entity_id, person_name):
        self.notifier.notify_people(
            category,
            response_entity_id=response_entity_id,
            person_name=person_name,
            entity_name=self._lock_name)
