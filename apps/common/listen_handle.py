from threading import Lock


class ListenHandle:
    """Base listen handle container."""
    __slots__ = ['is_active', '_handle', '_lock', '_app']

    def __init__(self, handle, app):
        self._lock = Lock()
        self._app = app
        self.is_active = True
        self._handle = handle

    async def cancel(self):
        """Cancel the listener."""
        if self._lock.locked() or not self.is_active:
            return

        self._lock.acquire()
        self.is_active = False
        await self._do_cancel()
        self._on_cancelled()
        self._lock.release()

    def _on_cancelled(self):
        """Set properties once cancelled."""
        self.is_active = False
        self._handle = None
        self._app = None

    async def _do_cancel(self):
        """Perform handle cancel."""
        pass

    def __eq__(self, o):
        if o is None:
            if self._handle is None:
                return True
            return False

        if isinstance(o, ListenHandle):
            return o._handle == self._handle

        return self._handle == o

    def __str__(self):
        return str(self._handle)

    def __hash__(self):
        if self._handle is None:
            return None

        return self._handle.__hash__()


class StateListenHandle(ListenHandle):
    """State listen handle container."""

    def __init__(self, handle, app):
        """Create a new listen state handle container."""
        super().__init__(handle, app)

    async def _do_cancel(self):
        await self._app.cancel_listen_state(self._handle)


class EventListenHandle(ListenHandle):
    """Event listen handle container."""

    def __init__(self, handle, app):
        """Create a new listen event handle container."""
        super().__init__(handle, app)

    async def _do_cancel(self):
        await self._app.cancel_listen_event(self._handle)


class TimerHandle(ListenHandle):
    """Timer handle container."""

    def __init__(self, handle, app):
        """Create a new timer handle container."""
        super().__init__(handle, app)

    async def _do_cancel(self):
        await self._app.cancel_timer(self._handle)
