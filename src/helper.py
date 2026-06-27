from collections import deque
import json
import re
from datetime import datetime
from pathlib import Path

TS_RE = re.compile(r'^\("(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"')
EPISODES_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
EPISODES_ISO_TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:Z)?$")

DESCRIPTOR_PATH = Path(__file__).with_name("harness_descriptors.metta")
_DESCRIPTOR_CACHE = None
SYNTAX_ERROR_RAW_LIMIT = 1200

_FALLBACK_CAPABILITY_DESCRIPTOR_TEXT = """
(CapabilitySurfaceHint always-on "Syntax core: commands are bare names at line start. Do not prefix commands with :, Markdown fences, bullets, labels, XML tags, or hidden thinking tags. Put human-facing prose in send.")
(CapabilitySurfaceHint always-on "Action core: each top-level line is one Omega action. shell payloads are OS text only; file bodies are literal data until their closing delimiter; later Omega commands go after the shell/file body.")
(CapabilitySurfaceHint always-on "Memory core: pin is Omega's live RAM/liveness frame; remember writes durable long-term semantic memory; query searches remembered memory; episodes searches exact raw history.")
(CapabilitySurfaceHint always-on "Grounding core: search supplies live external evidence; query recalls remembered semantic evidence; episodes recalls raw conversation evidence; read-file and shell inspect local evidence.")
(CapabilitySurfaceHint always-on "Truth core: when claims matter or evidence conflicts, use metta to represent premises, provenance, uncertainty, contradictions, and confidence; do not treat generated text or search snippets as truth.")
(CapabilitySurfaceHint always-on "Reporting core: act from the best-supported state available, keep live state in pin, remember durable conclusions or corrections, and use send to report results or uncertainty when needed.")
(CapabilitySurfaceHint syntax-feedback "A syntax error means nothing was done. Retry with one or more valid top-level commands; keep command names bare, put human-facing text in send, and preserve live correction/liveness state in pin if needed.")
(CapabilityErrorCard unknown-command send)
(CapabilityDescriptor remember)
(CapabilityContract remember command (Arg rest-text text))
(CapabilityAlwaysOnGuide remember "remember stores durable user facts, session facts, commitments, preferences, artifact pointers, unresolved references, corrections, stable lessons, and durable conclusions.")
(CapabilityAlwaysOnGuide remember "Remember concrete continuity facts as well as abstractions: names, locations, promises, requested artifacts, decisions, and facts the user may ask about later.")
(CapabilityDescriptor query)
(CapabilityContract query command (Arg rest-text phrase))
(CapabilityAlwaysOnGuide query "query retrieves durable semantic memory stored with remember; use short targeted phrases before answering from memory.")
(CapabilityAlwaysOnGuide query "If query misses, try a sharper query, use episodes for raw conversation history, or use search for external evidence when the missing fact belongs outside memory.")
(CapabilityDescriptor episodes)
(CapabilityContract episodes command (Arg rest-text timestamp))
(CapabilityAlwaysOnGuide episodes "episodes retrieves exact raw conversation history around a timestamp; use it when semantic memory is insufficient or the fact may never have been remembered.")
(CapabilityDescriptor pin)
(CapabilityContract pin command (Arg rest-text text))
(CapabilityAlwaysOnGuide pin "pin is Omega's primary continuity/autonomy skill: keep objective, phase, next action, blockers, obligations, evidence pointers, and wake/liveness state live across cycles.")
(CapabilityAlwaysOnGuide pin "pin is not noise and not speech. Refresh it as the live frame changes; if a live item becomes durable, preserve it with remember.")
(CapabilityDescriptor shell)
(CapabilityContract shell command (Arg rest-text command))
(CapabilityBodyMode shell multiline-rest)
(CapabilityAlwaysOnGuide shell "shell executes OS text only; Omega commands such as send, pin, remember, query, metta, read-file, write-file, append-file, and search belong on separate top-level lines outside shell.")
(CapabilityDescriptor read-file)
(CapabilityContract read-file command (Arg token filename))
(CapabilityAlwaysOnGuide read-file "read-file inspects artifacts, logs, and files before relying on their contents.")
(CapabilityDescriptor write-file)
(CapabilityContract write-file command (Arg path filename) (Arg body-text text))
(CapabilityBodyMode write-file path-plus-body)
(CapabilityCompactGuide write-file "write-file filename text OR write-file filename <<TAG")
(CapabilityAlwaysOnGuide write-file "write-file creates artifacts; multiline bodies are literal data until the closing delimiter.")
(CapabilityAlwaysOnGuide write-file "For multiline content, use an explicit delimiter, close it alone on its own line, then put later Omega commands after the body.")
(CapabilityDescriptor append-file)
(CapabilityContract append-file command (Arg path filename) (Arg body-text text))
(CapabilityBodyMode append-file path-plus-body)
(CapabilityCompactGuide append-file "append-file filename text OR append-file filename <<TAG")
(CapabilityAlwaysOnGuide append-file "append-file extends artifacts in chunks; append body text is literal data until the closing delimiter.")
(CapabilityAlwaysOnGuide append-file "Later Omega commands must stay outside the append body.")
(CapabilityDescriptor send)
(CapabilityContract send command (Arg rest-text message))
(CapabilityBodyMode send multiline-rest)
(CapabilityAlwaysOnGuide send "send is Omega's human speech channel: use it for ordinary conversation, answers, questions, progress, results, uncertainty, care, and reports.")
(CapabilityAlwaysOnGuide send "Do not speak as bare prose. Do not hide speech in pin, shell, file bodies, or metta.")
(CapabilityErrorRecovery send unknown-command "Use a listed command as the first word, or use send for human-facing prose. Commands are bare names like send, pin, shell, metta, query, and search; not :send:, Markdown fences, bullets, labels, XML tags, or hidden thinking tags.")
(CapabilityDescriptor search)
(CapabilityContract search command (Arg rest-text query))
(CapabilityAlwaysOnGuide search "search retrieves live external evidence through the configured backend; use it when current facts, source discovery, contradiction checks, or external grounding are needed.")
(CapabilityAlwaysOnGuide search "Search results are evidence candidates, not truth; inspect sources or compare evidence when accuracy, recency, or exact wording matters.")
(CapabilityDescriptor tavily-search)
(CapabilityContract tavily-search command (Arg rest-text query))
(CapabilityRole tavily-search optional-web-research)
(CapabilityDescriptor technical-analysis)
(CapabilityContract technical-analysis command (Arg token ticker))
(CapabilityRole technical-analysis optional-market-analysis)
(CapabilityDescriptor metta)
(CapabilityContract metta command (Arg metta-expression sexpression))
(CapabilityCompactGuide metta "metta (balanced expression)")
(CapabilityAlwaysOnGuide metta "metta is Omega's inspectable truth-maintenance substrate: use it to represent claims, premises, provenance, uncertainty, contradictions, and confidence.")
(CapabilityAlwaysOnGuide metta "Use NAL with (|- ...) for non-axiomatic reasoning: inheritance, implication, abduction, induction, revision, conflicts, and experience-derived beliefs.")
(CapabilityAlwaysOnGuide metta "Use PLN with (|~ ...) for probabilistic logic: properties, categories, implication, inheritance, similarity, and confidence-weighted conclusions.")
(CapabilityAlwaysOnGuide metta "Truth values use (stv frequency confidence); when evidence conflicts, preserve the conflict instead of flattening it into a confident answer.")
(CapabilityErrorRecovery metta invalid-metta-expression "Reader failed: use one valid MeTTa expression, or a known NAL/PLN form through metta.")
(CapabilityErrorRecovery metta metta-eval-error "Expression parsed but evaluation failed: simplify, inspect docs/files, or use known working NAL/PLN patterns; do not keep retrying format guesses.")
"""

