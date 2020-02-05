import hassmqttapi as hassmqtt

import voluptuous as vol

ATTR_EVENT_TYPE = "event_type"
ATTR_EVENT_DATA = "event_data"
ATTR_DOMAIN = "domain"
ATTR_SERVICE = "service"
ATTR_SERVICE_DATA = "service_data"
ATTR_SOURCE = "source"
ATTR_TOPIC = "topic"

EVENT_CALL_SERVICE = "call_service"


def _split_service(service):
    if '.' in service:
        return service.split('.')
    elif '/' in service:
        return service.split('/')
    else:
        raise ValueError("Invalid service %s" % service)


class BaseApp(hassmqtt.HassMqtt):

    config_schema = vol.Schema({}, extra=vol.ALLOW_EXTRA)

    def initialize(self):
        """Initialization of Base App class."""
        self.args = self.config_schema(self.args)
        self.initialize_app()

    def initialize_app(self):
        pass

    def call_service(self, service, **kwargs):
        domain, svc = _split_service(service)
        event_data = {
            ATTR_EVENT_TYPE: EVENT_CALL_SERVICE,
            ATTR_EVENT_DATA: {
                ATTR_DOMAIN: domain,
                ATTR_SERVICE: svc,
                ATTR_SERVICE_DATA: kwargs or {}
            },
            ATTR_SOURCE: self.name
        }
        return self.mqtt_publish(
            self.get_publish_topic(**kwargs),
            event_data
        )



