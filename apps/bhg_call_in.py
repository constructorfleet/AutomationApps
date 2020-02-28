import logging
import re
from datetime import time
from urllib import parse

import voluptuous as vol
from twilio.rest import Client
from twilio.rest.api.v2010.account.call import CallInstance

from common.base_app import BaseApp
from common.const import ARG_ENTITY_ID
from common.validation import entity_id
from notifiers.notification_category import NotificationCategory

_LOGGER = logging.getLogger(__name__)

REGEX_SCHEDULED = re.compile(r'You are scheduled to visit the treatment center',
                             re.RegexFlag.IGNORECASE)
REGEX_NOT_SCHEDULED = re.compile(r'You are not scheduled to come into the treatment center',
                                 re.RegexFlag.IGNORECASE)

ARG_CREDENTIALS = "twilio_credential"
ARG_CREDENTIALS_ACCOUNT_SID = "account_sid"
ARG_CREDENTIALS_TOKEN = "token"
ARG_CALL_TO = "call_to"
ARG_CALL_FROM = "call_from"
ARG_MESSAGE = "message"
ARG_FREQUENCY = "daily_at"
ARG_FREQUENCY_HOUR = "hour"
ARG_FREQUENCY_MINUTE = "minute"
ARG_NOTIFY = "notify"
ARG_NOTIFY_GROUP = "people"
ARG_NOTIFY_IGNORER = "ignored"
ARG_SCHEDULE_TOGGLE = "schedule_toggle"
ARG_TIMEOUT = "timeout"

DOMAIN_FLAG_SERVICE = "homeassistant"
TURN_OFF_SERVICE = "turn_off"
TURN_ON_SERVICE = "turn_on"

SCHEMA_DAILY_AT = vol.Schema({
    vol.Required(ARG_FREQUENCY_HOUR): vol.All(
        vol.Coerce(int),
        vol.Range(0, 6)
    ),
    vol.Optional(ARG_FREQUENCY_MINUTE, default=0): vol.All(
        vol.Coerce(int),
        vol.Range(0, 59)
    )
})

SCHEMA_CREDENTIALS_CONFIG = vol.Schema({
    vol.Required(ARG_CREDENTIALS_ACCOUNT_SID): str,
    vol.Required(ARG_CREDENTIALS_TOKEN): str
})


