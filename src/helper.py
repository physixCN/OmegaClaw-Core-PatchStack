from collections import deque
import json
import re
from datetime import datetime

TS_RE = re.compile(r'^\("(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"')
EPISODES_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
EPISODES_ISO_TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:Z)?$")

LLM_COMMANDS = {
    "append-file",
    "episodes",
    "metta",
    "pin",
    "query",
    "read-file",
    "remember",
    "search",
    "send",
    "shell",
    "tavily-search",
    "technical-analysis",
    "write-file",
}

BODY_COMMANDS = {"send", "write-file", "append-file"}
MULTILINE_BODY_COMMANDS = BODY_COMMANDS | {"shell"}
TWO_ARG_BODY_COMMANDS = {"write-file", "append-file"}
REST_TEXT_COMMANDS = {
    "episodes",
    "pin",
    "query",
    "remember",
    "search",
    "send",
    "shell",
    "tavily-search",
}
ONE_ARG_COMMANDS = {"read-file", "technical-analysis"}
SYNTAX_ERROR_RAW_LIMIT = 1200
OMEGA_COMMAND_LINE_RE = re.compile(
    r"(?m)^\s*(append-file|episodes|metta|pin|query|read-file|remember|search|send|shell|tavily-search|technical-analysis|write-file)(?:\s|:|$)"
)


def quote_arg(value):
    return json.dumps(str(value), ensure_ascii=False)


