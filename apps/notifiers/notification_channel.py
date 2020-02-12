from enum import Enum, auto


class NotificationChannel(Enum):
    SECURITY = auto()
    PRESENCE = auto()
    TRAINING = auto()
    WARNING = auto()
    INFO = auto()

    def __str__(self):
        return self.name.lower()

    def channel_name(self):
        return str(self)
