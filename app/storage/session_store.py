"""SessionStore 추상 클래스 + InMemory 구현 — Data Layer
나중에 PostgreSQL 등으로 교체 시 구현체만 추가하면 됨.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
from app.domain.models import AnalysisSession, SessionStatus


class SessionStore(ABC):
    @abstractmethod
    def save(self, session: AnalysisSession) -> None: ...

    @abstractmethod
    def get(self, session_id: str) -> Optional[AnalysisSession]: ...

    @abstractmethod
    def update_status(self, session_id: str, status: SessionStatus) -> None: ...


class InMemorySessionStore(SessionStore):
    def __init__(self) -> None:
        self._store: dict[str, AnalysisSession] = {}

    def save(self, session: AnalysisSession) -> None:
        self._store[session.id] = session

    def get(self, session_id: str) -> Optional[AnalysisSession]:
        return self._store.get(session_id)

    def update_status(self, session_id: str, status: SessionStatus) -> None:
        session = self._store.get(session_id)
        if session:
            session.status = status
