from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Patch5BLoopSpamguardTests(unittest.TestCase):
    def setUp(self):
        self.loop = (ROOT / "src" / "loop.metta").read_text(encoding="utf-8")

    def test_loop_uses_neutral_no_new_message_state_without_spamshield(self):
        self.assertNotIn("spamShield", self.loop)
        self.assertNotIn("DO NOT RE-SEND OR SPAM", self.loop)
        self.assertIn('"NO_NEW_HUMAN_MESSAGE"', self.loop)
        self.assertIn('(if $msgnew (HUMAN-MSG: $msg) "NO_NEW_HUMAN_MESSAGE")', self.loop)


if __name__ == "__main__":
    unittest.main()
