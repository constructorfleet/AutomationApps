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
ARG_VEHICLES = 'vehicles'
ARG_LOCK = 'lock'
ARG_COVER = 'cover'
ARG_GPS_MAX_ACCURACY = 'gps_max_accuracy'
ARG_CLASS = "class"
ARG_CONFIDENCE = "confidence"
ARG_CAMERA = 'camera'
ARG_BASE_IMAGE_URL = 'base_image_url'
ARG_NOTIFY_INTERVAL = 'notify_interval'
ARG_ALARM_PANEL = 'alarm_panel'
ARG_NIGHT_MODE_ENTITY = 'night_mode_entity'
ARG_NIGHT_MODE_EVENT = 'night_mode_events'
ARG_NIGHT_MODE_EVENT_ARM = 'arm'
ARG_NIGHT_MODE_EVENT_DISARM = 'disarm'

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
    _image_processor_handle = None
    _pause_handle = None
    _notification_category = None

    def initialize_app(self):
        self._notification_category = get_category_by_name(self.configs[ARG_NOTIFY_CATEGORY])
        doorbell = self.configs[ARG_DOORBELL]
        self.listen_state(self._handle_doorbell,
                          entity=doorbell[ARG_ENTITY_ID],
                          new=doorbell[ARG_STATE])
        if ARG_IMAGE_PROCESSING in self.configs:
            self._start_image_processing(None)

    @property
    def app_schema(self):
        return vol.Schema({
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
            vol.Inclusive(ARG_BASE_IMAGE_URL, 'snapshot'): url,
            vol.Optional(ARG_NOTIFY_CATEGORY,
                         default=NotificationCategory.PRESENCE_PERSON_DETECTED.name): vol.In(
                VALID_NOTIFICATION_CATEGORIES)
        }, extra=vol.ALLOW_EXTRA)

    def _start_image_processing(self, kwargs):
        if self._pause_handle is not None:
            self.cancel_timer(self._pause_handle)

        self._image_processor_handle = self.listen_state(
            self._handle_image_processor,
            entity=self.configs[ARG_IMAGE_PROCESSING][ARG_SENSOR],
            attribute=ATTR_MATCHES,
            oneshot=True)

    def _pause_image_processing(self):
        if self._image_processor_handle is not None:
            self.cancel_listen_state(self._image_processor_handle)
        self._pause_handle = self.run_in(self._start_image_processing,
                                         self.configs[ARG_IMAGE_PROCESSING][
                                             ARG_NOTIFY_INTERVAL] * 60)

    def _handle_image_processor(self, entity, attribute, old, new, kwargs):
        if old == new or self._should_ignore_processor:
            self._start_image_processing(None)
            return

        matches = new.get(self.configs[ARG_IMAGE_PROCESSING][ARG_CLASS], None)
        if matches:
            for match in matches:
                if match.get(ATTR_SCORE, 0.0) >= self.configs[ARG_IMAGE_PROCESSING][ARG_CONFIDENCE]:
                    self._pause_image_processing()
                    self._notify()
                    return
        self._start_image_processing(None)

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
        if ARG_CAMERA not in self.configs:
            return {}

        camera_id = self.configs[ARG_CAMERA]
        file_name = _get_file_name(camera_id)
        file_path = _get_file_path(camera_id, file_name)
        self.publish_service_call(
            DOMAIN_CAMERA,
            SERVICE_SNAPSHOT,
            {
                ARG_ENTITY_ID: camera_id,
                ARG_FILENAME: file_path
            }
        )

        return {
            ATTR_IMAGE_URL: _get_image_url(self.configs[ARG_BASE_IMAGE_URL], file_name),
            ATTR_EXTENSION: "jpg"
        }

    @property
    def _should_ignore_processor(self):
        if ARG_IMAGE_PROCESSING not in self.configs \
                or ARG_CONDITION not in self.configs[ARG_IMAGE_PROCESSING]:
            return False
        for condition in self.configs[ARG_IMAGE_PROCESSING][ARG_CONDITION]:
            if self.condition_met(condition):
                return True
        return False


class Secure(BaseApp):
    _security_entity_name = None
    _last_states = {}

    def initialize_app(self):
        self._security_entity_name = self.get_state(
            self.configs[self._arg_security_entity],
            attribute='friendly_name'
        )
        for entity in self.configs[self._arg_watched_entities]:
            self._last_states[entity] = None
            self.listen_state(self._handle_entity_change,
                              entity=entity,
                              oneshot=True)

    def _handle_entity_change(self, entity, attribute, old, new, kwargs):
        if old == new or new == self._last_states[entity] or \
                'unavailable' in [(new or "").lower(),
                                  (new or "").lower()]:
            self.listen_state(self._handle_entity_change,
                              entity=entity,
                              oneshot=True)
            return

        accuracy = self.get_state(entity, attribute='gps_accuracy', default=None)
        if accuracy is not None and accuracy > self.configs[ARG_GPS_MAX_ACCURACY]:
            self.warning('{} accuracy too high {}'.format(entity, accuracy))
            self.listen_state(self._handle_entity_change,
                              entity=entity,
                              oneshot=True)
            return
        self._last_states[entity] = new
        entity_name = self.get_state(entity, attribute='friendly_name')
        if new in ['Garage Radius', 'home'] and old != 'home':
            self._handle_arrive(entity_name)
        elif old in ['Garage Radius', 'home'] and new == 'not_home':
            self._handle_left(entity_name)

        self.listen_state(self._handle_entity_change,
                          entity=entity,
                          oneshot=True)

    def _handle_arrive(self, entity_name):
        pass

    def _handle_left(self, entity_name):
        pass

    @property
    def _arg_watched_entities(self):
        return None

    @property
    def _arg_security_entity(self):
        return None

    @property
    def is_secured(self):
        return False


