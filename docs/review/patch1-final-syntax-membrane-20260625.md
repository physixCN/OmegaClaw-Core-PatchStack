# Patch 1 Final Syntax Membrane - 2026-06-25

Base: ASI Alliance `main` at `4c1474851bca741c44d974375a87795cc18997d7`.

Branch: `patch/01-final-syntax-membrane`.

## Scope

This patch is syntax only. It changes the deterministic membrane that turns LLM output text into MeTTa command expressions and strips known provider transport noise before that membrane sees text.

It does not add capability descriptors, accountability, salience, channel routing, benchmark scoring, readiness policy, media affordances, or Jon-live private commands.

## Behaviors Covered

- Preserves `send`, `write-file`, and `append-file` bodies, including blank lines, Markdown, colons, bullets, and command words inside prose.
- Preserves quoted multiline artifact bodies until their closing quote, so command-looking rows inside LaTeX, Markdown tables, HTML, or reports stay file content.
- Adds explicit exact-body syntax for `shell`, `write-file`, and `append-file` using `<<BODY ... BODY`, plus triple-quoted bodies using `"""..."""`.
- Canonicalizes literal escaped line breaks such as `\n\n` inside body payloads so human-facing replies and file bodies keep paragraph/list formatting.
- Treats simple bare known command lines after one-line body commands as command boundaries, so internal control lines such as `pin ...` do not leak into user-facing `send` text.
- Keeps command-looking lines as body content when the surrounding body clearly signals prose or artifact content, such as a heading ending in `:`, LaTeX/table rows, HTML, or explicit multiline delimiters.
- Accepts explicit parenthesized command boundaries after body commands, for example `(remember done)`.
- Preserves direct balanced parenthesized MeTTa unchanged.
- Rejects malformed `metta` expressions and unbalanced direct MeTTa.
- Rejects `metta` payloads that contain trailing text after the first complete expression, such as `metta (add1 5)query ...`.
- Accepts `metta "(+ 1 2)"` by unwrapping one quoted payload only when the inside is exactly one balanced MeTTa expression.
- Converts MeTTa reader/evaluator failures inside the `metta` skill into specific syntax feedback, so runtime MeTTa failures do not masquerade as generic command-format errors.
- Rejects malformed `episodes` timestamp arguments before runtime so timestamp/query concatenation produces typed feedback instead of a generic single-command failure.
- Rejects known command heads missing the command/argument space, such as `query"topic"`, with a specific `missing-command-space` syntax error.
- Rejects shell payloads that begin with command-looking Omega lines or shell heredocs that are being used as Omega artifact transport, with a specific `shell-command-boundary` syntax error.
- Rejects unknown command-shaped output instead of silently inventing commands.
- Rejects raw shell-like text unless it is emitted through `shell`.
- Repairs a single trailing colon only on known ASI command heads.
- Splits safe top-level semicolon command chains.
- Keeps semicolons inside `send`, `shell`, and file bodies.
- Keeps empty output and literal `()` as no-op `()`.
- Strips known MiniMax transport markers before parser normalization.
- Keeps ASI Patch 1 command surface as `search`; it does not rename to `web-search`.

## Important Boundary Decision

After a simple one-line body command, a bare known command line starts a new command. This matches the model-facing output contract in `loop.metta`, where commands are shown as `toolName arg`.

Example:

```text
send Done.
pin Awaiting user input, idle
```

becomes a `send` followed by `pin`, not one leaked user-facing message.

Command words remain safe when they are part of prose or artifact content rather than a simple command boundary:

```text
send Summary: query result was empty, but search result was usable.
```

Bulleted command-looking text also remains body text:

```text
send Report:
- query result was empty
- pin is mentioned as text
```

The same applies to body text that begins with a prose heading:

```text
send I checked it:
query result was empty
search result was usable
```

and to generated file content:

```text
write-file report.tex "\midrule
query & Search memory \\
send & Send a message \\
\bottomrule"
```

This fixes the control-line leak without adding a bridge filter or changing Omega's cognition. A future explicit multiline data syntax may still be useful, but is outside Patch 1 Final.

## Explicit Multiline Data

Patch 1 Final now includes the syntax-only part of the older live Omega exact-body membrane. The recommended model-facing forms are:

```text
write-file report.md """
# Report

send this line is file content, not a command
"""
```

and, for content that may itself contain triple quotes:

```text
write-file script.py <<PY
def explain():
    """This docstring is file content."""
    return "colon: preserved"
PY
```

Shell bodies can also use the same exact delimiter when the command itself spans lines:

```text
shell <<BODY
find "$CORE_PATH" -type f -name '*.metta'
printf 'colon: ok\n'
BODY
```

Patch 1 now rejects shell bodies that appear to swallow top-level Omega commands. For example, `shell <<BODY ... pin ... BODY` returns `shell-command-boundary` instead of executing `pin` or silently preserving the mistake. This does not infer intent or extract commands from the shell body; it fails closed and tells the model to emit Omega commands as separate top-level lines. When the shell body starts with `cat > file <<EOF`, the feedback points to the existing `write-file path <<TAG` / `append-file path <<TAG` file-body syntax for Omega-authored artifacts.

This patch intentionally keeps the ASI core command names as `write-file` and `append-file`. It does not import the live repo's internal `write-file-base64` lowering, because that belongs to the larger signature-driven parser and runtime command surface, not this first syntax-only patch.

