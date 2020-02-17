from enum import Enum

from notifiers.notification_action import NotificationAction
from notifiers.notification_channel import NotificationChannel


def get_category_by_name(category_name):
    return [member for name, member in NotificationCategory.__members__.items() if
            name.lower().replace(' ', '_') == category_name.lower()][0]


class NotificationCategory(Enum):
    SECURITY_COVER_OPENED = (
        NotificationChannel.SECURITY, "Opened {entity_name} for {person_name}",
        [NotificationAction.ACTION_CLOSE_COVER])
    SECURITY_COVER_CLOSED = (
        NotificationChannel.SECURITY, "Closed {entity_name} for {person_name}",
        [NotificationAction.ACTION_OPEN_COVER])
    SECURITY_COVER_CLOSED_TIMEOUT = (
        NotificationChannel.SECURITY, "Closed {entity_name}",
        [NotificationAction.ACTION_OPEN_COVER])
    SECURITY_LOCKED = (
        NotificationChannel.SECURITY, "Locked {entity_name} for {person_name}",
        [NotificationAction.ACTION_UNLOCK])
    SECURITY_LOCK_TIMEOUT = (
        NotificationChannel.SECURITY, "Locked {entity_name}", [NotificationAction.ACTION_UNLOCK])
    SECURITY_LOCK_TIMEOUT_DELAY = (NotificationChannel.SECURITY, "Locking of {entity_name} delayed",
                                   [NotificationAction.ACTION_TIMEOUT_DELAY_ACKNOWLEDGE,
                                    NotificationAction.ACTION_TIMEOUT_DELAY_SILENCE])
    SECURITY_UNLOCKED = (
        NotificationChannel.SECURITY, "Unlocked {entity_name} for {person_name}",
        [NotificationAction.ACTION_LOCK])
    SECURITY_ALARM_DISARMED = (NotificationChannel.SECURITY, "Disarmed alarm",
                               [NotificationAction.ACTION_ALARM_ARM_AWAY,
                                NotificationAction.ACTION_ALARM_ARM_HOME])
    SECURITY_ALARM_ARM_HOME = (NotificationChannel.SECURITY, "Armed while home",
                               [NotificationAction.ACTION_ALARM_DISARM,
                                NotificationAction.ACTION_ALARM_ARM_AWAY])
    SECURITY_ALARM_ARM_AWAY = (NotificationChannel.SECURITY, "Armed while away",
                               [NotificationAction.ACTION_ALARM_DISARM,
                                NotificationAction.ACTION_ALARM_ARM_HOME])
    SECURITY_ALARM_TRIGGER = (NotificationChannel.SECURITY,
                              "Alarm triggered",
                              [NotificationAction.ACTION_ALARM_DISARM])  # TODO: Siren or something

    PRESENCE_PERSON_ARRIVED = (NotificationChannel.PRESENCE, "{person_name} has arrived")
    PRESENCE_PERSON_DEPARTED = (NotificationChannel.PRESENCE, "{person_name} has left")
    PRESENCE_PERSON_DETECTED = (NotificationChannel.PRESENCE, "Someone is at {location}",
                                [NotificationAction.ACTION_LOCK, NotificationAction.ACTION_UNLOCK])

    TRAIN = (NotificationChannel.TRAINING, "I performed $action on {entity_name}",
             [NotificationAction.ACTION_TRAIN_GOOD, NotificationAction.ACTION_TRAIN_BAD])

    WARNING_LOW_BATTERY = (
        NotificationChannel.WARNING, "Time to replace {entity_name}'s battery"
    )
    WARNING_BHG_ALL_CLEAR = (
        NotificationChannel.WARNING, "{transcript}"
    )
    WARNING_BHG_SCHEDULED = (
        NotificationChannel.WARNING,
        "{transcript}",
        None,
        "priority",
        True
    )

    INFO_APPLIANCE_DONE = (
        NotificationChannel.INFO, "The {appliance_name} is done."
    )

    def __init__(self, channel, body, actions=None, importance_override=None, critical=False):
        if actions is None:
            actions = []
        self.channel = channel
        self.body = body
        self.actions = actions
        self.importance_override = importance_override
        self.critical = critical

    def __str__(self):
        return "{}".format(str(self.name).lower().replace("_", ""))

    def category_name(self):
        return self.name.lower()
