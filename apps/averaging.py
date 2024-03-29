import asyncio

import voluptuous as vol

import common.validation as cv
from common.base_app import BaseApp
from common.conditions import SCHEMA_STATE_CONDITION
from common.const import (ARG_ATTRIBUTE,
                          ARG_ENTITY_ID)

ARG_TEMP_SENSORS = 'temp_sensors'
ARG_WEIGHT = 'weight'
ARG_MAX_WEIGHT = 'max_weight'
ARG_TRIGGER = 'trigger'
ARG_REMEMBER_LAST = 'remember_last'

ATTR_VALUE = 'value'
ATTR_WEIGHT = 'weight'

DEFAULT_WEIGHT = {
    ARG_WEIGHT: 1.0
}

SCHEMA_TEMP_SENSOR = vol.Schema({
    vol.Required(ARG_ENTITY_ID): cv.entity_id,
    vol.Required(ARG_WEIGHT): vol.Coerce(float),
    vol.Optional(ARG_REMEMBER_LAST,
                 default=False): vol.Coerce(bool),
    vol.Inclusive(ARG_MAX_WEIGHT, 'trigger'): vol.Coerce(float),
    vol.Inclusive(ARG_TRIGGER, 'trigger'): vol.All(cv.ensure_list, [SCHEMA_STATE_CONDITION])
})


class WeightedValue:
    """Represents a weighted value."""

    __slots__ = ['value', 'weight']

    def __init__(self, value, weight):
        """Initialize a weighed value."""
        self.value = value
        self.weight = weight

    @property
    def is_valid(self):
        return self.value is not None and self.weight is not None

    def __str__(self) -> str:
        return f"{self.value} {self.weight}"


class WeightedAveragedClimate(BaseApp):
    """Uses a weighed average to represent the current temperature."""

    _values = {}
    _last_triggered = None
    _current_average = 0

    async def initialize_app(self):
        for sensor in self.configs[ARG_TEMP_SENSORS]:
            self._values[sensor[ARG_ENTITY_ID]] = WeightedValue(0, sensor.get(ARG_WEIGHT))
            await self.listen_state(self.handle_temperature_changed,
                                    entity=sensor[ARG_ENTITY_ID],
                                    immediate=True,
                                    sensor_conf=sensor)
            triggers = sensor.get(ARG_TRIGGER, None)
            if triggers:
                for trigger in triggers:
                    await self.listen_state(self.handle_weight_trigger,
                                            entity=trigger[ARG_ENTITY_ID],
                                            attribute=trigger.get(ARG_ATTRIBUTE, None),
                                            immediate=True,
                                            sensor_conf=sensor)
        self.debug(f'Initial values {self._values}')
        await self.on_dataset_changed()

    @property
    def app_schema(self):
        return vol.Schema({
            vol.Required(ARG_TEMP_SENSORS): vol.All(cv.ensure_list, [SCHEMA_TEMP_SENSOR]),
            vol.Required(ARG_ENTITY_ID): cv.entity_id
        }, extra=vol.ALLOW_EXTRA)

    async def handle_weight_trigger(self, entity, attribute, old, new, kwargs):
        sensor = kwargs['sensor_conf']
        if sensor[ARG_ENTITY_ID] not in self._values:
            self._values[sensor[ARG_ENTITY_ID]] = WeightedValue(0.0, 0.0)

        weight = sensor[ARG_WEIGHT]
        is_met = any(result
                     for result
                     in await asyncio.gather(*[self.condition_met(trigger)
                                               for trigger
                                               in sensor[ARG_TRIGGER]
                                               ])
                     )
        if self._last_triggered == sensor[ARG_ENTITY_ID] or is_met:
            weight = sensor[ARG_MAX_WEIGHT]
            if self.configs[ARG_REMEMBER_LAST]:
                self._last_triggered = sensor[ARG_ENTITY_ID]
        self.debug(f'weight {weight}')
        self._values[sensor[ARG_ENTITY_ID]].weight = float(weight)
        self.debug(
            f'weighted value {self._values[sensor[ARG_ENTITY_ID]].value * self._values[sensor[ARG_ENTITY_ID]].weight}')
        await self.on_dataset_changed()

    async def handle_temperature_changed(self, entity, attribute, old, new, kwargs):
        sensor = kwargs['sensor_conf']
        self.debug(f"entity_id {sensor[ARG_ENTITY_ID]}")
        if sensor[ARG_ENTITY_ID] not in self._values:
            self._values[sensor[ARG_ENTITY_ID]] = WeightedValue(0.0, 0.0)

        self._values[sensor[ARG_ENTITY_ID]].value = float(new)
        await self.on_dataset_changed()

    def _weighted_average(self):
        if self._values is None or len(self._values) == 0:
            return 0.0
        total_weight = float(sum([val.weight for _, val in self._values.items() if val.is_valid]))
        total_value = float(sum([val.weight * val.value for _, val in self._values.items() if val.is_valid]))
        if total_weight == 0:
            return None
        return total_value / total_weight

    async def on_dataset_changed(self):
        """Calculate the weighted mean of a list."""
        w_average = self._weighted_average()
        if w_average is None:
            return
        self.debug(f"w_average {w_average}")
        if abs(w_average - self._current_average) > 0.1:
            await self.set_state(self.configs[ARG_ENTITY_ID], state=w_average)
            self._current_average = w_average
