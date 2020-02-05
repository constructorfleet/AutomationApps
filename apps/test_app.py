import hassmqttapi as hassmqtt
import json


class TestApp(hassmqtt.HassMqtt):

    def initialize(self):
        self.listen_event(self.handle_event,
                          event='test_event')
        self.listen_state(self.handle_state,
                          entity="binary_sensor.bottom_basement_stairs_motion")

    def handle_event(self, event_name, data, kwargs):
        self.log("EVENT_NAME " + event_name)
        self.log("topic " + data.get("topic", "n/a"))
        self.log("payload " + data.get("payload", "n/a"))

    def handle_state(self, entity, attribute, old, new, kwargs):
        self.log("STATE CHANGE " + entity + " " + str(old) + " " + str(new))
