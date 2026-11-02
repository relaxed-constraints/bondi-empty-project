# Model access

The synchronous LiteLLM adapter makes one non-streaming completion call. It does
not load credentials on import, parse output, execute queries, or orchestrate batches.

## Credentials

Copy `.env.example` to `.env` and fill in the providers you use. Both `.env` and
`.env.*` are ignored by Git; `.env.example` contains empty placeholders only.
Call `load_credentials` explicitly at notebook or experiment startup:

```python
from json_storm.models import LiteLLMModel, load_credentials

load_credentials(".env")  # explicit path, relative to the current working directory
model = LiteLLMModel(
    "provider/model-id",  # replace with a supported LiteLLM provider/model
    parameters={"reasoning_effort": "low"},  # only if supported by that model
)
# response = model.generate(prompt)
```

Existing environment variables take precedence. Missing files raise
`FileNotFoundError`; no parent-directory discovery occurs. Never put API keys in
experiment configuration or generation parameters. Custom provider parameters
must also be free of credentials: they are copied into response records.

For Ollama, set the appropriate `ollama/` or `ollama_chat/` model identifier and
`api_base="http://localhost:11434"`. Endpoint and model support must be verified
against the selected model before a live experiment.

## Parameters and reasoning

The constructor accepts a model identifier, positive finite `timeout_seconds`
(default 120), optional `api_base`, and a generation `parameters` mapping.
Parameters are defensively copied and forwarded to LiteLLM. Reasoning controls
such as `reasoning_effort` or provider-specific `thinking` settings are explicit;
omitting them uses provider defaults, not necessarily disabled reasoning.
The adapter does not inject temperature or an output limit.

Reserved controls (including credentials, messages, streaming, retries and cache
settings) cannot be supplied through parameters. Each call requests one completion,
with no retries, caching, or silent parameter dropping. Do not modify LiteLLM's
global callbacks, fallback, or parameter-dropping settings for these experiments.
Provider failures, including unsupported settings, propagate to the caller.

## Response observations

`ModelResponse` records final `text` (possibly `None`), separate `reasoning_content`,
requested/returned model identifiers, response ID, finish reason, elapsed call time,
and requested generation parameters. A length-limited or empty answer is retained.
The response ID is the normalized completion ID, not necessarily an HTTP request ID.

Token fields are `input_tokens`, `output_tokens`, `total_tokens`,
`reasoning_tokens`, and `cached_input_tokens`. The complete normalized `usage`
dictionary is also retained. Missing fields remain `None`; existing zeros reported
by LiteLLM are retained. Provider normalization can supply defaults, so these are
not a guarantee that every breakdown was measured by the underlying provider.
Reasoning and cached-token breakdowns may already be included in totals: do not
add them again.

`estimated_cost_usd` comes from LiteLLM's `completion_cost` calculation.
`cost_status` is `estimated`, `unavailable`, or `subscription`; missing pricing or calculation
failures never discard a successful response. This is not an invoice and does not
measure local hardware costs. Pricing can change independently of the package
lockfile. Elapsed time measures the completion call, excluding cost calculation.

Usage and parameter dictionaries remain mutable within the frozen response
record. Environment variables and credentials are not captured by the adapter.
Generation orchestration, persistence, Yanex integration, and live-provider
validation are separate steps. Current tests use fake completion responses.

## ChatGPT/Codex subscription

Use `chatgpt/<model-id>` to select subscription access instead of an OpenAI API
key. The project includes LiteLLM's `mcp` extra required by this provider.
Authenticate once in a foreground terminal before using notebooks or workers:

```sh
uv run python -c 'from litellm.llms.chatgpt.authenticator import Authenticator; Authenticator().get_access_token()'
```

Follow the printed device-code URL and sign in. Device-code login may need to be
enabled in ChatGPT security settings. No token is printed by the command.
LiteLLM manages its own credentials in `~/.config/litellm/chatgpt/auth.json` by
default, separately from Codex. `CHATGPT_TOKEN_DIR` can override the directory.
Keep it outside the repository; do not copy credentials into experiment artifacts.

```python
model = LiteLLMModel(
    "chatgpt/gpt-6.1-sol",  # availability must be checked for your account
    parameters={"reasoning_effort": "low"},
)
# response = model.generate(prompt)
```

