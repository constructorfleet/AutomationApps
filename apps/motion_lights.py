from builtins import int, float, isinstance, str

import voluptuous as vol

from common.base_app import BaseApp
from common.validation import entity_id

ARG_MOTION_SENSOR = "motion_sensor"
ARG_LIGHT = "light"
ARG_LIGHT_SENSOR = "light_sensor"
ARG_LIGHT_LEVEL = "light_level"
ARG_SWITCHES = "switches"
ARG_INPUT_MOTION_DURATION = "motion_duration"
ARG_INPUT_MAX_DURATION = "max_duration"
ARG_ENTITY_ID = "entity_id"
ARG_ENTITY_BLOCKING_STATE = "blocking_state"

DEFAULT_MOTION_DURATION = 5  # Turn off after 5 minutes of no motion

BASE_SCHEMA = vol.Schema({
    vol.Optional(ARG_MOTION_SENSOR): entity_id,
    vol.Required(ARG_LIGHT): entity_id,
    vol.Optional(ARG_SWITCHES, default=[]): [entity_id],
    vol.Optional(ARG_INPUT_MOTION_DURATION, default=DEFAULT_MOTION_DURATION): vol.Any(
        entity_id,
        vol.Coerce(int)
    ),
    vol.Optional(ARG_INPUT_MAX_DURATION): vol.Any(
        entity_id,
        vol.Coerce(int)
    )
}, extra=vol.ALLOW_EXTRA)


class MotionLights(BaseApp):
    config_schema = BASE_SCHEMA

    _MAP_DURATION_ARG_TO_PROP = {
        ARG_INPUT_MAX_DURATION: 'max_duration',
        ARG_INPUT_MOTION_DURATION: 'motion_duration'
    }

    motion_duration = DEFAULT_MOTION_DURATION
    max_duration = None
    light_on = False
    light_from_motion = False
    motion_handler = None
    light_handler = None
    args = None

    def initialize_app(self):
        self.light_on = self.get_state(self.args[ARG_LIGHT]) == "on"
        self.log("LIGHT_ON %s" % self.light_on)

        for arg_duration in [ARG_INPUT_MAX_DURATION, ARG_INPUT_MOTION_DURATION]:
            if arg_duration not in self.args:
                continue
            field = self._MAP_DURATION_ARG_TO_PROP[arg_duration]
            arg_value = self.args[arg_duration]
            if isinstance(arg_value, int):
                self.__setattr__(field,
                                 arg_value)
            elif isinstance(arg_value, str):
                try:
                    self.__setattr__(field, int(float(self.get_state(arg_value))))
                except:
                    self.log("Cannot retrieve initial duration")

                self.listen_state(self.duration_changed,
                                  entity=arg_value)

        if self.max_duration and self.light_on:
            self.listen_for_max_duration()

        if ARG_MOTION_SENSOR in self.args:
            self.log("LISTENING FOR MOTION %s" % self.args[ARG_MOTION_SENSOR])
            self.listen_state(self.motion_detected,
                              entity=self.args[ARG_MOTION_SENSOR],
                              new="on")
        self.log("LISTENING_FOR LIGHT CHANGES")
        self.listen_state(self.light_changed,
                          entity=self.args[ARG_LIGHT])

        if self.get_state(self.args[ARG_MOTION_SENSOR]) == 'on':
            self.listen_for_no_motion()

        self.initialize_sub_app()

        self.log("Initialized")

    def initialize_sub_app(self):
        return

    def duration_changed(self, entity, attribute, old, new, kwargs):
        if not new or old == new:
            return
        if entity == self.args[ARG_INPUT_MOTION_DURATION]:
            self.motion_duration = int(float(new))
            self.listen_for_no_motion()
        elif entity == self.args[ARG_INPUT_MAX_DURATION]:
            self.max_duration = int(float(new))
            self.listen_for_max_duration()
        else:
            self.log("motion light app: Unknown duration change " + entity)

    def light_changed(self, entity, attribute, old, new, kwargs):
        self.light_on = new == "on"
        if not self.light_on:
            if self.light_handler:
                self.cancel_timer(self.light_handler)
                self.light_handler = None
            if self.motion_handler:
                self.cancel_listen_state(self.motion_handler)
                self.motion_handler = None
            return
        self.listen_for_max_duration()
        self._reset_timer()

    def handle_max_duration(self, kwargs):
        if self.light_handler:
            self.cancel_listen_state(self.light_handler)
            self.light_handler = None

        self.turn_off_devices()

    def motion_detected(self, entity, attribute, old, new, kwargs):
        if not self.light_from_motion and not self.meets_criteria():
            return
        self._reset_timer()

    def meets_criteria(self):
        return True

    def turn_on_devices(self):
        self.turn_on(self.args[ARG_LIGHT])
        switches = self.args.get(ARG_SWITCHES, None)
        if switches is None:
            return

        for device in self.args[ARG_SWITCHES]:
            self.turn_on(device)

    def turn_off_devices(self):
        self.turn_off(self.args[ARG_LIGHT])

        for device in self.args.get(ARG_SWITCHES, []):
            self.turn_off(device)

        if self.light_handler:
            self.cancel_timer(self.light_handler)
            self.light_handler = None

    def light_timeout(self, entity, attribute, old, new, kwargs):
        self.turn_off_light()

    def motion_clear(self, entity, attribute, old, new, kwargs):
        if not self.light_from_motion:
            return
        self.turn_off_light()

    def turn_off_light(self):
        self.turn_off_devices()
        self.light_from_motion = False

    def listen_for_max_duration(self):
        if self.max_duration is None:
            return
        if self.light_handler:
            self.cancel_timer(self.light_handler)
            self.light_handler = None

        self.log("Listening for max duration")

        self.light_handler = \
            self.run_in(self.handle_max_duration,
                        self.max_duration * 60)

    def listen_for_no_motion(self):
        if ARG_MOTION_SENSOR not in self.args:
            return

        if self.motion_handler:
            self.cancel_listen_state(self.motion_handler)
            self.motion_handler = None

        self.log("Listening for no motion")

        self.motion_handler = \
            self.listen_state(self.motion_clear,
                              entity=self.args[ARG_MOTION_SENSOR],
                              new="off",
                              duration=self.motion_duration * 60)

    def _reset_timer(self):
        self.light_from_motion = True
        self.turn_on_devices()
        self.listen_for_no_motion()


