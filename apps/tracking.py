import voluptuous as vol

from common.base_app import BaseApp
from common.const import ARG_ENTITY_ID, ARG_GROUPS
from common.validation import ensure_list, entity_id

ARG_GROUP_NAME = 'group_name'
ARG_MAX_DISTANCE = 'max_distance'

ATTR_LATITUDE = 'latitude'
ATTR_LONGITUDE = 'longitude'
ATTR_SOURCE = 'source'
ATTR_SOURCE_TYPE = 'source_type'

SOURCE_TYPE_GPS = 'gps'
SOURCE_TYPE_ROUTER = 'router'

DEFAULT_DISTANCE = 300.0

SCHEMA_GROUP = vol.Schema({
    vol.Required(ARG_GROUP_NAME): str,
    vol.Optional(ARG_MAX_DISTANCE): vol.Coerce(float),
    vol.Required(ARG_ENTITY_ID): vol.All(
        ensure_list,
        [entity_id]
    )
})


class TrackerGroup(BaseApp):
    config_schema = vol.Schema({
        vol.Required(ARG_GROUPS): SCHEMA_GROUP,
        vol.Optional(ARG_MAX_DISTANCE, default=ARG_MAX_DISTANCE): vol.Coerce(float)
    }, extra=vol.ALLOW_EXTRA)

    _entity_last_gps = {}
    _home_gps = None

    def initialize_app(self):
        self._home_gps = {
            ATTR_LATITUDE: self.config.get(ATTR_LATITUDE, None),
            ATTR_LONGITUDE: self.config.get(ATTR_LONGITUDE, None)
        }

        for group in self.args[ARG_GROUPS]:
            group_name = group[ARG_GROUP_NAME]
            for entity in group[ARG_ENTITY_ID]:
                self.listen_state(self._handle_tracker_update,
                                  entity=entity,
                                  attribute='all',
                                  group_name=group_name,
                                  group_memberrs=group[ARG_ENTITY_ID],
                                  max_distance=group.get(ARG_MAX_DISTANCE,
                                                         self.args[ARG_MAX_DISTANCE]))

    def _handle_tracker_update(self, entity, attribute, old, new, kwargs):
        self.log('Attribute {}', str(attribute))
        self.log('New {}', str(new))
        self.log('Old {}', str(old))

    def _get_gps(self, state):
        if state.get(ATTR_SOURCE_TYPE, None) == SOURCE_TYPE_ROUTER:
            return self._home_gps

        if ATTR_LATITUDE not in state or ATTR_LONGITUDE in state:
            if ATTR_SOURCE not in state:
                return {
                    ATTR_LATITUDE: None,
                    ATTR_LONGITUDE: None
                }

            state = self.get_state(entity_id=state[ATTR_SOURCE], attribute='all')

        return {
            ATTR_LATITUDE: state.get(ATTR_LATITUDE, None),
            ATTR_LONGITUDE: state.get(ATTR_LONGITUDE, None)
        }