def extract_timestamp(line):
    m = TS_RE.search(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def around_time(needle_time_str, k):
    needle_time_str = needle_time_str.replace(r'\"', '').replace('"', '').strip()
    filename = "repos/OmegaClaw-Core/memory/history.metta"
    try:
        target = datetime.strptime(needle_time_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return f"EPISODES-FORMAT-ERROR expected YYYY-MM-DD HH:MM:SS got {needle_time_str}"
    best_lineno = None
    best_line = None
    best_diff = None
    buffer = []
    best_idx = None
    with open(filename, "r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            buffer.append((lineno, line))
            ts = extract_timestamp(line)
            if ts is None:
                continue
            diff = abs((ts - target).total_seconds())
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_lineno = lineno
                best_line = line
                best_idx = len(buffer) - 1
    if best_lineno is None:
        return
    start = max(0, best_idx - k)
    end = min(len(buffer), best_idx + k + 1)
    ret = ""
    for lineno, line in buffer[start:end]:
        ret += f"{lineno}:{line}"
    return ret


def _balanced_parenthesized(text):
    text = str(text or "").strip()
    depth = 0
    in_string = False
    escaped = False
    saw_paren = False
    closed_top = False
    for idx, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "(":
            if closed_top:
                return False
            saw_paren = True
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
            if depth == 0:
                closed_top = True
        elif closed_top and not ch.isspace():
            return False
    return saw_paren and depth == 0 and not in_string


def _strip_outer_parens(text):
    text = str(text or "").strip()
    if text.startswith("(") and text.endswith(")") and _balanced_parenthesized(text):
        return text[1:-1].strip()
    return text


def _consume_token(source):
    source = str(source or "").lstrip()
    if not source:
        return "", ""
    if source.startswith('"'):
        escaped = False
        for idx in range(1, len(source)):
            ch = source[idx]
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                token = source[:idx + 1]
                rest = source[idx + 1:].strip()
                try:
                    return json.loads(token), rest
                except Exception:
                    return token[1:-1], rest
        return source[1:], ""
    parts = source.split(maxsplit=1)
    token = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""
    return token, rest


def _get_command_name(line):
    normalized = _strip_outer_parens(str(line or "").strip())
    if not normalized:
        return ""
    return normalized.split(maxsplit=1)[0].rstrip(":")


def _missing_command_space_head(line):
    text = _strip_outer_parens(str(line or "").strip())
    for command in sorted(LLM_COMMANDS, key=len, reverse=True):
        if text.startswith(command + '"') or text.startswith(command + "'"):
            return command
    return ""


def _is_known_command(line):
    return _get_command_name(line) in LLM_COMMANDS


def _is_direct_metta(line):
    stripped = str(line or "").strip()
    if stripped.startswith("(") and _balanced_parenthesized(stripped) and not _is_known_command(stripped):
        return True
    if stripped.startswith("!") and _balanced_parenthesized(stripped[1:].strip()):
        return True
    return False


def _normalize_model_escaped_quotes(text):
    return str(text or "").replace(r'\"', '"')


def _split_top_level_semicolons(text):
    parts = []
    start = 0
    depth = 0
    in_string = False
    escaped = False
    for idx, ch in enumerate(str(text or "")):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ";" and depth == 0:
            parts.append(text[start:idx].strip())
            start = idx + 1
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def _split_semicolon_commands(line):
    if ";" not in line:
        return [line]
    parts = _split_top_level_semicolons(line)
    if len(parts) <= 1:
        return [line]
    first = _get_command_name(parts[0])
    if first in MULTILINE_BODY_COMMANDS:
        return [line]
    if all(_is_known_command(part) or _is_direct_metta(part) for part in parts):
        return parts
    return [line]


def _find_closing_quote(text, start=0):
    escaped = False
    for idx in range(start + 1, len(text)):
        ch = text[idx]
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            return idx
    return -1


def _body_command_parts(line):
    inner = _strip_outer_parens(str(line or "").strip())
    head, rest = _consume_token(inner)
    cmd = str(head).rstrip(":")
    if cmd not in MULTILINE_BODY_COMMANDS:
        return cmd, "", ""
    if cmd in {"send", "shell"}:
        return cmd, cmd, rest.lstrip()
    path, body = _consume_token(rest)
    if not path:
        return cmd, f"{cmd}", ""
    return cmd, f"{cmd} {quote_arg(path)}", body.lstrip()


def _read_delimited_body(lines, idx, prefix, marker):
    body = []
    while idx < len(lines):
        raw = lines[idx]
        idx += 1
        if raw.strip() == marker:
            return f"{prefix} {quote_arg(chr(10).join(body))}", idx
        body.append(raw.rstrip())
    raw = f"{prefix} <<{marker}\n" + "\n".join(body)
    return _syntax_error("missing-body-terminator", prefix.split()[0], _syntax_error_preview(raw), f"Missing body terminator {marker}."), idx


def _read_triple_quoted_body(lines, idx, prefix, body):
    content = body[3:]
    while True:
        close = content.find('"""')
        if close >= 0:
            return f"{prefix} {quote_arg(content[:close])}", idx
        if idx >= len(lines):
            raw = f"{prefix} " + body
            return _syntax_error("missing-body-terminator", prefix.split()[0], raw, 'Missing closing """ body delimiter.'), idx
        content += "\n" + lines[idx].rstrip()
        idx += 1


def _read_quoted_body(lines, idx, first_line):
    joined = first_line
    while True:
        cmd, _prefix, body = _body_command_parts(joined)
        if cmd not in MULTILINE_BODY_COMMANDS or not body.startswith('"'):
            return joined, idx
        if _find_closing_quote(body, 0) >= 0:
            return joined, idx
        if idx >= len(lines):
            return joined, idx
        joined += "\n" + lines[idx].rstrip()
        idx += 1


def _looks_like_body_continuation(body_lines, next_line):
    if not body_lines:
        return False
    prior = "\n".join(body_lines)
    first = body_lines[0].strip()
    stripped = str(next_line or "").strip()
    first_cmd = _get_command_name(first)
    if not stripped:
        return True
    if first_cmd == "shell" and (_is_known_command(stripped) or _is_direct_metta(stripped)):
        return False
    if stripped.startswith("("):
        return False
    if first.endswith(":"):
        return True
    artifact_markers = (
        "\\begin{",
        "\\end{",
        "\\toprule",
        "\\midrule",
        "\\bottomrule",
        "\\section{",
        "\\subsection{",
        "<svg",
        "<html",
        "<",
        "|",
    )
    if any(marker in prior for marker in artifact_markers):
        return True
    if " & " in stripped or stripped.endswith("\\\\"):
        return True
    return False


def _standalone_body_marker(line):
    match = re.match(r"^<<([A-Za-z_][A-Za-z0-9_-]*)$", str(line or "").strip())
    return match.group(1) if match else ""


def _normalize_pin_shorthand(line):
    stripped = str(line or "").strip()
    if stripped.startswith("(-"):
        return "(pin -" + stripped[2:]
    if stripped.startswith("-"):
        return "pin " + stripped[1:].lstrip()
    return stripped


def _logical_lines(text):
    text = str(text or "").replace("_quote_", '"').replace("_newline_", "\n")
    lines = text.splitlines()
    logical = []
    idx = 0
    while idx < len(lines):
        raw = lines[idx]
        stripped = raw.strip()
        idx += 1
        if not stripped:
            continue

        if stripped.startswith("(") and not _balanced_parenthesized(stripped):
            block_lines = [raw.rstrip()]
            while idx < len(lines):
                block_lines.append(lines[idx].rstrip())
                idx += 1
                candidate = "\n".join(block_lines).strip()
                if _balanced_parenthesized(candidate):
                    stripped = candidate
                    break

        segments = _split_semicolon_commands(stripped)
        if len(segments) > 1:
            logical.extend(segments)
            continue

        cmd = _get_command_name(stripped)
        if cmd not in MULTILINE_BODY_COMMANDS:
            logical.append(_normalize_pin_shorthand(stripped))
            continue

        body_cmd, body_prefix, body = _body_command_parts(stripped)
        if body.startswith("<<"):
            marker = body[2:].strip()
            if marker and re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", marker):
                logical_line, idx = _read_delimited_body(lines, idx, body_prefix, marker)
                logical.append(logical_line)
                continue
        if body.startswith('"""'):
            logical_line, idx = _read_triple_quoted_body(lines, idx, body_prefix, body)
            logical.append(logical_line)
            continue
        if body.startswith('"') and _find_closing_quote(body, 0) < 0:
            logical_line, idx = _read_quoted_body(lines, idx, stripped)
            logical.append(logical_line)
            continue

        body_lines = [stripped]
        misplaced_body_error = None
        while idx < len(lines):
            nxt = lines[idx]
            nxt_stripped = nxt.strip()
            marker = _standalone_body_marker(nxt_stripped)
            if marker and body_cmd in TWO_ARG_BODY_COMMANDS:
                raw_block = "\n".join(body_lines + [line.rstrip() for line in lines[idx:]])
                misplaced_body_error = _syntax_error(
                    "misplaced-body-delimiter",
                    body_cmd,
                    _syntax_error_preview(raw_block),
                    (
                        f"Found standalone <<{marker} inside an inline {body_cmd} body. "
                        f"Use {body_cmd} path <<{marker} on the first line, close {marker} alone, "
                        "then put later commands after the terminator."
                    ),
                )
                idx = len(lines)
                break
            if nxt_stripped and _is_direct_metta(nxt_stripped):
                break
            if nxt_stripped and _is_known_command(nxt_stripped) and not _looks_like_body_continuation(body_lines, nxt_stripped):
                break
            body_lines.append(nxt.rstrip())
            idx += 1
        if misplaced_body_error:
            logical.append(misplaced_body_error)
            continue
        while body_lines and body_lines[-1] == "":
            body_lines.pop()
        logical.append("\n".join(body_lines))
    return logical


def _syntax_error(kind, head, raw, hint):
    return f'(syntax-error {quote_arg(kind)} {quote_arg(head)} {quote_arg(raw)} {quote_arg(hint)})'


def _syntax_error_preview(raw):
    raw = str(raw or "")
    if len(raw) <= SYNTAX_ERROR_RAW_LIMIT:
        return raw
    omitted = len(raw) - SYNTAX_ERROR_RAW_LIMIT
    return raw[:SYNTAX_ERROR_RAW_LIMIT] + f"\n...[truncated {omitted} chars]"


def _decode_leading_quoted_body(text):
    text = str(text or "")
    if not text.startswith('"'):
        return text
    escaped = False
    for idx in range(1, len(text)):
        ch = text[idx]
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            tail = text[idx + 1:]
            if not tail:
                try:
                    return json.loads(text[:idx + 1])
                except Exception:
                    return text
            if tail.startswith("\n"):
                try:
                    return json.loads(text[:idx + 1]) + tail
                except Exception:
                    return text
            return text
    return text


def _normalize_body_text(text):
    return str(text or "").replace("\\n", "\n").replace("\\r", "")


def _decode_exact_quoted_rest(text):
    value, trailing = _consume_token(str(text or "").strip())
    if trailing:
        return str(text or "").strip()
    return str(value or "").strip()


def _normalize_episodes_timestamp(text):
    timestamp = _decode_exact_quoted_rest(text)
    if EPISODES_TIMESTAMP_RE.fullmatch(timestamp):
        return timestamp
    match = EPISODES_ISO_TIMESTAMP_RE.fullmatch(timestamp)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return None


def _decode_one_quoted_metta_expression(rest):
    expr, trailing = _consume_token(str(rest or "").strip())
    if trailing:
        return str(rest or "").strip()
    expr = str(expr or "").strip()
    if _balanced_parenthesized(expr):
        return expr
    return str(rest or "").strip()


def _shell_boundary_hint(rest):
    text = str(rest or "")
    if re.search(r"(?m)^\s*cat\s+>\s+\S+\s+<<", text):
        return (
            "Shell heredocs are shell text only. For Omega-authored artifacts, use "
            "write-file path <<TAG or append-file path <<TAG, close TAG alone on its own line, "
            "then emit send, pin, read-file, or metta as separate top-level Omega commands."
        )
    if OMEGA_COMMAND_LINE_RE.search(text):
        return (
            "Shell payload contains command-looking Omega lines. They remain shell text and are not "
            "Omega actions. Put send, pin, metta, query, read-file, write-file, append-file, or search "
            "on separate top-level lines outside shell."
        )
    return ""


def _parse_command(raw):
    original = str(raw or "").strip()
    if not original or original == "()":
        return None
    if _is_direct_metta(original):
        return original

    inner = _strip_outer_parens(original)
    missing_space_head = _missing_command_space_head(inner)
    if missing_space_head:
        return _syntax_error(
            "missing-command-space",
            missing_space_head,
            original,
            f"Missing space after command name. Use {missing_space_head} text, not {missing_space_head}\"text\".",
        )
    head, rest = _consume_token(inner)
    cmd = str(head).rstrip(":")
    if not cmd:
        return None
    if cmd not in LLM_COMMANDS:
        return _syntax_error("unknown-command", cmd, original, "Use a command listed in SKILLS, or put human-facing prose inside send.")

    if cmd == "metta":
        if not rest:
            return _syntax_error("missing-argument", cmd, original, "Missing expression. Use metta (expression).")
        if rest.strip().startswith('"'):
            rest = _decode_one_quoted_metta_expression(rest)
        if not _balanced_parenthesized(rest):
            return _syntax_error("invalid-metta", cmd, original, "Use one balanced MeTTa expression.")
        return f"(metta {quote_arg(rest)})"

    if cmd in TWO_ARG_BODY_COMMANDS:
        path, body = _consume_token(rest)
        if not path:
            return _syntax_error("missing-argument", cmd, original, f"Missing path. Use {cmd} file text.")
        if not body:
            return _syntax_error("missing-argument", cmd, original, f"Missing body. Use {cmd} file text.")
        if body.startswith('"'):
            decoded_body, trailing = _consume_token(body)
            if trailing:
                return _syntax_error(
                    "ambiguous-inline-body-quotes",
                    cmd,
                    original,
                    f"Inline {cmd} body has quote boundaries that cannot be preserved safely. Use {cmd} path <<TAG with TAG alone on a closing line.",
                )
            body = decoded_body
        body = _normalize_body_text(body)
        return f"({cmd} {quote_arg(path)} {quote_arg(body)})"

    if cmd in ONE_ARG_COMMANDS:
        arg, trailing = _consume_token(rest)
        if not arg:
            return _syntax_error("missing-argument", cmd, original, f"Missing argument. Use {cmd} value.")
        if trailing:
            return _syntax_error("unexpected-trailing-text", cmd, original, f"Use one argument for {cmd}; quote paths or values containing spaces.")
        return f"({cmd} {quote_arg(arg)})"

    if cmd in REST_TEXT_COMMANDS:
        if cmd in {"send", "shell"}:
            rest = _decode_leading_quoted_body(rest)
        if not rest:
            return _syntax_error("missing-argument", cmd, original, f"Missing text. Use {cmd} text.")
        if cmd not in {"shell", "episodes"}:
            rest = _normalize_model_escaped_quotes(rest)
        if cmd == "shell":
            boundary_hint = _shell_boundary_hint(rest)
            if boundary_hint:
                return _syntax_error("shell-command-boundary", cmd, original, boundary_hint)
        if cmd == "episodes":
            timestamp = _normalize_episodes_timestamp(rest)
            if timestamp is None:
                return _syntax_error(
                    "invalid-argument-format",
                    cmd,
                    original,
                    "Expected one timestamp argument: episodes YYYY-MM-DD HH:MM:SS. Put other text in a separate query or send command.",
                )
            return f"(episodes {quote_arg(timestamp)})"
        if cmd in BODY_COMMANDS:
            rest = _normalize_body_text(rest)
        return f"({cmd} {quote_arg(rest)})"

    return f"({cmd} {quote_arg(rest)})"


def balance_parentheses(s):
    sexprs = []
    for line in _logical_lines(s):
        parsed = _parse_command(line)
        if parsed:
            sexprs.append(parsed)
    ret = " ".join(sexprs)
    return "(" + ret + ")"


def normalize_string(x):
    try:
        if isinstance(x, bytes):
            return x.decode("utf-8", errors="ignore")
        return str(x).encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
    except Exception:
        return str(x)


def normalize_send_text(x):
    text = normalize_string(x)
    return text.replace("\\r", "").replace("\\n", "\n")


def test_balance_parenthesis():
    assert balance_parentheses('(write-file test.txt hello world)') == '((write-file "test.txt" "hello world"))'
    assert balance_parentheses('(append-file test.txt hello world)') == '((append-file "test.txt" "hello world"))'
    assert balance_parentheses('(write-file "test.txt" hello world)') == '((write-file "test.txt" "hello world"))'
    assert balance_parentheses('(write-file "test.txt" "hello world")') == '((write-file "test.txt" "hello world"))'
    assert balance_parentheses('(write-file test.txt "hello world")') == '((write-file "test.txt" "hello world"))'
    assert balance_parentheses('(send test.xt hello world)') == '((send "test.xt hello world"))'
    assert balance_parentheses('write-file test.txt hello world') == '((write-file "test.txt" "hello world"))'
    assert balance_parentheses('append-file test.txt hello world') == '((append-file "test.txt" "hello world"))'
    assert balance_parentheses('write-file "test.txt" hello world') == '((write-file "test.txt" "hello world"))'
    assert balance_parentheses('write-file "test.txt" "hello world"') == '((write-file "test.txt" "hello world"))'
    assert balance_parentheses('write-file test.txt "hello world"') == '((write-file "test.txt" "hello world"))'
    assert balance_parentheses('send test.xt hello world') == '((send "test.xt hello world"))'
    assert balance_parentheses('send Here are the planets:\n1. Mercury\n2. Venus') == '((send "Here are the planets:\\n1. Mercury\\n2. Venus"))'
    assert balance_parentheses('send Here are the options:\n- MacBook Air\n- ThinkPad X1\npin done') == '((send "Here are the options:\\n- MacBook Air\\n- ThinkPad X1\\npin done"))'
    assert balance_parentheses('send Here are the options:\n- MacBook Air\n- ThinkPad X1\n(pin done)') == '((send "Here are the options:\\n- MacBook Air\\n- ThinkPad X1") (pin "done"))'
    assert '(syntax-error "shell-command-boundary" "shell"' in balance_parentheses('shell <<BODY\npin stays shell text\nBODY')
    assert balance_parentheses('send "Plain text version:"\n**Mars** - red planet\nNote: Pluto is a dwarf planet') == '((send "Plain text version:\\n**Mars** - red planet\\nNote: Pluto is a dwarf planet"))'
    assert balance_parentheses('(send Here are the planets:\n1. Mercury\n2. Venus)') == '((send "Here are the planets:\\n1. Mercury\\n2. Venus"))'
    assert balance_parentheses('send "hello" world') == '((send "\\"hello\\" world"))'
    # bare "()" lines yield no tokens after _strip_outer_parens and must be skipped, not crash
    assert balance_parentheses('()') == '()'
    assert balance_parentheses('') == '()'
    assert balance_parentheses('   ') == '()'
    assert balance_parentheses('()\nsend hello') == '((send "hello"))'


if __name__ == "__main__":
    test_balance_parenthesis()
