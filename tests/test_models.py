"""Offline adapter tests: no provider credentials or calls required."""

from types import SimpleNamespace

import litellm
import pytest

from json_storm.models import DEFAULT_SYSTEM_INSTRUCTIONS, LiteLLMModel, load_credentials


@pytest.fixture
def response(monkeypatch):
    usage = dict(
        prompt_tokens=100,
        completion_tokens=40,
        total_tokens=140,
        completion_tokens_details={"reasoning_tokens": 25},
        prompt_tokens_details={"cached_tokens": 50},
        provider_detail=7,
    )
    result = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"queries": []}', reasoning_content="separate reasoning"
                ),
                finish_reason="length",
            )
        ],
        usage=SimpleNamespace(model_dump=lambda **kwargs: usage),
        model="returned-model",
        id="id-1",
    )
    monkeypatch.setattr(litellm, "completion", lambda **kwargs: result)
    monkeypatch.setattr(litellm, "completion_cost", lambda **kwargs: 0.001)
    return result


def test_usage_cost_and_reasoning_are_separate(response):
    result = LiteLLMModel("provider/model").generate("prompt")
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (100, 40, 140)
    assert result.reasoning_tokens == 25 and result.cached_input_tokens == 50
    assert result.usage["provider_detail"] == 7
    assert result.text == '{"queries": []}' and result.reasoning_content == "separate reasoning"
    assert result.estimated_cost_usd == 0.001 and result.cost_status == "estimated"
    assert result.finish_reason == "length" and result.response_id == "id-1"
    assert result.returned_model == "returned-model" and result.elapsed_ms >= 0


def test_parameters_and_request_controls(monkeypatch, response):
    seen = {}

    def complete(**kwargs):
        seen.update(kwargs)
        return response

    monkeypatch.setattr(litellm, "completion", complete)
    params = {"reasoning_effort": "low", "thinking": {"budget_tokens": 1024}}
    model = LiteLLMModel("provider/model", parameters=params, api_base="http://localhost:11434")
    params["thinking"]["budget_tokens"] = 9
    result = model.generate("exact prompt")
    assert seen["thinking"]["budget_tokens"] == 1024
    assert seen["messages"] == [
        {"role": "system", "content": DEFAULT_SYSTEM_INSTRUCTIONS},
        {"role": "user", "content": "exact prompt"},
    ]
    assert seen["num_retries"] == 0 and seen["drop_params"] is False
    assert seen["stream"] is False and seen["caching"] is False and seen["n"] == 1
    assert result.parameters["reasoning_effort"] == "low"


def test_missing_usage_and_cost_failure_keep_response(monkeypatch, response):
    response.usage = None
    response.choices[0].message.content = None

    def fail(**kwargs):
        raise ValueError("unknown pricing")

    monkeypatch.setattr(litellm, "completion_cost", fail)
    result = LiteLLMModel("unknown/model").generate("prompt")
    assert result.usage is None and result.input_tokens is None and result.reasoning_tokens is None
    assert result.estimated_cost_usd is None and result.cost_status == "unavailable"
    assert result.text is None and result.finish_reason == "length"


def test_provider_failure_propagates_without_retry(monkeypatch):
    calls = []
    error = RuntimeError("provider failure")

    def fail(**kwargs):
        calls.append(kwargs)
        raise error

    monkeypatch.setattr(litellm, "completion", fail)
    with pytest.raises(RuntimeError) as caught:
        LiteLLMModel("provider/model").generate("prompt")
    assert caught.value is error and len(calls) == 1


@pytest.mark.parametrize(
    "params",
    [{"api_key": "secret"}, {"stream": True}, {"drop_params": True}, {"num_retries": 3}, {"n": 2}],
)
def test_reserved_parameters(params):
    with pytest.raises(ValueError):
        LiteLLMModel("provider/model", parameters=params)


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), float("nan")])
def test_invalid_timeout(timeout):
    with pytest.raises(ValueError):
        LiteLLMModel("provider/model", timeout_seconds=timeout)


