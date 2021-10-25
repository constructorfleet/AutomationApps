import voluptuous as vol
import base64
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
    slugified,
    schema_with_slug_keys
)

ARG_ATTR_CONTAINS = 'attr_contains'
ARG_TRIGGER = 'trigger'
ARG_CONDITION = 'condition'
ARG_CALL_MET = 'call_met'
ARG_CALL_UNMET = 'call_unmet'

SCHEMA_TRIGGER = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_ATTR_CONTAINS, default={}): schema_with_slug_keys(
        vol.All(
            ensure_list,
            [vol.Coerce(str)]
        )
    )
})

SCHEMA_CALL = vol.Schema({
    vol.Required(ARG_DOMAIN): str,
    vol.Required(ARG_SERVICE): str,
    vol.Optional(ARG_SERVICE_DATA, default={}): dict
})


class DecodeBase64CallWhen(BaseApp):
    _last_attributes = {}

    async def initialize_app(self):
        for trigger in self.configs[ARG_TRIGGER]:
            for attribute in trigger[ARG_ATTR_CONTAINS].keys():
                self.debug(f"Listening for all changes to {trigger[ARG_ENTITY_ID]}")
                self._last_attributes[attribute] = ''
                await self.listen_state(self._handle_trigger,
                                        entity=trigger[ARG_ENTITY_ID],
                                        attribute=attribute,
                                        immediate=True)

    @property
    def app_schema(self):
        return vol.Schema({
            vol.Required(ARG_TRIGGER): SCHEMA_TRIGGER,
            vol.Required(ARG_CALL_MET): vol.All(
                ensure_list,
                [SCHEMA_CALL]
            ),
            vol.Required(ARG_CALL_UNMET): vol.All(
                ensure_list,
                [SCHEMA_CALL]
            )
        }, extra=vol.ALLOW_EXTRA)

    async def _handle_trigger(self, entity, attribute, old, new, kwargs):
        if new == old:
            self.debug("No change")
            return
        if attribute == 'body':
            new = base64.b64decode(new)
        self._last_attributes[attribute] = new

        met = await self._check_conditions()
        if not met:
            await self._call(self.args[ARG_CALL_UNMET])
        else:
            await self._call(self.args[ARG_CALL_MET])

    async def _check_conditions(self):
        for attribute, expected_values in self.args[ARG_TRIGGER][ARG_ATTR_CONTAINS].items():
            if not all([value.lower() in self._last_attributes.get(attribute, '').lower()
                        for value
                        in expected_values]):
                return False

        return True

    async def _call(self, services):
        for service in services:
            await self.publish_service_call(service[ARG_DOMAIN], service[ARG_SERVICE], **service[ARG_SERVICE_DATA])