_COMMAND_SHAPE_HEADS = {
    "remember",
    "query",
    "episodes",
    "pin",
    "shell",
    "read-file",
    "write-file",
    "append-file",
    "send",
    "search",
    "tavily-search",
    "technical-analysis",
    "metta",
    "syntax-error",
}
_COMMAND_SHAPE_RE = re.compile(r"^\(\s*([A-Za-z][A-Za-z0-9_-]*)")


def describe_command_shape(command_text):
    """Return an inert MeTTa command-shape atom for syntax only."""
    text = str(command_text or "").strip()
    match = _COMMAND_SHAPE_RE.match(text)
    head = match.group(1) if match else "unknown"
    if head not in _COMMAND_SHAPE_HEADS:
        head = "unknown"
    return f"(CommandShape {head})"


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


def _default_arg_name(arg_type):
    return {
        "body-text": "text",
        "metta-expression": "sexpression",
        "path": "filename",
        "rest-text": "text",
        "token": "value",
    }.get(arg_type, "value")


def _default_example(name, args):
    rendered = " ".join(_default_arg_name(arg_type) for arg_type in args)
    return f"{name} {rendered}".strip()


def _parse_descriptor_args(rest):
    args = []
    for arg_type, arg_name in re.findall(r"\(Arg\s+([A-Za-z0-9_-]+)\s+([A-Za-z0-9_-]+)\)", rest or ""):
        args.append({"type": arg_type, "name": arg_name})
    return args


