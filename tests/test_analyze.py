"""Run with: python3 -m unittest discover -s tests"""
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import analyze as a  # noqa: E402

CTX = {
    "repository": "o/r", "pull_request": 7,
    "meta": {"last_sha": "L", "body": "", "title": "t"},
    "review_threads": [{"id": 1, "path": "a.py", "body": "why 100?"}],
    "reviews": [], "issue_comments": [],
    "commits": [{"sha": "c", "after_first_review": True}],
    "diffs": [{"file": "a.py", "patch": "x"}, {"file": "b.py", "patch": "y"}],
    "diff_stat": [{"file": "a.py"}, {"file": "b.py"}],
}
GOOD = {
    "kind": "constraint", "scope": "general", "title": "t", "rule": "r", "problem": "p",
    "solution": "s", "reasoning": "why", "tags": ["x"], "confidence": 0.8,
    "evidence": {"files": ["a.py"], "review_comment_ids": [1]},
}


def block(lessons):
    return "chatter\n<lessons_json>" + json.dumps({"lessons": lessons}) + "</lessons_json>"


class ValidateTest(unittest.TestCase):
    def reason(self, **changes):
        return a.validate({**GOOD, **changes}, CTX)

    def test_good_lesson_is_accepted(self):
        self.assertIsNone(self.reason())

    def test_invalid_kind(self):
        self.assertTrue(self.reason(kind="rant").startswith("invalid kind"))

    def test_scope_required_and_project_rejected(self):
        self.assertTrue(self.reason(scope="nope").startswith("invalid scope"))
        self.assertTrue(self.reason(scope="project").startswith("project-specific"))

    def test_low_confidence(self):
        self.assertTrue(self.reason(confidence=0.2).startswith("confidence below"))

    def test_evidence_file_must_be_in_diff(self):
        r = self.reason(evidence={"files": ["nope.py"], "review_comment_ids": [1]})
        self.assertTrue(r.startswith("evidence.files"))

    def test_comment_required(self):
        r = self.reason(evidence={"files": ["a.py"], "review_comment_ids": []})
        self.assertTrue(r.startswith("no review comment cited"))

    def test_comment_must_match_evidence_file(self):
        r = self.reason(evidence={"files": ["b.py"], "review_comment_ids": [1]})
        self.assertTrue(r.startswith("cited review comment is on a file"))

    def test_comment_and_file_listed_together(self):
        r = self.reason(evidence={"files": ["a.py", "b.py"], "review_comment_ids": [1]})
        self.assertIsNone(r)


class ParseTest(unittest.TestCase):
    def test_closing_tag_optional(self):
        self.assertEqual(a.parse_output('<lessons_json>\n{"lessons": []}\n'), [])

    def test_trailing_text_ignored(self):
        self.assertEqual(
            a.parse_output('<lessons_json>{"lessons": []}}</lessons_json> more'), [])

    def test_missing_block(self):
        with self.assertRaises(ValueError):
            a.parse_output("no block")


class AnalyseTest(unittest.TestCase):
    def setUp(self):
        os.environ["ANALYZE_RETRY_SLEEP"] = "0"

    def test_accepts_and_rejects_and_caps(self):
        bad_file = {**GOOD, "evidence": {"files": ["nope.py"], "review_comment_ids": [1]}}
        bad_conf = {**GOOD, "confidence": 0.1}
        extra = {**GOOD, "title": "dropped by the cap"}
        out = a.analyse(CTX, "m", lambda p, m: block([GOOD, bad_file, bad_conf, extra]))
        self.assertEqual(len(out["lessons"]), 1)
        self.assertEqual(out["lessons"][0]["status"], "candidate")
        self.assertEqual(len(out["rejected"]), 2)

    def test_retries_then_succeeds(self):
        answers = iter(["no block", block([GOOD])])
        out = a.analyse(CTX, "m", lambda p, m: next(answers))
        self.assertEqual(len(out["lessons"]), 1)

    def test_fails_after_three_garbage_answers(self):
        answers = iter(["x", "y", "z"])
        with self.assertRaises(RuntimeError):
            a.analyse(CTX, "m", lambda p, m: next(answers))

    def test_empty_list_is_valid(self):
        self.assertEqual(a.analyse(CTX, "m", lambda p, m: block([]))["lessons"], [])

    def test_prompt_marks_context_untrusted(self):
        self.assertIn("untrusted", a.build_prompt(CTX))


class OpencodeConfigTest(unittest.TestCase):
    def test_every_tool_is_denied_and_no_mcp(self):
        cfg = a.opencode_config()
        self.assertTrue(cfg["permission"])
        self.assertEqual(set(cfg["permission"].values()), {"deny"})
        for tool in ("bash", "edit", "read", "webfetch", "external_directory"):
            self.assertEqual(cfg["permission"][tool], "deny")
        self.assertEqual(cfg["mcp"], {})


if __name__ == "__main__":
    unittest.main()
