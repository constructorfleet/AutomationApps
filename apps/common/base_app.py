import json
import logging
import os
import sys
from datetime import datetime
from threading import Lock

import voluptuous as vol
from appdaemon import utils

import hassmqttapi as hassmqtt
from common.const import (
    ARG_LOG_LEVEL,
    ARG_DEPENDENCIES,
    ARG_AND,
    ARG_OR,
    ARG_HOUR,
    ARG_MINUTE,
    ARG_SECOND,
    ARG_EXISTS,
    ARG_ENTITY_ID,
    ARG_ATTRIBUTE,
    ARG_VALUE,
    ARG_COMPARATOR,
    EQUALS,
    NOT_EQUAL,
    LESS_THAN,
    LESS_THAN_EQUAL_TO,
    GREATER_THAN,
    GREATER_THAN_EQUAL_TO
)
from common.listen_handle import ListenHandle, TimerHandle, StateListenHandle, EventListenHandle
from common.utils import converge_types
from common.validation import valid_log_level, valid_entity_id

# _srcfile is used when walking the stack to check when we've got the first
# caller stack frame.
#
if hasattr(sys, 'frozen'):  # support for py2exe
    _srcfile = "logging%s__init__%s" % (os.sep, __file__[-4:])
elif __file__[-4:].lower() in ['.pyc', '.pyo']:
    _srcfile = __file__[:-4] + '.py'
else:
    _srcfile = __file__
_srcfile = os.path.normcase(_srcfile)

APP_NOTIFIERS = "notifiers"
APP_HOLIDAYS = "holidays"

ATTR_EVENT_TYPE = "event_type"
ATTR_EVENT_DATA = "data"
ATTR_DOMAIN = "domain"
ATTR_PAYLOAD = "payload"
ATTR_SERVICE = "service"
ATTR_SERVICE_DATA = "service_data"
ATTR_SOURCE = "source"
ATTR_TOPIC = "topic"

EVENT_CALL_SERVICE = "call_service"

DEFAULT_PUBLISH_TOPIC = "events/rules"


