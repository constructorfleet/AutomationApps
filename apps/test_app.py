import voluptuous as vol
from appdaemon.plugins.mqtt.mqttapi import Mqtt

from common.base_app import BaseApp
from common.conditions import StateCondition, SCHEMA_STATE_CONDITION
from common.const import ARG_ENTITY_ID, ARG_COMPARATOR, ARG_VALUE

ARG_CONDITION = 'condition'


class MqttTestApp(Mqtt):
    config_schema = vol.Schema({
        vol.Required(ARG_CONDITION): SCHEMA_STATE_CONDITION
    }, extra=vol.ALLOW_EXTRA)

    _condition = None

    def initialize(self):
        self.args = self.config_schema(self.args)
        self._condition = StateCondition(
            self.get_state(self.args[ARG_CONDITION][ARG_ENTITY_ID]),
            self.args[ARG_CONDITION][ARG_VALUE],
            self.args[ARG_CONDITION][ARG_COMPARATOR],
            callback=self._handle_trigger,
            logger=self.log
        )

        self.listen_event(
            self._condition.handle_event,
            entity_id=self.args[ARG_CONDITION][ARG_ENTITY_ID],
            new_state={'state': 'on'},
            wildcard="states/#"
        )

    def _handle_trigger(self, event_name, data, kwargs):
        self.logger("{} {} {}".format(event_name, data, str(kwargs)))
        self.logger("TRIGGERED {}".format(str(kwargs)))


class TestApp(BaseApp):
    config_schema = vol.Schema({
        vol.Required(ARG_CONDITION): SCHEMA_STATE_CONDITION
    }, extra=vol.ALLOW_EXTRA)

    _condition = None

    def initialize_app(self):
        self._condition = StateCondition(
            self.get_state(self.args[ARG_CONDITION][ARG_ENTITY_ID]),
            self.args[ARG_CONDITION][ARG_VALUE],
            self.args[ARG_CONDITION][ARG_COMPARATOR],
            callback=self._handle_trigger,
            logger=self.log
        )
        self.listen_event(self._condition.handle_event,
                          event='state_changed',
                          entity=self.args[ARG_CONDITION][ARG_ENTITY_ID],
                          wildcard='states/#')

    def _handle_trigger(self, entity, attribute, old, new, kwargs):
        if new == old:
            return
        self.log("TRIGGERED {} {} {} {}".format(entity, attribute,old, new, str(kwargs)))