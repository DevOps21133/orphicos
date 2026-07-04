"""Tests for the brain's output-resilience layer: JSON extraction, the single
corrective retry on unparseable/truncated model replies, and usage metadata.

The LLM call boundary (_create_completion / _get_client) is patched with clearly
labeled TEST FIXTURES (CLAUDE.md Rule 14's unit-test exception) — everything from
the reply string down through parsing and retry control flow is the real code.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from server import brain

GOOD_REPLY = ('{"actions": [{"type": "launch", "target_selector": null, "coords": null, '
              '"value": "notepad"}], "done": true, "need_screenshot": false, '
              '"skill": null, "reasoning_summary": "launching"}')


def _completion(content, finish="stop", ptok=100, ctok=50):
    # TEST FIXTURE (Rule 14 exception): stands in for one provider completion.
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content),
                                 finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=ptok, completion_tokens=ctok,
                              total_tokens=ptok + ctok),
    )


def _decide(replies):
    with patch.object(brain, "_get_client", return_value=object()), \
         patch.object(brain, "_create_completion", side_effect=replies) as calls:
        decision, usage = brain.decide("open notepad", "a window")
    return decision, usage, calls


class ExtractJsonTests(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(brain._extract_json('{"done": true}'), {"done": True})

    def test_fenced_and_prose_wrapped(self):
        self.assertEqual(brain._extract_json('```json\n{"done": true}\n```'), {"done": True})
        self.assertEqual(brain._extract_json('Sure! {"done": true} — done.'), {"done": True})

    def test_unparseable_is_none_not_empty_decision(self):
        for garbage in ("", "I could not decide.", '{"actions": [truncated',
                        "[1, 2, 3]", "null"):
            self.assertIsNone(brain._extract_json(garbage), garbage)

    def test_parse_decision_still_degrades_safely(self):
        d = brain._parse_decision("total garbage", allow_coords=False)
        self.assertEqual(d["actions"], [])
        self.assertFalse(d["done"])

    def test_wait_for_timeout_passes_through_and_coerces(self):
        d = brain._parse_decision(
            '{"actions": ['
            '{"type": "wait_for", "value": "gone:Installing", "timeout": 180},'
            '{"type": "press", "value": "enter"},'
            '{"type": "wait_for", "value": "Save As", "timeout": "oops"}], "done": false}',
            allow_coords=False)
        self.assertEqual(d["actions"][0]["timeout"], 180.0)   # long-op override survives
        self.assertIsNone(d["actions"][1]["timeout"])         # absent -> None (short default)
        self.assertIsNone(d["actions"][2]["timeout"])         # bad value -> None, never crashes


class RetryTests(unittest.TestCase):
    def test_clean_reply_never_retries(self):
        decision, usage, calls = _decide([_completion(GOOD_REPLY)])
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(decision["actions"][0]["value"], "notepad")
        self.assertTrue(usage["parse_ok"])
        self.assertFalse(usage["retried"])
        self.assertEqual(usage["finish_reason"], "stop")

    def test_unparseable_reply_is_retried_once_with_a_nudge(self):
        decision, usage, calls = _decide(
            [_completion('{"actions": [{"type": "launch", cut off'),
             _completion(GOOD_REPLY)])
        self.assertEqual(calls.call_count, 2)
        self.assertEqual(decision["actions"][0]["type"], "launch")
        self.assertTrue(usage["parse_ok"])
        self.assertTrue(usage["retried"])
        retry_messages = calls.call_args_list[1].args[2]
        self.assertEqual(retry_messages[-1]["role"], "user")
        self.assertIn("ONLY the JSON object", retry_messages[-1]["content"])
        self.assertEqual(retry_messages[-2]["role"], "assistant")

    def test_token_cap_cutoff_is_retried_even_if_prefix_parsed(self):
        # finish_reason "length" means the plan was cut off: a JSON object salvaged
        # from the prefix could silently drop the tail of the plan.
        decision, usage, calls = _decide(
            [_completion(GOOD_REPLY, finish="length"),
             _completion(GOOD_REPLY)])
        self.assertEqual(calls.call_count, 2)
        self.assertTrue(usage["retried"])
        self.assertEqual(usage["finish_reason"], "stop")

    def test_two_bad_replies_degrade_to_the_safe_empty_decision(self):
        decision, usage, calls = _decide(
            [_completion(""), _completion("still not json")])
        self.assertEqual(calls.call_count, 2)
        self.assertEqual(decision["actions"], [])
        self.assertFalse(decision["done"])
        self.assertFalse(usage["parse_ok"])
        self.assertTrue(usage["retried"])

    def test_usage_tokens_accumulate_across_the_retry(self):
        _, usage, _ = _decide(
            [_completion("garbage", ptok=1000, ctok=2000),
             _completion(GOOD_REPLY, ptok=1100, ctok=80)])
        self.assertEqual(usage["prompt_tokens"], 2100)
        self.assertEqual(usage["completion_tokens"], 2080)
        self.assertEqual(usage["total_tokens"], 4180)


if __name__ == "__main__":
    unittest.main()