class LuminanceMotionLights(MotionLights):
    config_schema = BASE_SCHEMA.extend({
        vol.Inclusive(ARG_LIGHT_SENSOR, 'sensor'): entity_id,
        vol.Inclusive(ARG_LIGHT_LEVEL, 'sensor'): vol.Or(
            entity_id,
            vol.Coerce(int)
        )
    })

    luminance = 0
    lux_trigger = 0

    def initialize_sub_app(self):
        try:
            self.luminance = int(float(self.get_state(self.args[ARG_LIGHT_SENSOR])))
        except:
            self.log("Cannot retrieve initial luminance")

        self.listen_state(self._handle_luminance_change,
                          entity=self.args[ARG_LIGHT_SENSOR])

        if isinstance(self.args[ARG_LIGHT_LEVEL], int):
            self.lux_trigger = int(self.args[ARG_LIGHT_LEVEL])
        elif isinstance(self.args[ARG_LIGHT_LEVEL], str):
            try:
                self.lux_trigger = int(float(self.get_state(self.arg[ARG_LIGHT_LEVEL])))
            except:
                self.log("Cannot retrieve initial lux limit")
            self.listen_state(self._handle_luminance_change,
                              entity=self.args[ARG_LIGHT_LEVEL])

    def meets_criteria(self):
        return self.luminance < self.lux_trigger

    def _handle_luminance_change(self, entity, attribute, old, new, kwargs):
        if new == old:
            return
        self.luminance = int(float(new))

    def _handle_limit_change(self, entity, attribute, old, new, kwargs):
        if new == old:
            return
        self.lux_trigger = new


class ExternalStateControlledMotionLights(MotionLights):
    config_schema = BASE_SCHEMA.extend({
        vol.Required(ARG_ENTITY_ID): entity_id,
        vol.Required(ARG_ENTITY_BLOCKING_STATE): vol.Coerce(str)
    })

    external_state = None

    def initialize_sub_app(self):
        try:
            self.log("Trying to get state of external control")
            self.external_state = self.get_state(self.args[ARG_ENTITY_ID])
            self.log("External state %s" % self.external_state)
        except:
            self.log("Unable to get initial exterrnal state")
        self.log("Listening for external entity change")
        self.listen_state(self._handle_external_state_change,
                          entity=self.args[ARG_ENTITY_ID])

    def meets_criteria(self):
        self.log("Meets criteria %s %s" % (self.args[ARG_ENTITY_BLOCKING_STATE], self.external_state))
        return self.args[ARG_ENTITY_BLOCKING_STATE] != self.external_state

    def _handle_external_state_change(self, entity, attribute, old, new, kwargs):
        self.log("State change %s" %  new)
        self.external_state = new
