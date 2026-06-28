import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Patch2CapabilitySurfaceTests(unittest.TestCase):
    def setUp(self):
        self.helper = load_module("helper", ROOT / "src" / "helper.py")

    def test_descriptors_are_metta_source_of_truth_for_command_names(self):
        descriptors = self.helper._load_capability_descriptors()
        self.assertIn("send", descriptors)
        self.assertIn("search", descriptors)
        self.assertIn("metta", descriptors)
        self.assertNotIn("nal", descriptors)
        self.assertNotIn("pln", descriptors)
        self.assertNotIn("web-search", descriptors)
        self.assertEqual(
            tuple(arg["type"] for arg in descriptors["write-file"]["args"]),
            ("path", "body-text"),
        )
        self.assertEqual(descriptors["send"]["body_mode"], "multiline-rest")

    def test_python_does_not_duplicate_command_surface_constants(self):
        helper_text = (ROOT / "src" / "helper.py").read_text(encoding="utf-8")
        self.assertNotIn("LLM_COMMANDS =", helper_text)
        self.assertNotIn("append-file|episodes|metta|pin|query", helper_text)
        self.assertNotIn("_DEFAULT_CAPABILITY_CONTRACTS", helper_text)
        self.assertNotIn("_DEFAULT_BODY_MODES", helper_text)
        self.assertIn("_FALLBACK_CAPABILITY_DESCRIPTOR_TEXT", helper_text)
        fallback = self.helper._fallback_capability_descriptors()
        self.assertEqual(
            tuple(arg["type"] for arg in fallback["write-file"]["args"]),
            ("path", "body-text"),
        )

    def test_getskills_context_is_descriptor_derived_and_compact(self):
        rendered = self.helper.render_capability_context()
        self.assertIn("Commands are one per line", rendered)
        self.assertIn("Syntax core", rendered)
        self.assertIn("Action core", rendered)
        self.assertIn("Memory core", rendered)
        self.assertIn("Grounding core", rendered)
        self.assertIn("Evidence discipline", rendered)
        self.assertIn("wait for LAST_SKILL_USE_RESULTS", rendered)
        self.assertIn("Truth core", rendered)
        self.assertIn("Reporting core", rendered)
        self.assertIn("pin is Omega's live RAM/liveness frame", rendered)
        self.assertIn("remember writes durable long-term semantic memory", rendered)
        self.assertIn("query searches remembered memory", rendered)
        self.assertIn("episodes searches exact raw history", rendered)
        self.assertIn("Put human-facing prose in send", rendered)
        self.assertIn("- send: send message", rendered)
        self.assertIn("- write-file: write-file filename text OR write-file filename <<TAG", rendered)
        self.assertIn("- append-file: append-file filename text OR append-file filename <<TAG", rendered)
        self.assertIn("- search: search query", rendered)
        self.assertIn("- metta: metta (balanced expression)", rendered)
        self.assertIn("Always-on syntax guides", rendered)
        self.assertIn("pin is Omega's primary continuity/autonomy skill", rendered)
        self.assertIn("shell executes OS text only", rendered)
        self.assertIn("write-file creates artifacts", rendered)
        self.assertIn("send is Omega's human speech channel", rendered)
        self.assertIn("Use readable human formatting in send", rendered)
        self.assertIn("search retrieves live external evidence", rendered)
        self.assertIn("After search, wait for LAST_SKILL_USE_RESULTS before dependent claims", rendered)
        self.assertIn("After read-file, wait for LAST_SKILL_USE_RESULTS before dependent claims", rendered)
        self.assertIn("After shell, wait for LAST_SKILL_USE_RESULTS before dependent claims", rendered)
        self.assertIn("After query, wait for LAST_SKILL_USE_RESULTS before dependent claims", rendered)
        self.assertIn("After episodes, wait for LAST_SKILL_USE_RESULTS before dependent claims", rendered)
        self.assertIn("After metta, wait for LAST_SKILL_USE_RESULTS before dependent claims", rendered)
        self.assertIn("metta is Omega's inspectable truth-maintenance substrate", rendered)
        self.assertIn("Use NAL with (|- ...)", rendered)
        self.assertIn("Use PLN with (|~ ...)", rendered)
        self.assertIn("Truth values use (stv frequency confidence)", rendered)
        self.assertIn("(|- ...)", rendered)
        self.assertIn("(|~ ...)", rendered)
        self.assertIn("stv", rendered)
        self.assertIn("Also accepted: direct balanced parenthesized MeTTa", rendered)
        self.assertIn("top-level bang-prefixed MeTTa", rendered)
        self.assertIn("do not prefix it with direct-metta", rendered)
        self.assertLess(len(rendered), 5500)
        self.assertNotIn("remember only stable reusable lessons", rendered)
        self.assertNotIn("CapabilityContract", rendered)
        self.assertNotIn("CapabilityDescriptor", rendered)
        self.assertNotIn("text|<<TAG", rendered)
        self.assertNotIn("send command", rendered)
        self.assertNotIn("Arg", rendered)
        self.assertNotIn("rest-text", rendered)
        self.assertNotIn("concise-human-message", rendered)
        self.assertNotIn("command words, Markdown fences, tables, quotes, and MeTTa-looking text are raw file data", rendered)
        self.assertNotIn("Artifact composition can use", rendered)
        self.assertNotIn("put next commands after the terminator", rendered)
        self.assertNotIn("must read-file", rendered)
        self.assertNotIn("must verify", rendered)
        self.assertNotIn("do not claim", rendered)
        self.assertNotIn("CLOSE_NOW", rendered)
        self.assertNotIn("Next action", rendered)
        self.assertNotIn("web-search", rendered)
        self.assertNotIn("- direct-metta:", rendered)

    def test_parser_validates_against_descriptor_contract_shapes(self):
        self.assertEqual(
            self.helper.balance_parentheses("search Hyperon MeTTa"),
            '((search "Hyperon MeTTa"))',
        )
        self.assertEqual(
            self.helper.balance_parentheses("read-file notes.txt"),
            '((read-file "notes.txt"))',
        )
        trailing = self.helper.balance_parentheses("read-file notes.txt extra")
        self.assertIn("unexpected-trailing-text", trailing)
        unknown = self.helper.balance_parentheses("remembered this should fail")
        self.assertIn("unknown-command", unknown)
        self.assertIn('"remembered"', unknown)
        self.assertIn("Capability card", unknown)
        self.assertIn("send: send message", unknown)
        self.assertIn("A syntax error means nothing was done", unknown)

    def test_multiline_body_modes_remain_descriptor_controlled(self):
        rendered = self.helper.balance_parentheses(
            "write-file report.md Findings:\n"
            "query result was empty\n"
            "search result was usable"
        )
        self.assertEqual(
            rendered,
            '((write-file "report.md" "Findings:\\nquery result was empty\\nsearch result was usable"))',
        )
        send = self.helper.balance_parentheses("send Summary:\n\nResult: ok")
        self.assertEqual(send, '((send "Summary:\\n\\nResult: ok"))')

    def test_descriptor_guides_multiline_file_body_command_boundaries(self):
        descriptors = self.helper._load_capability_descriptors()
        self.assertIn("syntax-feedback", descriptors.get("__surface__", {}).get("surface_hints", {}))
        self.assertIn("always-on", descriptors.get("__surface__", {}).get("surface_hints", {}))
        self.assertEqual(descriptors["__surface__"]["error_cards"]["unknown-command"], "send")
        self.assertEqual(descriptors["__surface__"]["error_cards"]["shell-command-boundary"], "shell")
        self.assertEqual(descriptors["__surface__"]["error_cards"]["ambiguous-inline-body-quotes"], "write-file")
        self.assertEqual(
            descriptors["write-file"]["compact_guide"],
            "write-file filename text OR write-file filename <<TAG",
        )
        self.assertEqual(
            descriptors["append-file"]["compact_guide"],
            "append-file filename text OR append-file filename <<TAG",
        )
        self.assertNotIn("text|<<TAG", descriptors["write-file"]["compact_guide"])
        self.assertIn("artifact-extension", descriptors["append-file"]["roles"])
        file_always_on = " ".join(
            descriptors["write-file"]["always_on_guidance"]
            + descriptors["append-file"]["always_on_guidance"]
        )
        self.assertIn("literal data", file_always_on)
        self.assertIn("Later Omega commands must stay outside", file_always_on)
        self.assertIn("missing-body-terminator", descriptors["write-file"]["error_recovery"])
        self.assertIn("ambiguous-inline-body-quotes", descriptors["write-file"]["error_recovery"])
        self.assertIn("ambiguous-inline-body-quotes", descriptors["append-file"]["error_recovery"])
        self.assertIn("after the terminator", descriptors["write-file"]["recovery"])
        self.assertIn("after the terminator", descriptors["append-file"]["recovery"])
        self.assertIn("Markdown fences", " ".join(descriptors["write-file"]["guidance"]))
        append_guides = " ".join(descriptors["append-file"]["detailed_guides"])
        self.assertIn("Chunk large artifacts deliberately", append_guides)
        self.assertIn("does not insert a newline", append_guides)
        rendered = self.helper.balance_parentheses(
            "write-file report.md <<BODY\n"
            "| Command | Type |\n"
            "| send | Human-facing |\n"
            "BODY\n"
            "read-file report.md\n"
            "send done"
        )
        self.assertEqual(
            rendered,
            '((write-file "report.md" "| Command | Type |\\n| send | Human-facing |") '
            '(read-file "report.md") (send "done"))',
        )

    def test_syntax_error_feedback_is_descriptor_owned_and_learning_oriented(self):
        rendered = self.helper.balance_parentheses("write-file report.md <<BODY\nhello")
        self.assertIn("missing-body-terminator", rendered)
        self.assertIn("Close the exact delimiter alone on its own line", rendered)
        self.assertIn("put read-file, pin, send, or any next command after that terminator", rendered)
        self.assertIn("Capability card", rendered)
        self.assertIn("write-file: write-file filename text OR write-file filename <<TAG", rendered)
        self.assertIn("body-boundary-confusion", rendered)
        self.assertIn("A syntax error means nothing was done", rendered)
        self.assertIn("preserve live correction/liveness state in pin", rendered)
        self.assertNotIn("remember only stable reusable lessons", rendered)

        invalid_metta = self.helper.balance_parentheses("metta (+ 1 2")
        self.assertIn("invalid-metta", invalid_metta)
        self.assertIn("Retry with one balanced expression after metta", invalid_metta)
        self.assertIn("Capability card", invalid_metta)
        self.assertIn("affordances=nal, pln, atomspace", invalid_metta)

    def test_capability_cards_are_metta_owned_and_selected_by_exact_key(self):
        send_card = self.helper.render_capability_card("send")
        self.assertIn("send: send message", send_card)
        self.assertIn("role=human-facing-speech", send_card)
        self.assertIn("risks=reportification", send_card)
        self.assertIn("ordinary conversation", send_card)
        self.assertIn("Multiple sends are valid", send_card)
        self.assertNotIn("CapabilityDetailedGuide", send_card)

        shell_error = self.helper.balance_parentheses("shell <<BODY\npin hidden\nBODY")
        self.assertIn("shell-command-boundary", shell_error)
        self.assertIn("shell: shell command", shell_error)
        self.assertIn("role=os-execution", shell_error)

    def test_benchmark_driven_capability_guidance_is_descriptor_owned(self):
        descriptors = self.helper._load_capability_descriptors()
        pin_guides = " ".join(descriptors["pin"]["always_on_guidance"])
        shell_guides = " ".join(descriptors["shell"]["always_on_guidance"])
        remember_guides = " ".join(descriptors["remember"]["always_on_guidance"])
        query_guides = " ".join(descriptors["query"]["always_on_guidance"])
        episodes_guides = " ".join(descriptors["episodes"]["always_on_guidance"])
        search_guides = " ".join(descriptors["search"]["always_on_guidance"])
        send_guides = " ".join(
            descriptors["send"]["always_on_guidance"] + descriptors["send"]["detailed_guides"]
        )
        metta_guides = " ".join(
            descriptors["metta"]["always_on_guidance"] + descriptors["metta"]["detailed_guides"] + descriptors["metta"]["guidance"]
        )

        self.assertIn("primary continuity/autonomy skill", pin_guides)
        self.assertIn("not noise and not speech", pin_guides)
        self.assertIn("durable user facts", remember_guides)
        self.assertIn("concrete continuity facts", remember_guides)
        self.assertIn("durable semantic memory", query_guides)
        self.assertIn("try a sharper query", query_guides)
        self.assertIn("exact raw conversation history", episodes_guides)
        self.assertIn("live external evidence", search_guides)
        self.assertNotIn("pin useful findings", search_guides)
        self.assertIn("separate top-level lines", shell_guides)
        self.assertIn("ordinary conversation", send_guides)
        self.assertIn("short paragraphs", send_guides)
        self.assertIn("Multiple sends are valid", send_guides)
        self.assertIn("nal", descriptors["metta"]["affordances"])
        self.assertIn("pln", descriptors["metta"]["affordances"])
        self.assertIn("(|- ...)", metta_guides)
        self.assertIn("(|~ ...)", metta_guides)
        self.assertIn("stv frequency confidence", metta_guides)
        self.assertIn("evidence conflicts", metta_guides)
        self.assertIn("truth values outside implies", metta_guides)
        self.assertIn("top-level bang-prefixed MeTTa", metta_guides)
        self.assertIn("ACT when frequency >= 0.6", metta_guides)
        self.assertIn("HYPOTHESIZE when frequency >= 0.3", metta_guides)
        self.assertIn("proof trail", metta_guides)
        self.assertIn("invalid-metta-expression", descriptors["metta"]["error_recovery"])
        self.assertIn("metta-eval-error", descriptors["metta"]["error_recovery"])

    def test_loop_metta_is_not_patch2_integration_surface(self):
        text = (ROOT / "src" / "loop.metta").read_text(encoding="utf-8")
        self.assertIn('" SKILLS: " (getSkills)', text)
        self.assertNotIn("HARNESS_DESCRIPTOR_CONTEXT", text)
        self.assertNotIn("HARNESS_REPORT", text)


if __name__ == "__main__":
    unittest.main()
