"""Internal updater API foundation.

The worker deliberately does not execute host-engine commands yet. It persists
validated jobs so engine/socket integration can be added without coupling Flask
web requests to deployment operations.
"""

import secrets
from flask import Flask, jsonify, request
from sqlalchemy import select

from .config import settings
from .db import SessionLocal, UpdateJob, UpdateSafePoint, utcnow
from .services.update_engine import engine_from_name
from .services.update_provider import GitHubReleaseProvider


def create_updater_app() -> Flask:
    app = Flask(__name__)

    def authorized() -> bool:
        if not settings.updater_token:
            return True
        return secrets.compare_digest(request.headers.get("X-HAMQTT-Updater-Token", ""), settings.updater_token)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "updater"})

    @app.before_request
    def require_internal_token():
        if request.endpoint == "health":
            return None
        if not authorized():
            return jsonify({"error": "unauthorized"}), 401
        return None

    @app.get("/v1/status")
    def status():
        try:
            engine = engine_from_name(settings.hamqtt_engine)
            engine_name = engine.config.name
        except ValueError:
            engine_name = "unsupported"
        return jsonify({"service": "updater", "engine": engine_name, "self_update_supported": engine_name != "unsupported"})

    @app.get("/v1/releases/latest")
    def latest_release():
        try:
            release = GitHubReleaseProvider(settings.update_repository, include_prereleases=settings.update_include_prereleases).latest()
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 503
        return jsonify(release.__dict__)

    @app.get("/v1/jobs/<int:job_id>")
    def get_job(job_id: int):
        with SessionLocal() as session:
            job = session.get(UpdateJob, job_id)
            if not job:
                return jsonify({"error": "job_not_found"}), 404
            return jsonify(_job_json(job))

    @app.post("/v1/jobs/<int:job_id>/rollback")
    def rollback_job(job_id: int):
        with SessionLocal() as session:
            source = session.get(UpdateJob, job_id)
            if not source:
                return jsonify({"error": "job_not_found"}), 404
            if not source.rollback_available:
                return jsonify({"error": "rollback_unavailable"}), 409
            active = session.scalar(select(UpdateJob).where(UpdateJob.status.in_(["queued", "running"])).limit(1))
            if active:
                return jsonify({"error": "active_job_exists", "job_id": active.id}), 409
            job = UpdateJob(
                operation="rollback",
                target_version=source.previous_version or source.current_version or "",
                previous_version=source.target_version,
                engine=source.engine,
                safe_point_id=source.safe_point_id,
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            return jsonify(_job_json(job)), 202

    @app.post("/v1/jobs")
    def create_job():
        payload = request.get_json(silent=True) or {}
        target_version = str(payload.get("target_version", "")).strip()
        operation = payload.get("operation", "update")
        if not target_version or operation not in {"update", "rollback"}:
            return jsonify({"error": "invalid_job_request"}), 400
        with SessionLocal() as session:
            active = session.scalar(select(UpdateJob).where(UpdateJob.status.in_(["queued", "running"])).limit(1))
            if active:
                return jsonify({"error": "active_job_exists", "job_id": active.id}), 409
            job = UpdateJob(target_version=target_version, operation=operation, engine=settings.hamqtt_engine)
            session.add(job)
            session.commit()
            session.refresh(job)
            return jsonify(_job_json(job)), 202

    return app


def _job_json(job: UpdateJob) -> dict:
    return {
        "job_id": job.id,
        "operation": job.operation,
        "status": job.status,
        "current_step": job.current_step,
        "current_version": job.current_version,
        "target_version": job.target_version,
        "previous_version": job.previous_version,
        "engine": job.engine,
        "safe_point_id": job.safe_point_id,
        "rollback_available": job.rollback_available,
        "requires_manual_action": job.requires_manual_action,
        "error_summary": job.error_summary,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": utcnow().isoformat(),
    }


app = create_updater_app()