import json

import voluptuous as vol

from common.base_app import BaseApp, ATTR_EVENT_TYPE, ATTR_EVENT_DATA
from common.const import ARG_ENTITY_ID, ARG_GROUPS, EVENT_STATE_CHANGED
from common.helpers import get_distance_helper, Unit
from common.validation import ensure_list, entity_id

ARG_GROUP_NAME = 'group_name'
ARG_MAX_DISTANCE = 'max_distance'

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

SOURCE_TYPE_GPS = 'gps'
SOURCE_TYPE_ROUTER = 'router'

DEFAULT_DISTANCE = 300.0

SCHEMA_GROUP = vol.Schema({
    vol.Required(ARG_GROUP_NAME): vol.All(str, vol.Lower),
    vol.Optional(ARG_MAX_DISTANCE): vol.Coerce(float),
    vol.Required(ARG_ENTITY_ID): vol.All(
        ensure_list,
        [entity_id]
    )
})


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
            self._group_entities[group_name] = {}
            self._group_states[group_name] = None
            max_distance = group.get(ARG_MAX_DISTANCE,
                                     self.args[ARG_MAX_DISTANCE])
            self.log('GROUP {} {}'.format(group_name, max_distance))
            callback_args = {
                ATTR_GROUP_NAME: group_name,
                ATTR_GROUP_MEMBERS: group[ARG_ENTITY_ID],
                ATTR_MAX_DISTANCE: max_distance,
            }

            for entity in group[ARG_ENTITY_ID]:
                self.log('Listening state {}'.format(entity))
                self.listen_state(self._handle_tracker_update,
                                  entity=entity,
                                  attribute='all',
                                  immediate=True,
                                  **callback_args)

    def _handle_tracker_update(self, entity, attribute, old, new, kwargs):
        self.log('Recieved state {} for {}'.format(str(new), entity))
        if new[ATTR_STATE] == 'home':
            self.log('Is home')
            gps = self._home_gps
        else:
            self.log('Getting GPS')
            gps = self._get_gps(new[ATTR_ATTRIBUTES])
        if None in gps:
            return
        group_name = kwargs[ATTR_GROUP_NAME]
        self._entity_last_gps[group_name][entity] = {
            ARG_ENTITY_ID: entity,
            ATTR_GPS: gps
        }
        self._calculate_group_members(group_name, kwargs[ATTR_MAX_DISTANCE])

    def _set_group_state(self, group_name, members=None, lat_avg=0.0, long_avg=0.0):
        entity_id = 'device_tracker.group_%s' % group_name
        self.log('Setting state {}'.format(entity_id))
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

        self.log('Publishing {}'.format(str(payload)))

        return self.mqtt_publish(
            'states/slaves/rules/entity_id',
            payload=json.dumps(payload),
            qos=1,
            retain=True,
            namespace='default'
        )

    def _calculate_group_members(self, group_name, max_distance):
        self.log('Calculating members')
        avg_lat = 0
        avg_long = 0
        members = set()
        for entity1 in self._group_entities[group_name]:
            if None in entity1[ATTR_GPS]:
                self.log("{} has not GPS".format(entity1))
                continue
            for entity2 in [entity2 for entity2 in self._group_entities[group_name] if
                            entity1 != entity2 and None not in entity2[ATTR_GPS] and
                            entity2[ARG_ENTITY_ID] not in members]:
                distance = self._get_distance(entity1[ATTR_GPS], entity2[ATTR_GPS])
                if distance > max_distance:
                    self.log(
                        "{} too far from {}".format(entity1[ARG_ENTITY_ID], entity2[ARG_ENTITY_ID]))
                    continue
                members.add(entity1[ARG_ENTITY_ID])
                avg_lat += entity1[ATTR_GPS][0]
                avg_long += entity2[ATTR_GPS][1]

        if len(members) == 0:
            self.log('No members')
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
