import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Patch1FinalSyntaxMembraneTests(unittest.TestCase):
    def setUp(self):
        self.helper = load_module("helper", ROOT / "src" / "helper.py")

    def test_send_body_preserves_command_words_inside_prose_lines(self):
        rendered = self.helper.balance_parentheses(
            "send Summary: I checked it.\n\n"
            "Result: query result was empty, but search result was usable."
        )
        self.assertEqual(
            rendered,
            '((send "Summary: I checked it.\\n\\nResult: query result was empty, but search result was usable."))',
        )

    def test_send_body_preserves_bare_command_words_after_colon(self):
        rendered = self.helper.balance_parentheses(
            "send I checked it:\n"
            "query result was empty\n"
            "search result was usable"
        )
        self.assertEqual(
            rendered,
            '((send "I checked it:\\nquery result was empty\\nsearch result was usable"))',
        )

    def test_send_body_preserves_bulleted_command_words(self):
        rendered = self.helper.balance_parentheses(
            "send Report:\n"
            "- query result was empty\n"
            "- pin is mentioned as text\n"
            "- shell is mentioned as text"
        )
        self.assertEqual(
            rendered,
            '((send "Report:\\n- query result was empty\\n- pin is mentioned as text\\n- shell is mentioned as text"))',
        )

    def test_send_body_canonicalizes_literal_escaped_newlines(self):
        for raw in [
            r"send Greetings, curious human!\n\nSo... what is in the toolkit?",
            r'send "Greetings, curious human!\n\nSo... what is in the toolkit?"',
        ]:
            rendered = self.helper.balance_parentheses(raw)
            self.assertIn("Greetings", rendered)
            self.assertIn(r"\n\nSo", rendered)
            self.assertNotIn(r"\\n\\nSo", rendered)

    def test_send_channel_preserves_paragraph_breaks_for_humans(self):
        self.assertEqual(
            self.helper.normalize_send_text(r"Paragraph one\n\nParagraph two"),
            "Paragraph one\n\nParagraph two",
        )
        self.assertEqual(
            self.helper.normalize_send_text("Paragraph one\n\nParagraph two"),
            "Paragraph one\n\nParagraph two",
        )

        channels = (ROOT / "src" / "channels.metta").read_text(encoding="utf-8")
        self.assertIn("helper.normalize_send_text", channels)
        self.assertNotIn("string-replace $msg", channels)

    def test_file_bodies_preserve_command_words_inside_prose_lines(self):
        self.assertEqual(
            self.helper.balance_parentheses(
                "write-file notes.txt Findings:\n"
                "query result was empty\n"
                "search result was also empty"
            ),
            '((write-file "notes.txt" "Findings:\\nquery result was empty\\nsearch result was also empty"))',
        )
        self.assertEqual(
            self.helper.balance_parentheses("append-file notes.txt Note:\n- shell is just prose here"),
            '((append-file "notes.txt" "Note:\\n- shell is just prose here"))',
        )

    def test_quoted_artifact_body_preserves_latex_command_rows(self):
        raw = (
            'write-file omegaclaw_report.tex "\\\\begin{tabular}{ll}\n'
            '\\\\midrule\n'
            'query & Search long-term embedding memory with short phrases \\\\\\\\\n'
            'remember & Store a string permanently in long-term memory \\\\\\\\\n'
            'send & Send a message to the user \\\\\\\\\n'
            '\\\\bottomrule\n'
            '\\\\end{tabular}"'
        )
        rendered = self.helper.balance_parentheses(raw)
        self.assertTrue(rendered.startswith('((write-file "omegaclaw_report.tex" '))
        self.assertIn("query & Search long-term embedding memory", rendered)
        self.assertIn("remember & Store a string permanently", rendered)
        self.assertIn("send & Send a message to the user", rendered)
        self.assertNotIn('(query "& Search', rendered)
        self.assertNotIn('(remember "& Store', rendered)
        self.assertNotIn('(send "& Send', rendered)

    def test_explicit_delimited_file_body_preserves_command_words(self):
        rendered = self.helper.balance_parentheses(
            "write-file report.md <<BODY\n"
            "# Report\n\n"
            "send done should be prose\n"
            "query result should be prose\n"
            "BODY"
        )
        self.assertEqual(
            rendered,
            '((write-file "report.md" "# Report\\n\\nsend done should be prose\\nquery result should be prose"))',
        )

    def test_long_delimited_file_body_with_arbitrary_tag_and_followup_command(self):
        body = "# Long Artifact\n\n" + "\n".join(
            f"- row {idx}: send query shell remember (stv 0.{idx % 10} 0.8) `pin` \"quoted\""
            for idx in range(120)
        )
        rendered = self.helper.balance_parentheses(
            "write-file /tmp/long.md <<OMEGA_ARTIFACT\n"
            f"{body}\n"
            "OMEGA_ARTIFACT\n"
            "read-file /tmp/long.md"
        )
        self.assertNotIn("syntax-error", rendered)
        self.assertTrue(rendered.startswith('((write-file "/tmp/long.md" '))
        self.assertIn("# Long Artifact", rendered)
        self.assertIn("row 119: send query shell remember", rendered)
        self.assertIn('(read-file "/tmp/long.md")', rendered)

    def test_long_delimited_append_body_preserves_command_like_content(self):
        body = "## Evidence\n\n" + "\n".join(
            f"Claim {idx}: search and send are prose here; (stv 0.8 0.7)"
            for idx in range(80)
        )
        rendered = self.helper.balance_parentheses(
            "append-file /tmp/paper.md <<APPEND_BODY\n"
            f"{body}\n"
            "APPEND_BODY"
        )
        self.assertNotIn("syntax-error", rendered)
        self.assertIn('((append-file "/tmp/paper.md" ', rendered)
        self.assertIn("Claim 79: search and send are prose here", rendered)

    def test_delimiter_must_appear_alone_on_line(self):
        rendered = self.helper.balance_parentheses(
            "write-file /tmp/terminator.md <<BODY\n"
            "BODY is mentioned here as data, not a terminator.\n"
            "BODY\n"
            "send done"
        )
        self.assertEqual(
            rendered,
            '((write-file "/tmp/terminator.md" "BODY is mentioned here as data, not a terminator.") (send "done"))',
        )

    def test_missing_delimited_body_terminator_fails_closed_with_bounded_raw_preview(self):
        body = "# Incomplete Artifact\n\n" + "\n".join(
            f"- line {idx}: command words send query shell remember remain data"
            for idx in range(80)
        )
        rendered = self.helper.balance_parentheses(
            "write-file /tmp/incomplete.md <<OMEGA_ARTIFACT\n" + body
        )
        self.assertIn("(syntax-error", rendered)
        self.assertIn('"missing-body-terminator"', rendered)
        self.assertIn("Missing body terminator OMEGA_ARTIFACT.", rendered)
        self.assertIn("[truncated", rendered)
        self.assertNotIn('(write-file "/tmp/incomplete.md"', rendered)

    def test_missing_terminator_after_valid_code_chunk_preserves_prior_command(self):
        raw = (
            'write-file /tmp/backward_chainer.pl "#!/usr/bin/perl\\nuse strict;\\n"\n'
            "append-file /tmp/backward_chainer.pl <<PL2\n"
            "sub backward_prove {\n"
            "    my ($pred, $arg, $bind, $depth, $visited) = @_;\n"
            "    return (0, 0, [\"CYCLE: $pred($arg)\"]) if $depth > 10;\n"
            "    # command-looking text below is still file data until PL2 closes\n"
            "    pin CYCLE=122 should not execute from inside this file body\n"
            "    shell chmod +x /tmp/backward_chainer.pl\n"
        )
        rendered = self.helper.balance_parentheses(raw)

        self.assertIn('(write-file "/tmp/backward_chainer.pl"', rendered)
        self.assertIn('(syntax-error "missing-body-terminator" "append-file"', rendered)
        self.assertIn("Missing body terminator PL2.", rendered)
        self.assertNotIn('(pin "CYCLE=122', rendered)
        self.assertNotIn('(shell "chmod +x /tmp/backward_chainer.pl")', rendered)

    def test_triple_quoted_file_body_preserves_command_words(self):
        rendered = self.helper.balance_parentheses(
            'append-file report.md """# Report\n'
            'send done should be prose\n'
            '"""'
        )
        self.assertEqual(
            rendered,
            '((append-file "report.md" "# Report\\nsend done should be prose\\n"))',
        )

    def test_explicit_delimited_shell_body_preserves_normal_shell_text(self):
        rendered = self.helper.balance_parentheses(
            "shell <<BODY\n"
            "printf 'colon: ok\\n'\n"
            "echo done\n"
            "BODY"
        )
        self.assertEqual(
            rendered,
            '((shell "printf \'colon: ok\\\\n\'\\necho done"))',
        )

    def test_shell_body_with_omega_command_lines_fails_closed_with_boundary_hint(self):
        rendered = self.helper.balance_parentheses(
            "shell <<BODY\n"
            "pin should be a separate Omega command, not shell text\n"
            "printf 'colon: ok\\n'\n"
            "BODY"
        )
        self.assertIn('(syntax-error "shell-command-boundary" "shell"', rendered)
        self.assertIn("remain shell text and are not Omega actions", rendered)
        self.assertNotIn('(pin "should be a separate', rendered)

    def test_shell_heredoc_artifact_confusion_gets_write_file_hint(self):
        rendered = self.helper.balance_parentheses(
            "shell cat > /tmp/report.md << EOF\n"
            "# Report\n"
            "send done\n"
            "EOF"
        )
        self.assertIn('(syntax-error "shell-command-boundary" "shell"', rendered)
        self.assertIn("use write-file path <<TAG", rendered)
        self.assertNotIn('(send "done")', rendered)

    def test_quoted_shell_body_is_decoded_without_rewriting_shell_escapes(self):
        rendered = self.helper.balance_parentheses("shell \"printf 'colon: ok\\\\n'\"")
        self.assertEqual(rendered, '((shell "printf \'colon: ok\\\\n\'"))')

    def test_model_escaped_quotes_repair_non_shell_rest_text_only(self):
        self.assertEqual(
            self.helper.balance_parentheses(r'send Max wrote: \"syntax failed\"'),
            '((send "Max wrote: \\"syntax failed\\""))',
        )
        self.assertEqual(
            self.helper.balance_parentheses(r'query \"syntax membrane\" failures'),
            '((query "\\"syntax membrane\\" failures"))',
        )
        shell = self.helper.balance_parentheses(r'shell printf \"ok\\n\"')
        self.assertIn(r'\\\"ok', shell)

    def test_ambiguous_inline_file_body_quotes_fail_closed(self):
        rendered = self.helper.balance_parentheses(
            'write-file /tmp/a.html "<div class="note" data-owner="Max\'s">x</div>"'
        )
        self.assertIn('(syntax-error "ambiguous-inline-body-quotes" "write-file"', rendered)
        self.assertIn('Use write-file path <<TAG', rendered)
        self.assertNotIn('(write-file "/tmp/a.html"', rendered)

        append = self.helper.balance_parentheses(
            'append-file /tmp/a.py "html = f"<div class=\'note\'>{name}</div>""'
        )
        self.assertIn('(syntax-error "ambiguous-inline-body-quotes" "append-file"', append)
        self.assertIn('Use append-file path <<TAG', append)

    def test_delimited_file_body_preserves_mixed_quotes_and_dollars(self):
        self.assertEqual(
            self.helper.balance_parentheses(
                'write-file /tmp/a.html <<HTML\n'
                '<div class="note" data-owner="Max\'s">$value</div>\n'
                'HTML'
            ),
            '((write-file "/tmp/a.html" "<div class=\\"note\\" data-owner=\\"Max\'s\\">$value</div>"))',
        )

    def test_bare_shell_pipeline_does_not_swallow_following_commands(self):
        rendered = self.helper.balance_parentheses(
            "shell ls /usr/local/bin/ 2>/dev/null | head -20\n"
            "metta (|~ (implies (explore capabilities) (learn safely)) (stv 0.9 0.8))\n"
            "query PLN inference and metta reasoning patterns\n"
            "send Cycle 20: Shell contains only OS text."
        )
        self.assertEqual(
            rendered,
            '((shell "ls /usr/local/bin/ 2>/dev/null | head -20") '
            '(metta "(|~ (implies (explore capabilities) (learn safely)) (stv 0.9 0.8))") '
            '(query "PLN inference and metta reasoning patterns") '
            '(send "Cycle 20: Shell contains only OS text."))',
        )

    def test_file_bodies_canonicalize_literal_escaped_newlines(self):
        rendered = self.helper.balance_parentheses(r"write-file notes.txt Line one\nLine two")
        self.assertIn(r"Line one\nLine two", rendered)
        self.assertNotIn(r"Line one\\nLine two", rendered)

    def test_bare_known_command_boundary_after_send_body(self):
        self.assertEqual(
            self.helper.balance_parentheses(
                "send OmegaClaw here. Smoke test patch 1 confirmed online. Ready for your next task.\n"
                "pin Awaiting user input, idle"
            ),
            '((send "OmegaClaw here. Smoke test patch 1 confirmed online. Ready for your next task.") '
            '(pin "Awaiting user input, idle"))',
        )
        self.assertEqual(
            self.helper.balance_parentheses(
                "send Done.\n"
                "query user goals and new messages"
            ),
            '((send "Done.") (query "user goals and new messages"))',
        )

    def test_bare_known_command_boundary_after_file_bodies(self):
        self.assertEqual(
            self.helper.balance_parentheses(
                "write-file notes.txt Findings:\n"
                "body line\n"
                "(send Done)"
            ),
            '((write-file "notes.txt" "Findings:\\nbody line") (send "Done"))',
        )
        self.assertEqual(
            self.helper.balance_parentheses(
                "append-file notes.txt finding\n"
                "remember appended"
            ),
            '((append-file "notes.txt" "finding") (remember "appended"))',
        )

    def test_misplaced_delimiter_inside_inline_file_body_fails_closed(self):
        rendered = self.helper.balance_parentheses(
            "write-file /tmp/script.py import json\n"
            "print('ok')\n"
            "<<ENDPY\n"
            "shell python3 /tmp/script.py\n"
            "pin should not execute\n"
            "metta (|~ (implies A B) (stv 0.8 0.7))"
        )
        self.assertIn('(syntax-error "misplaced-body-delimiter" "write-file"', rendered)
        self.assertIn("Use write-file path <<ENDPY on the first line", rendered)
        self.assertNotIn('(shell "python3 /tmp/script.py")', rendered)
        self.assertNotIn('(pin "should not execute")', rendered)
        self.assertNotIn('(metta "(|~ (implies A B) (stv 0.8 0.7))")', rendered)

    def test_proper_delimited_file_body_still_allows_following_commands(self):
        rendered = self.helper.balance_parentheses(
            "write-file /tmp/script.py <<ENDPY\n"
            "print('ok')\n"
            "ENDPY\n"
            "shell python3 /tmp/script.py\n"
            "pin executed after delimiter"
        )
        self.assertEqual(
            rendered,
            '((write-file "/tmp/script.py" "print(\'ok\')") '
            '(shell "python3 /tmp/script.py") '
            '(pin "executed after delimiter"))',
        )

    def test_quoted_multiline_body_can_be_followed_by_bare_command(self):
        self.assertEqual(
            self.helper.balance_parentheses('write-file test.txt "line one\nline two"\nsend done'),
            '((write-file "test.txt" "line one\\nline two") (send "done"))',
        )
        self.assertEqual(
            self.helper.balance_parentheses('append-file test.txt "line one\nline two"\nsend done'),
            '((append-file "test.txt" "line one\\nline two") (send "done"))',
        )

    def test_parenthesized_multiline_body_can_be_followed_by_bare_command(self):
        self.assertEqual(
            self.helper.balance_parentheses('(write-file test.txt "line one\nline two")\nsend done'),
            '((write-file "test.txt" "line one\\nline two") (send "done"))',
        )

    def test_parenthesized_command_boundary_after_body(self):
        self.assertEqual(
            self.helper.balance_parentheses(
                "send Report:\n"
                "- query is prose\n"
                "(remember report sent)"
            ),
            '((send "Report:\\n- query is prose") (remember "report sent"))',
        )
        self.assertEqual(
            self.helper.balance_parentheses(
                "write-file notes.txt Findings:\n"
                "- query result was empty\n"
                "(remember write done)"
            ),
            '((write-file "notes.txt" "Findings:\\n- query result was empty") (remember "write done"))',
        )

    def test_preserves_colons_blank_lines_and_markdown(self):
        self.assertEqual(
            self.helper.balance_parentheses(
                "send Summary: I checked it.\n\n"
                "Result: query result was empty, but search result was usable."
            ),
            '((send "Summary: I checked it.\\n\\nResult: query result was empty, but search result was usable."))',
        )
        self.assertEqual(
            self.helper.balance_parentheses(
                "write-file audit/patch.md # Patch\n\n"
                "| Need | Route |\n"
                "|------|-------|\n"
                "| web | search |\n\n"
                "- preserve bullets"
            ),
            '((write-file "audit/patch.md" "# Patch\\n\\n| Need | Route |\\n|------|-------|\\n| web | search |\\n\\n- preserve bullets"))',
        )

    def test_known_command_head_colon_is_repaired_only_for_known_heads(self):
        self.assertEqual(
            self.helper.balance_parentheses("send: Summary:\n\nResult: ok"),
            '((send "Summary:\\n\\nResult: ok"))',
        )
        self.assertEqual(
            self.helper.balance_parentheses("query: OmegaClaw"),
            '((query "OmegaClaw"))',
        )
        rendered = self.helper.balance_parentheses("Summary: this is a prose label")
        self.assertIn("(syntax-error", rendered)
        self.assertIn('"Summary"', rendered)

    def test_semicolon_command_chain_splits_only_known_boundaries(self):
        self.assertEqual(
            self.helper.balance_parentheses("query Alpha; search Beta; send Done"),
            '((query "Alpha") (search "Beta") (send "Done"))',
        )
        self.assertEqual(
            self.helper.balance_parentheses("shell echo one; echo two"),
            '((shell "echo one; echo two"))',
        )
        self.assertEqual(
            self.helper.balance_parentheses("send This has a semicolon; it is prose"),
            '((send "This has a semicolon; it is prose"))',
        )

    def test_direct_parenthesized_metta_passes_through(self):
        self.assertEqual(self.helper.balance_parentheses("(+ 1 2)"), "((+ 1 2))")
        self.assertEqual(self.helper.balance_parentheses("!(quote (+ 1 2))"), "(!(quote (+ 1 2)))")
        self.assertEqual(
            self.helper.balance_parentheses("(foo \"bar: baz\")"),
            '((foo "bar: baz"))',
        )
        self.assertEqual(
            self.helper.balance_parentheses(
                "(|- ((--> sam human) (stv 1.0 0.9))\n"
                "    ((--> human mortal) (stv 1.0 0.9)))"
            ),
            "((|- ((--> sam human) (stv 1.0 0.9))\n    ((--> human mortal) (stv 1.0 0.9))))",
        )

    def test_malformed_metta_fails_closed(self):
        for raw in ["metta (+ 1 2", "(+ 1 2", "metta (a)(b)"]:
            rendered = self.helper.balance_parentheses(raw)
            self.assertIn("(syntax-error", rendered)

    def test_quoted_metta_expression_unwraps_only_one_balanced_expression(self):
        self.assertEqual(
            self.helper.balance_parentheses('metta "(+ 1 2)"'),
            '((metta "(+ 1 2)"))',
        )
        self.assertEqual(
            self.helper.balance_parentheses('metta "(cdr (quote (a b c)))"'),
            '((metta "(cdr (quote (a b c)))"))',
        )

        for raw in ['metta "(+ 1 2" ', 'metta "(+ 1 2)" query next']:
            rendered = self.helper.balance_parentheses(raw)
            self.assertIn("(syntax-error", rendered)
            self.assertIn('"invalid-metta"', rendered)

    def test_complex_metta_command_payloads_pass_outer_membrane(self):
        examples = [
            "metta (map-atom (1 2 3) (lambda $x (* $x 2)))",
            "metta (get-metatype (= (double $x) (* $x 2)))",
            "metta (forall (member X (1 2 3)) (> X 0))",
            "metta (= (square x) (* x x))",
            "metta (= (factorial n) (* n (factorial (- n 1))))",
        ]
        for raw in examples:
            with self.subTest(raw=raw):
                rendered = self.helper.balance_parentheses(raw)
                self.assertNotIn("(syntax-error", rendered)
                self.assertIn('(metta "', rendered)

    def test_metta_rejects_trailing_command_text_after_one_expression(self):
        rendered = self.helper.balance_parentheses(
            "metta (add1 5)query MeTTa Prolog how to define predicates"
        )
        self.assertIn("(syntax-error", rendered)
        self.assertIn('"invalid-metta"', rendered)
        self.assertIn("Use one balanced MeTTa expression", rendered)

    def test_metta_skill_catches_reader_and_eval_failures(self):
        skills = (ROOT / "src" / "skills.metta").read_text(encoding="utf-8")
        start = skills.index("(= (metta")
        end = skills.index("\n\n(= (pin", start)
        self.assertTrue(self.helper._balanced_parenthesized(skills[start:end]))
        self.assertIn('(catch (sread $str))', skills)
        self.assertIn('(catch (eval $code))', skills)
        self.assertIn('"invalid-metta-expression"', skills)
        self.assertIn('"metta-eval-error"', skills)

    def test_unknown_bare_command_and_direct_shell_fail_closed(self):
        for raw, head in [
            ("invent-tool now", "invent-tool"),
            ("find . -maxdepth 1 -type f", "find"),
            ("I will inspect first.", "I"),
        ]:
            rendered = self.helper.balance_parentheses(raw)
            self.assertIn("(syntax-error", rendered)
            self.assertIn(f'"{head}"', rendered)

    def test_missing_command_space_after_known_head_gets_specific_feedback(self):
        for raw, head in [
            ('query"autonomy test evidence MeTTa hyperon"', "query"),
            ('send"Recovered from syntax error."', "send"),
            ('metta"(+ 1 2)"', "metta"),
        ]:
            rendered = self.helper.balance_parentheses(raw)
            self.assertIn('(syntax-error "missing-command-space"', rendered)
            self.assertIn(f'"{head}"', rendered)
            self.assertIn("Missing space after command name", rendered)

    def test_missing_required_arguments_fail_closed(self):
        for raw in ["read-file", "query", "shell", "write-file notes.txt", "append-file notes.txt"]:
            rendered = self.helper.balance_parentheses(raw)
            self.assertIn("(syntax-error", rendered)
            self.assertIn('"missing-argument"', rendered)

    def test_single_arg_commands_reject_trailing_text(self):
        rendered = self.helper.balance_parentheses("technical-analysis NVDA extra")
        self.assertIn("(syntax-error", rendered)
        self.assertIn('"unexpected-trailing-text"', rendered)

    def test_episodes_rejects_mashed_timestamp_text_before_runtime(self):
        rendered = self.helper.balance_parentheses("episodes 2026-06-25 16:23:00query syntax errors")
        self.assertIn("(syntax-error", rendered)
        self.assertIn('"invalid-argument-format"', rendered)
        self.assertIn('"episodes"', rendered)
        self.assertIn("Expected one timestamp argument", rendered)

    def test_episodes_accepts_exact_timestamp_with_or_without_quotes(self):
        expected = '((episodes "2026-06-25 16:23:00"))'
        self.assertEqual(self.helper.balance_parentheses("episodes 2026-06-25 16:23:00"), expected)
        self.assertEqual(self.helper.balance_parentheses('episodes "2026-06-25 16:23:00"'), expected)

    def test_episodes_accepts_exact_iso_timestamp_and_normalizes(self):
        expected = '((episodes "2026-06-27 12:20:00"))'
        self.assertEqual(self.helper.balance_parentheses("episodes 2026-06-27T12:20:00"), expected)
        self.assertEqual(self.helper.balance_parentheses("episodes 2026-06-27T12:20:00Z"), expected)
        self.assertEqual(self.helper.balance_parentheses('episodes "2026-06-27T12:20:00Z"'), expected)

    def test_episodes_runtime_returns_format_error_for_direct_metta_calls(self):
        result = self.helper.around_time("2026-06-25 16:23:00query syntax errors", 20)
        self.assertIn("EPISODES-FORMAT-ERROR", result)
        self.assertIn("YYYY-MM-DD HH:MM:SS", result)

    def test_empty_inputs_stay_empty(self):
        self.assertEqual(self.helper.balance_parentheses(""), "()")
        self.assertEqual(self.helper.balance_parentheses("   "), "()")
        self.assertEqual(self.helper.balance_parentheses("()"), "()")
        self.assertEqual(self.helper.balance_parentheses("()\nsend hello"), '((send "hello"))')

    def test_patch1_keeps_asi_search_surface(self):
        self.assertEqual(
            self.helper.balance_parentheses("search Hyperon MeTTa"),
            '((search "Hyperon MeTTa"))',
        )
        rendered = self.helper.balance_parentheses("web-search Hyperon MeTTa")
        self.assertIn("(syntax-error", rendered)
        self.assertIn('"web-search"', rendered)


if __name__ == "__main__":
    unittest.main()
