import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Patch3MinimalSkillResultTests(unittest.TestCase):
    def setUp(self):
        self.feedback = (ROOT / "src" / "harness_feedback.metta").read_text(encoding="utf-8")
        self.loop = (ROOT / "src" / "loop.metta").read_text(encoding="utf-8")
        self.lib = (ROOT / "lib_omegaclaw.metta").read_text(encoding="utf-8")
        self.helper_text = (ROOT / "src" / "helper.py").read_text(encoding="utf-8")
        self.helper = load_module("helper_patch3_minimal", ROOT / "src" / "helper.py")

    def test_feedback_imports_after_descriptors(self):
        self.assertIn("./src/harness_feedback", self.lib)
        self.assertLess(self.lib.index("./src/harness_descriptors"), self.lib.index("./src/harness_feedback"))

    def test_loop_only_delegates_lastresults_compiler(self):
        self.assertIn("($results (feedback-eval-results $sexpr))", self.loop)
        self.assertIn("(change-state! &lastresults (feedback-render-lastresults $results (get-state &lastresults)))", self.loop)
        self.assertIn("(println! (feedback-debug-results $results))", self.loop)
        self.assertNotIn("helper.normalize_string $R", self.loop)
        self.assertNotIn("&feedbackReport", self.loop)

    def test_skill_result_shape_is_fixed_width_and_payload_free(self):
        self.assertIn("(SKILL_RESULT (skill-result-command-head $shape) (skill-result-status $shape $result))", self.feedback)
        self.assertNotIn("(SkillResult ", self.feedback)
        self.assertNotIn("excerpt", self.feedback)
        self.assertNotIn("hint", self.feedback)
        self.assertNotIn("class", self.feedback)
        self.assertNotIn("kind", self.feedback)
        self.assertNotIn("next", self.feedback)

    def test_command_return_keeps_existing_payload_transport(self):
        self.assertIn("(COMMAND_RETURN: ($command $normalized))", self.feedback)
        self.assertIn("helper.normalize_string $R", self.feedback)
        self.assertNotIn("COMMAND_RETURN: ($command $raw $", self.feedback)
        self.assertNotIn("COMMAND_RETURN: ($command $rawResult", self.feedback)

    def test_statuses_are_minimal(self):
        for status in ("success", "empty", "rejected", "failed", "timeout"):
            self.assertIn(f"(SkillResultStatus {status})", self.feedback)
        self.assertIn("((SYNTAX-ERROR $a $b $c $d) rejected)", self.feedback)
        self.assertIn("(timeout_error timeout)", self.feedback)
        self.assertIn("((Error $a $b) failed)", self.feedback)
        self.assertIn("(() (skill-result-empty-status $shape))", self.feedback)

    def test_empty_no_action_preserves_previous_lastresults(self):
        self.assertIn("(if (== $items ())", self.feedback)
        self.assertIn("       $previous", self.feedback)

    def test_python_shape_membrane_is_syntax_only(self):
        self.assertEqual(self.helper.describe_command_shape('(query "x")'), '(CommandShape query)')
        self.assertEqual(self.helper.describe_command_shape('(shell "echo hi")'), '(CommandShape shell)')
        self.assertEqual(self.helper.describe_command_shape('(syntax-error "k" "h" "r" "hint")'), '(CommandShape syntax-error)')
        self.assertEqual(self.helper.describe_command_shape('(not-a-command "x")'), '(CommandShape unknown)')
        self.assertEqual(self.helper.describe_command_shape('plain text'), '(CommandShape unknown)')

    def test_python_does_not_classify_result_meaning(self):
        forbidden = (
            "WRITE-FILE-SUCCESS",
            "APPEND-FILE-SUCCESS",
            "REMEMBER-SUCCESS",
            "PIN-SUCCESS",
            "timeout_error",
            "SYNTAX-ERROR",
            "SKILL_RESULT",
        )
        for token in forbidden:
            self.assertNotIn(token, self.helper_text)


if __name__ == "__main__":
    unittest.main()
