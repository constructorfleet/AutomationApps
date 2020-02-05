import hassmqttapi as hassmqtt
from common.base_app import BaseApp
from common.validation import entity_id
import voluptuous as vol

CONF_ENTITY_ID = 'entity_id'


class TestApp(hassmqtt.HassMqtt, BaseApp):

    config_schema = super(BaseApp).config_schema.extend({
        vol.Required(CONF_ENTITY_ID): entity_id
    })

    def initialize_app(self):
        self.listen_state(self.handle_state,
                          entity=self.args[CONF_ENTITY_ID])

    def handle_state(self, entity, attribute, old, new, kwargs):
        self.log("STATE CHANGE " + entity + " " + str(old) + " " + str(new))
