import voluptuous as vol

from common.base_app import BaseApp
from common.conditions import StateCondition, SCHEMA_STATE_CONDITION
from common.const import ARG_ENTITY_ID, ARG_COMPARATOR, ARG_VALUE

ARG_CONDITION = 'condition'


class TestApp(BaseApp):
    config_schema = vol.Schema({
        vol.Required(ARG_CONDITION): SCHEMA_STATE_CONDITION
    }, extra=vol.ALLOW_EXTRA)

    _condition = None

    def initialize_app(self):
        self._condition = StateCondition(
            self.get_state(self.args[ARG_CONDITION][ARG_ENTITY_ID]),
            self.args[ARG_CONDITION][ARG_COMPARATOR],
            self.args[ARG_CONDITION][ARG_VALUE],
            callback=self._handle_trigger,
            logger=self.log
        )
        self.listen_state(self._condition.handle_state_change,
                          entity=self.args[ARG_CONDITION][ARG_ENTITY_ID])

    def _handle_trigger(self, entity, attribute, old, new, kwargs):
        self.log("TRIGGERED")