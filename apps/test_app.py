import hassmqttapi as hassmqtt
import json


class TestApp(hassmqtt.HassMqtt):

    def initialize(self):
        self.listen_event(self.handle_event)

    def handle_event(self, event_name, data, kwargs):
        self.log("EVENT_NAME " + event_name)
        self.log("topic " + data.get("topic", "n/a"))
        self.log("payload " + data.get("payload", "n/a"))
