from asyncio import Lock
from builtins import int, isinstance

import voluptuous as vol

from common.base_app import BaseApp
from common.const import (
    ARG_ENTITY_ID,
    ARG_STATE,
    ARG_VALUE,
    ARG_DOMAIN,
    ARG_SERVICE,
    ARG_SERVICE_DATA,
    ARG_COMPARATOR,
    ARG_ENABLED_FLAG,
    EQUALS,
    VALID_COMPARATORS,
    ARG_NOTIFY,
    ARG_NOTIFY_CATEGORY,
    ARG_NOTIFY_REPLACERS,
    ARG_NOTIFY_ENTITY_ID)
from common.validation import (
    entity_id,
    ensure_list,
    any_value,
)
from notifiers.notification_category import (
    VALID_NOTIFICATION_CATEGORIES,
    get_category_by_name
)

ARG_TRIGGER = 'trigger'
ARG_PAUSE_WHEN = 'pause_when'
ARG_DURATION = 'duration'
ARG_EXCEPT_IF = 'except_if'
ARG_ON_TIMEOUT = 'on_timeout'
ARG_CONTINUE_ON_TIMEOUT = 'continue_on_timeout'

SCHEMA_TRIGGER = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_STATE, default='on'): any_value
})

SCHEMA_PAUSE_WHEN = vol.Schema({
    vol.Required(ARG_ENTITY_ID): entity_id,
    vol.Optional(ARG_COMPARATOR, default=EQUALS): vol.In(VALID_COMPARATORS),
    vol.Required(ARG_VALUE): any_value
})

SCHEMA_ON_TIMEOUT = SCHEMA_ON_TRIGGER = vol.Schema({
    vol.Required(ARG_DOMAIN): str,
    vol.Required(ARG_SERVICE): str,
    vol.Optional(ARG_SERVICE_DATA, default={}): dict
})


