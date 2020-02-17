from enum import Enum
from string import Formatter


def get_action_by_name(action_name):
    return [member for name, member in NotificationAction.__members__.items() if
            name.lower().replace(' ', '_') == action_name.lower()][0]


class KWArgFormatter(Formatter):
    def get_value(self, key, args, kwds):
        if isinstance(key, str):
            try:
                return kwds[key]
            except KeyError:
                return key
        else:
            return Formatter.get_value(key, args, kwds)


class NotificationAction(Enum):
    ACTION_CLOSE_COVER = ("Close", "cover/close_cover")
    ACTION_OPEN_COVER = ("Open", "cover/open_cover")

    ACTION_LOCK = ("Lock", "lock/lock")
    ACTION_UNLOCK = ("Unlock", "lock/unlock")

    ACTION_TIMEOUT_DELAY_ACKNOWLEDGE = ("Acknowledge", None)
    ACTION_TIMEOUT_DELAY_SILENCE = ("Silence Temporarily",
                                    None)

    ACTION_ALARM_DISARM = ("Disarm", "alarm_control_panel/disarm")
    ACTION_ALARM_ARM_AWAY = ("Arm Away", "alarm_control_panel/alarm_arm_away")
    ACTION_ALARM_ARM_HOME = ("Arm Home", "alarm_control_panel/alarm_arm_home")

    ACTION_TRAIN_GOOD = ("Good", "training/good")
    ACTION_TRAIN_BAD = ("Bad", "training/bad")

    def __init__(self, text, service):
        self.text = text
        self.service = service

    def __str__(self):
        return self.name.lower().replace('_', '')