class DoorLock(Secure):

    @property
    def app_schema(self):
        return vol.Schema({
            vol.Required(ARG_PEOPLE): vol.All(
                ensure_list,
                [entity_id]
            ),
            vol.Optional(ARG_GPS_MAX_ACCURACY, default=DEFAULT_ACCURACY): vol.Range(1, 100),
            vol.Required(ARG_LOCK): entity_id
        }, extra=vol.ALLOW_EXTRA)

    @property
    def is_secured(self):
        return self.get_state(self.configs[ARG_LOCK]) == 'locked'

    @property
    def _arg_watched_entities(self):
        return ARG_PEOPLE

    @property
    def _arg_security_entity(self):
        return ARG_LOCK

    def _handle_arrive(self, entity_name):
        if not self.is_secured:
            self._notify(
                NotificationCategory.PRESENCE_PERSON_ARRIVED,
                response_entity_id=None,
                person_name=entity_name)
            return
        self.publish_service_call(
            'lock',
            'unlock',
            {
                ARG_ENTITY_ID: self.configs[ARG_LOCK]
            }
        )
        self._notify(
            NotificationCategory.SECURITY_UNLOCKED,
            response_entity_id=self.configs[ARG_LOCK],
            person_name=entity_name)

    def _handle_left(self, entity_name):
        if self.is_secured:
            self._notify(
                NotificationCategory.PRESENCE_PERSON_DEPARTED,
                response_entity_id=None,
                person_name=entity_name)
            return
        self.publish_service_call(
            'lock',
            'lock',
            {
                ARG_ENTITY_ID: self.configs[ARG_LOCK]
            }
        )

        self._notify(
            NotificationCategory.SECURITY_LOCKED,
            response_entity_id=self.configs[ARG_LOCK],
            person_name=entity_name)

    def _notify(self, category, response_entity_id, person_name):
        self.notifier.notify_people(
            category,
            response_entity_id=response_entity_id,
            person_name=person_name,
            entity_name=self._security_entity_name)


class GarageDoor(Secure):

    @property
    def app_schema(self):
        return vol.Schema({
            vol.Required(ARG_VEHICLES): vol.All(
                ensure_list,
                [entity_id]
            ),
            vol.Optional(ARG_GPS_MAX_ACCURACY, default=DEFAULT_ACCURACY): vol.Range(1, 100),
            vol.Required(ARG_COVER): entity_id
        }, extra=vol.ALLOW_EXTRA)

    @property
    def _arg_watched_entities(self):
        return ARG_VEHICLES

    @property
    def _arg_security_entity(self):
        return ARG_COVER

    @property
    def is_secured(self):
        return self.get_state(self.configs[ARG_COVER]) == 'closed'

    def _handle_arrive(self, entity_name):
        if not self.is_secured:
            return
        self.publish_service_call(
            'cover',
            'open_cover',
            {
                ARG_ENTITY_ID: self.configs[ARG_COVER]
            }
        )
        self._notify(
            NotificationCategory.SECURITY_COVER_OPENED,
            response_entity_id=self.configs[ARG_COVER],
            vehicle_name=entity_name)

    def _handle_left(self, entity_name):
        if self.is_secured:
            return

        self.publish_service_call(
            'cover',
            'close_cover',
            {
                ARG_ENTITY_ID: self.configs[ARG_COVER]
            }
        )

        self._notify(
            NotificationCategory.SECURITY_COVER_CLOSED,
            response_entity_id=self.configs[ARG_LOCK],
            vehicle_name=entity_name)

    def _notify(self, category, response_entity_id, vehicle_name):
        self.notifier.notify_people(
            category,
            response_entity_id=response_entity_id,
            vehicle_name=vehicle_name,
            entity_name=self._security_entity_name)


