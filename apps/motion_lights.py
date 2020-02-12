from builtins import int, float, isinstance, str, property

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

DEFAULT_MOTION_DURATION = 5  # Turn off after 5 minutes of no motion


class MotionLights(BaseApp):
    config_schema = vol.Schema({
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
        ),
        vol.Inclusive(ARG_LIGHT_SENSOR, "sensor"): entity_id,
        vol.Inclusive(ARG_LIGHT_LEVEL, "sensor"): vol.Coerce(float)
    }, extra=vol.ALLOW_EXTRA)

    motion_duration = DEFAULT_MOTION_DURATION
    max_duration = None
    light_level = -1
    light_on = False
    light_from_motion = False
    motion_handler = None
    light_handler = None
    args = None

    def initialize_app(self):
        self.light_on = self.get_state(self.args[ARG_LIGHT]) == "on"

        if ARG_INPUT_MOTION_DURATION in self.args:
            arg = self.args[ARG_INPUT_MOTION_DURATION]
            if isinstance(arg, int):
                self.motion_duration = arg
            elif isinstance(arg, str):
                try:
                    self.motion_duration = int(float(self.get_state(arg)))
                except:
                    self.log("Cant get initial duration")
                self.listen_state(self.duration_changed,
                                  entity=arg)

        if ARG_INPUT_MAX_DURATION in self.args:
            arg = self.args[ARG_INPUT_MAX_DURATION]
            if isinstance(arg, int):
                self.max_duration = arg
            elif isinstance(arg, str):
                try:
                    self.max_duration = int(float(self.get_state(arg)))
                except:
                    self.log("Cant get initial duration")
                self.listen_state(self.duration_changed,
                                  entity=arg)

        if self.max_duration and self.get_state(self.args[ARG_LIGHT]) == "on":
            self.listen_for_max_duration()

        if ARG_MOTION_SENSOR in self.args:
            self.listen_state(self.motion_detected,
                              entity=self.args[ARG_MOTION_SENSOR],
                              new="on")
        self.listen_state(self.light_changed,
                          entity=self.args[ARG_LIGHT])

        if ARG_LIGHT_SENSOR in self.args:
            try:
                self.light_level = float(self.get_state(self.args[ARG_LIGHT_SENSOR]))
            except:
                self.log("Cant get initial light level")
            self.listen_state(self.light_level_changed,
                              entity=self.args[ARG_LIGHT_SENSOR])
        else:
            self.light_livel = -10

        self.listen_for_no_motion()

        self.log("Initialized")

    @property
    def is_dark(self):
        return float(self.light_level) < float(self.args.get(ARG_LIGHT_LEVEL, 1000))

    def light_level_changed(self, entity, attribute, old, new, kwargs):
        self.light_level = float(new)

    def duration_changed(self, entity, attribute, old, new, kwargs):
        if not new:
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
        self.log("Motion detected. Dark? {} Light from motion".format(self.is_dark,
                                                                      self.light_from_motion))
        if not self.is_dark and not self.light_from_motion:
            return
        self._reset_timer()

    def turn_on_devices(self):
        self.log("Turning on devices")
        self.turn_on(self.args[ARG_LIGHT])
        switches = self.args.get(ARG_SWITCHES, None)
        if switches is None:
            return

        for device in self.args[ARG_SWITCHES]:
            self.turn_on(device)

    def turn_off_devices(self):
        self.log("Turning off devices")
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
                        seconds=self.max_duration * 60)

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
