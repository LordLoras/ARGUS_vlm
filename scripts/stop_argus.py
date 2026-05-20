from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTS = (8000, 5173)


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    parent_pid: int | None
    command_line: str
    reason: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop local ARGUS API, worker, and frontend.")
    parser.add_argument("--dry-run", action="store_true", help="Show matching processes without killing.")
    args = parser.parse_args()

    processes = _processes()
    port_pids = _pids_on_ports(PORTS)
    matches = _matching_processes(processes, port_pids)

    if not matches:
        print("[stop_argus] No ARGUS server processes found.")
        return 0

    for proc in matches:
        print(f"[stop_argus] {'Would kill' if args.dry_run else 'Killing'} PID {proc.pid}: {proc.reason}")
        if args.dry_run:
            print(f"  {proc.command_line[:240]}")
            continue
        _taskkill(proc.pid)
    return 0


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _pids_on_ports(ports: tuple[int, ...]) -> dict[int, set[int]]:
    result = _run(["netstat", "-ano"])
    out: dict[int, set[int]] = {port: set() for port in ports}
    if result.returncode != 0:
        return out

    for line in result.stdout.splitlines():
        if "LISTENING" not in line.upper():
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address = parts[1]
        pid_text = parts[-1]
        for port in ports:
            if re.search(rf"(^|:|\]){port}$", local_address):
                with suppress(ValueError):
                    out[port].add(int(pid_text))
    return out


def _processes() -> list[dict[str, object]]:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-CimInstance Win32_Process | "
            "Select-Object ProcessId,ParentProcessId,CommandLine | "
            "ConvertTo-Json -Compress"
        ),
    ]
    result = _run(command)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    payload = json.loads(result.stdout)
    if isinstance(payload, dict):
        return [payload]
    return payload if isinstance(payload, list) else []


def _matching_processes(
    processes: list[dict[str, object]],
    port_pids: dict[int, set[int]],
) -> list[ProcessInfo]:
    current_pid = os.getpid()
    root = str(ROOT).lower()
    port_reason_by_pid = {
        pid: f"listening on port {port}"
        for port, pids in port_pids.items()
        for pid in pids
    }
    matches: dict[int, ProcessInfo] = {}

    for raw in processes:
        try:
            pid = int(raw.get("ProcessId") or 0)
        except (TypeError, ValueError):
            continue
        if pid <= 0 or pid == current_pid:
            continue
        command_line = str(raw.get("CommandLine") or "")
        command_lower = command_line.lower()
        parent_pid = _as_int(raw.get("ParentProcessId"))

        reason = port_reason_by_pid.get(pid)
        if reason is None and root in command_lower:
            reason = _repo_process_reason(command_lower)
        if reason is None:
            continue
        matches[pid] = ProcessInfo(
            pid=pid,
            parent_pid=parent_pid,
            command_line=command_line,
            reason=reason,
        )

    # Kill child processes before parent console windows. taskkill /T handles
    # descendants too, but this ordering keeps the printed list predictable.
    return sorted(matches.values(), key=lambda item: (item.parent_pid is None, item.parent_pid or 0))


def _repo_process_reason(command_lower: str) -> str | None:
    if "ad_classifier api" in command_lower or "ad_classifier.cli" in command_lower and " api " in command_lower:
        return "ARGUS API command"
    if "ad_classifier worker" in command_lower or " worker" in command_lower and "ad_classifier" in command_lower:
        return "ARGUS worker command"
    if "uvicorn" in command_lower and "ad_classifier" in command_lower:
        return "ARGUS uvicorn process"
    if "npm run dev" in command_lower or "vite" in command_lower and "frontend" in command_lower:
        return "ARGUS frontend dev server"
    return None


def _as_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _taskkill(pid: int) -> None:
    result = _run(["taskkill", "/F", "/T", "/PID", str(pid)])
    output = (result.stdout + result.stderr).strip()
    if output:
        for line in output.splitlines():
            print(f"  {line}")


if __name__ == "__main__":
    raise SystemExit(main())
