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


class MemoryTests(unittest.TestCase):
    SAMPLE = [
        {"bucket": "people", "key": "my accountant", "value": "Sarah Chen <sarah@firm.com>"},
        {"bucket": "preferences", "key": "email sign-off", "value": "Best, Alex"},
        {"bucket": "vocabulary", "key": "the deck", "value": "Q3-pitch.pptx"},
    ]

    def test_remember_array_is_parsed_and_validated(self):
        d = brain._parse_decision(
            '{"actions": [], "done": true, "reasoning_summary": "noted", "remember": ['
            '{"bucket": "people", "key": "my accountant", "value": "Sarah <s@x.com>"},'
            '{"bucket": "nonsense", "key": "x", "value": "y"},'      # unknown bucket -> dropped
            '{"bucket": "preferences", "key": "", "value": "z"}]}',  # empty key -> dropped
            allow_coords=False)
        self.assertEqual(d["remember"],
                         [{"bucket": "people", "key": "my accountant", "value": "Sarah <s@x.com>"}])

    def test_remember_defaults_to_empty_list(self):
        d = brain._parse_decision(GOOD_REPLY, allow_coords=False)
        self.assertEqual(d["remember"], [])

    def test_saved_facts_render_into_the_system_prompt_grouped(self):
        sp = brain._system_prompt(frozenset(), self.SAMPLE)
        self.assertIn("my accountant = Sarah Chen <sarah@firm.com>", sp)
        self.assertIn("email sign-off = Best, Alex", sp)
        self.assertIn("the deck = Q3-pitch.pptx", sp)
        # grouped under bucket headers, in the canonical order
        self.assertLess(sp.index("people:"), sp.index("preferences:"))
        self.assertLess(sp.index("preferences:"), sp.index("vocabulary:"))

    def test_memory_rules_present_even_with_no_saved_facts(self):
        sp = brain._system_prompt(frozenset(), None)
        self.assertIn("(nothing saved yet)", sp)
        for rule in ("RESOLVE references", "ONE QUESTION", "REMEMBER on request"):
            self.assertIn(rule, sp)

    def test_build_messages_injects_memory_into_the_system_message(self):
        msgs = brain._build_messages("email my accountant", "a window", None, None,
                                     frozenset(), self.SAMPLE)
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("Sarah Chen <sarah@firm.com>", msgs[0]["content"])


class AnswerFieldTests(unittest.TestCase):
    """The 'answer' field (Wave 2 'read it back'): the reply to a question about
    on-screen content. Parsed from the model reply, coerced to a capped string,
    defaulting to None for every command that does something instead of answering."""

    def test_answer_parsed_from_reply(self):
        d = brain._parse_decision(
            '{"actions": [], "done": true, "reasoning_summary": "reading the total",'
            ' "answer": "The total in A6 is $42.50."}',
            allow_coords=False)
        self.assertEqual(d["answer"], "The total in A6 is $42.50.")

    def test_answer_defaults_to_none_when_absent(self):
        # A doing-command (the common case) carries no answer.
        d = brain._parse_decision(GOOD_REPLY, allow_coords=False)
        self.assertIsNone(d["answer"])

    def test_answer_is_capped_at_2000_chars(self):
        long = "x" * 5000
        d = brain._parse_decision(
            f'{{"actions": [], "done": true, "reasoning_summary": "r", "answer": "{long}"}}',
            allow_coords=False)
        self.assertEqual(len(d["answer"]), 2000)

    def test_whitespace_only_answer_becomes_none(self):
        d = brain._parse_decision(
            '{"actions": [], "done": true, "reasoning_summary": "r", "answer": "   "}',
            allow_coords=False)
        self.assertIsNone(d["answer"])

    def test_answer_is_always_present_in_decision_shape(self):
        # Every decision carries the key, even on a safe-degrade empty plan.
        d = brain._parse_decision("total garbage", allow_coords=False)
        self.assertIn("answer", d)
        self.assertIsNone(d["answer"])


if __name__ == "__main__":
    unittest.main()
