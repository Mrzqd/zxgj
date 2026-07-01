from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str | None = None
    notes: str | None = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = None
    notes: str | None = None


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    created_at: datetime


class MemberInvite(BaseModel):
    email: EmailStr
    role: str = "editor"


class ProjectInviteLinkCreate(BaseModel):
    role: str = "editor"
    expires_in_hours: int = Field(default=72, ge=1, le=720)
    max_accepts: int = Field(default=1, ge=1, le=100)


class ProjectInviteLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    token: str
    role: str
    max_accepts: int
    accepted_count: int
    expires_at: datetime
    created_at: datetime


class ProjectMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    role: str
    user: UserRead


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    object_key: str
    url: str
    file_name: str
    content_type: str | None
    size_bytes: int
    created_at: datetime


class ExpenseCreate(BaseModel):
    stage: str
    category: str
    sub_item: str = Field(min_length=1, max_length=160)
    amount: Decimal = Field(gt=0)
    paid_at: date | None = None
    note: str | None = None
    attachment_id: int | None = None


class ExpenseUpdate(BaseModel):
    stage: str | None = None
    category: str | None = None
    sub_item: str | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    paid_at: date | None = None
    note: str | None = None
    attachment_id: int | None = None


class ExpenseRead(ExpenseCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_at: datetime
    attachment: AttachmentRead | None = None


class StageTaskCreate(BaseModel):
    stage: str
    title: str = Field(min_length=1, max_length=180)
    description: str | None = None
    status: str = "open"
    assignee_id: int | None = None
    due_at: datetime | None = None


class StageTaskUpdate(BaseModel):
    stage: str | None = None
    title: str | None = None
    description: str | None = None
    status: str | None = None
    assignee_id: int | None = None
    due_at: datetime | None = None


class StageTaskRead(StageTaskCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_at: datetime


class ComparisonItemCreate(BaseModel):
    space: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    note: str | None = None


class ComparisonItemUpdate(BaseModel):
    space: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    note: str | None = None


class ComparisonQuoteCreate(BaseModel):
    vendor: str = Field(min_length=1, max_length=120)
    price: Decimal = Field(gt=0)
    screenshot_attachment_id: int | None = None
    note: str | None = None


class ComparisonQuoteUpdate(BaseModel):
    vendor: str | None = Field(default=None, min_length=1, max_length=120)
    price: Decimal | None = Field(default=None, gt=0)
    screenshot_attachment_id: int | None = None
    note: str | None = None


class ComparisonQuoteRead(ComparisonQuoteCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    created_at: datetime
    screenshot: AttachmentRead | None = None


class ComparisonItemRead(ComparisonItemCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_at: datetime
    quotes: list[ComparisonQuoteRead] = []


class InspectionCreate(BaseModel):
    stage: str
    item: str = Field(min_length=1, max_length=180)
    standard: str = Field(min_length=1)
    status: str = "pending"
    note: str | None = None
    attachment_id: int | None = None


class InspectionUpdate(BaseModel):
    stage: str | None = None
    item: str | None = None
    standard: str | None = None
    status: str | None = None
    note: str | None = None
    attachment_id: int | None = None


class InspectionRead(InspectionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_at: datetime
    attachment: AttachmentRead | None = None


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = None
    due_at: datetime | None = None
    importance: int = Field(default=3, ge=1, le=5)
    status: str = "open"
    assignee_id: int | None = None


class TodoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_at: datetime | None = None
    importance: int | None = Field(default=None, ge=1, le=5)
    status: str | None = None
    assignee_id: int | None = None


class TodoRead(TodoCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_at: datetime


class ActivityLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    actor_id: int
    action: str
    target_type: str
    target_id: int | None
    message: str
    created_at: datetime
    actor: UserRead


class ProjectProgressUpdate(BaseModel):
    current_stage: str
    note: str | None = None


class ProjectProgressRead(ProjectProgressUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    updated_at: datetime


class ProjectStageCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    value: str | None = Field(default=None, max_length=80)
    planned_days: int = Field(default=7, ge=1, le=365)
    sort_order: int | None = None
    started_at: date | None = None
    completed_at: date | None = None


class ProjectStageUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    planned_days: int | None = Field(default=None, ge=1, le=365)
    sort_order: int | None = None
    started_at: date | None = None
    completed_at: date | None = None


class ProjectStageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    value: str
    label: str
    planned_days: int
    sort_order: int
    started_at: date | None
    completed_at: date | None
    created_at: datetime


class KnowledgeChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=2000)


class KnowledgeAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    history: list[KnowledgeChatMessage] = Field(default_factory=list, max_length=12)


class KnowledgeDocumentUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=2 * 1024 * 1024)
    content_type: str | None = Field(default="text/markdown", max_length=120)


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    source_type: str
    title: str
    filename: str
    download_url: str
    summary: str | None
    content: str | None = None
    index_status: str
    indexed_at: datetime | None = None
    index_error: str | None = None
    created_at: datetime


class KnowledgeIndexTriggerRead(BaseModel):
    queued: int
    skipped: int
    failed: int
    total_unready: int


class KnowledgeSourceRead(BaseModel):
    id: int
    document_id: int
    document_title: str
    heading: str
    text: str
    download_url: str
    score: float


class KnowledgeAnswerRead(BaseModel):
    answer: str
    sources: list[KnowledgeSourceRead]
    documents: list[KnowledgeDocumentRead]
