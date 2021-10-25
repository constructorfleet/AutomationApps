import datetime
import re
from datetime import (
    timedelta,
    time as time_sys
)
from urllib.parse import urlparse
from email.headerregistry import Address

import os
import string
import voluptuous as vol

from common.base_app import logging
from common.colors import COLORS

REGEX_IP = r'^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}' \
           r'([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$'

ENTITY_MATCH_ALL = "all"
ENTITY_ID_PATTERN = re.compile(r'(?:[a-z0-9_]*)\.(?:[a-z0-9_]*)')
FLOAT_PATTERN = re.compile(r'[+-]?([0-9]*[.])?[0-9]+')
IP_PATTERN = re.compile(REGEX_IP)
IP_PORT_PATTERN = re.compile(REGEX_IP + r':[0-9]{1,5}')

SUN_EVENT_SUNSET = 'sunset'
SUN_EVENT_SUNRISE = 'sunrise'
TEMP_CELSIUS = '°C'
TEMP_FAHRENHEIT = '°F'
CONF_UNIT_SYSTEM_METRIC = 'metric'  # type: str
CONF_UNIT_SYSTEM_IMPERIAL = 'imperial'  # type: str
_GLOBAL_DEFAULT_TIMEOUT = 60

_LOGGER = logging.getLogger(__name__)

TIME_PERIOD_ERROR = "offset {} should be format 'HH:MM' or 'HH:MM:SS'"
OLD_SLUG_VALIDATION = r'^[a-z0-9_]+$'
OLD_ENTITY_ID_VALIDATION = r"^(\w+)\.(\w+)$"
# Keep track of invalid slugs and entity ids found so we can create a
# persistent notification. Rare temporary exception to use a global.
INVALID_SLUGS_FOUND = {}
INVALID_ENTITY_IDS_FOUND = {}

# Home Assistant types
byte = vol.All(vol.Coerce(int), vol.Range(min=0, max=255))
small_float = vol.All(vol.Coerce(float), vol.Range(min=0, max=1))
positive_int = vol.All(vol.Coerce(int), vol.Range(min=0))
latitude = vol.All(vol.Coerce(float), vol.Range(min=-90, max=90),
                   msg='invalid latitude')
longitude = vol.All(vol.Coerce(float), vol.Range(min=-180, max=180),
                    msg='invalid longitude')
gps = vol.ExactSequence([latitude, longitude])
sun_event = vol.All(vol.Lower, vol.Any(SUN_EVENT_SUNSET, SUN_EVENT_SUNRISE))
port = vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))
color_rgb = vol.All(vol.ExactSequence((byte, byte, byte)), vol.Coerce(tuple))


def color_name(given_color_name):
    """Convert color name to RGB hex value."""
    # COLORS map has no spaces in it, so make the color_name have no
    # spaces in it as well for matching purposes
    rgb_value = COLORS.get(given_color_name.replace(" ", "").lower())
    if not rgb_value:
        raise vol.Invalid("Unknown color {0}".format(given_color_name))

    return rgb_value


# Adapted from:
# https://github.com/alecthomas/voluptuous/issues/115#issuecomment-144464666
def has_at_least_one_key(*keys):
    """Validate that at least one key exists."""

    def validate(obj):
        """Test keys exist in dict."""
        if not isinstance(obj, dict):
            raise vol.Invalid('expected dictionary')

        for k in obj.keys():
            if k in keys:
                return obj
        raise vol.Invalid('must contain one of {}.'.format(', '.join(keys)))

    return validate


def boolean(value):
    """Validate and coerce a boolean value."""
    if isinstance(value, str):
        value = value.lower()
        if value in ('1', 'true', 'yes', 'on', 'enable'):
            return True
        if value in ('0', 'false', 'no', 'off', 'disable'):
            return False
        raise vol.Invalid('invalid boolean value {}'.format(value))
    return bool(value)


