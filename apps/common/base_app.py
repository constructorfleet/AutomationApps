import json

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
    LogLevel,
    VALID_LOG_LEVELS
)
from common.utils import converge_types
from common.validation import valid_entity_id

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


class BaseApp(hassmqtt.HassMqtt):
    _base_config_schema = vol.Schema({
        vol.Optional(ARG_LOG_LEVEL, default=LogLevel): vol.In(VALID_LOG_LEVELS)
    }, extra=vol.ALLOW_EXTRA)
    config_schema = vol.Schema({}, extra=vol.ALLOW_EXTRA)
    notifier = None
    holidays = None
    plugin_config = None

    def initialize(self):
        """Initialization of Base App class."""
        self.plugin_config = self.get_plugin_config()

        self.config_schema.extend(self._base_config_schema)

        if APP_NOTIFIERS in self.args.get(ARG_DEPENDENCIES, []):
            self.notifier = self.get_app(APP_NOTIFIERS)
        if APP_HOLIDAYS in self.args.get(ARG_DEPENDENCIES, []):
            self.holidays = self.get_app(APP_HOLIDAYS)

        self.args = self.config_schema(self.args)
        self.set_log_level(self.args[ARG_LOG_LEVEL])
        self.initialize_app()

    def initialize_app(self):
        pass

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