Patch 1 treats long delimited bodies as ordinary syntax, not as a separate capability. Arbitrary tags such as `<<OMEGA_ARTIFACT` are valid, and the closing tag is recognized only when it appears alone on a line. Command-looking text inside the body remains raw data. If the closing tag is absent, the parser fails closed with `missing-body-terminator` and a bounded preview of the malformed input.

The GLM5.1/BaseTen autonomy run on 2026-06-26 exercised this exact boundary with generated Perl artifacts. Omega sometimes began a long `append-file <<TAG` code chunk and failed to close the tag before the output ended. Patch 1 handled this as intended: prior complete commands in the same response remained executable, the incomplete file-body command was rejected as `missing-body-terminator`, and command-looking text inside the incomplete body, such as `pin ...` or `shell chmod ...`, was not executed as Omega control. This is now covered by a benchmark-shaped regression test.

## Typed Rejections

Patch 1 now keeps parser rejections causal and mechanical. For example, `episodes 2026-06-25 16:23:00query syntax errors` is rejected as `invalid-argument-format` because `episodes` accepts exactly one timestamp-shaped argument. This is not semantic episode search and not intent guessing; it is command-shape validation. Semantic recall remains the role of `query`, while `episodes` remains timestamp-window lookup.

The runtime `helper.around_time` path also returns `EPISODES-FORMAT-ERROR` for malformed timestamps, so direct balanced MeTTa calls such as `(episodes "bad text")` fail with a specific skill-level format result rather than surfacing as a generic command failure.

## MeTTa Runtime Feedback

The autonomy baseline surfaced a subtle Patch 1 issue: expressions such as `metta (= (square x) (* x x))` were syntactically valid at the outer command membrane, but failures inside `sread` or `eval` bubbled out as `SINGLE_COMMAND_FORMAT_ERROR`. That misled the agent into retrying command formatting instead of changing the MeTTa expression or using a smaller test.

Patch 1 keeps the boundary explicit:

- The Python membrane accepts one complete balanced MeTTa expression after `metta`.
- If the model wraps that one expression in a single quoted string, the membrane unwraps that quote layer mechanically.
- Extra text after the first complete expression is rejected before runtime.
- The `metta` skill catches reader/evaluator failures and returns `invalid-metta-expression` or `metta-eval-error` feedback.

This stays syntax-only: it does not teach MeTTa semantics, add lambda support, change the PeTTa interpreter, or alter `loop.metta`.

## 2026-06-27 Model-Sweep Syntax Amendment

The 10-model autonomy sweep on 2026-06-26/27 exposed three remaining syntax-facing failure shapes across otherwise usable models:

- quoted MeTTa payloads, for example `metta "(+ 1 2)"`;
- missing spaces after known command heads, for example `query"autonomy test evidence"`;
- shell payloads swallowing Omega commands or being used as ad hoc file-body transport.

Patch 1 handles these mechanically. It unwraps only one quoted balanced MeTTa expression, returns a cause-specific `missing-command-space` error for known heads glued to quoted arguments, and fails closed with `shell-command-boundary` when shell text starts with command-looking Omega lines. It does not alias commands, infer goals, extract commands from shell text, add new capabilities, or modify the loop.

## 2026-06-28 Max Syntax Matrix Amendment

Max Botnick's failure report exposed three remaining syntax-envelope failures in the locked command membrane. Patch 1 now repairs accidental model-level `\"` quote escaping only for non-shell rest-text commands, rejects ambiguous inline `write-file` / `append-file` bodies whose internal quotes break the command envelope, and recognizes top-level bang-prefixed MeTTa such as `!(quote (+ 1 2))` as MeTTa-shaped syntax instead of a generic unknown command. Shell payload escaping is intentionally left unchanged because `\"` can be meaningful shell text; rich artifact content should use explicit delimited bodies.

## Escaped Newline Decision

The model may emit body text with literal escaped line breaks, for example `send Hello\n\nWorld`, especially when producing paragraph-formatted replies. Patch 1 treats those escapes as formatting inside body commands, not as literal text to show to the human. The parser canonicalizes them before command execution.

The channel send boundary must preserve that result. Patch 1 therefore removes final send-path re-escaping of real newlines back into visible escaped newline text, and normalizes any remaining escaped newline sequences immediately before dispatch. This keeps paragraph breaks human-readable without adding new commands or changing the reasoning loop.

## Patham / MeTTaClaw Alignment

Patham's MeTTaClaw loop asks the model for command-shaped lines such as `toolName arg`, then runs those lines through `balance_parentheses` before `sread` and evaluation. That means the syntax membrane is a deterministic canonicalizer from model-friendly command syntax into executable MeTTa command expressions.

Patch 1 Final follows that model. It does not ask the LLM to produce perfect raw MeTTa for every action, and it does not infer arbitrary prose into commands. It only normalizes the advertised command surface, preserves body text, and rejects malformed or unknown command-shaped output.

## Why Patch 1 Is Not Fully MeTTa-Owned

Patch 1 intentionally leaves the command grammar in the deterministic Python membrane. This is a scope boundary, not a desired end state. Moving command names, argument contracts, and body modes into MeTTa-owned declarations is the right long-term direction, but doing that here would turn Patch 1 from a syntax-only repair into a capability-surface/ontology patch.

The practical alignment target for Patch 1 is therefore narrower: keep Patham's loop contract intact, canonicalize model-friendly command text into executable MeTTa, fail closed on malformed output, and avoid modifying `src/loop.metta`. Patch 2 is the proper place to move the advertised command surface toward MeTTa ownership.

This is why Patch 1 should not be judged as the final capability architecture. It is the deterministic membrane that makes later MeTTa-owned capability work safer.
