import json
import logging
import os
import sys
from threading import Lock

import voluptuous as vol

import hassmqttapi as hassmqtt
from common.const import (
    ARG_ENTITY_ID,
    ARG_VALUE,
    ARG_COMPARATOR,
    ARG_LOG_LEVEL,
    EQUALS,
    NOT_EQUAL,
    LESS_THAN,
    LESS_THAN_EQUAL_TO,
    GREATER_THAN,
    GREATER_THAN_EQUAL_TO,
    ARG_DEPENDENCIES,
)
from common.utils import converge_types
from common.validation import valid_entity_id, valid_log_level

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
ATTR_EVENT_DATA = "event_data"
ATTR_DOMAIN = "domain"
ATTR_PAYLOAD = "payload"
ATTR_SERVICE = "service"
ATTR_SERVICE_DATA = "service_data"
ATTR_SOURCE = "source"
ATTR_TOPIC = "topic"

EVENT_CALL_SERVICE = "call_service"

DEFAULT_PUBLISH_TOPIC = "events/rules"


class BaseApp(hassmqtt.HassMqtt):
    config_schema = vol.Schema({}, extra=vol.ALLOW_EXTRA)
    notifier = None
    holidays = None
    plugin_config = None
    data = {}
    _persistent_data_file = None
    _data_save_handle = None
    _data_lock = Lock()
    _log_level = None

    _base_config_schema = {
        vol.Optional(ARG_LOG_LEVEL, default='ERROR'): valid_log_level
    }

    def initialize(self):
        """Initialization of Base App class."""
        self._persistent_data_file = os.path.join(self.config_dir, self.namespace,
                                                  self.name + ".js")
        self.plugin_config = self.get_plugin_config()

        if isinstance(self.config_schema, dict):
            config_schema = vol.Schema(self.config_schema, extra=vol.ALLOW_EXTRA)
        else:
            config_schema = self.config_schema

        config_schema = config_schema.extend(self._base_config_schema)
        self.args = config_schema(self.args)
        self._log_level = self.args[ARG_LOG_LEVEL]

        if APP_NOTIFIERS in self.args.get(ARG_DEPENDENCIES, []):
            self.notifier = self.get_app(APP_NOTIFIERS)
        if APP_HOLIDAYS in self.args.get(ARG_DEPENDENCIES, []):
            self.holidays = self.get_app(APP_HOLIDAYS)

        if os.path.exists(self._persistent_data_file):
            self.log("Reading storage")
            with open(self._persistent_data_file, 'r') as json_file:
                self.log("Loading json")
                self.data = json.load(json_file)
            self.log("JSON %s" % str(self.data))
            self._on_persistent_data_loaded()

        self.info("Initializing")
        self.initialize_app()
        self.info("Initialized")

    def initialize_app(self):
        pass

    def _on_persistent_data_loaded(self):
        return

    def _prepend_log_msg(self, msg):
        return "{}({}#{}): {}".format(self.name, '__function__', '__line__', msg)

    def record_data(self, key, value):
        with self._data_lock:
            if key not in self.data:
                self.data[key] = None
            self.data[key] = value

            if self._data_save_handle is not None:
                return

            self._data_save_handle = self.run_in(self.save_data, 4)

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

    def condition_met(self, condition):
        # TODO : Other conditions
        if condition is None:
            return
        return self._state_condition_met(condition)

    # noinspection PyTypeChecker
    def _state_condition_met(self, condition):
        if valid_entity_id(condition[ARG_ENTITY_ID]):
            entity_state = self.get_state(condition[ARG_ENTITY_ID])
        else:
            entity_state = condition[ARG_ENTITY_ID]

        value = condition.get(ARG_VALUE, None)
        if value is not None and valid_entity_id(value):
            value = self.get_state(value)
        if value is None or entity_state is None:
            return True
        entity_state, value = converge_types(entity_state, value)

        comparator = condition[ARG_COMPARATOR]
        self.warning(
            "[{}] {}{} {} {}{}".format(condition[ARG_ENTITY_ID], entity_state, type(entity_state),
                                       comparator, value, type(value)))
        if comparator == EQUALS:
            return entity_state == value
        elif comparator == NOT_EQUAL:
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
                self.error('Invalid comparator %s' % comparator)
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
