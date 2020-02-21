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
    time, valid_entity_id)

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


def _convert_to_state_condition(
        app,
        condition_args,
        callback=None,
        logger=None):
    value = condition_args[ARG_VALUE]
    if isinstance(value, str) and valid_entity_id(value):
        value = app.get_state(value)
    return StateCondition(
        args=condition_args,
        initial_state=app.get_state(condition_args[ARG_ENTITY_ID]),
        value=value,
        comparator=condition_args.get(ARG_COMPARATOR, EQUALS),
        callback=callback,
        logger=logger
    )


def _convert_to_time_condition(
        app,
        condition_args,
        callback=None,
        logger=None):
    return TimeCondition(
        condition_args,
        before=condition_args.get(ARG_BEFORE, None),
        after=condition_args.get(ARG_AFTER, None),
        at=condition_args.get(ARG_AT, None),
        callback=callback,
        logger=logger
    )


def convert_to_condition(
        app,
        condition_args,
        callback=None,
        logger=None):
    if ARG_ENTITY_ID in condition_args:
        return _convert_to_state_condition(
            app,
            condition_args,
            callback,
            logger
        )
    elif ARG_BEFORE in condition_args or ARG_AFTER in condition_args or ARG_AT in condition_args:
        return _convert_to_time_condition(
            app,
            condition_args,
            callback,
            logger
        )


def state_schema(app, callback=None, logger=None):
    def _validate(value):
        try:
            validated = SCHEMA_STATE_CONDITION(value)
            return _convert_to_state_condition(
                app,
                validated,
                callback,
                logger
            )
        except vol.Invalid as err:
            raise err

    return _validate


def time_schema(app, callback=None, logger=None):
    def _validate(value):
        try:
            validated = SCHEMA_TIME_CONDITION(value)
            return _convert_to_time_condition(
                app,
                validated,
                callback,
                logger
            )
        except vol.Invalid as err:
            raise err

    return _validate


def condition(app, callback=None, logger=None):
    def _validate(value):
        return vol.Any(
            state_schema(app, callback, logger),
            time_schema(app, callback, logger)
        )(value)

    return _validate


class Condition(dict):
    _args = {}

    def __init__(self, args):
        super().__init__()
        self._args = args

    @property
    def is_met(self):
        return True

    def __getitem__(self, k):
        return self._args.get(k)

    def __setitem__(self, k, v):
        return


class StateCondition(Condition):
    _state = None
    _comparator = EQUALS
    _value = None
    _callback = None
    _logger = None

    def __init__(self, args, initial_state, value, comparator=EQUALS, callback=None, logger=None):
        super().__init__(args)
        self._state = initial_state
        self._value = value
        self._comparator = comparator
        self._callback = callback
        self._logger = logger

    def handle_event(self, event_name, data, kwargs):
        # if self._logger:
        #     self._logger(str(data))
        #     self._logger(str(kwargs))
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
    _callback = None
    _logger = None

    def __init__(self, args, before=None, after=None, at=None, callback=None, logger=None):
        super().__init__(args)
        self._before = before
        self._after = after
        self._at = at
        self._callback = callback
        self._logger = logger

    def handle_time_change(self, kwargs):
        if self._callback is not None and self.is_met:
            self._callback(kwargs)

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