class Timeout(BaseApp):
    async def initialize_app(self):
        self._notification_category = None
        self._pause_when = {}
        self._when_handlers = set()
        self._timeout_handler = None
        self._paused = False
        self._running = False
        self._canceling_when_handlers = False
        self._when_handlers_lock = Lock()

        self._enabled_flag = True
        if ARG_ENABLED_FLAG in self.configs:
            self._enabled_flag = await self.get_state(self.configs[ARG_ENABLED_FLAG])
            await self.listen_state(self._flag_handler,
                                    entity=self.configs[ARG_ENABLED_FLAG])

        if ARG_NOTIFY in self.configs:
            self._notification_category = \
                get_category_by_name(self.configs[ARG_NOTIFY][ARG_NOTIFY_CATEGORY])

        for when in self.configs[ARG_PAUSE_WHEN]:
            self._pause_when[when[ARG_ENTITY_ID]] = when

        self.debug(f'PAUSE WHEN {str(self._pause_when)}')
        self.debug(f'ARGS {str(self.args)}')
        self.debug(f'CONFIGS {str(self.configs)}')

        trigger = self.configs[ARG_TRIGGER]
        await self.listen_state(self._trigger_met_handler,
                                entity=trigger[ARG_ENTITY_ID],
                                new=trigger[ARG_STATE],
                                immediate=True)
        await self.listen_state(self._trigger_unmet_handler,
                                entity=trigger[ARG_ENTITY_ID],
                                old=trigger[ARG_STATE],
                                immediate=True)

    @property
    def app_schema(self):
        return vol.Schema({
            vol.Required(ARG_TRIGGER): SCHEMA_TRIGGER,
            vol.Optional(ARG_PAUSE_WHEN, default=[]): vol.All(
                ensure_list,
                [SCHEMA_PAUSE_WHEN]
            ),
            vol.Required(ARG_DURATION): vol.Any(
                entity_id,
                int
            ),
            vol.Optional(ARG_ON_TIMEOUT): vol.All(
                ensure_list,
                [SCHEMA_ON_TIMEOUT]
            ),
            vol.Optional(ARG_ENABLED_FLAG): entity_id,
            vol.Optional(ARG_NOTIFY): vol.Schema({
                vol.Required(ARG_NOTIFY_CATEGORY): vol.In(VALID_NOTIFICATION_CATEGORIES),
                vol.Optional(ARG_NOTIFY_REPLACERS, default={}): dict
            }, extra=vol.ALLOW_EXTRA),
            vol.Optional(ARG_CONTINUE_ON_TIMEOUT, default=False): vol.Boolean
        }, extra=vol.ALLOW_EXTRA)

    @property
    async def duration(self):
        if isinstance(self.configs[ARG_DURATION], str):
            return await self.get_state(self.configs[ARG_DURATION])
        else:
            return self.configs[ARG_DURATION]

    async def _flag_handler(self, entity, attribute, old, new, kwargs):
        if self._enabled_flag == new:
            return

        self._enabled_flag = new if isinstance(new, bool) else new == 'on'

        if not self._enabled_flag:
            await self._stop('Automation disabled %s' % entity)
        else:
            self.debug('Automation enabled %s' % entity)
            trigger = self.configs[ARG_TRIGGER]
            state = await self.get_state(trigger[ARG_ENTITY_ID])
            if state == trigger[ARG_STATE]:
                await self._trigger_met_handler(
                    trigger[ARG_ENTITY_ID],
                    None,
                    '',
                    state,
                    {}
                )
            else:
                await self._trigger_unmet_handler(
                    trigger[ARG_ENTITY_ID],
                    None,
                    '',
                    state,
                    {}
                )

    async def _trigger_met_handler(self, entity, attribute, old, new, kwargs):
        if new == old or new != self.configs[ARG_TRIGGER][ARG_STATE] \
                or self._paused or self._running or not self._enabled_flag:
            return

        self.debug('MET old %s new %s' % (old, new))
        await self._run()

    async def _handle_pause_when(self, entity, attribute, old, new, kwargs):
        if old == new or not self._running or not self._enabled_flag:
            return

        self.debug(f'Pause check: {entity} {old} {new} paused {self._paused}')
        self.debug(f'Condition: {str(self._pause_when)}')
        if await self.condition_met(self._pause_when[entity]) and not self._paused:
            self.debug("Pause time because {} is {}".format(entity, new))
            await self._pause()
        elif self._paused:
            async with self._when_handlers_lock:
                for entity, condition in self._pause_when.items():
                    if await self.condition_met(condition):
                        return
            await self._unpause()

    async def _trigger_unmet_handler(self, entity, attribute, old, new, kwargs):
        if old == new or new == self.configs[ARG_TRIGGER][ARG_STATE] \
                or not self._running or not self._enabled_flag:
            return
        self.log('NOT MET')
        await self._stop('No longer met')

    async def _pause(self):
        self._paused = True
        await self._cancel_timer('Pause condition met')

    async def _unpause(self):
        self._paused = False
        await self._reset_timer('Pause condition unmet')

    async def _run(self):
        if not self._running:
            self.debug("Setting up pause handlers")
            async with self._when_handlers_lock:
                for pause_when in self.configs[ARG_PAUSE_WHEN]:
                    self._when_handlers.add(
                        await self.listen_state(self._handle_pause_when,
                                                entity=pause_when[ARG_ENTITY_ID],
                                                immediate=True))
        await self._reset_timer('Triggered')

    async def _stop(self, message='Stopping'):
        self._paused = True
        await self._cancel_timer(message)
        await self._cancel_handlers(message)
        self._running = False
        self._paused = False

    async def _handle_timeout(self, kwargs):
        self.debug('Handling timeout (STOPPING)')
        await self._stop()

        self.debug("Firing on time out events")
        events = self.configs.get(ARG_ON_TIMEOUT, [])
        for event in events:
            self.publish_service_call(event[ARG_DOMAIN], event[ARG_SERVICE],
                                      event[ARG_SERVICE_DATA])

        if self._notification_category is not None:
            await self.notifier.notify_people(
                self._notification_category,
                response_entity_id=self.configs[ARG_NOTIFY].get(ARG_NOTIFY_ENTITY_ID, None),
                **self.configs[ARG_NOTIFY][ARG_NOTIFY_REPLACERS])

        if not self.configs.get(ARG_CONTINUE_ON_TIMEOUT, False):
            return

        await self._reset_timer('Restarting automation...')

    async def _cancel_handlers(self, message):
        if self._canceling_when_handlers:
            return

        async with self._when_handlers_lock:
            self._canceling_when_handlers = True
            self.debug('Cancelling when handlers %s', message)
            for handler in self._when_handlers:
                await self.cancel_listen_state(handler)
            self._when_handlers.clear()
            self._canceling_when_handlers = False

    async def _cancel_timer(self, message):
        self.debug('Canceling Timer %s', message)
        if self._timeout_handler is not None:
            await self.cancel_timer(self._timeout_handler)
        self._timeout_handler = None

    async def _reset_timer(self, message):
        await self._cancel_timer(message)
        self.debug('Scheduling timer')
        self._timeout_handler = await self.run_in(self._handle_timeout,
                                                  await self.duration * 60)
        self._running = True
