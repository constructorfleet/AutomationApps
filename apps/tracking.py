import copy
import json
import logging

import voluptuous as vol

from common.base_app import BaseApp, ATTR_EVENT_TYPE, ATTR_EVENT_DATA
from common.const import (
    ARG_ENTITY_ID,
    ARG_GROUPS,
    ATTR_NEW_STATE,
    ATTR_OLD_STATE,
    EVENT_STATE_CHANGED
)
from common.helpers import get_distance_helper, Unit
from common.validation import ensure_list, entity_id

_LOGGER = logging.getLogger(__name__)

ARG_GROUP_NAME = 'group_name'
ARG_MAX_DISTANCE = 'max_distance'
ARG_ZONES_ASSUME_HOME = 'zones_assume_home'
ARG_MINUTES_BEFORE_ASSUME = 'minutes_before_assume_home'

ATTR_LATITUDE = 'latitude'
ATTR_LONGITUDE = 'longitude'
ATTR_SOURCE = 'source'
ATTR_SOURCE_TYPE = 'source_type'
ATTR_ATTRIBUTES = 'attributes'
ATTR_STATE = 'state'
ATTR_GROUP_NAME = 'group_name'
ATTR_GROUP_MEMBERS = 'group_members'
ATTR_MAX_DISTANCE = 'max_distance'
ATTR_GPS = 'gps'
ATTR_ENTITY_ID = 'entity_id'

SOURCE_TYPE_GPS = 'gps'
SOURCE_TYPE_ROUTER = 'router'

DEFAULT_DISTANCE = 300.0
DEFAULT_MINUTES_BEFORE_ASSUME = 40

SCHEMA_GROUP = vol.Schema({
    vol.Required(ARG_GROUP_NAME): vol.All(str, vol.Lower),
    vol.Optional(ARG_MAX_DISTANCE): vol.Coerce(float),
    vol.Required(ARG_ENTITY_ID): vol.All(
        ensure_list,
        [entity_id]
    )
})


def get_home_gps(hass_config):
    return (
            hass_config.get(ATTR_LATITUDE, None),
            hass_config.get(ATTR_LONGITUDE, None)
        )


class AssumeVehicleHome(BaseApp):
    config_schema = vol.Schema({
        vol.Required(ARG_ENTITY_ID): vol.All(
            ensure_list,
            [entity_id]
        ),
        vol.Required(ARG_ZONES_ASSUME_HOME): vol.All(
            ensure_list,
            [entity_id]
        ),
        vol.Optional(ARG_MINUTES_BEFORE_ASSUME, default=DEFAULT_MINUTES_BEFORE_ASSUME): vol.All(
            vol.Coerce(int),
            vol.Range(30, 60)
        )
    }, extra=vol.ALLOW_EXTRA)

    _home_gps = None
    _last_states = {}
    _timer_handlers = {}

    def initialize_app(self):
        self._home_gps = {
            ATTR_LATITUDE: self.config.get(ATTR_LATITUDE, None),
            ATTR_LONGITUDE: self.config.get(ATTR_LONGITUDE, None)
        }
        for entity in self.args[ARG_ENTITY_ID]:
            self._last_states[entity] = self.get_state(
                entity_id=entity,
                attribute='all')
            self.listen_state(self._handle_entity_change,
                              entity=entity,
                              attribute='all')

    def _handle_entity_change(self, entity, attribute, old, new, kwargs):
        self._last_states[entity] = new
        if new[ATTR_STATE] == 'home' or new[ATTR_STATE] not in self.args[ARG_ZONES_ASSUME_HOME]:
            self._stop_timer(entity)
        elif new[ATTR_STATE] in self.args[ARG_ZONES_ASSUME_HOME]:
            self._reset_timer(entity)

    def _stop_timer(self, entity):
        if entity in self._timer_handlers:
            self.cancel_timer(self._timer_handlers[entity])
            del self._timer_handlers[entity]

    def _reset_timer(self, entity):
        self._stop_timer(entity)
        self._timer_handlers[entity] = self.run_in(self._handle_assume_home,
                                                   self.args[ARG_MINUTES_BEFORE_ASSUME] * 60)

    def _handle_assume_home(self, kwargs):
        entity_id = kwargs.get(ATTR_ENTITY_ID, None)
        if entity_id is None:
            _LOGGER.warning('No entity id provided')
            return
        old_state = self._last_states[entity_id]
        new_state = copy.deepcopy(old_state)
        new_state[ATTR_STATE] = 'home'
        if ATTR_ATTRIBUTES in new_state and ATTR_LATITUDE in new_state[ATTR_ATTRIBUTES] and \
                ATTR_LONGITUDE in new_state[ATTR_ATTRIBUTES]:
            new_state[ATTR_LATITUDE] = self._home_gps[ATTR_LATITUDE]
            new_state[ATTR_LONGITUDE] = self._home_gps[ATTR_LONGITUDE]

        self.publish_event(
            EVENT_STATE_CHANGED,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_OLD_STATE: old_state,
                ATTR_NEW_STATE: new_state
            }
        )


