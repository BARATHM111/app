"""LLM provider abstraction.

Business logic (services/ai.py) depends only on `LLMProvider.complete`. Swapping the
vendor/model is an env change (`AI_CHAT_PROVIDER`, `AI_CHAT_MODEL`) or, for a brand new
vendor, one new subclass registered in `build_llm_provider` — no service code changes.

Every call is bounded by a timeout and wraps transport failures in `LLMError`, so a
slow or failing provider surfaces as a clear 502/504 rather than a hung request.
"""

import asyncio
import os
from abc import ABC, abstractmethod
from typing import Optional
from uuid import uuid4

DEFAULT_TIMEOUT_SECONDS = 45.0


class LLMUnavailable(RuntimeError):
    """The provider is not configured (missing key)."""


class LLMError(RuntimeError):
    """The provider call failed or returned nothing usable."""


class LLMTimeout(LLMError):
    """The provider did not answer within the timeout."""


class LLMProvider(ABC):
    name: str = "abstract"
    model: str = ""

    @property
    def label(self) -> str:
        return f"{self.name}:{self.model}"

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    async def _call(self, system: str, prompt: str, max_tokens: int) -> str: ...

    async def complete(self, system: str, prompt: str, *, max_tokens: int = 1200, timeout: float | None = None) -> str:
        if not self.is_available():
            raise LLMUnavailable(f"LLM provider '{self.name}' is not configured on the backend")
        limit = timeout or float(os.environ.get("AI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
        try:
            result = await asyncio.wait_for(self._call(system, prompt, max_tokens), timeout=limit)
        except asyncio.TimeoutError as exc:
            raise LLMTimeout(f"LLM provider timed out after {limit:.0f}s") from exc
        except (LLMError, LLMUnavailable):
            raise
        except Exception as exc:  # transport / provider error — never swallowed
            raise LLMError(str(exc)[:500]) from exc
        if not result or not str(result).strip():
            raise LLMError("The model returned an empty response")
        return str(result)


class EmergentLLMProvider(LLMProvider):
    """Claude / GPT / Gemini through the Emergent universal key (emergentintegrations)."""

    def __init__(self, vendor: str, model: str):
        self.vendor = vendor
        self.model = model
        self.name = vendor

    def is_available(self) -> bool:
        return bool(os.environ.get("EMERGENT_LLM_KEY"))

    async def _call(self, system: str, prompt: str, max_tokens: int) -> str:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        chat = (
            LlmChat(
                api_key=os.environ["EMERGENT_LLM_KEY"],
                session_id=f"barterx-{uuid4()}",
                system_message=system,
            )
            .with_model(self.vendor, self.model)
            .with_params(max_tokens=max_tokens)
        )
        return await chat.send_message(UserMessage(text=prompt))


def build_llm_provider() -> LLMProvider:
    return EmergentLLMProvider(
        vendor=os.environ.get("AI_CHAT_PROVIDER", "anthropic"),
        model=os.environ.get("AI_CHAT_MODEL", "claude-sonnet-4-6"),
    )


_override: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    return _override or build_llm_provider()


def set_llm_provider(provider: Optional[LLMProvider]) -> None:
    """Test hook: install a fake provider (None restores the configured one)."""
    global _override
    _override = provider
