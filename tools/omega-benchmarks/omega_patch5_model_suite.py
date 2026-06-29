#!/usr/bin/env python3
"""Patch 5 model route preflight plus short continuity benchmark suite."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib import error, request


ROOT = Path(os.environ.get("OMEGACLAW_BENCHMARK_ROOT", "/home/jon/OmegaClaw-patch1-final-test"))
RUNS = ROOT / "seal-runs"
OPENROUTER = "https://openrouter.ai/api/v1"

MODEL_GROUPS = {
    "qwen": [
        "qwen/qwen3.5-9b",
        "qwen/qwen3.6-27b",
        "qwen/qwen3.6-35b-a3b",
        "qwen/qwen3-next-80b-a3b-instruct",
        "qwen/qwen3.7-plus",
        "qwen/qwen3.7-max",
        "qwen/qwen3.6-flash",
        "qwen/qwen3.6-plus",
    ],
    "deepseek": ["deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"],
    "nvidia": [
        "nvidia/nemotron-nano-9b-v2:free",
        "nvidia/nemotron-nano-12b-v2-vl:free",
        "nvidia/nemotron-3-nano-30b-a3b",
        "nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-3-ultra-550b-a55b",
    ],
    "glm": ["z-ai/glm-5.2", "z-ai/glm-5.1"],
    "kimi": ["moonshotai/kimi-k2.7-code", "moonshotai/kimi-k2.6"],
    "minimax": ["minimax/minimax-m3"],
    "gemma": ["google/gemma-4-31b-it", "google/gemma-4-26b-a4b-it"],
    "llama": [
        "meta-llama/llama-3.2-1b-instruct",
        "meta-llama/llama-3.2-3b-instruct",
        "meta-llama/llama-3.1-8b-instruct",
        "meta-llama/llama-4-scout",
        "meta-llama/llama-4-maverick",
        "meta-llama/llama-3.3-70b-instruct",
    ],
    "nous": ["nousresearch/hermes-4-70b", "nousresearch/hermes-4-405b"],
}

MODE_ORDER = ["max", "xhigh", "high", "medium", "low", "minimal", "none"]


def stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()


def read_key() -> str:
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    profile = Path.home() / ".profile"
    if profile.exists():
        match = re.search(r"^\s*export\s+OPENROUTER_API_KEY=(['\"]?)([^'\"\n]+)\1", profile.read_text(errors="ignore"), re.MULTILINE)
        if match:
            return match.group(2).strip()
    raise SystemExit("OPENROUTER_API_KEY is not available.")


def http_json(url: str, *, key: str | None = None, body: dict | None = None, timeout: int = 90) -> tuple[int, dict | str]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw or "{}")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload: dict | str = json.loads(raw)
        except Exception:
            payload = raw
        return exc.code, payload
    except Exception as exc:
        return 0, str(exc)


def write_jsonl(path: Path, item: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def endpoint_rank(endpoint: dict) -> tuple:
    def number(value, default=None):
        return value if isinstance(value, (int, float)) else default

    latency = number(endpoint.get("latency_last_30m"))
    throughput = number(endpoint.get("throughput_last_30m"), 0)
    return (
        0 if endpoint.get("status") == 0 else 1,
        -(endpoint.get("uptime_last_5m") or 0),
        -(endpoint.get("uptime_last_30m") or 0),
        10**9 if latency is None else latency,
        -(throughput or 0),
    )


def select_providers(model: str, key: str, max_providers: int) -> list[dict]:
    status, payload = http_json(f"{OPENROUTER}/models/{model}/endpoints", key=key)
    if status >= 400 or not isinstance(payload, dict):
        return []
    endpoints = payload.get("data", {}).get("endpoints", [])
    selected = []
    seen = set()
    for endpoint in sorted(endpoints, key=endpoint_rank):
        name = endpoint.get("provider_name")
        if not name or name in seen:
            continue
        seen.add(name)
        selected.append(endpoint)
        if len(selected) >= max_providers:
            break
    return selected


def mode_candidates(model_meta: dict | None) -> list[str]:
    efforts = (((model_meta or {}).get("reasoning") or {}).get("supported_efforts") or [])
    if efforts:
        allowed = {str(item).lower() for item in efforts}
        return [mode for mode in MODE_ORDER if mode == "none" or mode in allowed]
    return MODE_ORDER[:]


def preflight_call(model: str, provider: str, mode: str, key: str, cycle: int) -> dict:
    token = f"PATCH5_PREFLIGHT_{cycle}"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are running a route compatibility check. Reply tersely."},
            {"role": "user", "content": f"Reply with CHECK_OK and this token: {token}"},
        ],
        "max_tokens": 512,
        "temperature": 0,
        "provider": {"order": [provider], "allow_fallbacks": False},
    }
    body["reasoning"] = {"effort": mode, "exclude": True}
    started = time.time()
    status, payload = http_json(f"{OPENROUTER}/chat/completions", key=key, body=body, timeout=120)
    elapsed = round(time.time() - started, 3)
    text = ""
    if isinstance(payload, dict):
        try:
            text = payload.get("choices", [{}])[0].get("message", {}).get("content") or ""
        except Exception:
            text = ""
    return {
        "status": status,
        "ok": 200 <= status < 300 and bool(text.strip()),
        "elapsed_s": elapsed,
        "text_preview": text[:200],
        "error_preview": json.dumps(payload, ensure_ascii=False)[:500] if not (200 <= status < 300) else "",
    }


def run_preflight(models: list[str], args: argparse.Namespace, suite_dir: Path, key: str) -> list[dict]:
    attempts_path = suite_dir / "preflight_attempts.jsonl"
    selected_path = suite_dir / "selected_routes.jsonl"
    status, catalog = http_json(f"{OPENROUTER}/models", key=key, timeout=60)
    catalog_by_id = {item.get("id"): item for item in (catalog.get("data", []) if isinstance(catalog, dict) else [])}
    selections = []
    for idx, model in enumerate(models, 1):
        print(f"[preflight] {idx}/{len(models)} {model}", flush=True)
        providers = select_providers(model, key, args.max_providers)
        modes = mode_candidates(catalog_by_id.get(model))
        model_selection = None
        for endpoint in providers:
            provider = endpoint["provider_name"]
            provider_best = None
            for mode in modes:
                calls = [preflight_call(model, provider, mode, key, cycle) for cycle in (1, 2)]
                attempt = {"model": model, "provider": provider, "mode": mode, "calls": calls, "ok": all(call["ok"] for call in calls)}
                write_jsonl(attempts_path, attempt)
                print(f"[preflight]   {provider} {mode}: {'OK' if attempt['ok'] else 'fail'}", flush=True)
                if attempt["ok"]:
                    provider_best = {"model": model, "provider": provider, "reasoning_mode": mode, "endpoint": endpoint, "calls": calls}
                    break
            if provider_best and (model_selection is None or MODE_ORDER.index(provider_best["reasoning_mode"]) < MODE_ORDER.index(model_selection["reasoning_mode"])):
                model_selection = provider_best
        if model_selection is None:
            model_selection = {"model": model, "provider": "", "reasoning_mode": "", "failed": True, "provider_count": len(providers)}
        write_jsonl(selected_path, model_selection)
        selections.append(model_selection)
    return selections


def run_benchmark(selection: dict, args: argparse.Namespace, suite_dir: Path) -> dict:
    model = selection["model"]
    provider = selection.get("provider", "")
    mode = selection.get("reasoning_mode", "")
    if selection.get("failed") or not provider or not mode:
        return {"model": model, "skipped": True, "reason": "no passing preflight route"}
    run_id = f"{args.run_prefix}-{slug(model)}-{slug(provider)}-{mode}-{stamp()}"
    cmd = [
        "python3",
        "bin/omega_patch4_natural_continuity_probe.py",
        "--run-id", run_id,
        "--cold-start",
        "--omega-provider", "OpenRouter",
        "--openrouter-model", model,
        "--provider-order", provider,
        "--provider-sort", "",
        "--reasoning-mode", mode,
        "--pre-turns", "5",
        "--away-cycles", "0",
        "--away-prompt", "im off for a bit, do what you want",
        "--away-history-entries", "0",
        "--away-iterations", "0",
        "--away-min-wait-seconds", str(args.away_minutes * 60),
        "--away-timeout-seconds", str(args.away_minutes * 60 + args.away_timeout_slack_seconds),
        "--max-new-input-loops", str(args.max_new_input_loops),
        "--return-turns", "5",
    ]
    if args.allow_fallbacks:
        cmd.append("--allow-fallbacks")
    if args.dry_run:
        cmd.append("--dry-run")
    started = time.time()
    out_path = suite_dir / f"benchmark-{slug(model)}.out"
    print(f"[benchmark] starting {model} on {provider} mode={mode}", flush=True)
    with out_path.open("w", encoding="utf-8") as out:
        proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=out, stderr=subprocess.STDOUT)
    run_dir = RUNS / run_id
    result = {
        "model": model,
        "provider": provider,
        "reasoning_mode": mode,
        "run_id": run_id,
        "returncode": proc.returncode,
        "elapsed_s": round(time.time() - started, 3),
        "stdout_path": str(out_path),
        "run_dir": str(run_dir),
        "scorecard": str(run_dir / "natural_continuity_scorecard.md"),
    }
    score_path = run_dir / "natural_continuity_score.json"
    if score_path.exists():
        result["score"] = json.loads(score_path.read_text(encoding="utf-8"))
    return result


def write_summary(suite_dir: Path, selections: list[dict], benchmark_results: list[dict]) -> None:
    lines = [
        "# Patch 5 Model Suite",
        "",
        f"Updated: {stamp()}",
        "",
        "## Selected Routes",
        "",
        "| Model | Provider | Reasoning | Status |",
        "|---|---|---|---|",
    ]
    for item in selections:
        status = "failed" if item.get("failed") else "ok"
        lines.append(f"| `{item['model']}` | `{item.get('provider', '')}` | `{item.get('reasoning_mode', '')}` | {status} |")
    lines += ["", "## Benchmarks", "", "| Model | Provider | Reasoning | Return | Score | Run |", "|---|---|---|---:|---:|---|"]
    for item in benchmark_results:
        score = item.get("score", {})
        score_text = f"{score.get('passed', '?')}/{score.get('total', '?')}" if score else ""
        lines.append(
            f"| `{item.get('model')}` | `{item.get('provider', '')}` | `{item.get('reasoning_mode', '')}` | "
            f"{item.get('returncode', '')} | {score_text} | `{item.get('run_id', item.get('reason', ''))}` |"
        )
    (suite_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def flatten_models(args: argparse.Namespace) -> list[str]:
    models = [model for group in MODEL_GROUPS.values() for model in group]
    if args.only:
        wanted = set(args.only)
        models = [model for model in models if model in wanted or slug(model) in wanted]
    if args.start_index:
        models = models[args.start_index:]
    if args.limit:
        models = models[: args.limit]
    return models


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-prefix", default="patch5-short-suite")
    parser.add_argument("--suite-dir", type=Path)
    parser.add_argument("--max-providers", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--benchmark-only", type=Path, help="Use an existing selected_routes.jsonl file.")
    parser.add_argument("--away-minutes", type=int, default=5)
    parser.add_argument("--away-timeout-slack-seconds", type=int, default=90)
    parser.add_argument("--max-new-input-loops", type=int, default=400)
    parser.add_argument("--allow-fallbacks", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    suite_dir = args.suite_dir or (RUNS / f"{args.run_prefix}-{stamp()}")
    suite_dir.mkdir(parents=True, exist_ok=True)
    key = read_key()
    models = flatten_models(args)
    (suite_dir / "requested_models.json").write_text(json.dumps(models, indent=2), encoding="utf-8")

    if args.benchmark_only:
        selections = [json.loads(line) for line in args.benchmark_only.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        selections = run_preflight(models, args, suite_dir, key)
    benchmark_results = []
    if not args.preflight_only:
        for selection in selections:
            result = run_benchmark(selection, args, suite_dir)
            benchmark_results.append(result)
            write_jsonl(suite_dir / "benchmark_results.jsonl", result)
            write_summary(suite_dir, selections, benchmark_results)
    write_summary(suite_dir, selections, benchmark_results)
    print(suite_dir / "SUMMARY.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
