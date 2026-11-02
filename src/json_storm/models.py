"""Synchronous model access with explicit credentials and observable usage."""

import math
import os
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Any, Protocol

from dotenv import load_dotenv

DEFAULT_SYSTEM_INSTRUCTIONS = "You generate MongoDB queries. Follow the user's query instructions and response format exactly."
_INSTRUCTION_LOCK = RLock()


@contextmanager
def _subscription_instructions(instructions: str | None):
    # LiteLLM exposes this setting through process-global environment state.
    # Serialize adapter calls and restore the environment even after failures.
    with _INSTRUCTION_LOCK:
        key = "CHATGPT_DEFAULT_INSTRUCTIONS"
        previous = os.environ.get(key)
        if instructions is not None:
            os.environ[key] = instructions
        try:
            yield
        finally:
            if instructions is not None:
                if previous is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous


def load_credentials(path: str | Path) -> bool:
    """Load an explicit dotenv file without overriding environment variables.

    Returns python-dotenv's loaded-variable indicator. A missing file raises
    FileNotFoundError rather than silently searching parent directories.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return load_dotenv(path, override=False)


@dataclass(frozen=True)
class ModelResponse:
    """One completion. Missing metadata remains None; usage is normalized by LiteLLM.

    Token breakdowns may already be included in totals. Cost is an estimate, not
    an invoice. reasoning_content is separate from the final answer in text.
    parameters contains requested generation settings, never environment variables.
    """

    text: str | None
    requested_model: str
    returned_model: str | None
    response_id: str | None
    finish_reason: str | None
    elapsed_ms: float
    parameters: dict[str, Any]
    usage: dict[str, Any] | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    reasoning_tokens: int | None
    cached_input_tokens: int | None
    estimated_cost_usd: float | None
    cost_status: str
    billing_mode: str
    system_instructions: str | None = None
    reasoning_content: str | None = None


class Model(Protocol):
    """Minimal interface consumed by future generation orchestration."""

    def generate(self, prompt: str) -> ModelResponse:
        """Return one completion or propagate the provider failure."""
        ...


_RESERVED = {
    "model",
    "messages",
    "instructions",
    "stream",
    "n",
    "timeout",
    "request_timeout",
    "api_base",
    "base_url",
    "api_key",
    "api_token",
    "headers",
    "extra_headers",
    "client",
    "num_retries",
    "max_retries",
    "fallbacks",
    "context_window_fallback_dict",
    "drop_params",
    "additional_drop_params",
    "allowed_openai_params",
    "mock_response",
    "caching",
    "cache",
    "metadata",
    "success_callback",
    "failure_callback",
}


class LiteLLMModel:
    """One non-streaming completion per call, with no retries or output repair.

    Parameters are copied and passed through, including reasoning_effort or
    provider-specific thinking settings. Omitted controls use provider defaults.
    Credentials belong in the environment, not parameters. This adapter assumes
    an otherwise unmodified LiteLLM global configuration (no global callbacks,
    fallbacks, or parameter-dropping overrides).
    """

    def __init__(
        self,
        model: str,
        *,
        timeout_seconds: float = 120,
        api_base: str | None = None,
        parameters: Mapping[str, Any] | None = None,
        system_instructions: str = DEFAULT_SYSTEM_INSTRUCTIONS,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a nonempty string")
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be positive and finite")
        if api_base is not None and (not isinstance(api_base, str) or not api_base.strip()):
            raise ValueError("api_base must be a nonempty string or None")
        if parameters is not None and not isinstance(parameters, Mapping):
            raise TypeError("parameters must be a mapping")
        params = deepcopy(dict(parameters or {}))
        if any(not isinstance(key, str) for key in params):
            raise TypeError("parameter names must be strings")
        if _RESERVED.intersection(params):
            raise ValueError(
                f"Reserved adapter parameters: {sorted(_RESERVED.intersection(params))}"
            )
        if model.startswith("chatgpt/"):
            forbidden = {"max_tokens", "max_output_tokens", "max_completion_tokens"} & params.keys()
            if forbidden:
                raise ValueError(
                    f"ChatGPT subscription does not support token limits: {sorted(forbidden)}"
                )
            if "extra_body" in params:
                raise ValueError(
                    "Use explicit parameters for chatgpt/; extra_body could hide unsupported settings"
                )
        if not isinstance(system_instructions, str) or not system_instructions.strip():
            raise ValueError("system_instructions must be a nonempty string")
        self.system_instructions = system_instructions
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.api_base = api_base
        self._parameters = params

    def generate(self, prompt: str) -> ModelResponse:
        """Call LiteLLM; provider errors propagate unchanged, pricing errors do not."""
        import litellm

        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a nonempty string")
        parameters = deepcopy(self._parameters)
        start = perf_counter()
        subscription = self.model.startswith("chatgpt/")
        messages = [{"role": "user", "content": prompt}]
        if not subscription:
            messages.insert(0, {"role": "system", "content": self.system_instructions})
        with _subscription_instructions(self.system_instructions if subscription else None):
            response = litellm.completion(
                model=self.model,
                messages=messages,
                timeout=self.timeout_seconds,
                api_base=self.api_base,
                stream=False,
                n=1,
                num_retries=0,
                drop_params=False,
                caching=False,
                **deepcopy(parameters),
            )
        elapsed_ms = (perf_counter() - start) * 1000
        if len(response.choices) != 1:
            raise ValueError("Expected exactly one completion choice")
        choice = response.choices[0]
        usage = response.usage.model_dump(exclude_none=True) if response.usage is not None else None
        counts = usage or {}
        cost = None
        cost_status = "unavailable"
        subscription = self.model.startswith("chatgpt/")
        if subscription:
            cost_status = "subscription"
        else:
            try:
                estimate = litellm.completion_cost(completion_response=response, model=self.model)
                if isinstance(estimate, (int, float)) and math.isfinite(estimate) and estimate >= 0:
                    cost = float(estimate)
                    cost_status = "estimated"
            except Exception:
                # Pricing metadata must never discard a successful completion.
                pass
        return ModelResponse(
            text=choice.message.content,
            requested_model=self.model,
            returned_model=response.model,
            response_id=response.id,
            finish_reason=choice.finish_reason,
            elapsed_ms=elapsed_ms,
            parameters=parameters,
            usage=deepcopy(usage),
            input_tokens=counts.get("prompt_tokens"),
            output_tokens=counts.get("completion_tokens"),
            total_tokens=counts.get("total_tokens"),
            reasoning_tokens=(counts.get("completion_tokens_details") or {}).get(
                "reasoning_tokens"
            ),
            cached_input_tokens=(counts.get("prompt_tokens_details") or {}).get("cached_tokens"),
            estimated_cost_usd=cost,
            cost_status=cost_status,
            billing_mode="subscription" if subscription else "provider",
            system_instructions=self.system_instructions,
            reasoning_content=getattr(choice.message, "reasoning_content", None),
        )
