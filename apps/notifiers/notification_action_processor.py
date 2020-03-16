from common.base_app import BaseApp
from notifiers.notification_action import NotificationAction

ACTION = "action"
ACTION_NAME = "actionName"
ACTION_DATA = "action_data"
CATEGORY = "category"
ENTITY_ID = "entity_id"
ACKNOWLEDGE_ID = "acknowledge_id"


class NotificationActionProcessor(BaseApp):
    acknowledge_listeners = []

    def initialize_app(self):
        self.log("Initializing")

        self.log("Starting listener for iOS")
        self.listen_event(self.handle_event,
                          event="ios.notification_action_fired")

        self.listen_event(self.handle_event,
                          event="mobile_app_notification_action")

        self.log("Starting listener for FCM")
        self.listen_event(self.handle_event,
                          event="html5_notification.clicked")

    def add_acknowledge_listener(self, listener):
        self.acknowledge_listeners.append(listener)

    def handle_event(self, event_name, data, kwargs):
        self.log("Event Data {} and kwargs {}".format(str(data), str(kwargs)))
        self.log("ACTION NAME {} ".format(data.get(ACTION_NAME, data.get(ACTION, "")).lower()))
        for name, member in NotificationAction.__members__.items():
            self.log("NAME {} VALUE {}".format(name, member))
        found_action = [member for name, member in NotificationAction.__members__.items() if
                        name.lower().replace('_', '') == data.get(ACTION_NAME,
                                                                  data.get(ACTION, "")).lower()]
        if not found_action:
            self.log("No action found for {}".format(str(data)))
            return

        action = found_action[0]
        if not action.service:
            acknowledge_id = data["data"][ACTION_DATA][ACKNOWLEDGE_ID] \
                if event_name == "html5_notification.clicked" \
                else data[ACTION_DATA][ACKNOWLEDGE_ID]
            if not acknowledge_id:
                return
            for listener in self.acknowledge_listeners:
                listener(acknowledge_id, action)
            return

        entity_id = data["data"][ACTION_DATA][ENTITY_ID] \
            if event_name == "html5_notification.clicked" \
            else data[ACTION_DATA][ENTITY_ID]

        if not action or not entity_id:
            self.log("Not enough data")
            return

        self.publish_service_call(
            action.service.split('/')[0],
            action.service.split('/')[1],
            {
                ENTITY_ID: entity_id
            }
        )