def isdevice(value):
    """Validate that value is a real device."""
    try:
        os.stat(value)
        return str(value)
    except OSError:
        raise vol.Invalid('No device at {} found'.format(value))


def matches_regex(regex):
    """Validate that the value is a string that matches a regex."""
    regex = re.compile(regex)

    def validator(value):
        """Validate that value matches the given regex."""
        if not isinstance(value, str):
            raise vol.Invalid('not a string value: {}'.format(value))

        if not regex.match(value):
            raise vol.Invalid('value {} does not match regular expression {}'
                              .format(value, regex.pattern))

        return value

    return validator


def is_regex(value):
    """Validate that a string is a valid regular expression."""
    try:
        r = re.compile(value)
        return r
    except TypeError:
        raise vol.Invalid("value {} is of the wrong type for a regular "
                          "expression".format(value))
    except re.error:
        raise vol.Invalid("value {} is not a valid regular expression".format(
            value))


def isfile(value):
    """Validate that the value is an existing file."""
    if value is None:
        raise vol.Invalid('None is not file')
    file_in = os.path.expanduser(str(value))

    if not os.path.isfile(file_in):
        raise vol.Invalid('not a file')
    if not os.access(file_in, os.R_OK):
        raise vol.Invalid('file not readable')
    return file_in


def isdir(value):
    """Validate that the value is an existing dir."""
    if value is None:
        raise vol.Invalid('not a directory')
    dir_in = os.path.expanduser(str(value))

    if not os.path.isdir(dir_in):
        raise vol.Invalid('not a directory')
    if not os.access(dir_in, os.R_OK):
        raise vol.Invalid('directory not readable')
    return dir_in


