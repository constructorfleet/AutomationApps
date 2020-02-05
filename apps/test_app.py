import voluptuous as vol

import hassmqttapi as hassmqtt
from common.base_app import BaseApp
from common.validation import entity_id

CONF_ENTITY_ID = 'entity_id'


class TestApp(hassmqtt.HassMqtt, BaseApp):
    config_schema = vol.Schema({
        vol.Required(CONF_ENTITY_ID): entity_id
    }, extra=vol.ALLOW_EXTRA)

    def initialize_app(self):
        self.listen_state(self.handle_state,
                          entity=self.args[CONF_ENTITY_ID])

    def handle_state(self, entity, attribute, old, new, kwargs):
        self.log("STATE CHANGE " + entity + " " + str(old) + " " + str(new))
