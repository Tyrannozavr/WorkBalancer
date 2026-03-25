from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AgentJobStatus(StrEnum):
    PENDING_LAUNCH = "PENDING_LAUNCH"
    CREATING = "CREATING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    STOPPED = "STOPPED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class Project:
    id: int
    name: str
    repository_url: str
    ref: str


@dataclass(frozen=True, slots=True)
class AgentJob:
    id: int
    cursor_agent_id: str | None
    project_id: int
    telegram_chat_id: int
    telegram_user_id: int
    status: AgentJobStatus
    prompt_preview: str
    summary: str | None
    agent_url: str | None
    pr_url: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AuditEntry:
    id: int
    telegram_user_id: int
    action: str
    details: dict
    created_at: datetime


@dataclass(slots=True)
class AgentWebhookPayload:
    event: str
    agent_id: str
    status: str
    summary: str | None
    repository: str | None
    ref: str | None
    agent_url: str | None
    branch_name: str | None
    pr_url: str | None
