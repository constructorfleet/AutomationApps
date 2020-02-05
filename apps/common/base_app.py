import voluptuous as vol
import json
import hassmqttapi as hassmqtt

ATTR_EVENT_TYPE = "event_type"
ATTR_EVENT_DATA = "event_data"
ATTR_DOMAIN = "domain"
ATTR_PAYLOAD = "payload"
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
        self.set_namespace('mqtt')
        self.args = self.config_schema(self.args)
        self.initialize_app()

    def initialize_app(self):
        pass

    def publish(self, service, **kwargs):
        domain, svc = _split_service(service)
        return self.mqtt_publish(
            self.get_publish_topic(**kwargs),
            payload=json.dumps({
                ATTR_EVENT_TYPE: EVENT_CALL_SERVICE,
                ATTR_EVENT_DATA: {
                    ATTR_DOMAIN: domain,
                    ATTR_SERVICE: svc,
                    ATTR_SERVICE_DATA: kwargs or {}
                },
                ATTR_SOURCE: self.name
            }),
            qos=0,
            retain=False,
            namespace='mqtt'
        )
