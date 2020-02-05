import hassmqttapi as hass_mqtt
import json


class TestApp(hass_mqtt):

    def initialize(self):
         self.listen_event(self.handle_state, event="state_changed")

    def handle_state(self, event_name, data, kwargs):
        self.log("GOT %S WITH %S", event_name, json.dumps(data));