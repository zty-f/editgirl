"""Pydantic 数据模型 / Schema(参考 zcheck 风格)。"""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


# ---------- 枚举 ----------
class Layer(str, Enum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"
    CHAT = "chat"
    USER = "user"


class Confidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class ReviewStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    edited = "edited"
    failed = "failed"


class FindingSource(str, Enum):
    auto = "auto"
    chat = "chat"
    user_direct = "user_direct"


# ---------- 核心模型 ----------
class Position(BaseModel):
    paragraph_idx: int
    char_start: int
    char_end: int


class Paragraph(BaseModel):
    paragraph_idx: int
    text: str
    style: str = "Normal"


class ErrorMetadata(BaseModel):
    pass_id: str = ""
    prompt_version: str = ""
    model: str = ""


class ProofreadError(BaseModel):
    id: str
    doc_id: str
    layer: Layer
    type: str
    confidence: Confidence
    paragraph_idx: int
    char_start: int
    char_end: int
    original: str
    suggestion: str
    explanation: str = ""
    status: ReviewStatus = ReviewStatus.pending
    source: FindingSource = FindingSource.auto
    user_feedback: str = ""
    final_text: str = ""
    metadata: ErrorMetadata = Field(default_factory=ErrorMetadata)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


class Document(BaseModel):
    id: str
    filename: str
    paragraph_count: int
    word_count: int
    file_path: str
    created_at: str


class ChatMessage(BaseModel):
    id: str
    doc_id: str
    role: str  # user / assistant / system
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class Rule(BaseModel):
    id: str
    summary: str
    category: str
    examples: list[str] = Field(default_factory=list)
    hit_count: int = 1
    enabled: bool = True
    created_at: str
    last_used: str = ""


class RuleCandidate(BaseModel):
    """规则草案 — zcheck 风格,需用户确认才升级为正式 Rule。"""
    id: str
    summary: str
    category: str
    source: str  # "rejection" | "chat_teaching" | "implicit"
    evidence: list[str] = Field(default_factory=list)  # 触发的 findings / 拒绝理由
    status: str = "draft"  # draft / approved / archived
    created_at: str


class Skill(BaseModel):
    """注册的能力单元 — 可插拔调度。

    runner 是真正干活的函数,签名:
      async def runner(ctx: SkillContext) -> list[ProofreadError]

    若 runner 为 None,该 skill 只是"声明",不参与调度(用于展示 / 占位)。
    """
    model_config = {"arbitrary_types_allowed": True}

    id: str
    name: str
    scope: str  # builtin / user / project
    layers: list[str]
    description: str
    enabled: bool = True
    phase: int = 50  # 0-100, 越小越先跑(L1 规则=10, fast=20, L4=30, ...)
    runner: object | None = None  # Callable, None=声明 only


class SkillContext(BaseModel):
    """传给 skill runner 的统一上下文。"""
    model_config = {"arbitrary_types_allowed": True}

    doc_id: str
    paragraphs: list[Paragraph]
    user_rules: list[Rule] = Field(default_factory=list)
    on_progress: object | None = None  # Callable[[stage, done, total, new], None]
