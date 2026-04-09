from pydantic import BaseModel, Field
from typing import Optional

# ── 统一响应格式 ──────────────────────────────────────────

class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: object = None


# ── 文档管理 ──────────────────────────────────────────────

class DocumentUploadData(BaseModel):
    doc_id: int
    name: str
    status: int
    created_at: str


class DocumentOut(BaseModel):
    id: int
    name: str
    file_type: str
    file_size: int
    status: int
    chunk_count: int
    created_at: str

    class Config:
        from_attributes = True


class DocumentDetail(BaseModel):
    id: int
    name: str
    file_type: str
    file_size: int
    minio_url: str
    status: int
    summary: Optional[str]
    chunk_count: int
    created_at: str

    class Config:
        from_attributes = True


class DocumentListData(BaseModel):
    total: int
    list: list[DocumentOut]


# ── 会话管理 ──────────────────────────────────────────────

class ConversationOut(BaseModel):
    id: str
    title: Optional[str]
    message_count: int
    updated_at: str

    class Config:
        from_attributes = True


class ConversationListData(BaseModel):
    total: int
    list: list[ConversationOut]


class ConversationCreateData(BaseModel):
    conv_id: str
    created_at: str


# ── 消息 ──────────────────────────────────────────────────

class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    reference_chunks: Optional[list[int]] = None
    created_at: str


class MessageListData(BaseModel):
    list: list[MessageOut]


# ── 问答 ──────────────────────────────────────────────────

class AskRequest(BaseModel):
    conv_id: str = Field(..., description="会话 ID")
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(5, ge=1, le=20)
    temperature: float = Field(0.7, ge=0.0, le=2.0)


class ReferenceChunk(BaseModel):
    chunk_id: int
    doc_name: str
    content: str


class AskData(BaseModel):
    answer: str
    message_id: int
    references: list[ReferenceChunk]


# ── 反馈 ──────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    message_id: int = Field(..., description="回答的消息 ID")
    score: int = Field(..., ge=0, le=1, description="1=好评, 0=差评")
    comment: Optional[str] = Field(None, max_length=500)


class FeedbackData(BaseModel):
    feedback_id: int
