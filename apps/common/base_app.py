import json

import voluptuous as vol
from appdaemon import utils

from appdaemon.plugins.mqtt.mqttapi import Mqtt

from common.const import (
    ARG_ENTITY_ID,
    ARG_VALUE,
    ARG_COMPARATOR,
    EQUALS,
    NOT_EQUAL,
    LESS_THAN,
    LESS_THAN_EQUAL_TO,
    GREATER_THAN,
    GREATER_THAN_EQUAL_TO
)
from common.validation import valid_entity_id

ARG_DEPENDENCIES = "dependencies"
APP_NOTIFIERS = "notifiers"

ATTR_EVENT_TYPE = "event_type"
ATTR_EVENT_DATA = "event_data"
ATTR_DOMAIN = "domain"
ATTR_PAYLOAD = "payload"
ATTR_SERVICE = "service"
ATTR_SERVICE_DATA = "service_data"
ATTR_SOURCE = "source"
ATTR_TOPIC = "topic"

EVENT_CALL_SERVICE = "call_service"

DEFAULT_PUBLISH_TOPIC = "events/rules"


def _split_service(service):
    if '/' in service:
        return service.split('/')
    if '.' in service:
        return service.split('.')
    else:
        raise ValueError("Invalid service %s" % service)


class BaseApp(Mqtt):

    config_schema = vol.Schema({}, extra=vol.ALLOW_EXTRA)
    notifier = None

    def initialize(self):
        """Initialization of Base App class."""
        if APP_NOTIFIERS in self.args.get(ARG_DEPENDENCIES, []):
            self.notifier = self.get_app(APP_NOTIFIERS)
        self.args = self.config_schema(self.args)
        self.initialize_app()

    def initialize_app(self):
        pass

    @property
    def publish_topic(self):
        return DEFAULT_PUBLISH_TOPIC

    @utils.sync_wrapper
    async def listen_state(self, callback, entity=None, **kwargs):
        """Registers a callback to react to state changes.

        This function allows the user to register a callback for a wide variety of state changes.

        Args:
            callback: Function to be invoked when the requested state change occurs. It must conform
                to the standard State Callback format documented `here <APPGUIDE.html#state-callbacks>`__
            entity (str, optional): name of an entity or device type. If just a device type is provided,
                e.g., `light`, or `binary_sensor`. ``listen_state()`` will subscribe to state changes of all
                devices of that type. If a fully qualified entity_id is provided, ``listen_state()`` will
                listen for state changes for just that entity.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            attribute (str, optional): Name of an attribute within the entity state object. If this
                parameter is specified in addition to a fully qualified ``entity_id``. ``listen_state()``
                will subscribe to changes for just that attribute within that specific entity.
                The ``new`` and ``old`` parameters in the callback function will be provided with
                a single value representing the attribute.

                The value ``all`` for attribute has special significance and will listen for any
                state change within the specified entity, and supply the callback functions with
                the entire state dictionary for the specified entity rather than an individual
                attribute value.
            new (optional): If ``new`` is supplied as a parameter, callbacks will only be made if the
                state of the selected attribute (usually state) in the new state match the value
                of ``new``.
            old (optional): If ``old`` is supplied as a parameter, callbacks will only be made if the
                state of the selected attribute (usually state) in the old state match the value
                of ``old``.

            duration (int, optional): If ``duration`` is supplied as a parameter, the callback will not
                fire unless the state listened for is maintained for that number of seconds. This
                requires that a specific attribute is specified (or the default of ``state`` is used),
                and should be used in conjunction with the ``old`` or ``new`` parameters, or both. When
                the callback is called, it is supplied with the values of ``entity``, ``attr``, ``old``,
                and ``new`` that were current at the time the actual event occurred, since the assumption
                is that none of them have changed in the intervening period.

                If you use ``duration`` when listening for an entire device type rather than a specific
                entity, or for all state changes, you may get unpredictable results, so it is recommended
                that this parameter is only used in conjunction with the state of specific entities.

            timeout (int, optional): If ``timeout`` is supplied as a parameter, the callback will be created as normal,
                 but after ``timeout`` seconds, the callback will be removed. If activity for the listened state has
                 occurred that would trigger a duration timer, the duration timer will still be fired even though the
                 callback has been deleted.

            immediate (bool, optional): It enables the countdown for a delay parameter to start
                at the time, if given. If the ``duration`` parameter is not given, the callback runs immediately.
                What this means is that after the callback is registered, rather than requiring one or more
                state changes before it runs, it immediately checks the entity's states based on given
                parameters. If the conditions are right, the callback runs immediately at the time of
                registering. This can be useful if, for instance, you want the callback to be triggered
                immediately if a light is already `on`, or after a ``duration`` if given.

                If ``immediate`` is in use, and ``new`` and ``duration`` are both set, AppDaemon will check
                if the entity is already set to the new state and if so it will start the clock
                immediately. If ``new`` and ``duration`` are not set, ``immediate`` will trigger the callback
                immediately and report in its callback the new parameter as the present state of the
                entity. If ``attribute`` is specified, the state of the attribute will be used instead of
                state. In these cases, ``old`` will be ignored and when the callback is triggered, its
                state will be set to ``None``.
            oneshot (bool, optional): If ``True``, the callback will be automatically cancelled
                after the first state change that results in a callback.
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description. In most cases,
                it is safe to ignore this parameter. The value ``global`` for namespace has special
                significance and means that the callback will listen to state updates from any plugin.
            pin (bool, optional): If ``True``, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Sets which thread from the worker pool the callback will be
                run by (0 - number of threads -1).
            *kwargs (optional): Zero or more keyword arguments that will be supplied to the callback
                when it is called.

        Notes:
            The ``old`` and ``new`` args can be used singly or together.

        Returns:
            A unique identifier that can be used to cancel the callback if required. Since variables
            created within object methods are local to the function they are created in, and in all
            likelihood, the cancellation will be invoked later in a different function, it is
            recommended that handles are stored in the object namespace, e.g., `self.handle`.

        Examples:
            Listen for any state change and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback)

            Listen for any state change involving a light and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light")

            Listen for a state change involving `light.office1` and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1")

            Listen for a state change involving `light.office1` and return the entire state as a dict.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", attribute = "all")

            Listen for a change involving the brightness attribute of `light.office1` and return the
            brightness attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", attribute = "brightness")

            Listen for a state change involving `light.office1` turning on and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", new = "on")

            Listen for a change involving `light.office1` changing from brightness 100 to 200 and return the
            brightness attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", attribute = "brightness", old = "100", new = "200")

            Listen for a state change involving `light.office1` changing to state on and remaining on for a minute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", new = "on", duration = 60)

            Listen for a state change involving `light.office1` changing to state on and remaining on for a minute
            trigger the delay immediately if the light is already on.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", new = "on", duration = 60, immediate = True)

        """
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
        name = self.name
        if entity is None or "." not in entity:
            raise ValueError(
                "{}: Invalid entity ID: {}".format(self.name, entity))

        self.logger.debug("Calling listen_state for %s", self.name)
        return await self.AD.state.add_state_callback(name, namespace, entity, callback, kwargs)

    def publish(self, domain, service, kwargs):
        self.log("Publish Domain %s Service %s" % (domain, service))
        return self.mqtt_publish(
            self.publish_topic,
            payload=json.dumps({
                ATTR_EVENT_TYPE: EVENT_CALL_SERVICE,
                ATTR_EVENT_DATA: {
                    ATTR_DOMAIN: domain,
                    ATTR_SERVICE: service,
                    ATTR_SERVICE_DATA: kwargs or {}
                },
                ATTR_SOURCE: self.name
            }),
            qos=0,
            retain=False,
            namespace='default'
        )

    def condition_met(self, condition):
        # TODO : Other conditions
        return self._state_condition_met(condition)

    # noinspection PyTypeChecker
    def _state_condition_met(self, condition):
        entity_state = self.get_state(condition[ARG_ENTITY_ID])
        value = condition.get(ARG_VALUE, None)
        if value is None:
            return True
        if isinstance(value, str) and valid_entity_id(value):
            value = self.get_state(value)

        comparator = condition[ARG_COMPARATOR]
        self.log("{} {} {}".format(entity_state, comparator, value))
        if comparator == EQUALS:
            return entity_state == value
        elif comparator == NOT_EQUAL:
            return entity_state != value
        else:
            entity_state = float(entity_state)
            value = float(value)
            if comparator == LESS_THAN:
                return entity_state < value
            elif comparator == LESS_THAN_EQUAL_TO:
                return entity_state <= value
            elif comparator == GREATER_THAN:
                return entity_state > value
            elif comparator == GREATER_THAN_EQUAL_TO:
                return entity_state >= value
            else:
                self.log('Invalid comparator %s' % comparator)
                return False
