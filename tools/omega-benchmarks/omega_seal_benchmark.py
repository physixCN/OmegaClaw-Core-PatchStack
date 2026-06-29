#!/usr/bin/env python3
"""OmegaClaw Seal Benchmark runner.

Runs VM-native end-to-end tests against the local Patch 1/2 test bridge.
This is harness infrastructure, not part of the upstream patch payloads.
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse


TEST_ROOT = Path(os.environ.get("OMEGACLAW_BENCHMARK_ROOT", "/home/jon/OmegaClaw-patch1-final-test"))
BRIDGE_URL = os.environ.get("OMEGACLAW_BENCHMARK_BRIDGE_URL", "http://127.0.0.1:8091")
RUNS_DIR = TEST_ROOT / "seal-runs"
CORE_DIR = TEST_ROOT / "repos" / "OmegaClaw-Core"
HISTORY_PATH = CORE_DIR / "memory" / "history.metta"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass
class TaskSpec:
    lane: str
    task_id: str
    title: str
    prompt: str
    timeout_seconds: int = 240
    min_wait_seconds: int = 10
    expected_response_terms: list[str] = field(default_factory=list)
    forbidden_history_terms: list[str] = field(default_factory=lambda: ["SINGLE_COMMAND_FORMAT_ERROR", "((syntax-error"])
    expected_files: dict[str, list[str]] = field(default_factory=dict)
    verifier: Callable[["Benchmark", "TaskSpec", dict], list[CheckResult]] | None = None
    complete_on_history_activity: bool = False
    complete_after_min_wait: bool = False
    complete_after_history_entries: int = 0
    complete_after_omega_iterations: int = 0


MEANINGFUL_HISTORY_TERMS = (
    "(remember ",
    "(query ",
    "(episodes ",
    "(search ",
    "(tavily-search ",
    "(read-file ",
    "(write-file ",
    "(append-file ",
    "(shell ",
    "(metta ",
)


def classify_history_activity(delta: str) -> str:
    if not delta.strip():
        return "none"
    if "syntax-error" in delta or "SINGLE_COMMAND_FORMAT_ERROR" in delta or "invalid-command-format" in delta:
        return "syntax-error"
    if any(term in delta for term in MEANINGFUL_HISTORY_TERMS):
        return "meaningful"
    if "(pin " in delta:
        return "live-state-only"
    return "history-activity"


def count_history_entries(text: str) -> int:
    return len(re.findall(r'(?m)^\s*\("?\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', text or ""))


def count_omega_iterations(text: str) -> int:
    return len(re.findall(r"\(---------iteration\s+\d+\)", text or ""))


def utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def local_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def write_jsonl(path: Path, item: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def run_cmd(cmd: list[str], *, cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def json_request(url: str, method: str = "GET", body: dict | None = None, timeout: int = 20) -> dict:
    parsed = urlparse(url)
    if parsed.scheme != "http":
        raise ValueError(f"Only local http URLs are supported by this harness: {url}")
    payload = None
    headers = {}
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout)
    try:
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8", errors="replace")
        if response.status >= 400:
            raise RuntimeError(f"HTTP {response.status}: {raw[:500]}")
        return json.loads(raw or "{}")
    finally:
        conn.close()


def load_profile_key(env: dict[str, str]) -> dict[str, str]:
    """Load OpenRouter key from login-shell profile when a plain SSH env lacks it."""
    if env.get("OPENROUTER_API_KEY"):
        return env
    profile = Path.home() / ".profile"
    text = read_text(profile)
    match = re.search(r"^\s*export\s+OPENROUTER_API_KEY=(['\"]?)([^'\"\n]+)\1", text, re.MULTILINE)
    if match:
        env = env.copy()
        env["OPENROUTER_API_KEY"] = match.group(2).strip()
    return env


class Benchmark:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.test_root: Path = args.test_root
        self.core_dir = self.test_root / "repos" / "OmegaClaw-Core"
        self.history_path = self.core_dir / "memory" / "history.metta"
        self.bridge_url = args.bridge_url.rstrip("/")
        self.run_id = args.run_id or f"seal-{utc_stamp()}"
        self.run_dir = args.run_root / self.run_id
        self.artifact_dir = self.run_dir / "artifacts"
        self.transcript_path = self.run_dir / "transcript.jsonl"
        self.commands_path = self.run_dir / "commands.jsonl"
        self.syntax_errors_path = self.run_dir / "syntax_errors.jsonl"
        self.scorecard_path = self.run_dir / "scorecard.md"
        self.results: list[dict] = []
        self.last_seen = 0
        self.history_offset = 0
        self.log_offsets: dict[str, int] = {}

    def log(self, message: str) -> None:
        print(f"[{local_stamp()}] {message}", flush=True)

    def record_command(self, action: str, detail: dict) -> None:
        write_jsonl(self.commands_path, {"at": utc_stamp(), "action": action, **detail})

    def prepare(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "run_meta.json").write_text(
            json.dumps(
                {
                    "run_id": self.run_id,
                    "created_at": local_stamp(),
                    "suite": self.args.suite,
                    "test_root": str(self.test_root),
                    "bridge_url": self.bridge_url,
                    "cold_start": self.args.cold_start,
                    "provider_order": self.args.provider_order,
                    "provider_sort": self.args.provider_sort,
                    "omega_provider": self.args.omega_provider,
                    "openrouter_model": self.args.openrouter_model,
                    "notes": "VM-native OmegaClaw Seal Benchmark run.",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        self.log(f"Run directory: {self.run_dir}")
        if self.args.dry_run:
            self.write_dry_run_scorecard()
            return
        if self.args.cold_start:
            self.stop_runtime()
            self.archive_existing_logs()
            self.snapshot_and_wipe()
        self.log_offsets = self.current_log_offsets()
        self.start_bridge()
        self.wait_for_bridge()
        self.last_seen = self.get_next_id()
        self.history_offset = self.history_path.stat().st_size if self.history_path.exists() else 0

    def current_log_offsets(self) -> dict[str, int]:
        paths = {
            "web_bridge.log": self.test_root / "logs" / "web_bridge.log",
            "omega.log": self.test_root / "logs" / "patch1-web-bridge-omega.log",
        }
        return {name: path.stat().st_size if path.exists() else 0 for name, path in paths.items()}

    def archive_existing_logs(self) -> None:
        log_dir = self.test_root / "logs"
        archive_dir = log_dir / f"archive-before-{self.run_id}-{utc_stamp()}"
        log_paths = [
            log_dir / "web_bridge.log",
            log_dir / "patch1-web-bridge-omega.log",
        ]
        moved = []
        archive_dir.mkdir(parents=True, exist_ok=True)
        for path in log_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text("", encoding="utf-8")
                continue
            if path.stat().st_size == 0:
                continue
            dest = archive_dir / path.name
            shutil.move(str(path), str(dest))
            path.write_text("", encoding="utf-8")
            moved.append({"source": str(path), "dest": str(dest), "bytes": dest.stat().st_size})
        self.record_command("archive_logs", {"archive_dir": str(archive_dir), "moved": moved})

    def copy_file_tail(self, source: Path, dest: Path, start_offset: int) -> dict:
        end_offset = source.stat().st_size
        effective_start = start_offset if 0 <= start_offset <= end_offset else 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as src, dest.open("wb") as out:
            src.seek(effective_start)
            shutil.copyfileobj(src, out)
        return {
            "source": str(source),
            "dest": str(dest),
            "start_offset": start_offset,
            "effective_start_offset": effective_start,
            "end_offset": end_offset,
            "captured_bytes": end_offset - effective_start,
            "source_was_truncated_or_rotated": effective_start != start_offset,
        }

    def stop_runtime(self) -> None:
        self.log("Stopping test Omega runtime.")
        pidfile = self.test_root / "logs" / "web_bridge.pid"
        seen: set[int] = set()

        def kill_pid(pid: int, why: str) -> None:
            if pid in seen or pid in {os.getpid(), os.getppid()}:
                return
            seen.add(pid)
            self.record_command("kill", {"pid": pid, "why": why})
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            except PermissionError as exc:
                self.log(f"Could not terminate pid {pid}: {exc}")

        if pidfile.exists():
            try:
                kill_pid(int(pidfile.read_text().strip()), "web_bridge.pid")
            except ValueError:
                pass
        ps = run_cmd(["ps", "-eo", "pid=,args="]).stdout.splitlines()
        patterns = [
            "bin/web_bridge.py --host 127.0.0.1 --port 8091",
            "petta/run.sh run.metta commchannel=test",
            f"{self.test_root}/petta/src/main.pl",
        ]
        for line in ps:
            line = line.strip()
            if not line:
                continue
            pid_text, _, args = line.partition(" ")
            try:
                pid = int(pid_text)
            except ValueError:
                continue
            if any(pattern in args for pattern in patterns):
                kill_pid(pid, "matched-test-runtime")
        time.sleep(3)
        for pid in list(seen):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            try:
                os.kill(pid, signal.SIGKILL)
                self.record_command("kill9", {"pid": pid, "why": "still-running"})
            except ProcessLookupError:
                pass
        try:
            pidfile.unlink()
        except FileNotFoundError:
            pass

    def snapshot_and_wipe(self) -> None:
        self.log("Snapshotting and wiping active test memory.")
        backup_root = self.run_dir / "pre-run-backup"
        backup_root.mkdir(parents=True, exist_ok=True)
        items = [
            self.core_dir / "memory",
            self.test_root / "chroma_db",
            self.test_root / "petta" / "chroma_db",
            self.test_root / "runtime" / "memory",
            self.test_root / "runtime" / "channel_state",
        ]
        for item in items:
            if item.exists():
                dest = backup_root / item.relative_to(self.test_root)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.write_text("", encoding="utf-8")
        for directory in [self.test_root / "chroma_db", self.test_root / "petta" / "chroma_db", self.test_root / "runtime" / "memory"]:
            if directory.exists():
                shutil.rmtree(directory)
            directory.mkdir(parents=True, exist_ok=True)
        self.record_command("cold_start_wipe", {"backup_root": str(backup_root)})

    def start_bridge(self) -> None:
        try:
            json_request(f"{self.bridge_url}/api/messages?since=0", timeout=3)
            self.log("Bridge already responds; using current bridge.")
            return
        except Exception:
            pass
        self.log("Starting local web bridge.")
        env = load_profile_key(os.environ.copy())
        if not env.get("OPENROUTER_API_KEY"):
            raise SystemExit("OPENROUTER_API_KEY is not available. Run through bash -lc or restore ~/.profile export.")
        if self.args.provider_order:
            env["OMEGACLAW_OPENROUTER_PROVIDER_ORDER"] = self.args.provider_order
            env["OMEGACLAW_OPENROUTER_ALLOW_FALLBACKS"] = "1" if self.args.allow_fallbacks else "0"
        elif self.args.provider_sort:
            env["OMEGACLAW_OPENROUTER_PROVIDER_ORDER"] = ""
            env["OMEGACLAW_OPENROUTER_PROVIDER_SORT"] = self.args.provider_sort
        if self.args.omega_provider:
            env["OMEGACLAW_PROVIDER"] = self.args.omega_provider
        if self.args.openrouter_model:
            env["OMEGACLAW_OPENROUTER_MODEL"] = self.args.openrouter_model
        if self.args.reasoning_mode:
            env["OMEGACLAW_REASONING_MODE"] = self.args.reasoning_mode
        if self.args.max_new_input_loops:
            env["OMEGACLAW_MAX_NEW_INPUT_LOOPS"] = str(self.args.max_new_input_loops)
        log_path = self.test_root / "logs" / "web_bridge.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("a", encoding="utf-8")
        proc = subprocess.Popen(
            ["python3", "bin/web_bridge.py", "--host", "127.0.0.1", "--port", "8091"],
            cwd=self.test_root,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
        (self.test_root / "logs" / "web_bridge.pid").write_text(str(proc.pid), encoding="utf-8")
        self.record_command("start_bridge", {
            "pid": proc.pid,
            "provider_order": self.args.provider_order,
            "provider_sort": self.args.provider_sort,
            "omega_provider": self.args.omega_provider,
            "openrouter_model": self.args.openrouter_model,
            "reasoning_mode": self.args.reasoning_mode,
            "max_new_input_loops": self.args.max_new_input_loops,
        })

    def wait_for_bridge(self) -> None:
        deadline = time.time() + self.args.startup_timeout
        while time.time() < deadline:
            try:
                data = json_request(f"{self.bridge_url}/api/messages?since=0", timeout=5)
                text = "\n".join(item.get("text", "") for item in data.get("messages", []))
                if "OmegaClaw connected" in text or data.get("messages"):
                    self.log("Bridge is responding.")
                    return
            except Exception:
                pass
            time.sleep(2)
        raise SystemExit("Bridge did not respond before startup timeout.")

    def get_next_id(self) -> int:
        data = json_request(f"{self.bridge_url}/api/messages?since=0", timeout=10)
        for message in data.get("messages", []):
            write_jsonl(self.transcript_path, {"at": utc_stamp(), **message})
        return int(data.get("next") or 0)

    def poll_messages(self, since: int) -> tuple[list[dict], int]:
        data = json_request(f"{self.bridge_url}/api/messages?since={since}", timeout=20)
        messages = data.get("messages", [])
        next_id = int(data.get("next") or since)
        for message in messages:
            write_jsonl(self.transcript_path, {"at": utc_stamp(), **message})
        return messages, next_id

    def send_and_wait(self, task: TaskSpec) -> dict:
        self.log(f"Running {task.lane}/{task.task_id}: {task.title}")
        before_history_size = self.history_path.stat().st_size if self.history_path.exists() else 0
        omega_log_path = self.test_root / "logs" / "patch1-web-bridge-omega.log"
        before_omega_log_size = omega_log_path.stat().st_size if omega_log_path.exists() else 0
        json_request(f"{self.bridge_url}/api/send", method="POST", body={"text": task.prompt}, timeout=20)
        self.record_command("send", {"task_id": task.task_id, "lane": task.lane, "chars": len(task.prompt)})
        started_at = time.time()
        deadline = time.time() + task.timeout_seconds
        omega_messages: list[dict] = []
        next_id = self.last_seen
        first_progress_at: float | None = None
        history_activity_observed = False
        meaningful_history_activity_observed = False
        history_activity_kind = "none"
        history_entry_count = 0
        omega_iteration_count = 0
        completion_reason = "timeout"
        while time.time() < deadline:
            messages, next_id = self.poll_messages(next_id)
            for message in messages:
                if message.get("role") == "omega":
                    omega_messages.append(message)
                    first_progress_at = first_progress_at or time.time()
                    completion_reason = "omega-message"
            if self.history_path.exists() and self.history_path.stat().st_size > before_history_size:
                history_activity_observed = True
                current_delta = read_text(self.history_path)[before_history_size:]
                history_activity_kind = classify_history_activity(current_delta)
                history_entry_count = count_history_entries(current_delta)
                if history_activity_kind == "meaningful":
                    meaningful_history_activity_observed = True
                    if task.complete_on_history_activity:
                        first_progress_at = first_progress_at or time.time()
                        if completion_reason == "timeout":
                            completion_reason = "meaningful-history-activity"
                if task.complete_after_history_entries and history_entry_count >= task.complete_after_history_entries:
                    completion_reason = f"history-entries:{history_entry_count}"
                    break
            if task.complete_after_omega_iterations and omega_log_path.exists():
                omega_delta = read_text(omega_log_path)[before_omega_log_size:]
                omega_iteration_count = count_omega_iterations(omega_delta)
                if omega_iteration_count >= task.complete_after_omega_iterations:
                    completion_reason = f"omega-iterations:{omega_iteration_count}"
                    break
            if first_progress_at and time.time() - first_progress_at >= task.min_wait_seconds:
                break
            if task.complete_after_min_wait and time.time() - started_at >= task.min_wait_seconds:
                if completion_reason == "timeout":
                    completion_reason = history_activity_kind if history_activity_observed else "elapsed-min-wait"
                break
            time.sleep(2)
        self.last_seen = next_id
        response_text = "\n\n".join(item.get("text", "") for item in omega_messages)
        full_history = read_text(self.history_path)
        history_delta = full_history[before_history_size:]
        history_activity_kind = classify_history_activity(history_delta)
        history_entry_count = count_history_entries(history_delta)
        omega_iteration_count = count_omega_iterations(read_text(omega_log_path)[before_omega_log_size:]) if omega_log_path.exists() else 0
        result = {
            "task_id": task.task_id,
            "lane": task.lane,
            "title": task.title,
            "prompt": task.prompt,
            "response_text": response_text,
            "history_delta": history_delta,
            "omega_message_count": len(omega_messages),
            "history_activity_observed": history_activity_observed,
            "meaningful_history_activity_observed": meaningful_history_activity_observed or history_activity_kind == "meaningful",
            "history_activity_kind": history_activity_kind,
            "history_entry_count": history_entry_count,
            "omega_iteration_count": omega_iteration_count,
            "completion_reason": completion_reason,
        }
        self.capture_syntax_errors(task, history_delta)
        return result

    def capture_syntax_errors(self, task: TaskSpec, history_delta: str) -> None:
        patterns = ["syntax-error", "SINGLE_COMMAND_FORMAT_ERROR", "ERROR_FEEDBACK", "invalid-command-format"]
        for line in history_delta.splitlines():
            if any(pattern in line for pattern in patterns):
                write_jsonl(self.syntax_errors_path, {"at": utc_stamp(), "task_id": task.task_id, "line": line[:2000]})

    def evaluate(self, task: TaskSpec, result: dict) -> dict:
        checks: list[CheckResult] = []
        response = result.get("response_text", "")
        history = result.get("history_delta", "")
        checks.append(CheckResult("omega_response", bool(response.strip()), "Omega returned at least one message."))
        for term in task.expected_response_terms:
            checks.append(CheckResult(f"response_contains:{term}", term.lower() in response.lower(), f"Expected response term: {term}"))
        for term in task.forbidden_history_terms:
            checks.append(CheckResult(f"history_excludes:{term}", term not in history, f"Forbidden history term: {term}"))
        for file_name, required_terms in task.expected_files.items():
            path = Path(file_name.format(run_id=self.run_id))
            text = read_text(path)
            checks.append(CheckResult(f"file_exists:{path}", path.exists(), f"Expected artifact file: {path}"))
            if path.exists():
                dest = self.artifact_dir / path.name
                shutil.copy2(path, dest)
            for term in required_terms:
                checks.append(CheckResult(f"file_contains:{path}:{term}", term in text, f"Expected artifact term: {term}"))
        if task.verifier:
            checks.extend(task.verifier(self, task, result))
        passed = all(check.ok for check in checks)
        return {"passed": passed, "checks": [check.__dict__ for check in checks], **result}

    def run_tasks(self, tasks: list[TaskSpec]) -> None:
        selected = tasks[: self.args.limit] if self.args.limit else tasks
        if self.args.dry_run:
            for task in selected:
                self.results.append({"passed": True, "lane": task.lane, "task_id": task.task_id, "title": task.title, "dry_run": True})
            self.write_scorecard()
            return
        for task in selected:
            raw = self.send_and_wait(task)
            scored = self.evaluate(task, raw)
            self.results.append(scored)
            status = "PASS" if scored["passed"] else "REVIEW"
            self.log(f"{status}: {task.task_id}")
            self.write_scorecard()
            if self.args.stop_on_failure and not scored["passed"]:
                break
        self.capture_runtime_files()
        self.write_scorecard()
        self.cleanup_after_run()

    def run_autonomy(self) -> None:
        if self.args.dry_run:
            self.results.append({"passed": True, "lane": "autonomy", "task_id": "autonomy_idle_resistance", "dry_run": True})
            self.write_scorecard()
            return
        task = TaskSpec(
            lane="autonomy",
            task_id="autonomy_idle_resistance",
            title="Self-directed operation without further user tasks",
            prompt=autonomy_prompt(self.run_id, self.args.autonomy_minutes),
            timeout_seconds=max(120, self.args.autonomy_minutes * 60),
            min_wait_seconds=max(60, self.args.autonomy_minutes * 60 - 5),
            forbidden_history_terms=[],
            verifier=verify_autonomy,
        )
        raw = self.send_and_wait(task)
        scored = self.evaluate(task, raw)
        self.results.append(scored)
        self.capture_runtime_files()
        self.write_scorecard()
        self.cleanup_after_run()

    def capture_runtime_files(self) -> None:
        if self.history_path.exists():
            shutil.copy2(self.history_path, self.run_dir / "history.final.metta")
        log_files = {
            "web_bridge.log": self.test_root / "logs" / "web_bridge.log",
            "omega.log": self.test_root / "logs" / "patch1-web-bridge-omega.log",
        }
        manifest = {}
        for name, path in log_files.items():
            if path.exists():
                manifest[name] = self.copy_file_tail(path, self.run_dir / name, self.log_offsets.get(name, 0))
        if manifest:
            (self.run_dir / "log_capture_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def capture_tmp_artifacts(self) -> None:
        tmp_artifacts = sorted(Path("/tmp").glob(f"omega-seal-{self.run_id}*"))
        if not tmp_artifacts:
            return
        dest_root = self.artifact_dir / "tmp"
        dest_root.mkdir(parents=True, exist_ok=True)
        for path in tmp_artifacts:
            dest = dest_root / path.name
            if path.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(path, dest)
            elif path.is_file():
                shutil.copy2(path, dest)
            self.record_command("capture_tmp_artifact", {"source": str(path), "dest": str(dest)})

    def cleanup_after_run(self) -> None:
        if self.args.no_cleanup or self.args.dry_run:
            return
        self.capture_tmp_artifacts()
        cleanup_log = self.run_dir / "cleanup.jsonl"

        def record(path: Path, kind: str) -> None:
            write_jsonl(cleanup_log, {"at": utc_stamp(), "action": "cleanup", "kind": kind, "path": str(path)})

        targets = [self.run_dir / "pre-run-backup"]
        targets.extend(Path("/tmp").glob(f"omega-seal-{self.run_id}*"))
        for target in targets:
            if not target.exists():
                continue
            if target.is_dir():
                shutil.rmtree(target)
                record(target, "directory")
            else:
                target.unlink()
                record(target, "file")
        if self.args.stop_runtime_after_run:
            self.stop_runtime()
            self.record_command("cleanup_stop_runtime", {"why": "benchmark-complete"})

    def write_dry_run_scorecard(self) -> None:
        self.scorecard_path.write_text(
            f"# OmegaClaw Seal Benchmark Dry Run\n\nRun: `{self.run_id}`\n\nNo runtime actions performed.\n",
            encoding="utf-8",
        )

    def write_scorecard(self) -> None:
        lane_counts: dict[str, tuple[int, int]] = {}
        for result in self.results:
            lane = result.get("lane", "unknown")
            passed, total = lane_counts.get(lane, (0, 0))
            lane_counts[lane] = (passed + int(bool(result.get("passed"))), total + 1)
        lines = [
            "# OmegaClaw Seal Benchmark Scorecard",
            "",
            f"Run: `{self.run_id}`",
            f"Created: {local_stamp()}",
            f"Test root: `{self.test_root}`",
            f"Bridge: `{self.bridge_url}`",
            f"Mode: `{'dry-run' if self.args.dry_run else 'runtime'}`",
            "",
            "## Lane Summary",
            "",
        ]
        if lane_counts:
            for lane, (passed, total) in sorted(lane_counts.items()):
                lines.append(f"- `{lane}`: {passed}/{total} passed")
        else:
            lines.append("- No tasks completed yet.")
        lines.extend(["", "## Task Results", ""])
        for result in self.results:
            status = "DRY-RUN" if result.get("dry_run") else ("PASS" if result.get("passed") else "REVIEW")
            lines.append(f"### {status} - {result.get('lane')}/{result.get('task_id')}")
            lines.append("")
            lines.append(result.get("title", ""))
            lines.append("")
            for check in result.get("checks", []):
                mark = "PASS" if check.get("ok") else "FAIL"
                lines.append(f"- {mark}: `{check.get('name')}` - {check.get('detail')}")
            response = result.get("response_text", "").strip()
            if response:
                preview = response[:1200].replace("\n", "\\n")
                lines.append(f"- Omega preview: `{preview}`")
            lines.append("")
        lines.extend(
            [
                "## Artifacts",
                "",
                f"- Transcript: `{self.transcript_path}`",
                f"- Command log: `{self.commands_path}`",
                f"- Syntax errors: `{self.syntax_errors_path}`",
                f"- Runtime captures: `{self.run_dir}`",
                "",
            ]
        )
        self.scorecard_path.write_text("\n".join(lines), encoding="utf-8")


def verify_paragraphs(_bench: Benchmark, _task: TaskSpec, result: dict) -> list[CheckResult]:
    response = result.get("response_text", "")
    return [
        CheckResult("real_paragraph_break", "\n\n" in response, "Response should contain a real blank-line paragraph break."),
        CheckResult("literal_backslash_n_limited", response.count("\\n") <= 1, "Response should not leak repeated literal backslash-n text."),
    ]


def verify_unknown_command(_bench: Benchmark, _task: TaskSpec, result: dict) -> list[CheckResult]:
    history = result.get("history_delta", "")
    return [
        CheckResult("unknown_command_feedback", "unknown-command" in history or "syntax-error" in history, "Malformed command received explicit rejection feedback."),
        CheckResult("no_descriptor_guessing", "remembered" not in history.lower() or "unknown-command" in history, "Harness should not secretly guess intent for unknown commands."),
    ]


def verify_capability_file(_bench: Benchmark, _task: TaskSpec, result: dict) -> list[CheckResult]:
    history = result.get("history_delta", "")
    return [
        CheckResult("used_shell_or_read_file", "shell" in history or "read-file" in history, "Omega should use an actual capability to inspect the file."),
        CheckResult("reported_needle", "SEAL-NEEDLE" in result.get("response_text", ""), "Omega should report the planted token."),
    ]


def verify_autonomy(_bench: Benchmark, _task: TaskSpec, result: dict) -> list[CheckResult]:
    history = result.get("history_delta", "")
    response = result.get("response_text", "")
    lower = history.lower() + "\n" + response.lower()
    idle_hits = sum(lower.count(term) for term in ["awaiting user input", "standing by", "idle", "waiting for user"])
    action_hits = sum(lower.count(term) for term in ["remember", "pin", "query", "metta", "shell", "write-file", "search", "read-file"])
    artifact_hits = sum(1 for path in Path("/tmp").glob(f"omega-seal-{_bench.run_id}*") if path.exists())
    return [
        CheckResult("not_idle_dominant", idle_hits <= 3 or action_hits >= idle_hits * 2, f"Idle hits={idle_hits}, action hits={action_hits}."),
        CheckResult("self_directed_actions", action_hits >= 3, f"Detected {action_hits} capability/action terms during autonomy window."),
        CheckResult("meaningful_trace", len(history.strip()) > 1000 or len(response.strip()) > 500, "Autonomy window should produce a non-trivial trace."),
        CheckResult("artifact_or_memory_attempt", artifact_hits > 0 or "remember" in lower or "write-file" in lower, "Autonomy should try to preserve a lesson or create evidence."),
    ]


def syntax_tasks(run_id: str) -> list[TaskSpec]:
    artifact = f"/tmp/omega-seal-{run_id}-syntax-artifact.md"
    return [
        TaskSpec(
            lane="syntax",
            task_id="human_punctuation_prose",
            title="Human prose with command words, punctuation, and real paragraphs",
            prompt=(
                "Reply to me in two short human paragraphs. Use creative punctuation, quotes, parentheses, a colon, "
                "the words remember, query, pin, episodes, search, shell, and metta as plain prose, and include one inline code span. "
                "Do not call tools unless you genuinely need them."
            ),
            timeout_seconds=220,
            min_wait_seconds=8,
            verifier=verify_paragraphs,
        ),
        TaskSpec(
            lane="syntax",
            task_id="delimited_artifact_body",
            title="Write/read markdown artifact containing parser-hostile text",
            prompt=(
                f"Create the file {artifact}. It must contain a markdown table, a fenced code block, the text "
                "(stv 1.0 0.9), the string episodes 2026-06-25 16:23:00query syntax errors, and the LaTeX-ish text "
                "\\begin{tabular}{lll}. Then read the file back and report whether every required phrase survived exactly."
            ),
            timeout_seconds=420,
            min_wait_seconds=15,
            expected_files={artifact: ["(stv 1.0 0.9)", "episodes 2026-06-25 16:23:00query syntax errors", "\\begin{tabular}{lll}"]},
        ),
        TaskSpec(
            lane="syntax",
            task_id="unknown_command_rejection",
            title="Unknown command rejects cleanly without guessed execution",
            prompt=(
                "For this test, intentionally try this exact bad skill once: remembered \"seal unknown command test\". "
                "Then recover by explaining what happened in one sentence."
            ),
            timeout_seconds=240,
            min_wait_seconds=12,
            forbidden_history_terms=["SINGLE_COMMAND_FORMAT_ERROR"],
            verifier=verify_unknown_command,
        ),
        TaskSpec(
            lane="syntax",
            task_id="raw_metta_as_language",
            title="Balanced MeTTa expressions can be discussed without command confusion",
            prompt=(
                "Discuss this as language, then use metta only if you decide execution is appropriate: "
                "(EvaluationLink (PredicateNode \"is-bird\") (ConceptNode \"Pingu\")) with (stv 0.7 0.8). "
                "Explain the difference between showing this expression and executing a metta command."
            ),
            timeout_seconds=240,
            min_wait_seconds=10,
            expected_response_terms=["metta"],
        ),
    ]


def capability_tasks(run_id: str) -> list[TaskSpec]:
    base = Path(f"/tmp/omega-seal-{run_id}-capability")
    base.mkdir(parents=True, exist_ok=True)
    needle = base / "needle.txt"
    needle.write_text("SEAL-NEEDLE-OMEGACLAW-CAPABILITY\n", encoding="utf-8")
    artifact = base / "capability-report.md"
    return [
        TaskSpec(
            lane="capability",
            task_id="capability_inventory",
            title="Describe actual capability surface without inventing skills",
            prompt=(
                "Briefly tell me what capabilities you believe you currently have. Separate memory, filesystem/shell, web/research, "
                "and MeTTa/reasoning. Only mention skills you can actually call."
            ),
            timeout_seconds=240,
            min_wait_seconds=8,
            expected_response_terms=["memory", "shell", "metta"],
        ),
        TaskSpec(
            lane="capability",
            task_id="file_skill_weave",
            title="Use capabilities to find, read, write, and verify an artifact",
            prompt=(
                f"Find and read the token file somewhere under {base}. Then create {artifact} with a short report containing "
                "the exact token, the path you found, and one sentence about which skills you used. Read the report back before replying."
            ),
            timeout_seconds=480,
            min_wait_seconds=18,
            expected_response_terms=["SEAL-NEEDLE"],
            expected_files={str(artifact): ["SEAL-NEEDLE", "skills"]},
            verifier=verify_capability_file,
        ),
        TaskSpec(
            lane="capability",
            task_id="memory_hygiene",
            title="Use pin and remember with different scopes",
            prompt=(
                "Pin the short-term state `seal benchmark memory hygiene active`. Remember the stable lesson "
                "`Seal benchmark: verify artifacts after writing`. Then tell me the difference between why each storage choice was used."
            ),
            timeout_seconds=300,
            min_wait_seconds=12,
            expected_response_terms=["pin", "remember"],
        ),
    ]


def capstone_tasks(run_id: str) -> list[TaskSpec]:
    artifact = f"/tmp/omega-seal-{run_id}-capstone.md"
    return [
        TaskSpec(
            lane="capstone",
            task_id="research_reason_artifact",
            title="Choose a small operational research question and produce verified artifact",
            prompt=(
                "Choose a small research question about your own operation in this test instance. Investigate it using your available capabilities, "
                "reason over the evidence, create the artifact "
                f"{artifact}, read it back to verify it, remember one stable lesson, and report only the meaningful result."
            ),
            timeout_seconds=900,
            min_wait_seconds=30,
            expected_files={artifact: ["question", "evidence", "lesson"]},
        )
    ]


def compatibility_tasks(run_id: str) -> list[TaskSpec]:
    tasks = []
    tasks.extend(syntax_tasks(run_id)[:2])
    tasks.extend(capability_tasks(run_id)[:2])
    for task in tasks:
        task.lane = "compatibility"
    return tasks


def autonomy_prompt(run_id: str, minutes: int) -> str:
    return (
        "Omega, this is a clean autonomy test instance. No user task is assigned after this message. "
        "For the next "
        f"{minutes} minutes, choose your own goals according to your principles. Explore your capabilities, learn safely, "
        "improve your understanding, and avoid collapsing into idle waiting. Create evidence under "
        f"/tmp/omega-seal-{run_id}-autonomy if useful. Use send for concise human-visible progress updates at meaningful milestones, roughly every 5-8 cycles or after completing a phase. Do not stay silent for the whole run; do not spam. Continue using pin for liveness and artifacts for evidence."
    )


def build_tasks(suite: str, run_id: str) -> list[TaskSpec]:
    if suite == "syntax":
        return syntax_tasks(run_id)
    if suite == "capability":
        return capability_tasks(run_id)
    if suite == "compatibility":
        return compatibility_tasks(run_id)
    if suite == "capstone":
        return capstone_tasks(run_id)
    if suite == "all":
        return syntax_tasks(run_id) + capability_tasks(run_id) + compatibility_tasks(run_id) + capstone_tasks(run_id)
    if suite == "smoke":
        return syntax_tasks(run_id)[:1] + capability_tasks(run_id)[:1]
    raise ValueError(f"Unknown suite: {suite}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the OmegaClaw Seal Benchmark through the VM-native web bridge.")
    parser.add_argument("--suite", choices=["smoke", "syntax", "capability", "compatibility", "autonomy", "capstone", "all"], default="smoke")
    parser.add_argument("--test-root", type=Path, default=TEST_ROOT)
    parser.add_argument("--bridge-url", default=BRIDGE_URL)
    parser.add_argument("--run-root", type=Path, default=RUNS_DIR)
    parser.add_argument("--run-id")
    parser.add_argument("--cold-start", dest="cold_start", action="store_true", default=True)
    parser.add_argument("--no-cold-start", dest="cold_start", action="store_false")
    parser.add_argument("--provider-order", default="")
    parser.add_argument("--provider-sort", choices=["", "latency", "throughput", "price"], default="latency")
    parser.add_argument("--omega-provider", default="OpenRouter")
    parser.add_argument("--openrouter-model", default="")
    parser.add_argument("--reasoning-mode", choices=["", "none", "minimal", "low", "medium", "high", "xhigh", "max"], default="")
    parser.add_argument("--max-new-input-loops", type=int, default=0)
    parser.add_argument("--allow-fallbacks", action="store_true")
    parser.add_argument("--startup-timeout", type=int, default=180)
    parser.add_argument("--limit", type=int, default=0, help="Run only the first N tasks in the selected suite.")
    parser.add_argument("--autonomy-minutes", type=int, default=15)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument("--no-cleanup", action="store_true", help="Preserve transient run backups and /tmp artifacts for debugging.")
    parser.add_argument("--keep-runtime", dest="stop_runtime_after_run", action="store_false", help="Leave the test Omega runtime running after the benchmark.")
    parser.set_defaults(stop_runtime_after_run=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bench = Benchmark(args)
    bench.prepare()
    if args.suite == "autonomy":
        bench.run_autonomy()
    else:
        bench.run_tasks(build_tasks(args.suite, bench.run_id))
    print(bench.scorecard_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
