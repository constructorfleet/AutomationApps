import logging

import voluptuous as vol
from datetime import datetime

from common.const import (
    EQUALS,
    ARG_ENTITY_ID,
    ARG_COMPARATOR,
    ARG_VALUE,
    VALID_COMPARATORS,
    ARG_HOUR,
    ARG_MINUTE,
    ARG_SECOND,
    ARG_AND,
    ARG_OR,
    ARG_ATTRIBUTE,
    ARG_EXISTS,
    NOT_EQUAL,
    LESS_THAN,
    LESS_THAN_EQUAL_TO,
    GREATER_THAN,
    GREATER_THAN_EQUAL_TO
)
from common.validation import (
    entity_id,
    any_value,
    ensure_list,
    slugified,
    valid_entity_id
)
from common.utils import converge_types

_LOGGER = logging.getLogger(__name__)

SCHEMA_STATE_CONDITION = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_ATTRIBUTE): slugified,
    vol.Optional(ARG_COMPARATOR, default=EQUALS): vol.In(VALID_COMPARATORS),
    vol.Optional(ARG_VALUE): any_value
})

SCHEMA_HAS_ATTRIBUTE_CONDITION = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Required(ARG_ATTRIBUTE): slugified,
    vol.Required(ARG_EXISTS): vol.Coerce(bool)
})

SCHEMA_TIME_CONDITION = vol.Schema({
    vol.Required(
        vol.Any(
            vol.Schema({
                vol.Required(ARG_HOUR): vol.All(vol.Coerce(int), vol.Range(0, 23))
            }, extra=vol.ALLOW_EXTRA),
            vol.Schema({
                vol.Required(ARG_MINUTE): vol.All(vol.Coerce(int), vol.Range(0, 59))
            }, extra=vol.ALLOW_EXTRA),
            vol.Schema({
                vol.Required(ARG_SECOND): vol.All(vol.Coerce(int), vol.Range(0, 59))
            }, extra=vol.ALLOW_EXTRA)
        )
    )
})

SCHEMA_LOGIC_CONDITION = vol.Schema({
    vol.Required(vol.Any(ARG_OR, ARG_AND)): vol.All(
        ensure_list,
        [vol.Any(
            SCHEMA_STATE_CONDITION,
            SCHEMA_TIME_CONDITION,
            SCHEMA_HAS_ATTRIBUTE_CONDITION,
            vol.Self
        )]
    )
})

SCHEMA_CONDITION = vol.All(
    ensure_list,
    [vol.Any(
        SCHEMA_LOGIC_CONDITION,
        SCHEMA_HAS_ATTRIBUTE_CONDITION,
        SCHEMA_TIME_CONDITION,
        SCHEMA_TIME_CONDITION
    )]
)


def are_conditions_met(app, condition_schema):
    """Verifies if condition is met."""
    if ARG_AND in condition_schema:
        for condition in condition_schema:
            if not are_conditions_met(app, condition):
                return False
        return True

    if ARG_OR in condition_schema:
        for condition in condition_schema:
            if are_conditions_met(app, condition):
                return True
        return False

    if len({ARG_HOUR, ARG_MINUTE, ARG_SECOND}.intersection(condition_schema.keys())) > 0:
        now = datetime.utcnow()
        hour = condition_schema.get(ARG_HOUR, now.hour)
        minute = condition_schema.get(ARG_MINUTE, now.minute)
        second = condition_schema.get(ARG_SECOND, now.second)
        return now.hour == hour and now.minute == minute and now.second == second

    if ARG_EXISTS in condition_schema:
        full_state = app.get_state(entity_id=condition_schema[ARG_ENTITY_ID],
                                   attribute='all')
        return condition_schema[ARG_ATTRIBUTE] in full_state == condition_schema[ARG_EXISTS]

    if ARG_ENTITY_ID in condition_schema:
        entity_value = app.get_state(entity_id=condition_schema[ARG_ENTITY_ID],
                                     attribute=condition_schema[ARG_ATTRIBUTE])
        if valid_entity_id(condition_schema[ARG_VALUE]):
            check_value = app.get_state(entity_id=condition_schema[ARG_VALUE])
        else:
            check_value = condition_schema.get(ARG_VALUE)

        entity_state, value = converge_types(entity_value, check_value)

        comparator = condition_schema[ARG_COMPARATOR]

        if comparator == EQUALS:
            if entity_state is None and value is None:
                return True
            return entity_state == value
        elif comparator == NOT_EQUAL:
            if entity_state is None and value is None:
                return False
            return entity_state != value
        else:
            if comparator == LESS_THAN:
                return entity_state < value
            elif comparator == LESS_THAN_EQUAL_TO:
                return entity_state <= value
            elif comparator == GREATER_THAN:
                return entity_state > value
            elif comparator == GREATER_THAN_EQUAL_TO:
                return entity_state >= value
            else:
                return False
