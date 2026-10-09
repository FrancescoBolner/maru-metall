"""One schema per AI output, defined once. Used for structured output, validation and the offline provider."""
from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------------------------
# Catalog of features the AI may extract from documents (key -> (group, label, description))
FACT_CATALOG: dict[str, tuple[str, str, str]] = {
    "client_company": ("commercial", "Client company", "Company asking for the price"),
    "client_contact": ("commercial", "Client contact", "Person who sent the inquiry / project leader"),
    "client_email": ("commercial", "Client e-mail", "E-mail address of the client contact"),
    "project_name": ("commercial", "Project name", "Name of the building project"),
    "project_number": ("commercial", "Client project number", "Client's project or quotation number"),
    "bid_deadline": ("commercial", "Offer deadline", "Deadline for sending the price offer"),
    "offer_validity": ("commercial", "Requested validity", "How long the offer must be valid"),
    "currency": ("commercial", "Currency", "Currency of prices mentioned (EUR, NOK, SEK, ...)"),
    "delivery_terms": ("commercial", "Delivery terms", "Incoterm, e.g. DAP, FCA, EXW"),
    "payment_terms": ("commercial", "Payment terms", "Payment terms"),
    "inquiry_date": ("commercial", "Inquiry date", "Date of the inquiry / request"),
    "delivery_address": ("logistics", "Delivery address", "Where the steel must be delivered"),
    "delivery_country": ("logistics", "Delivery country", "Destination country"),
    "delivery_time": ("logistics", "Delivery time", "Requested delivery weeks / dates"),
    "longest_piece": ("logistics", "Longest piece", "Longest assembly or member length"),
    "max_piece_weight": ("logistics", "Heaviest piece", "Maximum weight of a single piece"),
    "execution_class": ("specs", "Execution class", "EN 1090-2 execution class (EXC1-EXC4)"),
    "steel_grade": ("specs", "Steel grade", "Steel grades required (S235, S275, S355, ...)"),
    "tolerance_class": ("specs", "Tolerance class", "EN 1090-2 geometrical tolerance class"),
    "corrosivity_class": ("specs", "Corrosivity class", "ISO 12944 corrosivity category C1-C5"),
    "durability": ("specs", "Durability", "ISO 12944 durability L / M / H / VH"),
    "paint_system": ("specs", "Paint system", "Paint system name or class, e.g. C2M, C3.07 EPPUR 240/2"),
    "paint_color": ("specs", "Colour", "RAL colour"),
    "surface_prep": ("specs", "Surface preparation", "e.g. P2 EN ISO 8501-3, Sa 2.5"),
    "galvanising": ("specs", "Galvanising", "Hot-dip galvanising requirement (ISO 1461) and for which parts"),
    "surface_by_phase": ("specs", "Surface treatment per phase", "Which phases / parts are painted, which galvanised"),
    "fire_rating": ("specs", "Fire protection", "Fire resistance class (R30/R60/R90) or intumescent coating"),
    "recycled_content": ("specs", "Recycled content", "Minimum recycled steel content required"),
    "epd_required": ("specs", "EPD required", "Environmental product declaration requested (yes/no)"),
    "weld_requirements": ("specs", "Weld requirements", "Weld class, NDT, weld sizes"),
    "workshop_drawings_by": ("scope", "Workshop drawings by", "Who makes the workshop drawings"),
    "erection_included": ("scope", "Erection", "Is erection included"),
    "anchors": ("scope", "Anchors", "Anchor bolts / chemical anchors and quantities"),
    "bolts": ("scope", "Bolts", "Bolts and fasteners included or not"),
    "phases": ("scope", "Phases / lots", "Delivery phases or lots"),
    "estimated_weight": ("quantities", "Client's weight estimate", "Total steel weight stated by the client"),
}
FACT_KEYS = list(FACT_CATALOG.keys())

RequirementKind = Literal["fire_rating", "paint_system", "corrosivity", "galvanising", "recycled_content", "epd",
                          "execution_class", "steel_grade", "tolerance", "weld_quality", "other"]
FlagKind = Literal["other_currency", "mixed_units", "conflict", "missing_data", "model_incomplete", "duplicate", "other"]


class AIFact(BaseModel):
    key: str = Field(description="One of the catalog keys")
    value: str = Field(description="Normalised value as written in the document (no guessing)")
    unit: str = Field(description="Unit if any, else empty string")
    snippet: str = Field(description="Verbatim text from the document that contains the value")
    page: int = Field(description="1-based page number, 0 for e-mails or unknown")
    confidence: float = Field(description="0 to 1")


class AIScopeItem(BaseModel):
    item: str
    status: Literal["included", "excluded", "option", "unclear"]
    quantity: str = Field(description="Quantity if stated, else empty string")
    snippet: str
    page: int


class AIRequirement(BaseModel):
    kind: RequirementKind
    text: str = Field(description="Short normalised statement of the requirement")
    snippet: str
    page: int
    cost_impact: Literal["high", "medium", "low"]


class AIFlag(BaseModel):
    kind: FlagKind
    detail: str
    snippet: str
    page: int


class AINotFound(BaseModel):
    key: str
    reason: str


class FileClassification(BaseModel):
    status: Literal["metal-relevant", "partly-relevant", "not-relevant"]
    discipline: Literal["steel structure", "specification", "commercial", "architecture", "concrete", "mep",
                        "timber", "civil", "other"]
    reason: str
    confidence: float


class DocumentExtraction(BaseModel):
    facts: list[AIFact]
    scope_items: list[AIScopeItem]
    requirements: list[AIRequirement]
    flags: list[AIFlag]
    not_found: list[AINotFound]


class DrawingExtraction(BaseModel):
    description: str = Field(description="What the image / drawing shows, one or two sentences")
    facts: list[AIFact]
    scope_items: list[AIScopeItem]
    requirements: list[AIRequirement]
    flags: list[AIFlag]


class AIPrediction(BaseModel):
    key: str
    value: str
    unit: str
    reasoning: str
    confidence: float
    question: str = Field(description="Question to ask the client to confirm, empty if none")


class MissingPrediction(BaseModel):
    predictions: list[AIPrediction]


class AIChange(BaseModel):
    target: str = Field(description="Target id from the provided list")
    new_value: str
    explanation: str


class AINotApplied(BaseModel):
    text: str
    reason: str


class CorrectionProposal(BaseModel):
    changes: list[AIChange]
    not_applied: list[AINotApplied]


class GuidelineExample(BaseModel):
    situation: str
    correction: str


class GuidelinesUpdate(BaseModel):
    guidelines: list[str]
    examples: list[GuidelineExample]


# --------------------------------------------------------------------------------------------
def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema accepted by structured outputs: every object closed, every property required,
    no numeric / length constraints, no titles/defaults."""
    schema = copy.deepcopy(model.model_json_schema())

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k in ("title", "default", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                      "minLength", "maxLength", "pattern", "multipleOf", "maxItems"):
                node.pop(k, None)
            if node.get("type") == "object" or "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}).keys())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


SCHEMAS: dict[str, type[BaseModel]] = {
    "classify_file": FileClassification,
    "extract_document": DocumentExtraction,
    "extract_drawing": DrawingExtraction,
    "predict_missing": MissingPrediction,
    "interpret_correction": CorrectionProposal,
    "update_guidelines": GuidelinesUpdate,
}
