import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Patch4ContinuityContextTests(unittest.TestCase):
    def setUp(self):
        self.helper = load_module("helper_patch4_context", ROOT / "src" / "helper.py")
        self.lib = (ROOT / "lib_omegaclaw.metta").read_text(encoding="utf-8")
        self.memory = (ROOT / "src" / "memory.metta").read_text(encoding="utf-8")
        self.loop = (ROOT / "src" / "loop.metta").read_text(encoding="utf-8")
        self.context_policy = (ROOT / "src" / "harness_context.metta").read_text(encoding="utf-8")

    def with_history(self, text, fn):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.metta"
            path.write_text(text, encoding="utf-8")
            self.helper._core_memory_path = lambda name: path
            self.helper._CONTEXT_POLICY_CACHE = None
            return fn()

    def test_context_policy_imports_after_feedback(self):
        self.assertIn("./src/harness_context", self.lib)
        self.assertLess(self.lib.index("./src/harness_feedback"), self.lib.index("./src/harness_context"))

    def test_loop_and_memory_use_context_views(self):
        self.assertIn("(py-call (helper.context_history_view (maxHistory)))", self.memory)
        self.assertIn("helper.context_lastresults_view", self.loop)
        self.assertNotIn("(last_chars (get-state &lastresults) (maxFeedback))", self.loop)

    def test_policy_atoms_define_continuity_windows(self):
        for atom in (
            "(ContextWindow human-message full 1)",
            "(ContextWindow pin compact 7)",
            "(ContextWindow send exact 6)",
            "(ContextWindow artifact-pointer compact 16)",
            "(ContextNoCompact send)",
            "(ContextOmitAlways prompt-echo)",
            "(ContextOmitAlways anti-spam-echo)",
            "(ContextCollapse repeated-skill-result)",
            "(ContextPointer artifact-pointer)",
        ):
            self.assertIn(atom, self.context_policy)

    def test_history_view_keeps_recent_humans_pins_and_exact_sends(self):
        history = """
("2026-06-28 00:00:00"
 "HUMAN_MESSAGE: " first request
 ((pin "mode one") (send "first exact send")))
("2026-06-28 00:01:00"
 "HUMAN_MESSAGE: " second request
 ((pin "mode two") (send "second exact send with query word inside prose")))
("2026-06-28 00:02:00"
 ((pin "mode three") (send "third exact send")))
("2026-06-28 00:03:00"
 ((pin "mode four") (send "fourth exact send")))
("2026-06-28 00:04:00"
 ((pin "mode five") (send "fifth exact send")))
"""

        def run():
            return self.helper.context_history_view(12000)

        view = self.with_history(history, run)
        self.assertIn("HUMAN_RECENT:", view)
        self.assertIn("latest time=2026-06-28 00:01:00: second request", view)
        self.assertIn("PIN_RECENT:", view)
        self.assertIn("latest time=2026-06-28 00:04:00: mode five", view)
        self.assertIn("previous[3] time=2026-06-28 00:01:00: mode two", view)
        self.assertIn("mode one", view)
        self.assertIn("SEND_RECENT:", view)
        self.assertIn("fifth exact send", view)
        self.assertIn("second exact send with query word inside prose", view)
        self.assertIn("first exact send", view)
        self.assertNotIn("older-pin x1", view)
        self.assertNotIn("older-send x1", view)

    def test_prompt_echo_and_antispam_are_omitted_from_history_view(self):
        history = """
("2026-06-28 00:00:00"
 "HUMAN_MESSAGE: " hello
 ((send "visible send")))
("2026-06-28 00:01:00"
 CHARS_SENT: 999 PROMPT: noisy SKILLS: noisy OUTPUT_FORMAT: noisy LAST_SKILL_USE_RESULTS: noisy HISTORY: noisy)
("2026-06-28 00:02:00"
 DO NOT RE-SEND OR SPAM!)
"""

        view = self.with_history(history, lambda: self.helper.context_history_view(12000))
        self.assertIn("visible send", view)
        self.assertNotIn("PROMPT: noisy", view)
        self.assertNotIn("DO NOT RE-SEND OR SPAM", view)
        self.assertIn("prompt-echo x1", view)
        self.assertIn("anti-spam-echo x1", view)

    def test_lastresults_view_keeps_skill_atoms_and_bounds_raw_payload(self):
        token = "SKILL" + "_RESULT"
        raw = f'(RESULTS: (({token} search success) ({token} search success) (COMMAND_RETURN: ((search "x") "wrote /tmp/report.md ' + ("payload " * 2000) + '"))))'
        view = self.helper.context_lastresults_view(raw, 4000)
        self.assertIn(f"({token} search success) x2", view)
        self.assertIn("ARTIFACT_POINTERS:", view)
        self.assertIn("path=/tmp/report.md", view)
        self.assertIn("mechanically-excerpted", view)
        self.assertLessEqual(len(view), 4200)

    def test_wake_chatter_is_not_rendered_as_recent_human(self):
        history = """
("2026-06-28 00:00:00"
 "HUMAN_MESSAGE: " Wake pulse 1. Continue only if needed.
 ((send "standing by")))
("2026-06-28 00:01:00"
 "HUMAN_MESSAGE: " real request
 ((send "real answer")))
"""
        view = self.with_history(history, lambda: self.helper.context_history_view(12000))
        self.assertIn("latest time=2026-06-28 00:01:00: real request", view)
        self.assertNotIn("Wake pulse 1. Continue only if needed.", view)
        self.assertIn("wake-chatter x1", view)

    def test_history_view_retains_unique_artifact_pointers(self):
        history = """
("2026-06-28 00:00:00"
 ((write-file "/tmp/report.md" "first body")))
("2026-06-28 00:01:00"
 ((send "I wrote /tmp/report.md and notes.json")))
("2026-06-28 00:02:00"
 ((read-file "/tmp/report.md")))
"""
        view = self.with_history(history, lambda: self.helper.context_history_view(12000))
        self.assertIn("ARTIFACT_POINTERS:", view)
        self.assertEqual(view.count("path=/tmp/report.md"), 1)
        self.assertIn("path=notes.json", view)

    def test_error_recent_is_bounded_without_reinserting_prompt_scaffolding(self):
        noisy_raw = (
            "LAST_SKILL_USE_RESULTS: LAST_RESULTS_VIEW: "
            "SKILL_RESULTS: RAW_RESULTS: HISTORY: CONTEXT_VIEW: "
            "HUMAN_RECENT: latest time=2026-06-28 00:00:00: hello "
            "Capability card: send: send message; role=human-facing-speech; "
            "A syntax error means nothing was done."
        )
        history = f'''
("2026-06-28 00:00:00"
 ((syntax-error "unknown-command" "LAST_SKILL_USE_RESULTS" "{noisy_raw}" "Use a command listed in SKILLS. Capability card: send: send message; role=human-facing-speech; A syntax error means nothing was done."))
)
'''

        view = self.with_history(history, lambda: self.helper.context_history_view(12000))

        self.assertIn("ERROR_RECENT:", view)
        self.assertIn("kind=unknown-command", view)
        self.assertIn("head=LAST_SKILL_USE_RESULTS", view)
        self.assertIn("raw_head=LAST_SKILL_USE_RESULTS", view)
        self.assertIn("body_preview=LAST_SKILL_USE_RESULTS <omitted raw-history-preserved>", view)
        self.assertIn("hash=", view)
        self.assertNotIn("RAW_RESULTS:", view)
        self.assertNotIn("HISTORY:", view)
        self.assertNotIn("HUMAN_RECENT:", view)
        self.assertNotIn("Capability card:", view)

    def test_error_recent_is_capped_to_three_compact_records_by_policy(self):
        history = "\n".join(
            f'''("2026-06-28 00:0{i}:00"\n ((syntax-error "unknown-command" "bad{i}" "bad{i} body" "generic hint"))\n)'''
            for i in range(5)
        )

        view = self.with_history(history, lambda: self.helper.context_history_view(12000))

        self.assertIn("ERROR_RECENT:", view)
        self.assertIn("head=bad4", view)
        self.assertIn("head=bad3", view)
        self.assertIn("head=bad2", view)
        self.assertNotIn("head=bad1", view)
        self.assertNotIn("head=bad0", view)
        self.assertIn("older-error x2", view)

    def test_renderer_changes_when_metta_policy_window_changes(self):
        history = """
("2026-06-28 00:00:00" ((send "one")))
("2026-06-28 00:01:00" ((send "two")))
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            history_path = tmp / "history.metta"
            policy_path = tmp / "harness_context.metta"
            history_path.write_text(history, encoding="utf-8")
            policy_path.write_text("(ContextWindow send exact 1)\n(ContextNoCompact send)\n", encoding="utf-8")
            self.helper._core_memory_path = lambda name: history_path
            self.helper.CONTEXT_POLICY_PATH = policy_path
            self.helper._CONTEXT_POLICY_CACHE = None
            one = self.helper.context_history_view(12000)
            policy_path.write_text("(ContextWindow send exact 2)\n(ContextNoCompact send)\n", encoding="utf-8")
            self.helper._CONTEXT_POLICY_CACHE = None
            two = self.helper.context_history_view(12000)
        self.assertIn("two", one)
        self.assertNotIn("one", one)
        self.assertIn("two", two)
        self.assertIn("one", two)


if __name__ == "__main__":
    unittest.main()
