import voluptuous as vol
from appdaemon import utils

from common.base_app import BaseApp
from common.conditions import SCHEMA_CONDITION
from common.const import (
    ARG_ENTITY_ID,
    ARG_ATTRIBUTE,
    ARG_STATE,
    ARG_DOMAIN,
    ARG_SERVICE,
    ARG_SERVICE_DATA)
from common.validation import (
    entity_id,
    ensure_list,
    any_value,
    slugified
)

ARG_TRIGGER = 'trigger'
ARG_CONDITION = 'condition'
ARG_CALL = 'call'
ARG_TRANSFORM = 'transform'

SCHEMA_TRIGGER = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_ATTRIBUTE): slugified,
    vol.Optional(ARG_STATE): any_value
})

SCHEMA_CALL = vol.Schema({
    vol.Required(ARG_DOMAIN): str,
    vol.Required(ARG_SERVICE): str,
    vol.Optional(ARG_SERVICE_DATA, default={}): dict,
    vol.Optional(ARG_TRANSFORM): str
})


class CallWhen(BaseApp):

    async def initialize_app(self):
        for trigger in self.configs[ARG_TRIGGER]:
            if ARG_STATE not in trigger \
                    and trigger[ARG_ENTITY_ID].split('.')[0].lower() in ['binary_sensor', 'switch',
                                                                         'light']:
                trigger[ARG_STATE] = 'on'  # Default to on for these domains

            new_state = await self.get_state(
                entity_id=trigger[ARG_ENTITY_ID],
                attribute=trigger.get(ARG_ATTRIBUTE))
            self.debug(f"Trigger state: {new_state}")
            if ARG_STATE not in trigger or new_state == trigger[ARG_STATE]:
                await self._handle_trigger(
                    trigger[ARG_ENTITY_ID],
                    trigger.get(ARG_ATTRIBUTE),
                    None,
                    new_state,
                    {}
                )
            if ARG_STATE not in trigger:
                self.debug(f"Listening for all changes to {trigger[ARG_ENTITY_ID]}")
                await self.listen_state(self._handle_trigger,
                                        entity=trigger[ARG_ENTITY_ID],
                                        attribute=trigger.get(ARG_ATTRIBUTE),
                                        immediate=True)
            else:
                self.debug(f"Listening for {trigger[ARG_STATE]} on {trigger[ARG_ENTITY_ID]}")
                await self.listen_state(self._handle_trigger,
                                        entity=trigger[ARG_ENTITY_ID],
                                        attribute=trigger.get(ARG_ATTRIBUTE),
                                        new=trigger[ARG_STATE],
                                        immediate=True)

    @property
    def app_schema(self):
        return vol.Schema({
            vol.Required(ARG_TRIGGER): vol.All(
                ensure_list,
                [SCHEMA_TRIGGER]
            ),
            vol.Optional(ARG_CONDITION, default=[]): SCHEMA_CONDITION,
            vol.Required(ARG_CALL): vol.All(
                ensure_list,
                [SCHEMA_CALL]
            )
        }, extra=vol.ALLOW_EXTRA)

    @property
    async def conditions_met(self):
        for condition in self.configs[ARG_CONDITION]:
            if not await self.condition_met(condition):
                return False

        return True

    async def _handle_trigger(self, entity, attribute, old, new, kwargs):
        if new == old:
            return
        if not await self.conditions_met:
            self.debug("Conditions not met")
            return

        events = self.configs[ARG_CALL]
        for event in events:
            try:
                data = {}
                for key, value in event[ARG_SERVICE_DATA].items():
                    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                        entity_id = value.replace("{", "").replace("}", "").replace(" ", "")
                        self.debug(f"Getting state for {entity_id}")
                        value = int(await self.get_state(entity_id=entity_id))

                    transform = event.get(ARG_TRANSFORM)
                    if transform is not None:
                        fn = lambda k, v: eval(k, v)
                        value = fn(key, value)
                    data[key] = value
                self.debug(f"Calling {event[ARG_DOMAIN]}.{event[ARG_SERVICE]} with {str(data)}")
                self.publish_service_call(event[ARG_DOMAIN], event[ARG_SERVICE],
                                          data)
            except Exception:
                self.error("Unexpected error calling service.")