class BaseApp(hassmqtt.HassMqtt):
    notifier = None
    holidays = None
    plugin_config = None
    data = {}
    configs = {}
    _persistent_data_file = None
    _data_save_handle = None
    _data_lock = Lock()
    _log_level = None

    _base_config_schema = {
        vol.Optional(ARG_LOG_LEVEL, default='ERROR'): valid_log_level
    }

    @utils.sync_wrapper
    async def initialize(self):
        """Initialization of Base App class."""
        self._persistent_data_file = os.path.join(self.config_dir, self.namespace,
                                                  self.name + ".js")
        self.plugin_config = self.get_plugin_config()

        if isinstance(self.app_schema, dict):
            config_schema = vol.Schema(self.app_schema, extra=vol.ALLOW_EXTRA)
        else:
            config_schema = self.app_schema

        config_schema = config_schema.extend(self._base_config_schema)
        self.configs = config_schema(self.args)
        self._log_level = self.configs[ARG_LOG_LEVEL]

        self.log('Dependencies: %s', str(self.configs.get(ARG_DEPENDENCIES, [])))
        if APP_NOTIFIERS in self.configs.get(ARG_DEPENDENCIES, []):
            self.log('Getting reference to notifiers app')
            self.notifier = await self.get_app(APP_NOTIFIERS)
        if APP_HOLIDAYS in self.configs.get(ARG_DEPENDENCIES, []):
            self.log('Getting reference to holidays app')
            self.holidays = await self.get_app(APP_HOLIDAYS)

        if os.path.exists(self._persistent_data_file):
            self.log("Reading storage")
            with open(self._persistent_data_file, 'r') as json_file:
                self.log("Loading json")
                self.data = json.load(json_file)
            self.log("JSON %s" % str(self.data))
            self._on_persistent_data_loaded()

        self.info("Initializing")
        await self.initialize_app()
        self.info("Initialized")

    @utils.sync_wrapper
    async def initialize_app(self):
        pass

    @utils.sync_wrapper
    async def run_in(self, callback, delay, **kwargs):
        handle = await super().run_in(callback, delay, **kwargs)
        return TimerHandle(handle, self)

    @utils.sync_wrapper
    async def run_every(self, callback, start, interval, **kwargs):
        handle = await super().run_every(callback, start, interval, **kwargs)
        return TimerHandle(handle, self)

    @utils.sync_wrapper
    async def run_at(self, callback, start, **kwargs):
        handle = await super().run_at(callback, start, **kwargs)
        return TimerHandle(handle, self)

    @utils.sync_wrapper
    async def run_at_sunset(self, callback, **kwargs):
        handle = await super().run_at_sunset(callback, **kwargs)
        return TimerHandle(handle, self)

    @utils.sync_wrapper
    async def run_at_sunrise(self, callback, **kwargs):
        handle = await super().run_at_sunrise(callback, **kwargs)
        return TimerHandle(handle, self)

    @utils.sync_wrapper
    async def run_once(self, callback, start, **kwargs):
        handle = await super().run_once(callback, start, **kwargs)
        return TimerHandle(handle, self)

    @utils.sync_wrapper
    async def run_daily(self, callback, start, **kwargs):
        handle = await super().run_daily(callback, start, **kwargs)
        return TimerHandle(handle, self)

    @utils.sync_wrapper
    async def run_hourly(self, callback, start, **kwargs):
        handle = await super().run_hourly(callback, start, **kwargs)
        return TimerHandle(handle, self)

    @utils.sync_wrapper
    async def run_minutely(self, callback, start, **kwargs):
        handle = await super().run_minutely(callback, start, **kwargs)
        return TimerHandle(handle, self)

    @utils.sync_wrapper
    async def listen_state(self, callback, entity=None, **kwargs):
        if entity is None:
            raise ValueError(f'Listen state called with no entity')
        handle = await super().listen_state(callback, entity, **kwargs)
        return StateListenHandle(handle, self)

    @utils.sync_wrapper
    async def listen_event(self, callback, event=None, **kwargs):
        if event is None:
            raise ValueError(f'Listen event called with no event')
        handle = await super().listen_event(callback, event, **kwargs)
        return EventListenHandle(handle, self)

    @utils.sync_wrapper
    async def cancel_timer(self, handle):
        if isinstance(handle, ListenHandle):
            return await handle.cancel()
        return await super().cancel_timer(handle)

    @utils.sync_wrapper
    async def cancel_listen_event(self, handle):
        if isinstance(handle, ListenHandle):
            return await handle.cancel()
        return await super().cancel_listen_event(handle)

    @utils.sync_wrapper
    async def cancel_listen_state(self, handle):
        if handle is None:
            return
        if isinstance(handle, ListenHandle):
            return await handle.cancel()
        return await super().cancel_listen_state(handle)

    def _on_persistent_data_loaded(self):
        return

    def _prepend_log_msg(self, msg):
        return "{}({}#{}): {}".format(self.name, '__function__', '__line__', msg)

    @utils.sync_wrapper
    async def record_data(self, key, value):
        with self._data_lock:
            if key not in self.data:
                self.data[key] = None
            self.data[key] = value

            if self._data_save_handle is not None:
                return

            self._data_save_handle = await self.run_in(self.save_data, 4)

    def clear_data(self):
        with self._data_lock:
            os.makedirs(
                os.path.join(self.config_dir, self.namespace),
                exist_ok=True)
            if os.path.exists(self._persistent_data_file):
                os.remove(self._persistent_data_file)
            self.data = {}

    def save_data(self, kwargs):
        self.debug("Saving %s" % str(self.data))
        with self._data_lock:
            with open(self._persistent_data_file, 'w') as json_file:
                json.dump(self.data, json_file)
            self._data_save_handle = None

    @property
    def app_schema(self):
        return vol.Schema({}, extra=vol.ALLOW_EXTRA)

    @property
    def publish_topic(self):
        return DEFAULT_PUBLISH_TOPIC

    def publish_service_call(self, domain, service, kwargs):
        self.debug("Publish Domain %s Service %s with args %s" % (domain, service, str(kwargs)))
        return self.publish_event(
            EVENT_CALL_SERVICE,
            {
                ATTR_DOMAIN: domain,
                ATTR_SERVICE: service,
                ATTR_SERVICE_DATA: kwargs or {}
            }
        )

    def publish_event(self, event, event_data, qos=0, retain=False, namespace='default'):
        self.debug("Publish Event %s Data %s " % (event, str(event_data)))
        return self.mqtt_publish(
            self.publish_topic,
            payload=json.dumps({
                ATTR_EVENT_TYPE: event,
                ATTR_EVENT_DATA: event_data,
                ATTR_SOURCE: self.name
            }),
            qos=qos,
            retain=retain,
            namespace=namespace
        )

    @utils.sync_wrapper
    async def condition_met(self, condition_spec):
        """Verifies if condition is met."""
        if ARG_AND in condition_spec:
            for condition in condition_spec[ARG_AND]:
                if not await self.condition_met(condition):
                    self.debug(f'Condition not met: {str(condition)}')
                    return False
            return True

        if ARG_OR in condition_spec:
            for condition in condition_spec[ARG_OR]:
                if await self.condition_met(condition):
                    self.debug(f'Condition met: {str(condition)}')
                    return True
            return False

        if len({ARG_HOUR, ARG_MINUTE, ARG_SECOND}.intersection(condition_spec.keys())) > 0:
            now = datetime.utcnow()
            hour = condition_spec.get(ARG_HOUR, now.hour)
            minute = condition_spec.get(ARG_MINUTE, now.minute)
            second = condition_spec.get(ARG_SECOND, now.second)
            return now.hour == hour and now.minute == minute and now.second == second

        if ARG_EXISTS in condition_spec:
            full_state = await self.get_state(entity_id=condition_spec[ARG_ENTITY_ID],
                                              attribute='all')
            return (condition_spec.get(ARG_ATTRIBUTE) in full_state) == condition_spec[ARG_EXISTS]

        if ARG_ENTITY_ID in condition_spec:
            entity_value = await self.get_state(
                entity_id=condition_spec[ARG_ENTITY_ID],
                attribute=condition_spec.get(ARG_ATTRIBUTE))
            self.debug(
                f'Entity {condition_spec[ARG_ENTITY_ID]}[{condition_spec.get(ARG_ATTRIBUTE)}]'
                f' {entity_value}: {str(condition_spec)}')
            if valid_entity_id(condition_spec[ARG_VALUE]):
                check_value = await self.get_state(entity_id=condition_spec[ARG_VALUE])
            else:
                check_value = condition_spec.get(ARG_VALUE)

            self.debug(f'Check value {check_value}')

            entity_state, value = converge_types(entity_value, check_value)

            self.debug(f'Converged Type {entity_state} {value}')

            comparator = condition_spec.get(ARG_COMPARATOR, EQUALS)
            self.debug(f'Comparator {comparator}')

            if comparator == EQUALS:
                if entity_state is None and value is None:
                    return False
                return entity_state == value
            elif comparator == NOT_EQUAL:
                if entity_state is None and value is None:
                    return False
                return entity_state != value
            else:
                if comparator == LESS_THAN:
                    return entity_state < value
                elif comparator == LESS_THAN_EQUAL_TO:
                    return entity_state <= value
                elif comparator == GREATER_THAN:
                    return entity_state > value
                elif comparator == GREATER_THAN_EQUAL_TO:
                    return entity_state >= value
                else:
                    return False

    def debug(self, msg, *args, **kwargs):
        if self._log_level >= logging.DEBUG:
            self.log(self._prepend_log_msg(msg),
                     *args,
                     level=logging.getLevelName(logging.DEBUG), **kwargs)

    def info(self, msg, *args, **kwargs):
        if self._log_level >= logging.INFO:
            self.log(self._prepend_log_msg(msg),
                     *args,
                     level=logging.getLevelName(logging.INFO), **kwargs)

    def warning(self, msg, *args, **kwargs):
        if self._log_level >= logging.WARNING:
            self.log(self._prepend_log_msg(msg),
                     *args,
                     level=logging.getLevelName(logging.WARNING), **kwargs)

    def error(self, msg, *args, **kwargs):
        if self._log_level >= logging.ERROR:
            self.log(self._prepend_log_msg(msg),
                     *args,
                     level=logging.getLevelName(logging.ERROR), **kwargs)

    def critical(self, msg, *args, **kwargs):
        if self._log_level >= logging.CRITICAL:
            self.log(self._prepend_log_msg(msg),
                     *args,
                     level=logging.getLevelName(logging.CRITICAL), **kwargs)