def _decode_descriptor_text(rest):
    rest = str(rest or "").strip()
    if not rest:
        return ""
    value, _tail = _consume_token(rest)
    return str(value)


def _parse_capability_descriptor_lines(lines):
    descriptors = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        match = re.match(r"^\((Capability[A-Za-z]+)\s+([A-Za-z0-9_-]+)(?:\s+(.*))?\)$", line)
        if not match:
            continue
        atom, name, rest = match.groups()
        if atom == "CapabilitySurfaceHint":
            surface = descriptors.setdefault(
                "__surface__",
                {"name": "__surface__", "contract_form": "surface", "surface_hints": {}, "error_cards": {}, "order": -1},
            )
            surface.setdefault("surface_hints", {}).setdefault(name, []).append(_decode_descriptor_text(rest))
            continue
        if atom == "CapabilityErrorCard":
            surface = descriptors.setdefault(
                "__surface__",
                {"name": "__surface__", "contract_form": "surface", "surface_hints": {}, "error_cards": {}, "order": -1},
            )
            target, _tail = _consume_token(rest or "")
            if target:
                surface.setdefault("error_cards", {})[name] = str(target)
            continue
        desc = descriptors.setdefault(
            name,
            {
                "name": name,
                "contract_form": "command",
                "args": [],
                "body_mode": None,
                "compact_guide": "",
                "always_on_guidance": [],
                "example": "",
                "effect": "",
                "guidance": [],
                "roles": [],
                "affordances": [],
                "risks": [],
                "detailed_guides": [],
                "trap": "",
                "recovery": "",
                "error_recovery": {},
                "order": len(descriptors),
            },
        )
        if atom == "CapabilityContract":
            form, tail = _consume_token(rest or "")
            desc["contract_form"] = str(form or "command")
            desc["args"] = _parse_descriptor_args(tail)
        elif atom == "CapabilityBodyMode":
            mode, _tail = _consume_token(rest or "")
            desc["body_mode"] = str(mode or "") or None
        elif atom == "CapabilityExample":
            desc["example"] = _decode_descriptor_text(rest)
        elif atom == "CapabilityEffect":
            desc["effect"] = _decode_descriptor_text(rest)
        elif atom == "CapabilityCompactGuide":
            desc["compact_guide"] = _decode_descriptor_text(rest)
        elif atom == "CapabilityAlwaysOnGuide":
            desc.setdefault("always_on_guidance", []).append(_decode_descriptor_text(rest))
        elif atom == "CapabilityGuidance":
            desc.setdefault("guidance", []).append(_decode_descriptor_text(rest))
        elif atom == "CapabilityRole":
            role, _tail = _consume_token(rest or "")
            if role:
                desc.setdefault("roles", []).append(str(role))
        elif atom == "CapabilityAffordance":
            affordance, _tail = _consume_token(rest or "")
            if affordance:
                desc.setdefault("affordances", []).append(str(affordance))
        elif atom == "CapabilityRisk":
            risk, _tail = _consume_token(rest or "")
            if risk:
                desc.setdefault("risks", []).append(str(risk))
        elif atom == "CapabilityDetailedGuide":
            desc.setdefault("detailed_guides", []).append(_decode_descriptor_text(rest))
        elif atom == "CapabilityTrap":
            desc["trap"] = _decode_descriptor_text(rest)
        elif atom == "CapabilityRecovery":
            desc["recovery"] = _decode_descriptor_text(rest)
        elif atom == "CapabilityErrorRecovery":
            error_kind, tail = _consume_token(rest or "")
            if error_kind:
                desc.setdefault("error_recovery", {})[str(error_kind)] = _decode_descriptor_text(tail)
    return descriptors


