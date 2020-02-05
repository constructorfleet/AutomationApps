import appdaemon.plugins.mqtt.mqttapi as mqtt
import json


class TestApp(mqtt.Mqtt):

    def initialize(self):
        self.listen_event(self.handle_event)

    def handle_event(self, event_name, data, kwargs):
        self.log("EVENT_NAME " + event_name)
        self.log("topic " + data.get("topic"))
        self.log("payload " + data.get("payload"))
