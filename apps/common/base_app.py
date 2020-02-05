import appdaemon.plugins.mqtt.mqttapi as mqtt

EVENT_MQTT_STATTE = 'MQTT_STATE_EVENT'


class MQTTBase(mqtt.Mqtt):

    _callback_handle = None

    def initialize(self):
        """Initialization of Base App class."""
        self._callback_handle = self.listen_event(
            self._handle_mqtt_event,
            EVENT_MQTT_STATTE
        )

    def _handle_mqtt_event(self, event, data, kwargs):
        """Handle MQTT event received."""
