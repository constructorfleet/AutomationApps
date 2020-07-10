import logging

import voluptuous as vol

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
    ARG_EXISTS
)
from common.validation import (
    entity_id,
    any_value,
    ensure_list,
    slugified
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
