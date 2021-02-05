import logging
import re
from datetime import datetime
from urllib import parse

import voluptuous as vol
from common.base_app import BaseApp
from common.const import ARG_ENTITY_ID
from common.validation import entity_id, ensure_list
from notifiers.notification_category import NotificationCategory
from twilio.rest import Client
from twilio.rest.api.v2010.account.call import CallInstance

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
ARG_CALLED_TOGGLE = "called_toggle"
ARG_TIMEOUT = "timeout"
ARG_SKIP_WEEKENDS = "skip_weekends"

DOMAIN_FLAG_SERVICE = "homeassistant"
TURN_OFF_SERVICE = "turn_off"
TURN_ON_SERVICE = "turn_on"
RETRY_ACKNOWLEDGE_ID = "bhg_retry_acknowledge"

MAX_RETRY = 5

SCHEMA_DAILY_AT = vol.Schema({
    vol.Required(ARG_FREQUENCY_HOUR): vol.All(
        vol.Coerce(int),
        vol.Range(0, 12)
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

    async def initialize_app(self):
        self._twiML = None
        self._call_instance = None
        self._calling = False
        self._retry_handle = None
        self._retries = 0
        self._client = Client(
            self.configs[ARG_CREDENTIALS][ARG_CREDENTIALS_ACCOUNT_SID],
            self.configs[ARG_CREDENTIALS][ARG_CREDENTIALS_TOKEN]
        )

        # action_processor = await self.get_app("notification_action_processor")
        # action_processor.add_acknowledge_listener(self._cancel_retry)

        await self.run_daily(self._new_day,
                             "00:01:00")
        await self.listen_event(self._call_bhg,
                                event="call_bhg")
        await self.listen_event(self._cancel_retry,
                                event="ios.notification_action_fired")
        for schedule in self.configs[ARG_FREQUENCY]:
            await self.run_daily(self._daily_call,
                                 "%02d:%02d:00" % (
                                     schedule[ARG_FREQUENCY_HOUR],
                                     schedule[ARG_FREQUENCY_MINUTE]))

    @property
    def app_schema(self):
        return vol.Schema({
            vol.Required(ARG_CALL_FROM): vol.Match(r"\+1\d{10}$"),
            vol.Required(ARG_CALL_TO): vol.Match(r"\+1\d{10}$"),
            vol.Required(ARG_MESSAGE): str,
            vol.Required(ARG_FREQUENCY): vol.All(
                ensure_list,
                [SCHEMA_DAILY_AT]
            ),
            vol.Optional(ARG_SKIP_WEEKENDS, default=False): vol.Coerce(bool),
            vol.Required(ARG_CREDENTIALS): SCHEMA_CREDENTIALS_CONFIG,
            vol.Optional(ARG_TIMEOUT, default=3): vol.Range(1, 5),
            vol.Optional(ARG_SCHEDULE_TOGGLE): entity_id,
            vol.Optional(ARG_CALLED_TOGGLE): entity_id
        }, extra=vol.ALLOW_EXTRA)

    async def _new_day(self, kwargs):
        self._set_called(False)

    async def _cancel_retry(self, event, data, kwargs):
        self.info(str(data))
        action_name = data.get('actionName', None)
        if action_name == "ACTIONCANCELBHGRETRY":
            self.info("Cancelling retry...")
            if self._retry_handle:
                await self._retry_handle.cancel()
            self._retry_handle = None
        else:
            self.info('Wrong action name')

    async def _retry(self, kwargs):
        self._retries += 1
        if self._retries > MAX_RETRY:
            return
        await self._call_bhg('call_bhg', {}, {})

    async def _daily_call(self, kwargs):
        self._retries = 0
        if self.configs[ARG_SKIP_WEEKENDS] and datetime.today().weekday() >= 5:  # Skip Weekend
            return
        await self._call_bhg('call_bhg', {}, {})

    async def _call_bhg(self, event, data, kwargs):
        if self._retry_handle:
            await self._retry_handle.cancel()
        self._retry_handle = None
        if self._calling:
            return
        self._calling = True
        self._call_instance = None

        self.info("Calling BHG")

        if self.configs[ARG_MESSAGE].startswith("http"):
            twimlet_url = self.configs[ARG_MESSAGE]
        else:
            twimlet_url = "http://twimlets.com/message?Message="
            twimlet_url += parse.quote(self.configs[ARG_MESSAGE], safe="")

        if self._call_instance is not None:
            return

        self._call_instance = self._client.calls.create(
            to=self.configs[ARG_CALL_TO],
            from_=self.configs[ARG_CALL_FROM],
            url=twimlet_url
        )

        await self.run_in(self._process_status, 5)

    async def _process_status(self, kwargs):
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
        await status_map.get(call_status, self._handle_unknown_call_status)(call_status)

    async def _handle_call_in_process(self, status):
        _LOGGER.error("Call in process %s, retrying in %d sec" % (status, 10))
        await self.run_in(self._process_status, 10)

    async def _handle_call_failed(self, status):
        _LOGGER.error("Call failed to complete due to %s, retrying in %d min" % (status, 30))
        await self._notify(NotificationCategory.IMPORTANT_BHG_CALL_FAILED)
        self._calling = False
        self._call_instance = None
        self._retry_handle = await self.run_in(self._retry,
                                               30 * 60)

    async def _handle_call_complete(self, status):
        _LOGGER.debug("Call complete, waiting for transcript")
        await self.run_in(self._get_transcripts, 45)

    async def _handle_unknown_call_status(self, status):
        _LOGGER.warning("Unknown status %s" % status)
        await self.run_in(self._process_status, 10)

    async def _get_transcripts(self, kwargs):
        call_inst = self._call_instance.fetch()
        _LOGGER.debug(f"Grabbing transcripts for {call_inst.sid}")
        recording_sids = [recording.sid for recording in
                          self._call_instance.fetch().recordings.list() if
                          recording is not None and recording.sid]

        _LOGGER.debug(f"Found recordings: {recording_sids}")

        if not recording_sids or len(recording_sids) == 0:
            _LOGGER.debug("NO RECORDINGS FOUND, retry in 60")
            await self._notify(NotificationCategory.IMPORTANT_BHG_TRANSCRIBE_FAILED)
            self._calling = False
            self._call_instance = None
            await self.run_in(self._retry,
                              10 * 60)
        else:
            transcription_texts = [transcription.transcription_text
                                   for transcription in self._client.transcriptions.list()
                                   if transcription and transcription.transcription_text
                                   and transcription.recording_sid in recording_sids]
            _LOGGER.debug(f"Found transcriptions: {str(transcription_texts)}")
            await self._process_transcriptions(transcription_texts)
        self._call_instance = None
        self._calling = False

    async def _notify(self, category, **kwargs):
        await self.notifier.notify_people(
            category,
            None,
            **kwargs
        )

    async def _process_transcriptions(self, transcripts):
        for transcript in [transcript for transcript in transcripts]:
            if REGEX_SCHEDULED.match(transcript):
                _LOGGER.debug('SCHEDULED')
                self._set_scheduled(True)
                await self._notify(NotificationCategory.IMPORTANT_BHG_SCHEDULED,
                                   transcript=transcript)
                return
            elif REGEX_NOT_SCHEDULED.match(transcript):
                _LOGGER.debug('CLEAR')
                self._set_scheduled(False)
                await self._notify(NotificationCategory.IMPORTANT_BHG_ALL_CLEAR,
                                   transcript=transcript)
                return

        _LOGGER.debug("SOMETHING WENT WRONG!!!!")

    def _set_scheduled(self, scheduled):
        if ARG_SCHEDULE_TOGGLE in self.configs:
            self.publish_service_call(DOMAIN_FLAG_SERVICE,
                                      TURN_ON_SERVICE if scheduled else TURN_OFF_SERVICE,
                                      {
                                          ARG_ENTITY_ID: self.configs[ARG_SCHEDULE_TOGGLE]
                                      })
        self._set_called(True)

    def _set_called(self, called):
        if ARG_CALLED_TOGGLE in self.configs:
            self.publish_service_call(DOMAIN_FLAG_SERVICE,
                                      TURN_ON_SERVICE if called else TURN_OFF_SERVICE,
                                      {
                                          ARG_ENTITY_ID: self.configs[ARG_CALLED_TOGGLE]
                                      })
