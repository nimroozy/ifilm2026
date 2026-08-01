#!/usr/bin/env python3
"""iFilm privileged update agent.

Listens on a root-owned Unix domain socket. Accepts only typed JSON commands.
Never executes arbitrary shell. Never accepts Git URLs, paths, or Docker args
from the web application.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SOCKET_PATH = Path(os.environ.get("UPDATE_AGENT_SOCKET", "/run/ifilm/update-agent.sock"))
SHARED_SECRET = os.environ.get("UPDATE_AGENT_SHARED_SECRET", "")
IFILM_HOME = Path(os.environ.get("IFILM_HOME", "/opt/ifilm"))
IFILM_ETC = Path(os.environ.get("IFILM_ETC", "/etc/ifilm"))
IFILM_VAR = Path(os.environ.get("IFILM_VAR", "/var/lib/ifilm"))
COMPOSE_FILE = IFILM_HOME / "current" / "packaging" / "compose" / "docker-compose.production.yml"
ENV_FILE = IFILM_ETC / "ifilm.env"
REPO = os.environ.get("IFILM_REPO", "nimroozy/ifilm2026")
PUBLIC_KEY = IFILM_HOME / "current" / "packaging" / "keys" / "release-signing.pub"
STATE_DIR = IFILM_VAR / "update-agent"
LOCK_FILE = STATE_DIR / "update.lock"
JOBS_DIR = STATE_DIR / "jobs"


def _load_image_refs():
    """Import image_refs from the active release tree (not the copied agent path)."""
    candidates = [
        IFILM_HOME / "current" / "packaging" / "release",
        Path(__file__).resolve().parents[1] / "release",
    ]
    for path in candidates:
        if (path / "image_refs.py").is_file():
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
            break
    from image_refs import (  # noqa: WPS433
        ImageRefError,
        env_vars_from_digests,
        validate_image_digests,
    )

    return ImageRefError, env_vars_from_digests, validate_image_digests


ImageRefError, env_vars_from_digests, validate_image_digests = _load_image_refs()

ALLOWED_COMMANDS = frozenset(
    {
        "get_current_version",
        "check_latest_release",
        "run_preflight",
        "create_backup",
        "install_verified_release",
        "query_update_progress",
        "query_update_result",
        "rollback_last_update",
    }
)


class AgentError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _run(argv: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """Fixed-argv subprocess helper. Never uses shell=True."""
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _require_secret(payload: dict[str, Any]) -> None:
    provided = str(payload.get("shared_secret") or "")
    if not SHARED_SECRET or provided != SHARED_SECRET:
        raise AgentError("unauthorized", "update agent shared secret rejected")


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "version": "0.0.0-dev",
            "commit_sha": "unknown",
            "channel": os.environ.get("UPDATE_CHANNEL", "stable"),
            "migration_head": "unknown",
        }
    return json.loads(path.read_text(encoding="utf-8"))


def get_current_version(_payload: dict[str, Any]) -> dict[str, Any]:
    manifest = _read_manifest(IFILM_HOME / "current" / "release-manifest.json")
    return {
        "version": manifest.get("version"),
        "commit_sha": manifest.get("commit_sha"),
        "channel": manifest.get("channel") or os.environ.get("UPDATE_CHANNEL", "stable"),
        "migration_head": manifest.get("migration_head"),
        "published_at": manifest.get("published_at"),
    }


def check_latest_release(payload: dict[str, Any]) -> dict[str, Any]:
    channel = str(payload.get("channel") or os.environ.get("UPDATE_CHANNEL") or "stable")
    url = f"https://api.github.com/repos/{REPO}/releases?per_page=20"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "ifilm-update-agent"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — fixed GitHub API host
        releases = json.loads(resp.read().decode("utf-8"))
    current = get_current_version({})
    selected = None
    for rel in releases:
        if rel.get("draft"):
            continue
        if channel == "stable" and rel.get("prerelease"):
            continue
        selected = rel
        break
    if not selected:
        return {"update_available": False, "current": current, "latest": None}
    tag = selected["tag_name"]
    assets = {a["name"]: a["browser_download_url"] for a in selected.get("assets") or []}
    archive_name = None
    for name in assets:
        if name.endswith(".tar.gz") or name.endswith(".tgz"):
            archive_name = name
            break
    latest = {
        "version": tag.lstrip("v"),
        "tag": tag,
        "prerelease": bool(selected.get("prerelease")),
        "published_at": selected.get("published_at"),
        "notes": selected.get("body") or "",
        "manifest_url": assets.get("release-manifest.json"),
        "signature_url": assets.get("release-manifest.json.sig"),
        "archive_url": assets.get(archive_name) if archive_name else None,
        "archive_name": archive_name,
    }
    update_available = latest["version"] != current.get("version")
    return {"update_available": update_available, "current": current, "latest": latest, "channel": channel}


def _verify_manifest(manifest_path: Path, sig_path: Path) -> dict[str, Any]:
    if not PUBLIC_KEY.is_file():
        raise AgentError("missing_public_key", "release signing public key not installed")
    result = _run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(PUBLIC_KEY),
            "-sigfile",
            str(sig_path),
            "-rawin",
            "-in",
            str(manifest_path),
        ],
        timeout=30,
    )
    if result.returncode != 0:
        # Older OpenSSL builds may omit -rawin; retry once for compatibility.
        result = _run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(PUBLIC_KEY),
                "-sigfile",
                str(sig_path),
                "-in",
                str(manifest_path),
            ],
            timeout=30,
        )
    if result.returncode != 0:
        raise AgentError("invalid_signature", "release manifest signature verification failed")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def run_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    ok = True

    def add(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            ok = False

    add("compose_file", COMPOSE_FILE.is_file(), str(COMPOSE_FILE))
    add("env_file", ENV_FILE.is_file() and oct(ENV_FILE.stat().st_mode & 0o777) == "0o600", str(ENV_FILE))
    add("public_key", PUBLIC_KEY.is_file(), str(PUBLIC_KEY))
    add("lock_free", not LOCK_FILE.exists() or payload.get("ignore_lock") is True, str(LOCK_FILE))

    disk = _run(["df", "-BG", "--output=avail", str(IFILM_VAR)])
    free_gb = 0
    if disk.returncode == 0:
        try:
            free_gb = int("".join(ch for ch in disk.stdout.strip().splitlines()[-1] if ch.isdigit()))
        except ValueError:
            free_gb = 0
    add("disk_space", free_gb >= 5, f"{free_gb}GB free")

    # Optional target version verification when URLs provided by check step (GitHub only).
    manifest_url = payload.get("manifest_url")
    signature_url = payload.get("signature_url")
    if manifest_url and signature_url:
        if not str(manifest_url).startswith("https://github.com/") and not str(manifest_url).startswith(
            "https://objects.githubusercontent.com/"
        ):
            add("release_source", False, "manifest URL host not allowlisted")
        else:
            with tempfile.TemporaryDirectory(prefix="ifilm-preflight-") as tmp:
                mpath = Path(tmp) / "release-manifest.json"
                spath = Path(tmp) / "release-manifest.json.sig"
                urllib.request.urlretrieve(str(manifest_url), mpath)  # noqa: S310
                urllib.request.urlretrieve(str(signature_url), spath)  # noqa: S310
                try:
                    manifest = _verify_manifest(mpath, spath)
                    add("signature", True, manifest.get("version", ""))
                    current = get_current_version({})
                    add(
                        "newer_version",
                        str(manifest.get("version")) != str(current.get("version")),
                        f"{current.get('version')} -> {manifest.get('version')}",
                    )
                except AgentError as exc:
                    add("signature", False, exc.message)

    return {"ok": ok, "checks": checks, "checked_at": _utc_now()}


def create_backup(_payload: dict[str, Any]) -> dict[str, Any]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = IFILM_VAR / "backups" / f"pre-update-{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    # PostgreSQL custom-format dump via compose (binary capture only).
    dump = out / "postgres.dump"
    proc_bin = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(ENV_FILE),
            "-f",
            str(COMPOSE_FILE),
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            os.environ.get("POSTGRES_USER", "ifilm"),
            "-d",
            os.environ.get("POSTGRES_DB", "ifilm"),
            "-Fc",
        ],
        check=False,
        capture_output=True,
        timeout=1800,
    )
    if proc_bin.returncode != 0:
        raise AgentError(
            "backup_failed",
            (proc_bin.stderr or b"").decode("utf-8", errors="replace")[-500:] or "pg_dump failed",
        )
    dump.write_bytes(proc_bin.stdout)

    list_proc = _run(
        ["pg_restore", "-l", str(dump)],
        timeout=120,
    )
    if list_proc.returncode != 0:
        # pg_restore may not exist on host; validate inside postgres container
        list_proc = _run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{out}:/b:ro",
                "postgres:16-alpine",
                "pg_restore",
                "-l",
                "/b/postgres.dump",
            ],
            timeout=120,
        )
        if list_proc.returncode != 0:
            raise AgentError("backup_invalid", "pg_restore -l failed for pre-update dump")

    # Config redacted copy
    if ENV_FILE.is_file():
        redacted = []
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if any(line.startswith(p) for p in ("POSTGRES_PASSWORD=", "JWT_SECRET=", "PLAYBACK_TOKEN_SECRET=", "REDIS_PASSWORD=", "UPDATE_AGENT_SHARED_SECRET=", "ADMIN_BOOTSTRAP_PASSWORD=", "RADIUS_SECRET=")):
                key = line.split("=", 1)[0]
                redacted.append(f"{key}=REDACTED")
            else:
                redacted.append(line)
        (out / "ifilm.env.redacted").write_text("\n".join(redacted) + "\n", encoding="utf-8")
        os.chmod(out / "ifilm.env.redacted", 0o600)

    meta = {
        "backup_id": out.name,
        "created_at": _utc_now(),
        "path": str(out),
        "postgres_dump": "postgres.dump",
        "validated": True,
        "current": get_current_version({}),
    }
    (out / "MANIFEST.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def _acquire_lock(job_id: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        raise AgentError("locked", "another update/rollback is in progress")
    LOCK_FILE.write_text(json.dumps({"job_id": job_id, "started_at": _utc_now()}), encoding="utf-8")


def _release_lock() -> None:
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()


def _write_job(job_id: str, data: dict[str, Any]) -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    path = JOBS_DIR / f"{job_id}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_job(job_id: str) -> dict[str, Any]:
    path = JOBS_DIR / f"{job_id}.json"
    if not path.is_file():
        raise AgentError("not_found", "update job not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _upsert_env(key: str, value: str) -> None:
    if not ENV_FILE.is_file():
        raise AgentError("missing_env", f"env file missing: {ENV_FILE}")
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    found = False
    out: list[str] = []
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.chmod(ENV_FILE, 0o600)


def _apply_image_digests(manifest: dict[str, Any]) -> dict[str, str]:
    try:
        digests = validate_image_digests(manifest.get("image_digests"), require_all=True)
        env_vars = env_vars_from_digests(digests)
    except ImageRefError as exc:
        raise AgentError("invalid_image_digest", str(exc)) from exc
    for key, value in env_vars.items():
        _upsert_env(key, value)
    return env_vars


def _verify_pulled_image(ref: str) -> None:
    """Refuse to continue if the local image does not match the manifest digest."""
    want_digest = ref.split("@", 1)[1] if "@" in ref else ""
    if not want_digest.startswith("sha256:") or len(want_digest) != len("sha256:") + 64:
        raise AgentError("invalid_image_digest", f"malformed digest ref: {ref}")
    inspect = _run(
        ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", ref],
        timeout=60,
    )
    if inspect.returncode != 0:
        # Fallback inspect by pulling-ref may leave only repository digests.
        inspect = _run(
            ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", ref.split("@", 1)[0]],
            timeout=60,
        )
    if inspect.returncode != 0:
        raise AgentError("image_pull_failed", f"could not inspect pulled image {ref}")
    digests = json.loads(inspect.stdout or "[]")
    if not any(want_digest in str(item) for item in digests):
        raise AgentError(
            "image_digest_mismatch",
            f"downloaded image digest differs from manifest for {ref}",
        )


def _compose_pull_and_up() -> None:
    pull = _run(
        ["docker", "compose", "--env-file", str(ENV_FILE), "-f", str(COMPOSE_FILE), "pull"],
        timeout=1800,
    )
    if pull.returncode != 0:
        raise AgentError("image_pull_failed", "docker compose pull failed")
    # Verify both application images against env (written from signed manifest).
    env_text = ENV_FILE.read_text(encoding="utf-8")
    refs: dict[str, str] = {}
    for line in env_text.splitlines():
        if line.startswith("IFILM_IMAGE_BACKEND_API="):
            refs["backend-api"] = line.split("=", 1)[1]
        elif line.startswith("IFILM_IMAGE_FRONTEND="):
            refs["frontend"] = line.split("=", 1)[1]
    if "backend-api" not in refs or "frontend" not in refs:
        raise AgentError("invalid_image_digest", "image digest env vars missing after apply")
    _verify_pulled_image(refs["backend-api"])
    _verify_pulled_image(refs["frontend"])
    up = _run(
        [
            "docker",
            "compose",
            "--env-file",
            str(ENV_FILE),
            "-f",
            str(COMPOSE_FILE),
            "up",
            "-d",
            "--no-build",
        ],
        timeout=1800,
    )
    if up.returncode != 0:
        raise AgentError("compose_up_failed", "docker compose up failed")


def _flatten_release_tree(dest: Path) -> None:
    """Support both flat archives and nested ifilm/ archives."""
    nested = dest / "ifilm"
    if nested.is_dir() and not (dest / "packaging").is_dir():
        for child in nested.iterdir():
            target = dest / child.name
            if target.exists():
                if target.is_dir():
                    import shutil

                    shutil.rmtree(target)
                else:
                    target.unlink()
            child.rename(target)
        nested.rmdir()


def install_verified_release(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = hashlib.sha256(f"{time.time()}:{os.getpid()}".encode()).hexdigest()[:16]
    job: dict[str, Any] = {
        "job_id": job_id,
        "state": "preflight",
        "started_at": _utc_now(),
        "target_version": payload.get("target_version"),
        "result": None,
        "error": None,
        "backup_id": None,
    }
    _write_job(job_id, job)
    try:
        # Preflight before acquiring the exclusive lock so lock_free can pass.
        pre = run_preflight(payload)
        job["preflight"] = pre
        if not pre["ok"]:
            job["state"] = "preflight_failed"
            job["error"] = {"code": "preflight_failed", "message": "mandatory preflight failed"}
            _write_job(job_id, job)
            return job

        _acquire_lock(job_id)
        job["state"] = "backing_up"
        _write_job(job_id, job)
        backup = create_backup({})
        job["backup_id"] = backup["backup_id"]

        job["state"] = "downloading"
        _write_job(job_id, job)
        manifest_url = str(payload.get("manifest_url") or "")
        signature_url = str(payload.get("signature_url") or "")
        archive_url = str(payload.get("archive_url") or "")
        if not (manifest_url and signature_url and archive_url):
            raise AgentError("missing_artifacts", "manifest_url, signature_url, and archive_url required")
        for url in (manifest_url, signature_url, archive_url):
            if not (url.startswith("https://github.com/") or url.startswith("https://objects.githubusercontent.com/")):
                raise AgentError("invalid_source", "release asset host not allowlisted")

        with tempfile.TemporaryDirectory(prefix="ifilm-update-") as tmp:
            tmp_path = Path(tmp)
            mpath = tmp_path / "release-manifest.json"
            spath = tmp_path / "release-manifest.json.sig"
            apath = tmp_path / "ifilm-release.tar.gz"
            urllib.request.urlretrieve(manifest_url, mpath)  # noqa: S310
            urllib.request.urlretrieve(signature_url, spath)  # noqa: S310
            urllib.request.urlretrieve(archive_url, apath)  # noqa: S310

            job["state"] = "verifying"
            _write_job(job_id, job)
            manifest = _verify_manifest(mpath, spath)
            expected = None
            for art in manifest.get("artifacts") or []:
                if str(art.get("name", "")).endswith(".tar.gz"):
                    expected = art.get("sha256")
                    break
            if not expected:
                raise AgentError("missing_checksum", "manifest missing archive checksum")
            actual = hashlib.sha256(apath.read_bytes()).hexdigest()
            if actual != expected:
                raise AgentError("checksum_mismatch", "archive sha256 mismatch")

            # Fail closed before mutating the install if digests are missing/mutable.
            try:
                validate_image_digests(manifest.get("image_digests"), require_all=True)
            except ImageRefError as exc:
                raise AgentError("invalid_image_digest", str(exc)) from exc

            job["state"] = "installing"
            _write_job(job_id, job)
            version = str(manifest.get("version") or payload.get("target_version") or "unknown")
            dest = IFILM_HOME / "releases" / f"v{version}" if not version.startswith("v") else IFILM_HOME / "releases" / version
            # Keep previous
            previous = IFILM_HOME / "current"
            previous_target = previous.resolve() if previous.exists() else None
            (IFILM_HOME / "releases").mkdir(parents=True, exist_ok=True)
            if dest.exists():
                # atomic replace
                import shutil

                shutil.rmtree(dest)
            dest.mkdir(parents=True)
            _run(["tar", "-xzf", str(apath), "-C", str(dest)], timeout=600)
            _flatten_release_tree(dest)
            (dest / "release-manifest.json").write_text(mpath.read_text(encoding="utf-8"), encoding="utf-8")
            # Save previous pointer for rollback
            (STATE_DIR / "previous_release").write_text(str(previous_target or ""), encoding="utf-8")
            if previous.exists() or previous.is_symlink():
                previous.unlink()
            previous.symlink_to(dest)

            # Pin compose to the newly signed immutable digests, then pull/verify.
            _apply_image_digests(manifest)
            job["state"] = "restarting"
            _write_job(job_id, job)
            _compose_pull_and_up()

            job["state"] = "migrating"
            _write_job(job_id, job)
            mig = _run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    str(ENV_FILE),
                    "-f",
                    str(COMPOSE_FILE),
                    "exec",
                    "-T",
                    "backend-api",
                    "sh",
                    "-c",
                    "set -a; . /run/ifilm/runtime.env 2>/dev/null || true; set +a; alembic upgrade head",
                ],
                timeout=1800,
            )
            if mig.returncode != 0:
                job["state"] = "migration_failed"
                job["error"] = {"code": "migration_failed", "message": "alembic upgrade failed"}
                _write_job(job_id, job)
                rollback_last_update({"job_id": job_id, "reason": "migration_failed"})
                return _read_job(job_id)

            job["state"] = "health_checking"
            _write_job(job_id, job)
            healthy = False
            http_port = os.environ.get("IFILM_HTTP_PORT", "8080")
            ready_url = f"http://127.0.0.1:{http_port}/api/health/ready"
            for _ in range(60):
                health = _run(["curl", "-fsS", ready_url], timeout=10)
                if health.returncode == 0:
                    healthy = True
                    break
                time.sleep(2)
            if not healthy:
                job["state"] = "health_check_failed"
                job["error"] = {"code": "health_check_failed", "message": "readiness did not recover"}
                _write_job(job_id, job)
                rollback_last_update({"job_id": job_id, "reason": "health_check_failed"})
                return _read_job(job_id)

        job["state"] = "completed"
        job["finished_at"] = _utc_now()
        job["result"] = {"version": get_current_version({}).get("version")}
        _write_job(job_id, job)
        return job
    except AgentError as exc:
        verification_codes = ("sign", "checksum", "image_digest", "invalid_image", "digest_mismatch")
        job["state"] = (
            "verification_failed"
            if any(token in exc.code for token in verification_codes)
            else "failed"
        )
        job["error"] = {"code": exc.code, "message": exc.message}
        job["finished_at"] = _utc_now()
        _write_job(job_id, job)
        return job
    finally:
        _release_lock()


def query_update_progress(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or "")
    return _read_job(job_id)


def query_update_result(payload: dict[str, Any]) -> dict[str, Any]:
    return query_update_progress(payload)


def rollback_last_update(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or "rollback")
    prev_file = STATE_DIR / "previous_release"
    if not prev_file.is_file():
        raise AgentError("no_previous", "no previous release recorded")
    previous = prev_file.read_text(encoding="utf-8").strip()
    if not previous or not Path(previous).exists():
        raise AgentError("no_previous", "previous release path missing")
    job = {
        "job_id": job_id,
        "state": "rollback_running",
        "started_at": _utc_now(),
        "reason": payload.get("reason"),
    }
    _write_job(job_id, job)
    current = IFILM_HOME / "current"
    if current.exists() or current.is_symlink():
        current.unlink()
    current.symlink_to(previous)
    # Restore previous immutable digest references before compose up.
    prev_manifest_path = Path(previous) / "release-manifest.json"
    if prev_manifest_path.is_file():
        prev_manifest = json.loads(prev_manifest_path.read_text(encoding="utf-8"))
        try:
            _apply_image_digests(prev_manifest)
            _compose_pull_and_up()
            job["state"] = "rolled_back"
            job["result"] = get_current_version({})
        except AgentError as exc:
            job["state"] = "rollback_failed"
            job["error"] = {"code": "rollback_failed", "message": exc.message}
    else:
        job["state"] = "rollback_failed"
        job["error"] = {
            "code": "rollback_failed",
            "message": "previous release missing release-manifest.json",
        }
    job["finished_at"] = _utc_now()
    _write_job(job_id, job)
    return job


HANDLERS = {
    "get_current_version": get_current_version,
    "check_latest_release": check_latest_release,
    "run_preflight": run_preflight,
    "create_backup": create_backup,
    "install_verified_release": install_verified_release,
    "query_update_progress": query_update_progress,
    "query_update_result": query_update_result,
    "rollback_last_update": rollback_last_update,
}


class ThreadedUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            raw = self.rfile.readline(1_000_000)
            if not raw:
                return
            req = json.loads(raw.decode("utf-8"))
            cmd = str(req.get("command") or "")
            payload = req.get("payload") or {}
            if cmd not in ALLOWED_COMMANDS:
                raise AgentError("invalid_command", f"command not allowed: {cmd}")
            _require_secret(payload if isinstance(payload, dict) else {})
            if not isinstance(payload, dict):
                raise AgentError("invalid_payload", "payload must be an object")
            # Strip secret before handler logs/persistence
            safe_payload = {k: v for k, v in payload.items() if k != "shared_secret"}
            result = HANDLERS[cmd](safe_payload)
            resp = {"ok": True, "command": cmd, "result": result}
        except AgentError as exc:
            resp = {"ok": False, "error": {"code": exc.code, "message": exc.message}}
        except Exception as exc:  # noqa: BLE001
            resp = {"ok": False, "error": {"code": "internal", "message": "update agent error"}}
            # Avoid leaking details to clients; write local log only.
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            with (STATE_DIR / "agent-errors.log").open("a", encoding="utf-8") as fh:
                fh.write(f"{_utc_now()} {type(exc).__name__}\n")
        self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadedUnixServer(str(SOCKET_PATH), Handler)
    os.chmod(SOCKET_PATH, int(os.environ.get("UPDATE_AGENT_SOCKET_MODE", "0o660"), 8))
    print(f"ifilm-update-agent listening on {SOCKET_PATH}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
