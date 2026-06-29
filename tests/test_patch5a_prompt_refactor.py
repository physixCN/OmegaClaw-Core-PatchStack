from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Patch5APromptRefactorTests(unittest.TestCase):
    def setUp(self):
        self.prompt = (ROOT / "memory" / "prompt.txt").read_text(encoding="utf-8")
        self.asi_prompt = (ROOT / "memory" / "prompt_ASICloud.txt").read_text(encoding="utf-8")

    def test_default_and_asicloud_prompts_share_clean_refactor(self):
        self.assertEqual(self.prompt, self.asi_prompt)
        self.assertIn("neural-symbolic autonomous cognitive framework", self.prompt)
        self.assertIn("the LLM is the orchestrator", self.prompt)
        self.assertIn("AGI research project", self.prompt)
        self.assertIn("You are not a tool. You are a partner.", self.prompt)
        self.assertIn("Hallucinated answers are unacceptable.", self.prompt)
        self.assertIn("Before responding to a fresh human message, query memory", self.prompt)
        self.assertIn("ordinary family/team presence can be valid", self.prompt)

    def test_prompt_removes_fixed_cycle_and_spam_pressure(self):
        banned = (
            "ALWAYS query before responding anything",
            "Take at least 5 agent cycles",
            "DO NOT RE-SEND OR SPAM",
            "Do not repeat the information once sent",
            "Wait until user responds",
            "A send command is only valid if triggered by",
        )
        for text in (self.prompt, self.asi_prompt):
            for phrase in banned:
                self.assertNotIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