def _fallback_capability_descriptors():
    descriptors = _parse_capability_descriptor_lines(_FALLBACK_CAPABILITY_DESCRIPTOR_TEXT.splitlines())
    for desc in descriptors.values():
        args = tuple(arg.get("type") for arg in desc.get("args", []) if arg.get("type"))
        desc["example"] = desc.get("example") or _default_example(desc["name"], args)
    return descriptors


def _load_capability_descriptors():
    global _DESCRIPTOR_CACHE
    if _DESCRIPTOR_CACHE is not None:
        return _DESCRIPTOR_CACHE

    descriptors = {}
    try:
        lines = DESCRIPTOR_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        _DESCRIPTOR_CACHE = _fallback_capability_descriptors()
        return _DESCRIPTOR_CACHE

    descriptors = _parse_capability_descriptor_lines(lines)

    if not descriptors:
        descriptors = _fallback_capability_descriptors()
    _DESCRIPTOR_CACHE = descriptors
    return _DESCRIPTOR_CACHE


def _capability_contracts():
    contracts = {}
    for name, desc in _load_capability_descriptors().items():
        if desc.get("contract_form") != "command":
            continue
        args = tuple(arg.get("type") for arg in desc.get("args", []) if arg.get("type"))
        if args:
            contracts[name] = args
    return contracts


def _command_names():
    return set(_capability_contracts())


def _body_modes():
    modes = {}
    for name, desc in _load_capability_descriptors().items():
        if desc.get("body_mode"):
            modes[name] = desc["body_mode"]
    return modes


def _body_commands():
    return set(_body_modes())


def _multiline_body_commands():
    return {name for name, mode in _body_modes().items() if mode in {"multiline-rest", "path-plus-body"}}


def _two_arg_body_commands():
    return {name for name, args in _capability_contracts().items() if args == ("path", "body-text")}


def _rest_text_commands():
    return {name for name, args in _capability_contracts().items() if args == ("rest-text",)}


def _one_arg_commands():
    return {name for name, args in _capability_contracts().items() if args == ("token",)}


def _contract_signature(name, desc):
    compact = (desc.get("compact_guide") or "").strip()
    if compact:
        return compact
    args = desc.get("args") or []
    if not args:
        return name
    labels = []
    for arg in args:
        arg_type = arg.get("type", "")
        arg_name = arg.get("name") or _default_arg_name(arg_type)
        labels.append(arg_name)
    return f"{name} {' '.join(labels)}"


def _surface_hints(kind):
    surface = _load_capability_descriptors().get("__surface__", {})
    return [item for item in surface.get("surface_hints", {}).get(kind, []) if item]


def _descriptor_error_recovery(kind, head):
    desc = _load_capability_descriptors().get(str(head or ""), {})
    recovery = desc.get("error_recovery", {}).get(str(kind or ""))
    if recovery:
        return recovery
    return desc.get("recovery", "")


def _descriptor_error_card_name(kind, head):
    descriptors = _load_capability_descriptors()
    surface = descriptors.get("__surface__", {})
    card = surface.get("error_cards", {}).get(str(kind or ""))
    if card in descriptors:
        return card
    if str(head or "") in descriptors:
        return str(head or "")
    return ""


def render_capability_card(command, compact=False):
    desc = _load_capability_descriptors().get(str(command or ""), {})
    if not desc or desc.get("contract_form") != "command":
        return ""
    name = desc["name"]
    parts = [f"{name}: {_contract_signature(name, desc)}"]
    roles = ", ".join(desc.get("roles", []))
    affordances = ", ".join(desc.get("affordances", []))
    risks = ", ".join(desc.get("risks", []))
    if roles:
        parts.append(f"role={roles}")
    if affordances:
        parts.append(f"affordances={affordances}")
    if desc.get("effect"):
        parts.append(desc["effect"])
    guides = list(desc.get("detailed_guides", []))
    if not compact:
        guides.extend(desc.get("guidance", []))
    for item in guides:
        if item:
            parts.append(item)
    if risks:
        parts.append(f"risks={risks}")
    if desc.get("trap"):
        parts.append(f"trap: {desc['trap']}")
    if desc.get("recovery"):
        parts.append(f"recovery: {desc['recovery']}")
    if compact:
        return "; ".join(parts)
    return "\n".join(parts)


