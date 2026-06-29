import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("openai", types.SimpleNamespace(OpenAI=object))

import lib_llm_ext  # noqa: E402


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, content="ok"):
        self.content = content
        self.calls = []
        self.raise_on_create = False

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_on_create:
            raise RuntimeError("boom")
        return FakeResponse(self.content)


class FakeChat:
    def __init__(self, completions):
        self.completions = completions


class FakeClient:
    def __init__(self, content="ok"):
        self.completions = FakeCompletions(content)
        self.chat = FakeChat(self.completions)


class Patch5CProviderRoleSplitTests(unittest.TestCase):
    def make_provider(self, provider_cls=lib_llm_ext.AIProvider, content="ok"):
        provider = provider_cls("Fake", "FAKE_KEY", "fake-model", "http://example.invalid/v1")
        provider._client = FakeClient(content)
        return provider

    def test_generic_provider_sends_plain_content_as_single_user_message(self):
        provider = self.make_provider()

        result = provider.chat("plain user content", max_tokens=123)

        self.assertEqual(result, "ok")
        call = provider._client.completions.calls[-1]
        self.assertEqual(call["model"], "fake-model")
        self.assertEqual(call["max_tokens"], 123)
        self.assertEqual(call["messages"], [{"role": "user", "content": "plain user content"}])

    def test_generic_provider_splits_harness_prompt_and_live_user_message(self):
        provider = self.make_provider(content="clean _quote_reply_quote_")

        result = provider.chat("SYSTEM PROMPT:-:-:-:HUMAN TURN")

        self.assertEqual(result, 'clean "reply"')
        call = provider._client.completions.calls[-1]
        self.assertEqual(
            call["messages"],
            [
                {"role": "system", "content": "SYSTEM PROMPT"},
                {"role": "user", "content": "HUMAN TURN"},
            ],
        )

    def test_provider_splits_only_once(self):
        provider = self.make_provider()

        provider.chat("SYS:-:-:-:USER mentions :-:-:-: literally")

        call = provider._client.completions.calls[-1]
        self.assertEqual(
            call["messages"],
            [
                {"role": "system", "content": "SYS"},
                {"role": "user", "content": "USER mentions :-:-:-: literally"},
            ],
        )

    def test_openrouter_preserves_reasoning_extra_body_with_split_messages(self):
        provider = self.make_provider(lib_llm_ext.OpenRouterProvider)

        provider.chat("SYS:-:-:-:USER", max_tokens=456)

        call = provider._client.completions.calls[-1]
        self.assertEqual(
            call["messages"],
            [
                {"role": "system", "content": "SYS"},
                {"role": "user", "content": "USER"},
            ],
        )
        self.assertEqual(call["max_tokens"], 456)
        self.assertEqual(
            call["extra_body"],
            {
                "reasoning": {
                    "effort": "medium",
                    "exclude": True,
                }
            },
        )

    def test_openrouter_honors_env_model_provider_order_and_reasoning(self):
        provider = self.make_provider(lib_llm_ext.OpenRouterProvider)

        with mock.patch.dict(
            "os.environ",
            {
                "OMEGACLAW_OPENROUTER_MODEL": "qwen/qwen3.6-27b",
                "OMEGACLAW_OPENROUTER_PROVIDER_ORDER": "Provider A, Provider B",
                "OMEGACLAW_OPENROUTER_ALLOW_FALLBACKS": "0",
            },
            clear=False,
        ):
            provider.chat("SYS:-:-:-:USER", reasoning="high")

        call = provider._client.completions.calls[-1]
        self.assertEqual(call["model"], "qwen/qwen3.6-27b")
        self.assertEqual(
            call["extra_body"],
            {
                "reasoning": {"effort": "high", "exclude": True},
                "provider": {"order": ["Provider A", "Provider B"], "allow_fallbacks": False},
            },
        )

    def test_openrouter_disables_reasoning_with_none_and_provider_sort(self):
        provider = self.make_provider(lib_llm_ext.OpenRouterProvider)

        with mock.patch.dict(
            "os.environ",
            {
                "OMEGACLAW_OPENROUTER_PROVIDER_ORDER": "",
                "OMEGACLAW_OPENROUTER_PROVIDER_SORT": "throughput",
            },
            clear=False,
        ):
            provider.chat("SYS:-:-:-:USER", reasoning="none")

        call = provider._client.completions.calls[-1]
        self.assertEqual(
            call["extra_body"],
            {"reasoning": {"effort": "none", "exclude": True}, "provider": {"sort": "throughput"}},
        )

    def test_provider_exception_path_still_returns_empty_string(self):
        provider = self.make_provider()
        provider._client.completions.raise_on_create = True

        self.assertEqual(provider.chat("SYS:-:-:-:USER"), "")


if __name__ == "__main__":
    unittest.main()
