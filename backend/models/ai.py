"""AI request/response models. Every AI output is advisory and unverified by construction."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr


class AIStatus(BaseModel):
    available: bool
    provider: str = "emergent-universal"
    model: str = ""
    detail: str = ""
    embeddings_model: str = ""
    embeddings_provider: str = ""


class ExtractListingRequest(BaseModel):
    text: str = Field(min_length=10, max_length=6000)


class ExtractedListing(BaseModel):
    """Structured extraction proposed by the LLM for a human to review and edit."""

    title: str
    description: str = ""
    type: str = Field(default="goods", pattern="^(goods|services)$")
    category: str = "Other"
    condition: str = ""
    estimated_value: float = Field(default=0, ge=0)
    currency: str = "USD"
    tags: List[str] = Field(default_factory=list)
    key_attributes: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0, ge=0, le=1)
    warnings: List[str] = Field(default_factory=list)


class ExtractListingResponse(BaseModel):
    extraction: ExtractedListing
    model: str
    generated_at: datetime
    disclaimer: str = (
        "AI suggestions are not verified valuations and must be reviewed before publishing."
    )


AttributeValue = Union[StrictStr, StrictBool, StrictInt, StrictFloat]
ListingKind = Literal["goods", "services"]
ValueBasis = Literal["stated_by_user", "ai_estimate", "none"]


class SuggestedWant(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    target_type: Literal["goods", "services", "any"] = "any"
    reason: str = Field(default="", max_length=300)


class ListingAnalysisLLM(BaseModel):
    """Strict schema the raw LLM JSON must satisfy before anything else trusts it."""

    model_config = ConfigDict(extra="ignore")

    name: StrictStr = Field(min_length=2, max_length=120)
    category: StrictStr = Field(min_length=1, max_length=60)
    listing_type: ListingKind
    description: StrictStr = Field(default="", max_length=4000)
    condition: Optional[StrictStr] = Field(default=None, max_length=80)
    attributes: Dict[str, AttributeValue] = Field(default_factory=dict, max_length=20)
    estimated_value: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    value_basis: ValueBasis = "none"
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    keywords: List[StrictStr] = Field(default_factory=list, max_length=15)
    suggested_wants: List[SuggestedWant] = Field(default_factory=list, max_length=5)
    confidence: float = Field(ge=0, le=1)
    warnings: List[StrictStr] = Field(default_factory=list, max_length=12)


class ListingAnalysis(BaseModel):
    """Validated, normalised AI analysis returned to the client."""

    name: str
    category: str
    listing_type: ListingKind
    description: str = ""
    condition: Optional[str] = None
    attributes: Dict[str, AttributeValue] = Field(default_factory=dict)
    estimated_value: Optional[float] = None
    value_basis: ValueBasis = "none"
    currency: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    suggested_wants: List[SuggestedWant] = Field(default_factory=list)
    confidence: float = 0
    warnings: List[str] = Field(default_factory=list)


class AnalyzeListingRequest(BaseModel):
    text: str = Field(min_length=10, max_length=6000)


class AnalyzeListingResponse(BaseModel):
    analysis: ListingAnalysis
    model: str
    generated_at: datetime
    valuation_verified: Literal[False] = False
    disclaimer: str = (
        "AI suggestions are not verified valuations. Review every field before publishing."
    )


class EmbeddingStatus(BaseModel):
    provider: str
    model: str
    version: str
    dim: int
    store: str
    total: int
    current: int
    stale: int


class ReembedRequest(BaseModel):
    force: bool = False


class ReembedResponse(BaseModel):
    listings: int
    wants: int
    failed: int
    status: EmbeddingStatus


class SimilarListing(BaseModel):
    listing_id: str
    title: str
    category: str
    type: str
    estimated_value: float
    currency: str
    owner_id: str
    score: float


class SimilarListingsResponse(BaseModel):
    want_id: str
    model: str
    version: str
    items: List[SimilarListing] = Field(default_factory=list)
    note: str = "Similarity ranks candidates only; deterministic rules still decide compatibility."


class CategorizeRequest(BaseModel):
    text: str = Field(min_length=3, max_length=4000)


class CategorizeResponse(BaseModel):
    categories: List[str] = Field(default_factory=list)
    primary: str = "Other"
    model: str
    generated_at: datetime


class DealSummaryRequest(BaseModel):
    exchange_id: str


class DealSummaryResponse(BaseModel):
    exchange_id: str
    summary: str
    open_questions: List[str] = Field(default_factory=list)
    negotiation_suggestions: List[str] = Field(default_factory=list)
    model: str
    generated_at: datetime
    disclaimer: str = (
        "Advisory only. AI cannot accept offers, approve proposals or authorise payments."
    )


class MatchExplanation(BaseModel):
    match_id: str
    explanation: str
    model: str
    generated_at: datetime
    cached: bool = False


class GraphStats(BaseModel):
    nodes: int
    edges: int
    two_cycles: int
    three_cycles: int
    generated_at: datetime
    note: Optional[str] = None
