"""AI service: listing intelligence, categorisation, explanations and deal summaries.

Hard boundary: this module produces *text and validated structured drafts only*. It
never approves a proposal, authorises a payment or decides whether a trade is valid.

Trust policy for LLM output:
1. The raw reply is parsed as JSON. Prose or malformed JSON is rejected.
2. The JSON is validated against a strict Pydantic schema (`ListingAnalysisLLM`):
   types, ranges, enums, lengths. Anything invalid is rejected, with one repair
   retry that feeds the validation errors back to the model.
3. Post-validation normalisation is deterministic: categories are clamped to the
   vocabulary, and a value is only kept when it has an explicit basis. Every value is
   flagged `valuation_verified = False`.
"""

import json
import re
from typing import Any, Dict, List

from pydantic import ValidationError

from lib.ai_providers import LLMError, LLMTimeout, LLMUnavailable, get_llm_provider
from models.ai import ExtractedListing, ListingAnalysis, ListingAnalysisLLM

CATEGORY_VOCABULARY = [
    "Electronics",
    "Photography",
    "Audio",
    "Furniture",
    "Home & Kitchen",
    "Tools & Workshop",
    "Crafts & Pottery",
    "Sports & Outdoors",
    "Books & Music",
    "Fashion",
    "Web Development",
    "Design",
    "Marketing",
    "Writing & Copywriting",
    "Legal & Admin",
    "Tutoring & Coaching",
    "Photography Services",
    "Trades & Repair",
    "Other",
]
_CATEGORY_LOOKUP = {c.lower(): c for c in CATEGORY_VOCABULARY}
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

# Re-exported so routers map provider failures to HTTP statuses in one place.
AIUnavailable = LLMUnavailable
AIError = LLMError
AITimeout = LLMTimeout


def is_available() -> bool:
    return get_llm_provider().is_available()


def model_label() -> str:
    return get_llm_provider().label


async def _complete(system: str, prompt: str, max_tokens: int = 1200) -> str:
    return await get_llm_provider().complete(system, prompt, max_tokens=max_tokens)