def ensure_list(value):
    """Wrap value in list if it is not one."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def valid_entity_id(entity_id):
    """Test if an entity ID is a valid format.
    Format: <domain>.<entity> where both are slugs.
    """
    if not isinstance(entity_id, str):
        return False
    if FLOAT_PATTERN.match(entity_id):
        return False

    return isinstance(entity_id, str) and \
        '.' in entity_id and \
        len(entity_id.split('.')) == 2 and \
        entity_id == entity_id.replace(' ', '_')


def valid_service(value):
    """Test if a service is a valid format.
    Format: <domain>/<service> where both are slugs.
    """
    return ('.' in value and
            value == value.replace(' ', '_'))


def slugified(value):
    """Test if value is sluggified."""
    if OLD_SLUG_VALIDATION is None:
        raise ValueError('SLUG VALIDATION IS NONE')
    if value is None:
        raise ValueError('VALUE IS NONE')
    if re.match(OLD_SLUG_VALIDATION, value) is None:
        raise ValueError(f'{value} is not a slug')
    return value


def service(value):
    """Validate service."""

    value = string(value).lower()
    if valid_service(value):
        return value

    raise vol.Invalid('Service {} is an invalid service'.format(value))


def entity_id(value):
    """Validate Entity ID."""
    value = string(value).lower()
    if valid_entity_id(value):
        return value

    raise vol.Invalid('Entity ID {} is an invalid entity id'.format(value))


def entity_ids(value):
    """Validate Entity IDs."""
    if value is None:
        raise vol.Invalid('Entity IDs can not be None')
    if isinstance(value, str):
        value = [ent_id.strip() for ent_id in value.split(',')]

    return [entity_id(ent_id) for ent_id in value]


comp_entity_ids = vol.Any(
    vol.All(vol.Lower, ENTITY_MATCH_ALL),
    entity_ids
)


def entity_domain(domain):
    """Validate that entity belong to domain."""

    def validate(value):
        """Test if entity domain is domain."""
        ent_domain = entities_domain(domain)
        return ent_domain(value)[0]

    return validate


def split_entity_id(entity_id):
    """Split a state entity_id into domain, object_id."""
    return entity_id.split(".", 1)


def entities_domain(domain):
    """Validate that entities belong to domain."""

    def validate(values):
        """Test if entity domain is domain."""
        values = entity_ids(values)
        for ent_id in values:
            if split_entity_id(ent_id)[0] != domain:
                raise vol.Invalid(
                    "Entity ID '{}' does not belong to domain '{}'"
                        .format(ent_id, domain))
        return values

    return validate


def email(value):
    """Validate value is a valid email address."""
    try:
        return Address(addr_spec=value).addr_spec
    except ValueError as e:
        vol.Invalid('Unable to parse email {0}: {1}'.format(value, str(e)))


def enum(enumClass):
    """Create validator for specified enum."""
    return vol.All(vol.In(enumClass.__members__), enumClass.__getitem__)


def icon(value):
    """Validate icon."""
    value = str(value)

    if ':' in value:
        return value

    raise vol.Invalid('Icons should be specifed on the form "prefix:name"')


time_period_dict = vol.All(
    dict, vol.Schema({
        'days': vol.Coerce(int),
        'hours': vol.Coerce(int),
        'minutes': vol.Coerce(int),
        'seconds': vol.Coerce(int),
        'milliseconds': vol.Coerce(int),
    }),
    has_at_least_one_key('days', 'hours', 'minutes',
                         'seconds', 'milliseconds'),
    lambda value: timedelta(**value))


def time_period_str(value):
    """Validate and transform time offset."""
    if isinstance(value, int):
        raise vol.Invalid('Make sure you wrap time values in quotes')
    elif not isinstance(value, str):
        raise vol.Invalid(TIME_PERIOD_ERROR.format(value))

    negative_offset = False
    if value.startswith('-'):
        negative_offset = True
        value = value[1:]
    elif value.startswith('+'):
        value = value[1:]

    try:
        parsed = [int(x) for x in value.split(':')]
    except ValueError:
        raise vol.Invalid(TIME_PERIOD_ERROR.format(value))

    if len(parsed) == 2:
        hour, minute = parsed
        second = 0
    elif len(parsed) == 3:
        hour, minute, second = parsed
    else:
        raise vol.Invalid(TIME_PERIOD_ERROR.format(value))

    offset = timedelta(hours=hour, minutes=minute, seconds=second)

    if negative_offset:
        offset *= -1

    return offset


def time_period_seconds(value):
    """Validate and transform seconds to a time offset."""
    try:
        return timedelta(seconds=int(value))
    except (ValueError, TypeError):
        raise vol.Invalid('Expected seconds, got {}'.format(value))


time_period = vol.Any(time_period_str, time_period_seconds, timedelta,
                      time_period_dict)


def match_all(value):
    """Validate that matches all values."""
    return value


def positive_timedelta(value):
    """Validate timedelta is positive."""
    if value < timedelta(0):
        raise vol.Invalid('Time period should be positive')
    return value


def string(value):
    """Coerce value to string, except for None."""
    if value is None:
        raise vol.Invalid('string value is None')
    if isinstance(value, (list, dict)):
        raise vol.Invalid('value should be a string')

    return str(value)


def temperature_unit(value) -> str:
    """Validate and transform temperature unit."""
    value = str(value).upper()
    if value == 'C':
        return TEMP_CELSIUS
    if value == 'F':
        return TEMP_FAHRENHEIT
    raise vol.Invalid('invalid temperature unit (expected C or F)')


unit_system = vol.All(vol.Lower, vol.Any(CONF_UNIT_SYSTEM_METRIC,
                                         CONF_UNIT_SYSTEM_IMPERIAL))

any_value = vol.Any(
    vol.Coerce(float),
    vol.Coerce(int),
    vol.Coerce(str),
    entity_id
)


# def template(value):
#     """Validate a jinja2 template."""
#     if value is None:
#         raise vol.Invalid('template value is None')
#     elif isinstance(value, (list, dict, template_helper.Template)):
#         raise vol.Invalid('template value should be a string')
#
#     value = template_helper.Template(str(value))
#
#     try:
#         value.ensure_valid()
#         return value
#     except TemplateError as ex:
#         raise vol.Invalid('invalid template ({})'.format(ex))


# def template_complex(value):
#     """Validate a complex jinja2 template."""
#     if isinstance(value, list):
#         for idx, element in enumerate(value):
#             value[idx] = template_complex(element)
#         return value
#     if isinstance(value, dict):
#         for key, element in value.items():
#             value[key] = template_complex(element)
#         return value
#
#     return template(value)


# def datetime(value):
#     """Validate datetime."""
#     if isinstance(value, datetime_sys):
#         return value
#
#     try:
#         date_val = dt_util.parse_datetime(value)
#     except TypeError:
#         date_val = None
#
#     if date_val is None:
#         raise vol.Invalid('Invalid datetime specified: {}'.format(value))
#
#     return date_val
#
#
def time(value):
    """Validate and transform a time."""
    if isinstance(value, time_sys):
        return value

    try:
        time_val = _parse_time(value)
    except TypeError:
        raise vol.Invalid("Not a parseable type")

    if time_val is None:
        raise vol.Invalid(f"Invalid time specified: {value}")

    return time_val


#
#
# weekdays = vol.All(ensure_list, [vol.In(WEEKDAYS)])

def valid_log_level(value):
    if value.upper() not in logging._nameToLevel:
        raise vol.Invalid("Invalid log level {}".format(value.upper()))

    return logging._nameToLevel[value.upper()]


def socket_timeout(value):
    """Validate timeout float > 0.0.
    None coerced to socket._GLOBAL_DEFAULT_TIMEOUT bare object.
    """
    if value is None:
        return _GLOBAL_DEFAULT_TIMEOUT
    try:
        float_value = float(value)
        if float_value > 0.0:
            return float_value
        raise vol.Invalid('Invalid socket timeout value.'
                          ' float > 0.0 required.')
    except Exception as _:
        raise vol.Invalid('Invalid socket timeout: {err}'.format(err=_))


# pylint: disable=no-value-for-parameter
def url(value):
    """Validate an URL."""
    url_in = str(value)

    if IP_PATTERN.match(value):
        return value + ':80'

    if IP_PORT_PATTERN.match(value):
        return value

    if urlparse(url_in).scheme in ['http', 'https']:
        return vol.Schema(vol.Url())(url_in)

    raise vol.Invalid('invalid url')


def x10_address(value):
    """Validate an x10 address."""
    regex = re.compile(r'([A-Pa-p]{1})(?:[2-9]|1[0-6]?)$')
    if not regex.match(value):
        raise vol.Invalid('Invalid X10 Address')
    return str(value).lower()


def ensure_list_csv(value):
    """Ensure that input is a list or make one from comma-separated string."""
    if isinstance(value, str):
        return [member.strip() for member in value.split(',')]
    return ensure_list(value)


def ensure_obj_key(key, default=None):
    """Ensure that input is an object with key."""

    def _convert(value):
        if isinstance(value, dict):
            if key not in value:
                value[key] = default
            return value
        return {
            key: value
        }

    return _convert


def _parse_time(time_str):
    """Parse a time string (00:20:00) into Time object.
    Return None if invalid.
    """
    parts = str(time_str).split(":")
    if len(parts) < 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) > 2 else 0
        return datetime.time(hour, minute, second)
    except ValueError:
        # ValueError if value cannot be converted to an int or not in range
        return None


def schema_with_slug_keys(value_schema):
    """Ensure dicts have slugs as keys.
    Replacement of vol.Schema({cv.slug: value_schema}) to prevent misleading
    "Extra keys" errors from voluptuous.
    """
    schema = vol.Schema({str: value_schema})

    def verify(value: dict) -> dict:
        """Validate all keys are slugs and then the value_schema."""
        if not isinstance(value, dict):
            raise vol.Invalid("expected dictionary")

        for key in value.keys():
            slugified(key)

        return schema(value)

    return verify
