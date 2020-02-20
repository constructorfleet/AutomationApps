import logging
from datetime import datetime

import voluptuous as vol

from common.const import (
    EQUALS,
    NOT_EQUAL,
    LESS_THAN,
    LESS_THAN_EQUAL_TO,
    GREATER_THAN,
    GREATER_THAN_EQUAL_TO,
    ARG_ENTITY_ID,
    ARG_COMPARATOR,
    ARG_VALUE,
    VALID_COMPARATORS,
    ARG_BEFORE, ARG_AFTER, ARG_AT)
from common.validation import (
    entity_id,
    any_value,
    time)

_LOGGER = logging.getLogger(__name__)

SCHEMA_STATE_CONDITION = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_COMPARATOR, default=EQUALS): vol.In(VALID_COMPARATORS),
    vol.Optional(ARG_VALUE, None): any_value
})

SCHEMA_TIME_CONDITION = vol.Schema({
    vol.Optional(ARG_BEFORE, default=None): time,
    vol.Optional(ARG_AFTER, default=None): time,
    vol.Optional(ARG_AT, default=None): time
})

SCHEMA_CONDITION = vol.Any(
    SCHEMA_STATE_CONDITION,
    SCHEMA_TIME_CONDITION
)


class Condition:
    @property
    def is_met(self):
        return True


class StateCondition(Condition):
    _state = None
    _comparator = EQUALS
    _value = None
    _callback = None
    _logger = None

    def __init__(self, initial_state, value, comparator=EQUALS, callback=None, logger=None):
        self._state = initial_state
        self._value = value
        self._comparator = comparator
        self._callback = callback
        self._logger = logger

    def handle_event(self, event_name, data, kwargs):
        if self._logger:
            self._logger(str(data))
            self._logger(str(kwargs))
        if self._callback and self.is_met:
            self._callback(event_name, data, kwargs)

    def handle_state_change(self, entity, attribute, old, new, kwargs):
        self._state = new
        if self._callback and self.is_met:
            self._callback(entity, attribute, old, new, kwargs)

    def handle_value_change(self, entity, attribute, old, new, kwargs):
        self._value = new
        if self._callback and self.is_met:
            self._callback(entity, attribute, old, new, kwargs)

    # noinspection PyTypeChecker
    @property
    def is_met(self):
        if self._value is None:
            return True
        # self._logger("{} {} {}".format(self._state, self._comparator, self._value))
        if self._comparator == EQUALS:
            return self._state == self._value
        elif self._comparator == NOT_EQUAL:
            return self._state != self._value
        else:
            state = float(self._state)
            value = float(self._value)
            if self._comparator == LESS_THAN:
                return state < value
            elif self._comparator == LESS_THAN_EQUAL_TO:
                return state <= value
            elif self._comparator == GREATER_THAN:
                return state > value
            elif self._comparator == GREATER_THAN_EQUAL_TO:
                return state >= value
            else:
                _LOGGER.error('Invalid comparator %s' % self._comparator)
                return False


class TimeCondition(Condition):
    _before = None
    _after = None
    _at = None

    def __init__(self, before=None, after=None, at=None):
        self._before = before
        self._after = after
        self._at = at

    @property
    def is_met(self):
        now = datetime.now().time()
        if self._at:
            hour = now.hour
            minute = now.minute
            return hour == self._at.time().hour and minute == self._at.time().minute

        is_before = True
        if self._before:
            is_before = now < self._before
        is_after = True
        if self._after:
            is_after = now > self._after

        return is_after and is_before
