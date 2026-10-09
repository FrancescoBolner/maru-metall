"""Pydantic schemas for everything the pipeline produces.

Every number shown to the estimator is a `V` (traceable value) stored in the run's value
registry. Report tables only hold value ids; the UI resolves them and opens the source panel.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

ValueType = Literal["extracted", "calculated", "predicted"]
FileStatus = Literal["metal-relevant", "partly-relevant", "not-relevant", "unreadable", "duplicate"]
RefKind = Literal[
    "pdf_page", "sheet_cell", "ifc_elements", "email", "text", "image", "knowledge_row", "user_edit"
]


class Ref(BaseModel):
    """A precise pointer to where a value comes from."""

    kind: RefKind
    file_id: Optional[str] = None
    path: Optional[str] = None          # relative to the project folder (or knowledge file name)
    page: Optional[int] = None          # 1-based page number (PDF)
    sheet: Optional[str] = None
    cell: Optional[str] = None          # "F426" or a range "A7:G7"
    row: Optional[int] = None
    guids: list[str] = Field(default_factory=list)
    bbox: Optional[list[float]] = None  # [x0, y0, x1, y1] in PDF points (page coordinates)
    bboxes: list[list[float]] = Field(default_factory=list)
    snippet: Optional[str] = None
    label: Optional[str] = None         # human readable, e.g. "Price Inquiry.pdf · page 1"
    kn_id: Optional[str] = None         # knowledge-file row id (kind = knowledge_row)


class ConflictOption(BaseModel):
    value: Any
    unit: Optional[str] = None
    refs: list[Ref] = Field(default_factory=list)
    note: Optional[str] = None


class Edit(BaseModel):
    before: Any
    after: Any
    reason: Optional[str] = None
    source: Literal["direct_edit", "written_correction", "file_override"] = "direct_edit"
    at: Optional[str] = None


class V(BaseModel):
    """A traceable value."""

    id: str
    label: str
    value: Any = None
    unit: Optional[str] = None
    type: ValueType
    confidence: float = 1.0
    refs: list[Ref] = Field(default_factory=list)
    formula: Optional[str] = None
    inputs: list[str] = Field(default_factory=list)
    kn: list[str] = Field(default_factory=list)  # knowledge row ids
    reasoning: Optional[str] = None
    question: Optional[str] = None
    conflict: list[ConflictOption] = Field(default_factory=list)
    edited: Optional[Edit] = None
    editable: bool = False
    edit_key: Optional[str] = None          # override target, e.g. "line:<id>:kg", "fact:spec.paint_system"
    allowed: Optional[list[Any]] = None     # allowed values for edits (enums)
    group: Optional[str] = None             # feature group / report section


class FileEntry(BaseModel):
    id: str
    path: str                     # relative to the project folder; attachments: "<email>::<name>"
    name: str
    ext: str
    kind: str                     # ifc, bom, pdf, email, image, tekla-db, dwg, dxf, nc1, text, other
    size: int = 0
    pages: Optional[int] = None
    sheets: Optional[int] = None
    elements: Optional[int] = None
    date: Optional[str] = None
    sha256: str = ""
    parent_id: Optional[str] = None
    status: FileStatus = "partly-relevant"
    reason: str = ""
    decided_by: Literal["rule", "ai", "estimator"] = "rule"
    duplicate_of: Optional[str] = None
    superseded_by: Optional[str] = None
    used_for: list[str] = Field(default_factory=list)
    read_by: Optional[Literal["code", "ai", "code+ai", "none"]] = None
    error: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


class FileMap(BaseModel):
    root: str
    entries: list[FileEntry]
    level: Literal["idea", "draft", "full"]
    level_reason: str
    counts: dict[str, int]
    total_size: int
    seconds: float = 0.0


class Fact(BaseModel):
    key: str
    group: Literal["commercial", "scope", "specs", "logistics", "quantities"]
    label: str
    value_id: str


class TakeoffLine(BaseModel):
    id: str
    category: str
    phase: Optional[str] = None
    profile: str
    family: str
    grade: Optional[str] = None
    is_plate: bool = False
    thickness_mm: Optional[float] = None
    source: str                       # ifc | bom | pdf
    pieces_id: str
    kg_id: str
    length_id: Optional[str] = None
    area_id: Optional[str] = None
    longest_mm: Optional[float] = None
    surface: Optional[str] = None
    included: bool = True


class CategorySummary(BaseModel):
    name: str
    phase: Optional[str] = None
    kg_id: str
    pieces_id: str
    area_id: str
    plate_share_id: str
    surface_id: str
    longest_mm: Optional[float] = None
    included: bool = True
    assemblies: int = 0


class HoursRow(BaseModel):
    operation: str
    category: str
    quantity_id: Optional[str] = None
    hours_id: str
    norm: str
    kn: list[str] = Field(default_factory=list)
    costed_in: Literal["labour", "surface", "galvanising", "packaging", "transport"] = "labour"


class PaintRow(BaseModel):
    category: str
    system: str
    area_id: str
    coats: int
    litres: list[dict[str, Any]]   # [{product, value_id}]
    hours_id: str
    cost_id: str
    kn: list[str] = Field(default_factory=list)


class CostLine(BaseModel):
    group: str
    label: str
    value_id: str
    kn: list[str] = Field(default_factory=list)
    category: Optional[str] = None


class Risk(BaseModel):
    id: str
    rank: int
    severity: Literal["high", "medium", "low"]
    kind: Literal["requirement", "conflict", "missing", "messy", "scope", "carbon", "other"]
    title: str
    detail: str
    value_ids: list[str] = Field(default_factory=list)
    refs: list[Ref] = Field(default_factory=list)
    question: Optional[str] = None


class Question(BaseModel):
    id: str
    text: str
    reason: str
    value_ids: list[str] = Field(default_factory=list)


class Override(BaseModel):
    id: str = ""
    target: Literal["fact", "line", "category", "file", "param", "value"]
    key: str
    field: str = "value"
    value: Any = None
    reason: Optional[str] = None
    source: Literal["direct_edit", "written_correction"] = "direct_edit"
    text: Optional[str] = None
    created_at: Optional[str] = None
    label: Optional[str] = None
    before: Any = None


class Progress(BaseModel):
    job_id: str
    project_id: str
    state: Literal["queued", "running", "done", "failed"]
    phase: str = ""
    stage: str = ""
    message: str = ""
    started_at: float = 0.0
    elapsed: float = 0.0
    files: list[dict[str, Any]] = Field(default_factory=list)
    stages: list[dict[str, Any]] = Field(default_factory=list)
    revision: Optional[int] = None
    error: Optional[str] = None


class RunResult(BaseModel):
    project_id: str
    company: str
    project_name: str
    project_path: str
    revision: int
    quote_number: str
    report_name: str
    status: Literal["draft", "approved"] = "draft"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    timings: dict[str, float] = Field(default_factory=dict)
    ai: dict[str, Any] = Field(default_factory=dict)
    filemap: FileMap
    facts: list[Fact] = Field(default_factory=list)
    lines: list[TakeoffLine] = Field(default_factory=list)
    categories: list[CategorySummary] = Field(default_factory=list)
    features: dict[str, list[str]] = Field(default_factory=dict)     # feature group -> value ids
    hours: list[HoursRow] = Field(default_factory=list)
    hours_totals: dict[str, Any] = Field(default_factory=dict)
    paint: list[PaintRow] = Field(default_factory=list)
    paint_totals: dict[str, Any] = Field(default_factory=dict)
    material: dict[str, Any] = Field(default_factory=dict)
    cost: dict[str, Any] = Field(default_factory=dict)
    offer_lines: list[dict[str, Any]] = Field(default_factory=list)
    carbon: dict[str, Any] = Field(default_factory=dict)
    risks: list[Risk] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    assumptions: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    values: dict[str, V] = Field(default_factory=dict)
    overrides: list[Override] = Field(default_factory=list)
    changes: list[dict[str, Any]] = Field(default_factory=list)
    knowledge: dict[str, Any] = Field(default_factory=dict)
    reports: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
