"""Small, process-local session log. Each SSE viewer has its own cursor.

# ponytail: sessions live in memory; use a database and worker queue for a public multi-process deployment.
"""

import asyncio
import uuid

from app.schemas.docking import SessionSummary
from app.schemas.events import DockingEvent


class Session:
    def __init__(self, session_id: str, queue_size: int = 1000):
        self.session_id = session_id
        self.event_log: list[DockingEvent] = []
        self.summary: SessionSummary | None = None
        self.finished = asyncio.Event()
        self.task: asyncio.Task | None = None
        self.stream_pacing_s = 0.0
        self.cancel_requested = False
        self.dock_requested = False
        self.capture: dict = {}
        self.request_data: dict | None = None

    async def append(self, event):
        event.session_id = self.session_id
        event.event_id = len(self.event_log) + 1
        self.event_log.append(event)
        if self.summary:
            self.summary.events_emitted = len(self.event_log)


class InMemorySessionStore:
    def __init__(self, queue_size=1000):
        self._sessions: dict[str, Session] = {}

    async def create(self):
        session = Session(uuid.uuid4().hex)
        # Keep only the latest 32 completed sessions. Active sessions are capped at the API.
        completed = [key for key, value in self._sessions.items() if value.finished.is_set()]
        for key in completed[:-31]:
            del self._sessions[key]
        self._sessions[session.session_id] = session
        return session

    async def get(self, session_id):
        return self._sessions.get(session_id)

    async def close(self, session_id):
        session = self._sessions.get(session_id)
        if session:
            session.finished.set()