def test_explicit_dotenv_preserves_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("STORM_EXISTING", "environment")
    monkeypatch.delenv("STORM_NEW", raising=False)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    path = tmp_path / ".env"
    path.write_text("STORM_EXISTING=file\nSTORM_NEW=loaded\n")
    try:
        assert load_credentials(path)
        import os

        assert os.environ["STORM_EXISTING"] == "environment"
        assert os.environ["STORM_NEW"] == "loaded"
    finally:
        monkeypatch.delenv("STORM_NEW", raising=False)
    with pytest.raises(FileNotFoundError):
        load_credentials(tmp_path / "missing")


@pytest.mark.parametrize(
    "name", ["max_tokens", "max_output_tokens", "max_completion_tokens", "extra_body"]
)
def test_subscription_rejects_silently_dropped_settings(name):
    with pytest.raises(ValueError):
        LiteLLMModel("chatgpt/test-model", parameters={name: 20})


def test_subscription_preserves_usage_but_does_not_estimate_api_cost(monkeypatch, response):
    def forbidden(**kwargs):
        pytest.fail("Subscription must not calculate API cost")

    monkeypatch.setattr(litellm, "completion_cost", forbidden)
    result = LiteLLMModel("chatgpt/test-model", parameters={"reasoning_effort": "low"}).generate(
        "prompt"
    )
    assert result.billing_mode == "subscription"
    assert result.cost_status == "subscription" and result.estimated_cost_usd is None
    assert result.input_tokens == 100 and result.reasoning_tokens == 25


@pytest.mark.parametrize("previous", [None, "existing instructions"])
def test_subscription_instructions_replace_defaults_and_restore_environment(
    monkeypatch, response, previous
):
    import os

    from json_storm.models import DEFAULT_SYSTEM_INSTRUCTIONS

    key = "CHATGPT_DEFAULT_INSTRUCTIONS"
    if previous is None:
        monkeypatch.delenv(key, raising=False)
    else:
        monkeypatch.setenv(key, previous)

    def complete(**kwargs):
        from litellm.llms.chatgpt.common_utils import get_chatgpt_default_instructions

        assert get_chatgpt_default_instructions() == DEFAULT_SYSTEM_INSTRUCTIONS
        return response

    monkeypatch.setattr(litellm, "completion", complete)
    result = LiteLLMModel("chatgpt/test-model").generate("prompt")
    assert result.system_instructions == DEFAULT_SYSTEM_INSTRUCTIONS
    assert os.environ.get(key) == previous


def test_subscription_failure_restores_instructions(monkeypatch):
    import os

    monkeypatch.setenv("CHATGPT_DEFAULT_INSTRUCTIONS", "original")

    def fail(**kwargs):
        raise RuntimeError("failed")

    monkeypatch.setattr(litellm, "completion", fail)
    with pytest.raises(RuntimeError):
        LiteLLMModel("chatgpt/test-model").generate("prompt")
    assert os.environ["CHATGPT_DEFAULT_INSTRUCTIONS"] == "original"


def test_other_providers_record_default_instructions(response):
    assert (
        LiteLLMModel("provider/model").generate("prompt").system_instructions
        == DEFAULT_SYSTEM_INSTRUCTIONS
    )


@pytest.mark.parametrize("route", ["provider/model", "chatgpt/test-model"])
def test_custom_system_instructions_are_sent_once_and_recorded(monkeypatch, response, route):
    def complete(**kwargs):
        if route.startswith("chatgpt/"):
            from litellm.llms.chatgpt.common_utils import get_chatgpt_default_instructions

            assert get_chatgpt_default_instructions() == "Custom instruction."
            assert kwargs["messages"] == [{"role": "user", "content": "prompt"}]
        else:
            assert kwargs["messages"] == [
                {"role": "system", "content": "Custom instruction."},
                {"role": "user", "content": "prompt"},
            ]
        return response

    monkeypatch.setattr(litellm, "completion", complete)
    result = LiteLLMModel(route, system_instructions="Custom instruction.").generate("prompt")
    assert result.system_instructions == "Custom instruction."


@pytest.mark.parametrize("value", [None, "", "  ", 1])
def test_system_instruction_must_be_nonblank(value):
    with pytest.raises(ValueError):
        LiteLLMModel("provider/model", system_instructions=value)
