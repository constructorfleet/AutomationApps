import voluptuous as vol

from common.base_app import BaseApp
from common.validation import entity_id

CONF_ENTITY_ID = 'entity_id'


class TestApp(BaseApp):
    config_schema = vol.Schema({
        vol.Required(CONF_ENTITY_ID): entity_id
    }, extra=vol.ALLOW_EXTRA)

    def initialize_app(self):
        self.listen_state(self.handle_state,
                          entity=self.args[CONF_ENTITY_ID])
        self.log("LISTENING " + self.args[CONF_ENTITY_ID])

    def handle_state(self, entity, attribute, old, new, kwargs):
        self.log("STATE CHANGE " + entity + " " + str(old) + " " + str(new))
        self.publish("lock/lock", entity_id="lock.front_door")