The provider bridges completion requests to Responses and aggregates the stream
for our synchronous interface. Subscription limits and model availability apply.
There is no paid API fallback. `billing_mode="subscription"` and
`cost_status="subscription"` identify these calls; `estimated_cost_usd=None`
means per-token API pricing is not applicable, not that the subscription is free.
Token usage is retained as reported. Other routes use `billing_mode="provider"`,
which does not itself establish whether the provider charges for a call.

The subscription backend does not accept `max_tokens`, `max_output_tokens`, or
`max_completion_tokens`; the adapter rejects them instead of allowing LiteLLM to
silently strip them. `extra_body` is also rejected for this route to prevent hidden
overrides. Reasoning remains configurable, subject to the chosen model's support.
The request timeout is a client deadline, not a token budget or guarantee of
server-side cancellation. Keep subscription and API cohorts distinct in research.

Provider reference: [LiteLLM ChatGPT subscription](https://docs.litellm.ai/docs/providers/chatgpt).

### Live validation (2026-11-03)

A foreground device-code login succeeded with LiteLLM 1.106.6. One live
`chatgpt/gpt-6.1-sol` call with `reasoning_effort="low"` generated two find queries
from the p3 template and a synthetic business schema. Both entries parsed into
BONDI queries; finish reason was `stop`. Reported usage was 2,014 input tokens,
131 output tokens, and 2,145 total tokens; reasoning tokens were reported as zero.
Client latency was approximately 3.68 seconds. Billing metadata was `subscription`
with no API cost estimate. Queries were not executed against MongoDB.

The normalized usage attribution included 1,624 input tokens for request
instructions. Inspection of the installed provider confirms it prepends default
Codex instructions; therefore the rendered project prompt is not the entire model
input on this route. LiteLLM exposes `CHATGPT_DEFAULT_INSTRUCTIONS` to customize
those instructions. Before comparative experiments, explicitly fix and record
that instruction text (and the LiteLLM version) alongside the project prompt.
A reported zero reasoning count does not prove reasoning was disabled.


### Explicit subscription instructions

The adapter now replaces LiteLLM's coding-agent default with:

```text
You generate MongoDB queries. Follow the user's query instructions and response format exactly.
```

Every response records the exact string in `system_instructions`. API routes
send it as a system message; subscription routes use the LiteLLM instruction
override without duplicating it as a message. The adapter temporarily sets
`CHATGPT_DEFAULT_INSTRUCTIONS` during the call and restores its previous value,
even on failure. A process-local lock serializes calls through this adapter because
LiteLLM exposes this control through global environment state. Do not concurrently
make direct LiteLLM calls outside the adapter in the same process.
The constructor instruction takes precedence over a dotenv/environment override.
This replaces LiteLLM's added instructions, not any internal backend instructions.
The earlier live-validation figures above describe the old default prompt.


### Configuring system instructions

All routes default to the MongoDB instruction above. Override it for a prompt
experiment with `LiteLLMModel("provider/model-id", system_instructions="Your instructions.")`.
The value must be a nonblank string; empty values are rejected rather than allowing
LiteLLM to fall back to its coding-agent instructions. `DEFAULT_SYSTEM_INSTRUCTIONS`
is exported from `json_storm.models`. The instruction is recorded separately from
generation parameters. Identical supplied text improves comparison, but provider
message handling and internal backend instructions can still differ.

### Local Ollama validation (2026-11-03)

The existing adapter was tested against `ollama_chat/qwen3.6:latest` at
`http://localhost:11434`, with the shared MongoDB system instruction. A p3 prompt
requested two queries against a synthetic schema. Both parsed successfully;
reported usage was 430 input and 2,712 output tokens, with separate reasoning
content but no reasoning-token breakdown. Completion took approximately 42.15 s.
LiteLLM estimated API cost as zero; this excludes local compute costs.

A second, shorter one-query smoke test with `parameters={"think": False}` also
parsed successfully and returned no reasoning content (64 input, 19 output tokens,
approximately 0.53 s). These were different prompts, not a controlled timing
comparison. Neither test executed the generated queries against MongoDB.

```python
model = LiteLLMModel(
    "ollama_chat/qwen3.6:latest",
    api_base="http://localhost:11434",
    parameters={"think": False},  # omit to use the model's default behavior
)
```