class TrackerGroup(BaseApp):
    config_schema = vol.Schema({
        vol.Required(ARG_GROUPS): vol.All(
            ensure_list,
            [SCHEMA_GROUP]
        ),
        vol.Optional(ARG_MAX_DISTANCE, default=ARG_MAX_DISTANCE): vol.Coerce(float)
    }, extra=vol.ALLOW_EXTRA)

    _entity_last_gps = {}
    _group_entities = {}
    _group_states = {}
    _home_gps = None
    _get_distance = get_distance_helper(unit=Unit.MILES)

    def initialize_app(self):
        self._home_gps = (
            self.config.get(ATTR_LATITUDE, None),
            self.config.get(ATTR_LONGITUDE, None)
        )

        for group in self.args[ARG_GROUPS]:
            group_name = group[ARG_GROUP_NAME]
            self._entity_last_gps[group_name] = {}
            self._group_entities[group_name] = []
            self._group_states[group_name] = None
            max_distance = group.get(ARG_MAX_DISTANCE,
                                     self.args[ARG_MAX_DISTANCE])
            callback_args = {
                ATTR_GROUP_NAME: group_name,
                ATTR_GROUP_MEMBERS: group[ARG_ENTITY_ID],
                ATTR_MAX_DISTANCE: max_distance,
            }

            for entity in group[ARG_ENTITY_ID]:
                self._entity_last_gps[group_name][entity] = self._home_gps
                self._group_entities[group_name].append(entity)
                self.listen_state(self._handle_tracker_update,
                                  entity=entity,
                                  attribute='all',
                                  immediate=True,
                                  **callback_args)

    def _handle_tracker_update(self, entity, attribute, old, new, kwargs):
        if new[ATTR_STATE] == 'home':
            gps = self._home_gps
        else:
            gps = self._get_gps(new[ATTR_ATTRIBUTES])
        if None in gps:
            return
        group_name = kwargs[ATTR_GROUP_NAME]
        self._entity_last_gps[group_name][entity] = gps
        self._calculate_group_members(group_name, kwargs[ATTR_MAX_DISTANCE])

    def _set_group_state(self, group_name, members=None, lat_avg=0.0, long_avg=0.0):
        entity_id = 'device_tracker.group_%s' % group_name
        new_state = {
                        ARG_ENTITY_ID: entity_id,
                        ATTR_STATE: 'tracking',
                        ATTR_ATTRIBUTES: {
                            ATTR_GROUP_MEMBERS: members or [],
                            ATTR_LATITUDE: lat_avg,
                            ATTR_LONGITUDE: long_avg
                        }
                    }
        old_state = self._group_states[group_name]
        self._group_states[group_name] = new_state

        payload = {
            ATTR_EVENT_TYPE: EVENT_STATE_CHANGED,
            ATTR_EVENT_DATA: {
                ARG_ENTITY_ID: entity_id,
                'new_state': new_state
            },
            ATTR_SOURCE: self.name
        }

        if old_state is not None:
            payload[ATTR_EVENT_DATA]['old_state'] = old_state

        return self.mqtt_publish(
            'states/slaves/rules/entity_id',
            payload=json.dumps(payload),
            qos=1,
            retain=True,
            namespace='default'
        )

    def _calculate_group_members(self, group_name, max_distance):
        avg_lat = 0
        avg_long = 0
        members = set()
        for entity1 in self._group_entities[group_name]:
            if None in self._entity_last_gps[group_name][entity1]:
                continue
            for entity2 in [entity2 for entity2 in self._group_entities[group_name] if
                            entity1 != entity2 and
                            None not in self._entity_last_gps[group_name][entity2] and
                            entity2 not in members]:
                distance = self._get_distance(
                    self._entity_last_gps[group_name][entity1],
                    self._entity_last_gps[group_name][entity2])
                if distance > max_distance:
                    continue
                members.add(entity1)
                members.add(entity2)
                avg_lat += self._entity_last_gps[group_name][entity1][0]
                avg_long += self._entity_last_gps[group_name][entity1][1]
                avg_lat += self._entity_last_gps[group_name][entity2][0]
                avg_long += self._entity_last_gps[group_name][entity2][1]

        if len(members) == 0:
            self._set_group_state(group_name)
        else:
            self._set_group_state(
                group_name,
                members=list(members),
                lat_avg=avg_lat / len(members),
                long_avg=avg_long / len(members)
            )

    def _get_gps(self, state):
        if state.get(ATTR_SOURCE_TYPE, None) == SOURCE_TYPE_ROUTER:
            return self._home_gps

        if ATTR_LATITUDE not in state or ATTR_LONGITUDE in state:
            if ATTR_SOURCE not in state:
                return (
                    None,
                    None
                )

            state = self.get_state(entity_id=state[ATTR_SOURCE], attribute='all')

        return (
            state.get(ATTR_LATITUDE, None),
            state.get(ATTR_LONGITUDE, None)
        )
