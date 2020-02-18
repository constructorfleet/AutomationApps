import json

import voluptuous as vol

import hassmqttapi as hassmqtt
from common.const import (
    ARG_ENTITY_ID,
    ARG_VALUE,
    ARG_COMPARATOR,
    EQUALS,
    NOT_EQUAL,
    LESS_THAN,
    LESS_THAN_EQUAL_TO,
    GREATER_THAN,
    GREATER_THAN_EQUAL_TO
)
from common.validation import valid_entity_id

ATTR_EVENT_TYPE = "event_type"
ATTR_EVENT_DATA = "event_data"
ATTR_DOMAIN = "domain"
ATTR_PAYLOAD = "payload"
ATTR_SERVICE = "service"
ATTR_SERVICE_DATA = "service_data"
ATTR_SOURCE = "source"
ATTR_TOPIC = "topic"

EVENT_CALL_SERVICE = "call_service"

DEFAULT_PUBLISH_TOPIC = "events/master"


def _split_service(service):
    if '/' in service:
        return service.split('/')
    if '.' in service:
        return service.split('.')
    else:
        raise ValueError("Invalid service %s" % service)


class BaseApp(hassmqtt.HassMqtt):
    config_schema = vol.Schema({}, extra=vol.ALLOW_EXTRA)

    def initialize(self):
        """Initialization of Base App class."""
        # self.set_namespace('mqtt')
        self.args = self.config_schema(self.args)
        self.initialize_app()

    def initialize_app(self):
        pass

    @property
    def publish_topic(self):
        return DEFAULT_PUBLISH_TOPIC

    def publish(self, domain, service, kwargs):
        self.log("Publish Domain %s Service %s" % (domain, service))
        return self.mqtt_publish(
            self.publish_topic,
            payload=json.dumps({
                ATTR_EVENT_TYPE: EVENT_CALL_SERVICE,
                ATTR_EVENT_DATA: {
                    ATTR_DOMAIN: domain,
                    ATTR_SERVICE: service,
                    ATTR_SERVICE_DATA: kwargs or {}
                },
                ATTR_SOURCE: self.name
            }),
            qos=0,
            retain=False,
            namespace='default'
        )

    def condition_met(self, condition):
        # TODO : Other conditions
        return self._state_condition_met(condition)

    def _state_condition_met(self, condition):
        entity_state = self.get_state(condition[ARG_ENTITY_ID])
        value = condition[ARG_VALUE]
        if valid_entity_id(value):
            value = self.get_state(value)

        comparator = condition[ARG_COMPARATOR]
        self.log("{} {} {}".format(entity_state, comparator, value))
        if comparator == EQUALS:
            return entity_state == value
        elif comparator == NOT_EQUAL:
            return entity_state != value
        elif comparator == LESS_THAN:
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
