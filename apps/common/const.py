ARG_OR = 'or'
ARG_AND = 'and'
ARG_ENTITY_ID = 'entity_id'
ARG_ATTRIBUTE = 'attribute'
ARG_EXISTS = 'exists'
ARG_STATE = 'state'
ARG_VALUE = 'value'
ARG_HOUR = 'hour'
ARG_MINUTE = 'minute'
ARG_SECOND = 'second'
ARG_BEFORE = 'before'
ARG_AFTER = 'after'
ARG_AT = 'at'
ARG_DOMAIN = 'domain'
ARG_GROUPS = 'groups'
ARG_SERVICE = 'service'
ARG_SERVICE_DATA = 'service_data'
ARG_COMPARATOR = 'comparator'
ARG_DEPENDENCIES = "dependencies"
ARG_NOTIFY = 'notify'
ARG_NOTIFY_CATEGORY = 'notify_category'
ARG_NOTIFY_REPLACERS = 'replacers'
ARG_NOTIFY_ENTITY_ID = 'response_entity_id'
ARG_SENSOR = 'sensor'
ARG_FILENAME = 'filename'
ARG_LOG_LEVEL = 'log_level'
ARG_ENABLED_FLAG = 'enabled_flag'

ATTR_SCORE = 'score'
ATTR_FILENAME = 'filename'
ATTR_OLD_STATE = 'old_state'
ATTR_NEW_STATE = 'new_state'
ATTR_ENTITY_NAME = 'entity_name'
ATTR_RGB_COLOR = "rgb_color"
ATTR_COLOR_NAME = "color_name"

EVENT_STATE_CHANGED = 'state_changed'

DOMAIN_NOTIFY = 'notify'
DOMAIN_HOMEASSISTANT = 'homeassistant'
DOMAIN_CAMERA = 'camera'
DOMAIN_INPUT_SELECT = 'input_select'
DOMAIN_INPUT_DATETIME = 'input_datetime'

SERVICE_TURN_ON = 'turn_on'
SERVICE_TURN_OFF = 'turn_off'
SERVICE_SNAPSHOT = 'snapshot'
SERVICE_SELECT_OPTION = 'select_option'
SERVICE_SET_DATETIME = 'set_datetime'

EQUALS = '='
LESS_THAN = '<'
LESS_THAN_EQUAL_TO = '<='
GREATER_THAN = '>'
GREATER_THAN_EQUAL_TO = '>='
NOT_EQUAL = '!='

VALID_COMPARATORS = [
    EQUALS,
    LESS_THAN,
    LESS_THAN_EQUAL_TO,
    GREATER_THAN,
    GREATER_THAN_EQUAL_TO,
    NOT_EQUAL
]