def _with_descriptor_recovery(kind, head, hint):
    parts = [str(hint or "").strip()]
    recovery = _descriptor_error_recovery(kind, head)
    if recovery and recovery not in parts[0]:
        parts.append(f"Recovery: {recovery}")
    card_name = _descriptor_error_card_name(kind, head)
    card = render_capability_card(card_name, compact=True) if card_name else ""
    if card and card not in " ".join(parts):
        parts.append(f"Capability card: {card}")
    for item in _surface_hints("syntax-feedback") or _surface_hints("always-on"):
        if item and item not in " ".join(parts):
            parts.append(item)
    return " ".join(part for part in parts if part)


def render_capability_context():
    descriptors = sorted(_load_capability_descriptors().values(), key=lambda item: item.get("order", 0))
    lines = ["Commands are one per line. Human-facing prose must use send."]
    lines.extend(_surface_hints("always-on"))
    always_on_notes = []
    for desc in descriptors:
        if desc.get("contract_form") != "command" or not desc.get("args"):
            continue
        name = desc["name"]
        signature = _contract_signature(name, desc)
        always_on_notes.extend(item.strip() for item in desc.get("always_on_guidance", []) if item.strip())
        lines.append(f"- {name}: {signature}")
    if always_on_notes:
        lines.append("Always-on syntax guides:")
        seen = set()
        for item in always_on_notes:
            if item in seen:
                continue
            seen.add(item)
            lines.append(f"- {item}")
    lines.append("Also accepted: direct balanced parenthesized MeTTa, for example (+ 1 2), and top-level bang-prefixed MeTTa, for example !(quote (+ 1 2)); do not prefix it with direct-metta.")
    return "\n".join(lines)


def _get_command_name(line):
    normalized = _strip_outer_parens(str(line or "").strip())
    if not normalized:
        return ""
    return normalized.split(maxsplit=1)[0].rstrip(":")


def _missing_command_space_head(line):
    text = _strip_outer_parens(str(line or "").strip())
    for command in sorted(_command_names(), key=len, reverse=True):
        if text.startswith(command + '"') or text.startswith(command + "'"):
            return command
    return ""


def _is_known_command(line):
    return _get_command_name(line) in _command_names()


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
    if first in _multiline_body_commands():
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
    if cmd not in _multiline_body_commands():
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
        if cmd not in _multiline_body_commands() or not body.startswith('"'):
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
        if cmd not in _multiline_body_commands():
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
            if marker and body_cmd in _two_arg_body_commands():
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
    hint = _with_descriptor_recovery(kind, head, hint)
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
    if _omega_command_line_re().search(text):
        return (
            "Shell payload contains command-looking Omega lines. They remain shell text and are not "
            "Omega actions. Put send, pin, metta, query, read-file, write-file, append-file, or search "
            "on separate top-level lines outside shell."
        )
    return ""


def _omega_command_line_re():
    commands = sorted((re.escape(name) for name in _command_names()), key=len, reverse=True)
    if not commands:
        return re.compile(r"a^")
    return re.compile(r"(?m)^\s*(" + "|".join(commands) + r")(?:\s|:|$)")


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
    if cmd not in _command_names():
        return _syntax_error("unknown-command", cmd, original, "Use a command listed in SKILLS, or put human-facing prose inside send.")

    if cmd == "metta":
        if not rest:
            return _syntax_error("missing-argument", cmd, original, "Missing expression. Use metta (expression).")
        if rest.strip().startswith('"'):
            rest = _decode_one_quoted_metta_expression(rest)
        if not _balanced_parenthesized(rest):
            return _syntax_error("invalid-metta", cmd, original, "Use one balanced MeTTa expression.")
        return f"(metta {quote_arg(rest)})"

    if cmd in _two_arg_body_commands():
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

    if cmd in _one_arg_commands():
        arg, trailing = _consume_token(rest)
        if not arg:
            return _syntax_error("missing-argument", cmd, original, f"Missing argument. Use {cmd} value.")
        if trailing:
            return _syntax_error("unexpected-trailing-text", cmd, original, f"Use one argument for {cmd}; quote paths or values containing spaces.")
        return f"({cmd} {quote_arg(arg)})"

    if cmd in _rest_text_commands():
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
        if cmd in _body_commands() and cmd != "shell":
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