def parse_json_object(raw: str) -> Dict[str, Any]:
    if not raw or not raw.strip():
        raise AIError("The model returned an empty response")
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    match = _JSON_BLOCK.search(cleaned)
    if not match:
        raise AIError("The model did not return a JSON object")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise AIError(f"The model returned invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise AIError("The model returned JSON that is not an object")
    return data


# --------------------------------------------------------------- listing analysis

ANALYSIS_SYSTEM = (
    "You are the listing analyst for BarterX, a barter exchange marketplace. You turn a "
    "trader's free-text description into structured listing data. You never invent facts "
    "that are not supported by the text. You are not an appraiser: you never present a "
    "number as a verified market valuation. Reply with a single JSON object and nothing else."
)

_ANALYSIS_SCHEMA_TEXT = f"""{{
  "name": string (2-120 chars, the item or service name),
  "category": one of {json.dumps(CATEGORY_VOCABULARY)},
  "listing_type": "goods" | "services",
  "description": string (clean 1-3 sentence description using only facts in the text),
  "condition": string or null (physical goods only; null for services or when not stated),
  "attributes": object of up to 20 short key -> string|number|boolean facts stated in the text,
  "estimated_value": number or null,
  "value_basis": "stated_by_user" | "ai_estimate" | "none",
  "currency": 3-letter ISO 4217 code or null,
  "keywords": array of up to 15 short lowercase search keywords,
  "suggested_wants": array of up to 5 objects {{"title": string, "category": one of the categories above,
                     "target_type": "goods" | "services" | "any", "reason": string}},
  "confidence": number 0-1 (how much of the output is explicit in the text),
  "warnings": array of strings (missing or unverifiable details)
}}"""


def _analysis_prompt(text: str) -> str:
    return f"""Analyse this barter listing description and return JSON with exactly these keys:
{_ANALYSIS_SCHEMA_TEXT}

Rules:
- listing_type is "services" only when the trader offers their own time, skills or expertise.
- estimated_value: if the text states a price or value, use it with value_basis "stated_by_user".
  Otherwise you MAY give a rough estimate with value_basis "ai_estimate", or null with "none" when
  there is no reasonable basis. Never claim the number is verified.
- currency: the currency stated in the text; null if none is stated.
- suggested_wants: things this trader might plausibly want in return, phrased as wants.
- Put anything unclear, missing or unverifiable in warnings instead of guessing.

Description:
\"\"\"{text}\"\"\""""


def normalise_analysis(raw: ListingAnalysisLLM) -> ListingAnalysis:
    """Deterministic post-validation clean-up of a schema-valid LLM analysis."""
    warnings = list(raw.warnings)

    category = _CATEGORY_LOOKUP.get(raw.category.strip().lower())
    if category is None:
        warnings.append(f"Category '{raw.category}' is not in the BarterX list, so it was set to Other.")
        category = "Other"

    estimated_value = raw.estimated_value
    value_basis = raw.value_basis
    if value_basis == "none" or estimated_value is None:
        estimated_value, value_basis = None, "none"
        warnings.append("No value basis was found. Set your own value before publishing.")
    elif value_basis == "ai_estimate":
        warnings.append("The value is a rough AI estimate, not a verified market valuation.")

    condition = raw.condition if raw.listing_type == "goods" else None

    suggested = []
    for want in raw.suggested_wants:
        want_category = _CATEGORY_LOOKUP.get(want.category.strip().lower(), "Other")
        suggested.append(want.model_copy(update={"category": want_category}))

    keywords = []
    for keyword in raw.keywords:
        cleaned = keyword.strip().lower()
        if cleaned and cleaned not in keywords:
            keywords.append(cleaned)

    return ListingAnalysis(
        name=raw.name.strip(),
        category=category,
        listing_type=raw.listing_type,
        description=raw.description.strip(),
        condition=condition,
        attributes=raw.attributes,
        estimated_value=estimated_value,
        value_basis=value_basis,
        currency=raw.currency,
        keywords=keywords,
        suggested_wants=suggested,
        confidence=raw.confidence,
        warnings=warnings,
    )


def _validation_summary(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors()[:8]:
        location = ".".join(str(piece) for piece in error.get("loc", ()))
        parts.append(f"{location}: {error.get('msg')}")
    return "; ".join(parts)


async def analyze_listing(text: str) -> ListingAnalysis:
    """LLM, then strict schema validation (one repair retry), then normalisation."""
    prompt = _analysis_prompt(text)
    reply = await _complete(ANALYSIS_SYSTEM, prompt, max_tokens=1400)
    problem = ""
    for attempt in range(2):
        try:
            return normalise_analysis(ListingAnalysisLLM.model_validate(parse_json_object(reply)))
        except ValidationError as exc:
            problem = _validation_summary(exc)
        except AIError as exc:
            problem = str(exc)
        if attempt == 0:
            reply = await _complete(
                ANALYSIS_SYSTEM,
                f"{prompt}\n\nYour previous reply was rejected because: {problem}\n"
                "Reply again with one JSON object that follows the schema exactly.",
                max_tokens=1400,
            )
    raise AIError(f"The AI response failed schema validation: {problem}")


async def extract_listing(text: str) -> ExtractedListing:
    """Older listing-form shape, derived from the validated analysis."""
    analysis = await analyze_listing(text)
    return ExtractedListing(
        title=analysis.name,
        description=analysis.description,
        type=analysis.listing_type,
        category=analysis.category,
        condition=analysis.condition or "",
        estimated_value=analysis.estimated_value or 0,
        currency=analysis.currency or "USD",
        tags=analysis.keywords[:12],
        key_attributes=analysis.attributes,
        confidence=analysis.confidence,
        warnings=analysis.warnings,
    )


async def categorize(text: str) -> List[str]:
    prompt = f"""Pick the best-fitting categories for this listing.

Choose 1 to 3 values from this list, most relevant first: {json.dumps(CATEGORY_VOCABULARY)}
Reply with JSON only: {{"categories": string[]}}

Listing: \"\"\"{text}\"\"\""""
    data = parse_json_object(await _complete(ANALYSIS_SYSTEM, prompt, max_tokens=300))
    raw = data.get("categories")
    if not isinstance(raw, list):
        raise AIError("The AI response failed schema validation: categories must be a list")
    categories = []
    for item in raw:
        category = _CATEGORY_LOOKUP.get(str(item).strip().lower())
        if category and category not in categories:
            categories.append(category)
    return categories[:3] or ["Other"]


# --------------------------------------------------------------- explanations

MATCH_SYSTEM = (
    "You explain barter matches for BarterX in plain language. You are given deterministic "
    "compatibility facts and a text-similarity score. You describe what already holds true; "
    "you never promise that a trade will happen and you never call an estimate a valuation."
)


async def match_explanation(context: Dict[str, Any]) -> str:
    listing = context.get("listing") or {}
    want = context.get("want") or {}
    offered = context.get("offered_listing") or {}
    match = context.get("match") or {}
    prompt = f"""Explain why this candidate match is worth a look, in 2 or 3 short sentences.

Candidate listing: {listing.get('title')} ({listing.get('type')}, {listing.get('category')})
Candidate description: {str(listing.get('description', ''))[:600]}
Their estimated value: {listing.get('estimated_value')} {listing.get('currency')}

Your want: {want.get('title')} — {str(want.get('description', ''))[:400]}
Acceptable value range: {want.get('min_value')}–{want.get('max_value')} {want.get('currency')}
Your own offering: {offered.get('title')} at {offered.get('estimated_value')} {offered.get('currency')}

Deterministic facts already verified: {json.dumps(match.get('reasons') or [])}
Text similarity score: {match.get('semantic_score')} (0 to 1, embeddings only)
Value closeness score: {match.get('value_score')} (0 to 1, deterministic)

Mention any gap the trader should consider. Do not invent terms. Plain text only."""
    text = (await _complete(MATCH_SYSTEM, prompt, max_tokens=500)).strip()
    if len(text) > 2000:
        text = text[:2000].rsplit(" ", 1)[0] + "…"
    return text


DEAL_SYSTEM = (
    "You summarise barter deals for BarterX. You describe the proposal exactly as given. "
    "You never approve, never authorise payment and never present AI output as a commitment. "
    "Reply with JSON only."
)


def _string_list(value: Any, limit: int = 8) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]


async def deal_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""Summarise this exchange proposal for its participants.

Proposal data: {json.dumps(payload, default=str)}

Reply with JSON only:
{{"summary": string, "open_questions": string[], "negotiation_suggestions": string[]}}

Rules:
- "summary" states who gives what to whom, the values, and each participant's balancing payment.
- "open_questions" lists what still needs a human decision.
- "negotiation_suggestions" are optional ideas to balance the deal better."""
    data = parse_json_object(await _complete(DEAL_SYSTEM, prompt, max_tokens=900))
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise AIError("The AI response failed schema validation: summary must be a non-empty string")
    return {
        "summary": summary.strip(),
        "open_questions": _string_list(data.get("open_questions")),
        "negotiation_suggestions": _string_list(data.get("negotiation_suggestions")),
    }
