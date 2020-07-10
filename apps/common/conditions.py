import logging
from datetime import datetime

import voluptuous as vol
from appdaemon import utils

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
from common.utils import converge_types
from common.validation import (
    entity_id,
    any_value,
    ensure_list,
    slugified,
    valid_entity_id
)

_LOGGER = logging.getLogger(__name__)

SCHEMA_STATE_CONDITION = vol.Schema({
    ARG_ENTITY_ID: entity_id,
    vol.Optional(ARG_ATTRIBUTE): vol.All(vol.Coerce(str), slugified),
    vol.Optional(ARG_COMPARATOR, default=EQUALS): vol.In(VALID_COMPARATORS),
    vol.Optional(ARG_VALUE): any_value
}, extra=vol.ALLOW_EXTRA)

SCHEMA_HAS_ATTRIBUTE_CONDITION = vol.Schema({
    ARG_ENTITY_ID: entity_id,
    ARG_ATTRIBUTE: vol.All(vol.Coerce(str), slugified),
    ARG_EXISTS: vol.Coerce(bool)
}, extra=vol.ALLOW_EXTRA)

SCHEMA_TIME_CONDITION = vol.Schema(
    vol.Any(
        vol.Schema({
            ARG_HOUR: vol.All(vol.Coerce(int), vol.Range(0, 23))
        }, extra=vol.ALLOW_EXTRA),
        vol.Schema({
            ARG_MINUTE: vol.All(vol.Coerce(int), vol.Range(0, 59))
        }, extra=vol.ALLOW_EXTRA),
        vol.Schema({
            ARG_SECOND: vol.All(vol.Coerce(int), vol.Range(0, 59))
        }, extra=vol.ALLOW_EXTRA)
    ), extra=vol.ALLOW_EXTRA)

SCHEMA_LOGIC_CONDITION = vol.Schema({
    vol.In([ARG_OR, ARG_AND]): vol.All(
        ensure_list,
        [vol.Any(
            SCHEMA_STATE_CONDITION,
            SCHEMA_TIME_CONDITION,
            SCHEMA_HAS_ATTRIBUTE_CONDITION,
            vol.Self
        )]
    )
}, extra=vol.ALLOW_EXTRA)

SCHEMA_CONDITION = vol.All(
    ensure_list,
    [vol.All(
        vol.Exclusive(SCHEMA_LOGIC_CONDITION, 'cond'),
        vol.Exclusive(SCHEMA_HAS_ATTRIBUTE_CONDITION, 'cond'),
        vol.Exclusive(SCHEMA_STATE_CONDITION, 'cond'),
        vol.Exclusive(SCHEMA_TIME_CONDITION, 'cond'),
    )]
)


@utils.sync_wrapper
async def are_conditions_met(app, condition_spec):
    """Verifies if condition is met."""
    if ARG_AND in condition_spec:
        for condition in condition_spec[ARG_AND]:
            if not are_conditions_met(app, condition):
                app.debug(f'Condition not met: {str(condition)}')
                return False
        return True

    if ARG_OR in condition_spec:
        for condition in condition_spec[ARG_OR]:
            if are_conditions_met(app, condition):
                app.debug(f'Condition met: {str(condition)}')
                return True
        return False

    if len({ARG_HOUR, ARG_MINUTE, ARG_SECOND}.intersection(condition_spec.keys())) > 0:
        now = datetime.utcnow()
        hour = condition_spec.get(ARG_HOUR, now.hour)
        minute = condition_spec.get(ARG_MINUTE, now.minute)
        second = condition_spec.get(ARG_SECOND, now.second)
        return now.hour == hour and now.minute == minute and now.second == second

    if ARG_EXISTS in condition_spec:
        full_state = await app.get_state(entity_id=condition_spec[ARG_ENTITY_ID],
                                         attribute='all')
        return (condition_spec.get(ARG_ATTRIBUTE) in full_state) == condition_spec[ARG_EXISTS]

    if ARG_ENTITY_ID in condition_spec:
        entity_value = await app.get_state(
            entity_id=condition_spec[ARG_ENTITY_ID],
            attribute=condition_spec.get(ARG_ATTRIBUTE))
        app.debug(
            f'Entity {condition_spec[ARG_ENTITY_ID]}[{condition_spec.get(ARG_ATTRIBUTE)}]'
            f' {entity_value}: {str(condition_spec)}')
        if valid_entity_id(condition_spec[ARG_VALUE]):
            check_value = await app.get_state(entity_id=condition_spec[ARG_VALUE])
        else:
            check_value = condition_spec.get(ARG_VALUE)

        app.debug(
            f'Check value {check_value}'
        )

        entity_state, value = converge_types(entity_value, check_value)

        app.debug(
            f'Converged Type {entity_state} {value}'
        )

        comparator = condition_spec.get(ARG_COMPARATOR, EQUALS)
        app.debug(f'Comparator {comparator}')

        if comparator == EQUALS:
            if entity_state is None and value is None:
                return False
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
