from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ExceptionLinkedEntity(BaseModel):
    id: int
    label: str


class ExceptionOwnerOut(BaseModel):
    id: int
    full_name: str
    email: str
    role: str | None


class ExceptionCommentOut(BaseModel):
    id: int
    author: ExceptionOwnerOut | None
    comment: str
    created_at: datetime


class ExceptionListItem(BaseModel):
    id: int
    tenant_id: int
    type: str
    severity: str
    status: str
    title: str
    summary: str | None
    trigger_source: str
    linked_shipment: ExceptionLinkedEntity | None
    linked_plant: ExceptionLinkedEntity | None
    linked_material: ExceptionLinkedEntity | None
    current_owner: ExceptionOwnerOut | None
    created_at: datetime
    updated_at: datetime
    triggered_at: datetime
    due_at: datetime | None
    recommended_next_step: str | None
    action_status: str
    action_started_at: datetime | None
    action_completed_at: datetime | None
    action_sla_breach: bool
    action_age_hours: Decimal | None


class ExceptionCounts(BaseModel):
    open_exceptions: int
    critical_exceptions: int
    unassigned_exceptions: int
    resolved_recently: int


class ExceptionListResponse(BaseModel):
    counts: ExceptionCounts
    items: list[ExceptionListItem]


class ExceptionDetailResponse(BaseModel):
    exception: ExceptionListItem
    linked_shipment_detail: dict[str, str | int | None] | None
    linked_context_notes: list[str]
    comments: list[ExceptionCommentOut]
    status_options: list[str]


class ExceptionAssignmentRequest(BaseModel):
    owner_user_id: int | None


class ExceptionStatusRequest(BaseModel):
    status: str


class ExceptionActionRequest(BaseModel):
    action_status: str


class ExceptionCommentRequest(BaseModel):
    comment: str


class ExceptionEvaluationResponse(BaseModel):
    created: int
    updated: int
    resolved: int
    open_after_evaluation: int
