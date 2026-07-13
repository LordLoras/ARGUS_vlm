"""Aggregate queue, provider, and runtime health for operators and ARGUS."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from ad_classifier.intelligence_crawler.contract import INTELLIGENCE_SCHEMA_VERSION
from ad_classifier.intelligence_crawler.timeutils import utcnow

if TYPE_CHECKING:
    from ad_classifier.intelligence_crawler.config import IntelConfig
    from ad_classifier.intelligence_crawler.repository import IntelRepository


def build_health(config: IntelConfig, repo: IntelRepository) -> dict:
    now = utcnow()
    stale_before = now - timedelta(seconds=config.service.heartbeat_stale_seconds)
    with repo.connect(readonly=True) as conn:
        queue = repo.queue_stats(conn, now=now)
        sources = repo.list_sources(conn)
        enabled = [source for source in sources if source.enabled]
        due = repo.list_sources(conn, enabled_only=True, due_at=now)
        statuses = repo.list_source_statuses(conn)
        heartbeats = {item["service_name"]: item for item in repo.list_service_heartbeats(conn)}

    services = []
    for name in ("worker", "scheduler"):
        heartbeat = heartbeats.get(name)
        if heartbeat is None:
            services.append(
                {
                    "service_name": name,
                    "status": "not_started",
                    "activity": "not_started",
                    "instance_id": None,
                    "started_at": None,
                    "heartbeat_at": None,
                    "metadata": {},
                }
            )
            continue
        heartbeat_at = heartbeat["heartbeat_at"]
        if heartbeat["activity"] == "stopped":
            service_status = "stopped"
        elif heartbeat["activity"] == "error":
            service_status = "error"
        else:
            service_status = (
                "online" if heartbeat_at is not None and heartbeat_at >= stale_before else "stale"
            )
        services.append({**heartbeat, "status": service_status})

    service_by_name = {item["service_name"]: item for item in services}
    failing = [item for item in statuses if item.state.last_outcome == "failed"]
    partial = [item for item in statuses if item.state.last_outcome == "partial"]
    circuit_providers = {
        item.provider_circuit.provider for item in statuses if item.provider_circuit is not None
    }
    resumable = [item for item in statuses if item.resume_available]
    issues: list[dict] = []
    if queue["abandoned_running"]:
        issues.append(
            {
                "code": "abandoned_runs",
                "severity": "critical",
                "message": f"{queue['abandoned_running']} running crawl lease(s) expired.",
            }
        )
    if queue["queued"] and service_by_name["worker"]["status"] != "online":
        issues.append(
            {
                "code": "worker_unavailable",
                "severity": "critical",
                "message": "Queued crawls are waiting, but no current worker heartbeat exists.",
            }
        )
    if due and service_by_name["scheduler"]["status"] != "online":
        issues.append(
            {
                "code": "scheduler_unavailable",
                "severity": "warning",
                "message": f"{len(due)} source(s) are due, but the scheduler is not running.",
            }
        )
    for item in [*failing, *partial]:
        is_failure = item.state.last_outcome == "failed"
        issues.append(
            {
                "code": item.state.last_error_code
                or ("source_failed" if is_failure else "source_partial"),
                "severity": "warning",
                "message": item.state.last_error
                or (
                    "The last source crawl failed."
                    if is_failure
                    else "The last source crawl was incomplete."
                ),
                "source_id": item.source.id,
                "provider": item.source.source_type,
            }
        )
    severity = {item["severity"] for item in issues}
    status = "critical" if "critical" in severity else "degraded" if issues else "healthy"
    return {
        "schema_version": INTELLIGENCE_SCHEMA_VERSION,
        "status": status,
        "checked_at": now,
        "database": {"path": str(config.db_path), "writable": True},
        "queue": queue,
        "sources": {
            "total": len(sources),
            "enabled": len(enabled),
            "due": len(due),
            "failed": len(failing),
            "partial": len(partial),
            "open_provider_circuits": len(circuit_providers),
            "resume_available": len(resumable),
        },
        "services": services,
        "issues": issues,
    }