class AlarmSystem(BaseApp):
    people_in_house = []

    @property
    def app_schema(self):
        return vol.Schema({
            vol.Required(ARG_PEOPLE): vol.All(
                ensure_list,
                [entity_id]
            ),
            vol.Required(ARG_LOCK): entity_id,
            vol.Required(ARG_COVER): entity_id,
            vol.Required(ARG_ALARM_PANEL): entity_id,
            vol.Exclusive(ARG_NIGHT_MODE_ENTITY, 'night_mode'): entity_id,
            vol.Exclusive(ARG_NIGHT_MODE_EVENT, 'night_mode'): vol.Schema({
                vol.Required(ARG_NIGHT_MODE_EVENT_ARM): str,
                vol.Required(ARG_NIGHT_MODE_EVENT_DISARM): str
            })
        }, extra=vol.ALLOW_EXTRA)

    def initialize_app(self):
        for person in self.configs[ARG_PEOPLE]:
            if self.get_state(person) == 'home':
                self.people_in_house.append(person)
            self.listen_state(self._handle_presence_change,
                              entity=person)
        self.info('PEOPLE AT HOME %s', str(self.people_in_house))
        alarm_status = str(self.alarm_status)

        if ARG_NIGHT_MODE_ENTITY in self.configs:
            self.listen_state(self._handle_night_mode_change,
                              entity=self.configs[ARG_NIGHT_MODE_ENTITY])
        elif ARG_NIGHT_MODE_EVENT in self.configs:
            self.listen_event(self._handle_night_mode_event,
                              event=self.configs[ARG_NIGHT_MODE_EVENT][ARG_NIGHT_MODE_EVENT_ARM])
            self.listen_event(self._handle_night_mode_event,
                              event=self.configs[ARG_NIGHT_MODE_EVENT][ARG_NIGHT_MODE_EVENT_DISARM])

        if alarm_status.startswith('armed_away') and len(self.people_in_house) > 0:
            self._disarm()
        elif alarm_status.startswith('disarmed') and len(self.people_in_house) == 0:
            self._arm()

    def _handle_night_mode_change(self, entity, attribute, old, new, kwargs):
        alarm_status = str(self.alarm_status)
        if old == new or alarm_status.startswith('armed'):
            return

        if new == 'on' and len(self.people_in_house) > 0:
            self._arm_night_mode()
        elif new == 'off' and len(self.people_in_house) > 0:
            self._disarm()

    def _handle_night_mode_event(self, event, data, kwargs):
        alarm_status = str(self.alarm_status)
        if event == self.configs[ARG_NIGHT_MODE_EVENT][ARG_NIGHT_MODE_EVENT_ARM]:
            if alarm_status.startswith('armed'):
                return
            else:
                self._arm_night_mode()
        if event == self.configs[ARG_NIGHT_MODE_EVENT][ARG_NIGHT_MODE_EVENT_DISARM]:
            if alarm_status.startswith('disarmed'):
                return
            else:
                self._disarm()

    def _handle_presence_change(self, entity, attribute, old, new, kwargs):
        self.info('Presence change %s %s', entity, new)
        if old == new:
            return

        alarm_status = str(self.alarm_status)
        self.info('Current alarm %s', alarm_status)

        if new == 'home':
            self.people_in_house.append(entity)
            if alarm_status.startswith('armed'):
                self._disarm()
        elif entity in self.people_in_house:
            self.people_in_house.remove(entity)
            if alarm_status.startswith('disarmed') and len(self.people_in_house) == 0:
                self._arm()

    @property
    def alarm_status(self):
        return self.get_state(entity_id=self.configs[ARG_ALARM_PANEL])

    def _disarm(self):
        self.publish_service_call(
            'alarm_control_panel',
            'alarm_disarm',
            {
                "entity_id": self.configs[ARG_ALARM_PANEL]
            }
        )
        self.publish_service_call(
            'lock',
            'unlock',
            {
                'entity_id': self.configs[ARG_LOCK]
            }
        )
        self._notify(NotificationCategory.SECURITY_ALARM_DISARMED)

    def _arm(self):
        self.publish_service_call(
            'alarm_control_panel',
            'alarm_arm_away',
            {
                "entity_id": self.configs[ARG_ALARM_PANEL]
            }
        )
        self.publish_service_call(
            'lock',
            'unlock',
            {
                'entity_id': self.configs[ARG_LOCK]
            }
        )
        self.publish_service_call(
            'cover',
            'close_cover',
            {
                'entity_id': self.configs[ARG_COVER]
            }
        )
        self._notify(NotificationCategory.SECURITY_ALARM_ARM_AWAY)

    def _arm_night_mode(self):
        self.publish_service_call(
            'alarm_control_panel',
            'alarm_arm_night',
            {
                "entity_id": self.configs[ARG_ALARM_PANEL]
            }
        )
        self.publish_service_call(
            'lock',
            'unlock',
            {
                'entity_id': self.configs[ARG_LOCK]
            }
        )
        self.publish_service_call(
            'cover',
            'close_cover',
            {
                'entity_id': self.configs[ARG_COVER]
            }
        )
        self._notify(NotificationCategory.SECURITY_ALARM_ARM_HOME)

    def _notify(self, category):
        self.notifier.notify_people(
            category,
            response_entity_id=self.configs[ARG_ALARM_PANEL]
        )
