import json
import os
import abc
import logging
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


def _split_service(service):
    if '/' in service:
        return service.split('/')
    if '.' in service:
        return service.split('.')
    else:
        raise ValueError("Invalid service %s" % service)


class SaneLoggingApp(object):

    def _setup_logging(self, app_class_name, log_level=logging.ERROR):
        self._app_class_name = app_class_name
        self._log = LogWrapper(self.get_main_log(), log_level)
        formatter = logging.Formatter(
            fmt="[%(levelname)s %(filename)s:%(lineno)s - "
                "%(name)s.%(funcName)s() ] %(message)s"
        )
        self.get_main_log().handlers[0].setFormatter(formatter)
        self.set_log_level(log_level)

    def set_log_level(self, level):
        self._log.set_log_level(level)

    def debug(self, msg, *args, **kwargs):
        self._log.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._log.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._log.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._log.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self._log.critical(msg, *args, **kwargs)

    def log(self, msg, *args, **kwargs):
        self._log.log(msg, *args, **kwargs)


class LogWrapper:
    """
    Thanks to https://stackoverflow.com/a/22091220/211734
    """
    _log_level = logging.ERROR

    def __init__(self, logger, log_level=logging.ERROR):
        self.logger = logger
        self.set_log_level(log_level)

    def set_log_level(self, log_level):
        self._log_level = log_level
        self.logger.handlers[0].setLevel(log_level)

    def debug(self, msg, *args, **kwargs):
        if self.logger.isEnabledFor(logging.DEBUG):
            self._log(logging.DEBUG, msg, args, **kwargs)

    def info(self, msg, *args, **kwargs):
        if self.logger.isEnabledFor(logging.INFO):
            self._log(logging.INFO, msg, args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        if self.logger.isEnabledFor(logging.WARNING):
            self._log(logging.WARNING, msg, args, **kwargs)

    def error(self, msg, *args, **kwargs):
        if self.logger.isEnabledFor(logging.ERROR):
            self._log(logging.ERROR, msg, args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        if self.logger.isEnabledFor(logging.CRITICAL):
            self._log(logging.CRITICAL, msg, args, **kwargs)

    def log(self, msg, *args, **kwargs):
        """
        Log 'msg % args' with the integer severity 'level'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.log(level, "We have a %s", "mysterious problem", exc_info=1)
        """
        level = self._log_level
        if not isinstance(level, int):
            if logging.raiseExceptions:
                raise TypeError("level must be an integer")
            else:
                return
        if self.logger.isEnabledFor(level):
            self._log(level, msg, args, **kwargs)

    def _log(self, level, msg, args, exc_info=None, extra=None):
        """
        Low-level logging routine which creates a LogRecord and then calls
        all the handlers of this logger to handle the record.
        """
        # Add wrapping functionality here.
        if _srcfile:
            # IronPython doesn't track Python frames, so findCaller throws an
            # exception on some versions of IronPython. We trap it here so that
            # IronPython can use logging.
            try:
                fn, lno, func = self._find_caller()
            except ValueError:
                fn, lno, func = "(unknown file)", 0, "(unknown function)"
        else:
            fn, lno, func = "(unknown file)", 0, "(unknown function)"
        if exc_info:
            if not isinstance(exc_info, tuple):
                exc_info = sys.exc_info()
        record = self.logger.makeRecord(
            self.logger.name, level, fn, lno, msg, args, exc_info, func, extra)
        self.logger.handle(record)

    def _find_caller(self):
        """
        Find the stack frame of the caller so that we can note the source
        file name, line number and function name.
        """
        f = logging.currentframe()
        # On some versions of IronPython, currentframe() returns None if
        # IronPython isn't run with -X:Frames.
        if f is not None:
            f = f.f_back
        rv = "(unknown file)", 0, "(unknown function)"
        while hasattr(f, "f_code"):
            co = f.f_code
            filename = os.path.normcase(co.co_filename)
            if filename == _srcfile:
                f = f.f_back
                continue
            rv = (co.co_filename, f.f_lineno, co.co_name)
            break
        return rv


class BaseApp(hassmqtt.HassMqtt, SaneLoggingApp):
    config_schema = vol.Schema({}, extra=vol.ALLOW_EXTRA)
    notifier = None
    holidays = None
    plugin_config = None
    data = {}
    _persistent_data_file = None
    _data_save_handle = None
    _data_lock = Lock()
    _min_log_level = None

    _base_config_schema = {
        vol.Optional(ARG_LOG_LEVEL, default='ERROR'): valid_log_level
    }

    def initialize(self):
        """Initialization of Base App class."""
        self._persistent_data_file = os.path.join(self.config_dir, self.namespace, self.name + ".js")
        self.plugin_config = self.get_plugin_config()

        if isinstance(self.config_schema, dict):
            self.log("Wrapping dict with Schema")
            self.config_schema = vol.Schema(self.config_schema, extra=vol.ALLOW_EXTRA)

        self.config_schema = self.config_schema.extend(self._base_config_schema)
        self.args = self.config_schema(self.args)

        self._setup_logging(self.__class__.__name__, self.args[ARG_LOG_LEVEL])

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

        self.initialize_app()

    def initialize_app(self):
        pass

    def _on_persistent_data_loaded(self):
        return

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
        self.log("Saving %s" % str(self.data))
        with self._data_lock:
            with open(self._persistent_data_file, 'w') as json_file:
                json.dump(self.data, json_file)
            self._data_save_handle = None

    @property
    def publish_topic(self):
        return DEFAULT_PUBLISH_TOPIC

    def publish_service_call(self, domain, service, kwargs):
        self.log("Publish Domain %s Service %s with args %s" % (domain, service, str(kwargs)))
        return self.publish_event(
            EVENT_CALL_SERVICE,
            {
                ATTR_DOMAIN: domain,
                ATTR_SERVICE: service,
                ATTR_SERVICE_DATA: kwargs or {}
            }
        )

    def publish_event(self, event, event_data, qos=0, retain=False, namespace='default'):
        self.log("Publish Event %s Data %s " % (event, str(event_data)))
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
        self.log(
            "{}{} {} {}{}".format(entity_state, type(entity_state), comparator, value, type(value)))
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
                self.log('Invalid comparator %s' % comparator)
                return False

    def __del__(self):
        """Handle application death."""

