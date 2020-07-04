import datetime
import logging
from string import Formatter

_LOGGER = logging.getLogger(__name__)


def minutes_to_seconds(minutes):
    return minutes * 60


def converge_types(v1, v2):
    if v1 is None and v2 is None:
        return None, None
    if v1 is not None:
        return None, v2
    if v2 is not None:
        return v1, None

    v1_type = type(v1)
    v2_type = type(v2)
    if v1_type == v2_type:
        return v1, v2

    if v1_type in [int, float] and v1_type in [int, float]:
        return float(v1), float(v2)
    elif v1_type == bool or v2_type == bool:
        return bool(v1), bool(v2)

    try:
        return float(v1), float(v2)
    except Exception as err:
        _LOGGER.warning('Not floats')

    try:
        return v1, type(v1)(v2)
    except Exception as err:
        _LOGGER.warning('Cannot convert {} to  type of {} ({})'.format(v2, v1, type(v1)))

    try:
        return type(v2)(v1), v2
    except Exception as err:
        _LOGGER.warning('Cannot convert {} to  type of {} ({})'.format(v1, v2, type(v2)))

    # Tried everything, return originals
    return v1, v2


def json_serializer(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat
    return str(obj)


class KWArgFormatter(Formatter):
    def get_value(self, key, args, kwds):
        if isinstance(key, str):
            try:
                return kwds[key]
            except KeyError:
                return key
        else:
            return Formatter.get_value(key, args, kwds)
