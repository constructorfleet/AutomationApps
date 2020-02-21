import voluptuous as vol

from common.base_app import BaseApp
from common.conditions import condition, state_schema
from common.const import ARG_ENTITY_ID, ARG_COMPARATOR, ARG_VALUE

ARG_CONDITION = 'condition'


class TestApp(BaseApp):
    config_schema = None

    def __init__(self, ad, name, logging, args, config, app_config, global_vars):
        super().__init__(ad, name, logging, args, config, app_config, global_vars)
        self.config_schema = vol.Schema({
            vol.Required(ARG_CONDITION): state_schema(self, self._handle_trigger, self.log)
        }, extra=vol.ALLOW_EXTRA)

    def initialize_app(self):
        self.listen_event(self.args[ARG_CONDITION].handle_event,
                          event='state_changed',
                          entity=self.args[ARG_CONDITION][ARG_ENTITY_ID],
                          wildcard='states/#')

    def _handle_trigger(self, entity, attribute, old, new, kwargs):
        if new == old:
            return
        self.log("TRIGGERED {} {} {} {}".format(entity, attribute, old, new, str(kwargs)))
