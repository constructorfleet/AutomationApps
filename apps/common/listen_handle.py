from asyncio import Lock


class ListenHandle:
    """Base listen handle container."""

    def __init__(self, handle, app):
        self._lock = Lock()
        self._app = app
        self.is_active = True
        self._handle = handle

    async def cancel(self):
        """Cancel the listener."""
        if self._lock.locked() or not self.is_active or self._handle is None:
            return

        self.is_active = False
        async with self._lock:
            await self._do_cancel()
            self._on_cancelled()

    def _on_cancelled(self):
        """Set properties once cancelled."""
        self.is_active = False
        self._handle = None
        self._app = None

    async def _do_cancel(self):
        """Perform handle cancel."""
        pass

    def __str__(self):
        return self._handle

    def __eq__(self, o):
        if self._handle is None:
            return False
        if isinstance(o, ListenHandle):
            return self._handle.__eq__(o._handle)
        return self._handle.__eq__(o)

    def __hash__(self):
        return hash(self._handle)


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