class CallBHG(BaseApp):
    """Calls a NGH to determine if Alan needs to go in."""

    config_schema = vol.Schema({
        vol.Required(ARG_CALL_FROM): vol.Match(r"\+1\d{10}$"),
        vol.Required(ARG_CALL_TO): vol.Match(r"\+1\d{10}$"),
        vol.Required(ARG_MESSAGE): str,
        vol.Required(ARG_FREQUENCY): SCHEMA_DAILY_AT,
        vol.Required(ARG_CREDENTIALS): SCHEMA_CREDENTIALS_CONFIG,
        vol.Optional(ARG_TIMEOUT, default=3): vol.Range(1, 5),
        vol.Optional(ARG_SCHEDULE_TOGGLE): entity_id
    }, extra=vol.ALLOW_EXTRA)

    _client = None
    _twiML = None
    _call_instance = None
    _called_today = False
    _calling = False

    def initialize_app(self):
        self.log("Initializing")

        self._client = Client(
            self.args[ARG_CREDENTIALS][ARG_CREDENTIALS_ACCOUNT_SID],
            self.args[ARG_CREDENTIALS][ARG_CREDENTIALS_TOKEN]
        )

        self.run_daily(self._new_day,
                       time(0, 0, 0))
        self.listen_event(self._call_bhg,
                          event="call_bhg")
        self.run_daily(self._daily_call,
                       time(self.args[ARG_FREQUENCY][ARG_FREQUENCY_HOUR],
                            self.args[ARG_FREQUENCY][ARG_FREQUENCY_MINUTE]))

        self.log("Initialized")

    def _new_day(self, kwargs):
        self._called_today = False

    def _daily_call(self, kwargs):
        if self._called_today:
            return
        self._call_bhg('call_bhg', {}, {})

    def _call_bhg(self, event, data, kwargs):
        if self._calling:
            return
        self._calling = True
        self._call_instance = None

        self.log("Calling BHG")

        if self.args[ARG_MESSAGE].startswith("http"):
            twimlet_url = self.args[ARG_MESSAGE]
        else:
            twimlet_url = "http://twimlets.com/message?Message="
            twimlet_url += parse.quote(self.args[ARG_MESSAGE], safe="")

        if self._call_instance is not None:
            return

        self._call_instance = self._client.calls.create(
            to=self.args[ARG_CALL_TO],
            from_=self.args[ARG_CALL_FROM],
            url=twimlet_url
        )

        self.run_in(self._process_status, 5)

    def _process_status(self, kwargs):

        call_status = self._call_instance.fetch().status
        status_map = {
            CallInstance.Status.BUSY: self._handle_call_failed,
            CallInstance.Status.CANCELED: self._handle_call_failed,
            CallInstance.Status.FAILED: self._handle_call_failed,
            CallInstance.Status.NO_ANSWER: self._handle_call_failed,

            CallInstance.Status.IN_PROGRESS: self._handle_call_in_process,

            CallInstance.Status.QUEUED: self._handle_call_in_process,
            CallInstance.Status.RINGING: self._handle_call_in_process,

            CallInstance.Status.COMPLETED: self._handle_call_complete
        }
        status_map.get(call_status,
                       self._handle_unknown_call_status)(call_status)

    def _handle_call_in_process(self, status):
        _LOGGER.error("Call in process %s, retrying in %d sec" % (status, 10))
        self.run_in(self._process_status, 10)

    def _handle_call_failed(self, status):
        _LOGGER.error("Call failed to complete due to %s, retrying in %d min" % (status, 10))
        self._notify(NotificationCategory.WARNING_BHG_CALL_FAILED)
        self._calling = False
        self._called_today = False
        self._call_instance = None

    def _handle_call_complete(self, status):
        _LOGGER.warning("Call complete, waiting for transcript")
        self.run_in(self._get_transcripts, 45)

    def _handle_unknown_call_status(self, status):
        _LOGGER.warning("Unknown status %s" % status)
        self.run_in(self._process_status, 10)

    def _get_transcripts(self, kwargs):
        recording_sids = [recording.sid for recording in
                          self._call_instance.fetch().recordings.list() if
                          recording is not None and recording.sid]

        if not recording_sids or len(recording_sids) == 0:
            self._notify(NotificationCategory.WARNING_BHG_TRANSCRIBE_FAILED)
            self._called_today = False
            return

        transcription_texts = [transcription.transcription_text
                               for transcription in self._client.transcriptions.list()
                               if transcription and transcription.transcription_text
                               and transcription.recording_sid in recording_sids]
        self._process_transcriptions(transcription_texts)
        self._call_instance = None
        self._calling = False

    def _notify(self, category, **kwargs):
        self.notifier.notify_people(
            category,
            None,
            **kwargs
        )

    def _process_transcriptions(self, transcripts):
        for transcript in [transcript for transcript in transcripts]:
            if REGEX_SCHEDULED.match(transcript):
                if ARG_SCHEDULE_TOGGLE in self.args:
                    self.publish(DOMAIN_FLAG_SERVICE,
                                 TURN_ON_SERVICE,
                                 {
                                     ARG_ENTITY_ID: self.args[ARG_SCHEDULE_TOGGLE]
                                 })
                self._notify(NotificationCategory.WARNING_BHG_SCHEDULED, transcript=transcript)
            elif REGEX_NOT_SCHEDULED.match(transcript):
                if ARG_SCHEDULE_TOGGLE in self.args:
                    self.publish(DOMAIN_FLAG_SERVICE,
                                 TURN_OFF_SERVICE,
                                 {
                                     ARG_ENTITY_ID: self.args[ARG_SCHEDULE_TOGGLE]
                                 })
                self._notify(NotificationCategory.WARNING_BHG_ALL_CLEAR, transcript=transcript)
