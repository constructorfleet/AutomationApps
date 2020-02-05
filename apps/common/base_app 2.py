import appdaemon.plugins.mqtt.mqttapi as mqtt

import voluptuous as vol

ATTR_MQTT_TOPIC = 'topic'
ATTR_MQTT_PAYLOAD = 'payload'


class BaseApp(mqtt.Mqtt):
    config_schema = vol.Schema(
        {},
        extra=vol.ALLOW_EXTRA
    )

    def initialize(self):
        """Initialization of Base App class."""
        self.args = self.config_schema(self.args)
        self.listen_event
        self.initialize_app()

    def initialize_app(self):
        """Initialize application."""
        pass

    def _on_mqtt_message(self, event_name, data, kwargs):
        """Handle MQTT Message."""
        if not event_name or not data:
            return

