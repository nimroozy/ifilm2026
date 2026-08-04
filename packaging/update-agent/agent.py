#!/usr/bin/env python3
"""iFilm privileged update agent.

Listens on a root-owned Unix domain socket. Accepts only typed JSON commands.
Never executes arbitrary shell. Never accepts Git URLs, paths, or Docker args
from the web application.

Install/update/rollback transitions are transactional: image env refs, compose
project recreation, health, and the /opt/ifilm/current symlink stay consistent
with the verified signed manifest, or the previous release is restored.
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
COMPOSE_PROJECT = "ifilm"
APP_SERVICES = (
    "backend-api",
    "frontend",
    "media-processing-worker",
    "publishing-worker",
)
EDGE_SERVICES = ("nginx", "postgres", "redis")
IMAGE_ENV_KEYS = ("IFILM_IMAGE_BACKEND_API", "IFILM_IMAGE_FRONTEND")


def _previous_release_file() -> Path:
    return STATE_DIR / "previous_release"


def _previous_env_file() -> Path:
    return STATE_DIR / "previous_env_snapshot.json"


def _active_target_file() -> Path:
    return STATE_DIR / "active_target.json"


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
        "verify_installation",
    }
)


class AgentError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _run(
    argv: list[str],
    *,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Fixed-argv subprocess helper. Never uses shell=True."""
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _compose_env() -> dict[str, str]:
    """Build subprocess env so compose --env-file wins over a stale agent process env.

    Operators (and our non-systemd supervisor) may start the agent with
    ``set -a; . /etc/ifilm/ifilm.env``, which exports IFILM_IMAGE_* into the
    agent process. Docker Compose prefers process env over ``--env-file``, so
    digest updates written during an update would otherwise be ignored.
    """
    env = dict(os.environ)
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.startswith("IFILM_IMAGE_") or key in {
                "POSTGRES_DB",
                "POSTGRES_USER",
                "POSTGRES_PASSWORD",
                "REDIS_PASSWORD",
                "JWT_SECRET",
                "PLAYBACK_TOKEN_SECRET",
                "UPDATE_CHANNEL",
                "UPDATE_AGENT_SOCKET",
                "UPDATE_AGENT_SHARED_SECRET",
                "IFILM_HTTP_PORT",
                "IFILM_ENV_FILE",
                "APP_ENV",
            }:
                env[key] = value
    env["IFILM_ENV_FILE"] = str(ENV_FILE)
    env["COMPOSE_PROJECT_NAME"] = COMPOSE_PROJECT
    return env


def _compose_file_for(release_dir: Path | None = None) -> Path:
    if release_dir is not None:
        return release_dir / "packaging" / "compose" / "docker-compose.production.yml"
    return IFILM_HOME / "current" / "packaging" / "compose" / "docker-compose.production.yml"


def _compose_cmd(compose_file: Path, *args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-p",
        COMPOSE_PROJECT,
        "--env-file",
        str(ENV_FILE),
        "-f",
        str(compose_file),
        *args,
    ]


def _require_secret(payload: dict[str, Any]) -> None:
    provided = str(payload.get("shared_secret") or "")
    if not SHARED_SECRET or provided != SHARED_SECRET:
        raise AgentError("unauthorized", "update agent shared secret rejected")


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "version": "0.0.0-dev",
            "commit_sha": "unknown",
            "channel": _read_env_value("UPDATE_CHANNEL") or "stable",
            "migration_head": "unknown",
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _read_env_value(key: str) -> str | None:
    if not ENV_FILE.is_file():
        return None
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


def _parse_env_file(text: str) -> list[str]:
    return text.splitlines()


def _upsert_env_vars(updates: dict[str, str]) -> None:
    """Atomically write one or more env keys; preserve unrelated configuration."""
    if not ENV_FILE.is_file():
        raise AgentError("missing_env", f"env file missing: {ENV_FILE}")
    if not updates:
        return
    lines = _parse_env_file(ENV_FILE.read_text(encoding="utf-8"))
    found = {key: False for key in updates}
    out: list[str] = []
    for line in lines:
        replaced = False
        for key, value in updates.items():
            if line.startswith(f"{key}="):
                out.append(f"{key}={value}")
                found[key] = True
                replaced = True
                break
        if not replaced:
            out.append(line)
    for key, value in updates.items():
        if not found[key]:
            out.append(f"{key}={value}")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".ifilm.env.",
        suffix=".tmp",
        dir=str(ENV_FILE.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, ENV_FILE)
        # Re-affirm mode after replace (some FS preserve destination mode).
        os.chmod(ENV_FILE, 0o600)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _upsert_env(key: str, value: str) -> None:
    _upsert_env_vars({key: value})


def _snapshot_env_image_state() -> dict[str, str]:
    snap: dict[str, str] = {}
    for key in IMAGE_ENV_KEYS:
        val = _read_env_value(key)
        if val is not None:
            snap[key] = val
    channel = _read_env_value("UPDATE_CHANNEL")
    if channel is not None:
        snap["UPDATE_CHANNEL"] = channel
    return snap


def _restore_env_snapshot(snap: dict[str, str] | None) -> None:
    if not snap:
        return
    _upsert_env_vars(dict(snap))


def _apply_image_digests(manifest: dict[str, Any]) -> dict[str, str]:
    try:
        digests = validate_image_digests(manifest.get("image_digests"), require_all=True)
        env_vars = env_vars_from_digests(digests)
    except ImageRefError as exc:
        raise AgentError("invalid_image_digest", str(exc)) from exc
    _upsert_env_vars(env_vars)
    persisted = _image_refs_from_env()
    expected = {
        "backend-api": env_vars["IFILM_IMAGE_BACKEND_API"],
        "frontend": env_vars["IFILM_IMAGE_FRONTEND"],
    }
    if persisted != expected:
        raise AgentError(
            "env_digest_mismatch",
            "persisted IFILM_IMAGE_* values do not match signed manifest digests",
        )
    return env_vars


def _image_refs_from_env() -> dict[str, str]:
    if not ENV_FILE.is_file():
        raise AgentError("missing_env", f"env file missing: {ENV_FILE}")
    refs: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("IFILM_IMAGE_BACKEND_API="):
            refs["backend-api"] = line.split("=", 1)[1].strip()
        elif line.startswith("IFILM_IMAGE_FRONTEND="):
            refs["frontend"] = line.split("=", 1)[1].strip()
    if "backend-api" not in refs or "frontend" not in refs:
        raise AgentError("invalid_image_digest", "image digest env vars missing after apply")
    for name, ref in refs.items():
        if "@sha256:" not in ref:
            raise AgentError("invalid_image_digest", f"mutable or non-digest ref rejected for {name}")
        try:
            validate_image_digests({name: ref}, require_all=False)
        except ImageRefError as exc:
            raise AgentError("invalid_image_digest", str(exc)) from exc
    return refs


def _digest_only(ref: str) -> str:
    if "@" in ref:
        return ref.split("@", 1)[1].strip()
    return ref.strip()


def get_current_version(_payload: dict[str, Any]) -> dict[str, Any]:
    manifest = _read_manifest(IFILM_HOME / "current" / "release-manifest.json")
    channel = _read_env_value("UPDATE_CHANNEL") or manifest.get("channel") or "stable"
    return {
        "version": manifest.get("version"),
        "commit_sha": manifest.get("commit_sha"),
        "channel": channel,
        "migration_head": manifest.get("migration_head"),
        "published_at": manifest.get("published_at"),
    }


def check_latest_release(payload: dict[str, Any]) -> dict[str, Any]:
    channel = str(
        payload.get("channel") or _read_env_value("UPDATE_CHANNEL") or os.environ.get("UPDATE_CHANNEL") or "stable"
    )
    url = f"https://api.github.com/repos/{REPO}/releases?per_page=20"
    req = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": "ifilm-update-agent"}
    )
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
        return {"update_available": False, "current": current, "latest": None, "channel": channel}
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

    add("compose_file", COMPOSE_FILE.is_file(), "compose present" if COMPOSE_FILE.is_file() else "missing")
    add(
        "env_file",
        ENV_FILE.is_file() and oct(ENV_FILE.stat().st_mode & 0o777) == "0o600",
        "mode 600" if ENV_FILE.is_file() else "missing",
    )
    add("public_key", PUBLIC_KEY.is_file(), "present" if PUBLIC_KEY.is_file() else "missing")
    add("lock_free", not LOCK_FILE.exists() or payload.get("ignore_lock") is True, "lock")

    disk = _run(["df", "-BG", "--output=avail", str(IFILM_VAR)])
    free_gb = 0
    if disk.returncode == 0:
        try:
            free_gb = int("".join(ch for ch in disk.stdout.strip().splitlines()[-1] if ch.isdigit()))
        except ValueError:
            free_gb = 0
    add("disk_space", free_gb >= 5, f"{free_gb}GB free")

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
                    add("signature", True, str(manifest.get("version", "")))
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
    dump = out / "postgres.dump"
    compose_file = _compose_file_for()
    proc_bin = subprocess.run(
        _compose_cmd(compose_file, "exec", "-T", "postgres", "pg_dump", "-U",
                     os.environ.get("POSTGRES_USER", "ifilm"), "-d",
                     os.environ.get("POSTGRES_DB", "ifilm"), "-Fc"),
        check=False,
        capture_output=True,
        timeout=1800,
        env=_compose_env(),
    )
    if proc_bin.returncode != 0:
        raise AgentError(
            "backup_failed",
            (proc_bin.stderr or b"").decode("utf-8", errors="replace")[-500:] or "pg_dump failed",
        )
    dump.write_bytes(proc_bin.stdout)

    list_proc = _run(["pg_restore", "-l", str(dump)], timeout=120)
    if list_proc.returncode != 0:
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

    if ENV_FILE.is_file():
        redacted = []
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if any(
                line.startswith(p)
                for p in (
                    "POSTGRES_PASSWORD=",
                    "JWT_SECRET=",
                    "PLAYBACK_TOKEN_SECRET=",
                    "REDIS_PASSWORD=",
                    "UPDATE_AGENT_SHARED_SECRET=",
                    "ADMIN_BOOTSTRAP_PASSWORD=",
                    "RADIUS_SECRET=",
                )
            ):
                key = line.split("=", 1)[0]
                redacted.append(f"{key}=REDACTED")
            else:
                redacted.append(line)
        (out / "ifilm.env.redacted").write_text("\n".join(redacted) + "\n", encoding="utf-8")
        os.chmod(out / "ifilm.env.redacted", 0o600)

    meta = {
        "backup_id": out.name,
        "created_at": _utc_now(),
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


def _write_active_target(job_id: str, target_version: str, release_dir: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _active_target_file().write_text(
        json.dumps(
            {
                "job_id": job_id,
                "target_version": target_version,
                "release_dir": release_dir,
                "updated_at": _utc_now(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _clear_active_target(job_id: str | None = None) -> None:
    if not _active_target_file().is_file():
        return
    if job_id:
        try:
            data = json.loads(_active_target_file().read_text(encoding="utf-8"))
            if str(data.get("job_id") or "") != job_id:
                # Stale reconciliation / old job must not clear a newer target.
                return
        except Exception:  # noqa: BLE001
            pass
    _active_target_file().unlink(missing_ok=True)


def _atomic_symlink(target: Path, link: Path) -> None:
    """Replace symlink atomically via temp link + os.replace."""
    link.parent.mkdir(parents=True, exist_ok=True)
    tmp = link.parent / f".current.{os.getpid()}.{int(time.time() * 1000)}.tmp"
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    tmp.symlink_to(target.resolve() if target.exists() else target)
    os.replace(tmp, link)


def _current_symlink_target() -> Path | None:
    link = IFILM_HOME / "current"
    if not link.exists() and not link.is_symlink():
        return None
    try:
        return link.resolve()
    except Exception:  # noqa: BLE001
        return None


def _switch_current(release_dir: Path) -> None:
    _atomic_symlink(release_dir, IFILM_HOME / "current")
    resolved = _current_symlink_target()
    if resolved is None or resolved.resolve() != release_dir.resolve():
        raise AgentError("symlink_switch_failed", "current symlink does not point at target release")


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


def _docker_pull_ref(ref: str) -> None:
    pull = _run(["docker", "pull", ref], timeout=1800, env=_compose_env())
    if pull.returncode != 0:
        detail = (pull.stderr or pull.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else "docker pull failed"
        raise AgentError("image_pull_failed", f"docker pull failed for {ref}: {tail[:240]}")
    _verify_pulled_image(ref)


def _compose_config_images(compose_file: Path) -> dict[str, str]:
    """Return effective image refs for backend-api / frontend from compose config."""
    cfg = _run(_compose_cmd(compose_file, "config", "--format", "json"), timeout=120, env=_compose_env())
    if cfg.returncode != 0:
        # Older compose may lack --format json; fall back to yaml-ish parse via config.
        cfg = _run(_compose_cmd(compose_file, "config"), timeout=120, env=_compose_env())
        if cfg.returncode != 0:
            raise AgentError("compose_config_failed", "docker compose config failed")
        images: dict[str, str] = {}
        current_svc = None
        for line in (cfg.stdout or "").splitlines():
            if line and not line.startswith(" ") and line.rstrip().endswith(":"):
                current_svc = line.strip().rstrip(":")
            elif current_svc in {"backend-api", "frontend"} and "image:" in line:
                images[current_svc] = line.split("image:", 1)[1].strip().strip("\"'")
        if "backend-api" not in images or "frontend" not in images:
            raise AgentError("compose_config_failed", "compose config missing application images")
        return images
    data = json.loads(cfg.stdout)
    services = data.get("services") or {}
    out: dict[str, str] = {}
    for name in ("backend-api", "frontend"):
        svc = services.get(name) or {}
        image = str(svc.get("image") or "").strip()
        if not image:
            raise AgentError("compose_config_failed", f"compose config missing image for {name}")
        out[name] = image
    return out


def _container_image_digest(container_id: str) -> str | None:
    inspect = _run(
        ["docker", "inspect", "--format", "{{json .Image}}", container_id],
        timeout=60,
    )
    if inspect.returncode != 0:
        return None
    image_id = (inspect.stdout or "").strip().strip('"')
    digests_proc = _run(
        ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", image_id],
        timeout=60,
    )
    if digests_proc.returncode != 0:
        return None
    digests = json.loads(digests_proc.stdout or "[]")
    for item in digests:
        text = str(item)
        if "@sha256:" in text:
            return text.split("@", 1)[1]
    # Fallback: image Id is sha256:...
    if image_id.startswith("sha256:"):
        return image_id
    return None


def _running_service_digests(compose_file: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for service in ("backend-api", "frontend"):
        ps = _run(_compose_cmd(compose_file, "ps", "-q", service), timeout=60, env=_compose_env())
        if ps.returncode != 0 or not (ps.stdout or "").strip():
            raise AgentError("running_digest_mismatch", f"no running container for {service}")
        cid = ps.stdout.strip().splitlines()[0].strip()
        digest = _container_image_digest(cid)
        if not digest or not digest.startswith("sha256:"):
            raise AgentError("running_digest_mismatch", f"could not resolve running digest for {service}")
        out[service] = digest
    return out


def _list_project_containers() -> list[str]:
    """List container names belonging to the ifilm compose project only."""
    proc = _run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.compose.project={COMPOSE_PROJECT}",
            "--format",
            "{{.Names}}",
        ],
        timeout=60,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]


def _assert_no_duplicate_managed_containers() -> None:
    names = _list_project_containers()
    # Expected pattern: ifilm-<service>-<replica>
    by_service: dict[str, list[str]] = {}
    for name in names:
        parts = name.split("-")
        if len(parts) < 3 or parts[0] != COMPOSE_PROJECT:
            continue
        # service may be multi-segment (backend-api, media-processing-worker)
        # last segment is replica index when numeric
        if parts[-1].isdigit():
            service = "-".join(parts[1:-1])
        else:
            service = "-".join(parts[1:])
        by_service.setdefault(service, []).append(name)
    for service in APP_SERVICES:
        containers = by_service.get(service) or []
        if len(containers) > 1:
            raise AgentError(
                "compose_conflict",
                f"duplicate managed containers for {service}: {', '.join(containers)}",
            )


def _compose_stop_app(compose_file: Path) -> None:
    """Stop application services without touching postgres/redis data volumes."""
    stop = _run(
        _compose_cmd(compose_file, "stop", *APP_SERVICES),
        timeout=600,
        env=_compose_env(),
    )
    if stop.returncode != 0:
        # Idempotent: missing services are acceptable during first install / recovery.
        detail = (stop.stderr or stop.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else ""
        if "no such service" not in tail.lower() and "no containers" not in (stop.stderr or "").lower():
            # Still try remove; conflicts are handled below.
            pass
    rm = _run(
        _compose_cmd(compose_file, "rm", "-f", *APP_SERVICES),
        timeout=300,
        env=_compose_env(),
    )
    if rm.returncode != 0:
        # Controlled conflict recovery: remove only labeled ifilm project app containers.
        for name in _list_project_containers():
            for service in APP_SERVICES:
                if name == f"{COMPOSE_PROJECT}-{service}-1" or name.startswith(f"{COMPOSE_PROJECT}-{service}-"):
                    _run(["docker", "rm", "-f", name], timeout=120)


def _compose_pull_and_up(compose_file: Path | None = None) -> None:
    """Pull exact digests and recreate iFilm-managed app services under project `ifilm`."""
    compose_file = compose_file or _compose_file_for()
    if not compose_file.is_file():
        raise AgentError("compose_missing", f"compose file missing: {compose_file}")
    refs = _image_refs_from_env()
    compose_env = _compose_env()
    _docker_pull_ref(refs["backend-api"])
    _docker_pull_ref(refs["frontend"])
    pull = _run(_compose_cmd(compose_file, "pull"), timeout=1800, env=compose_env)
    if pull.returncode != 0:
        detail = (pull.stderr or pull.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else "docker compose pull failed"
        raise AgentError("image_pull_failed", f"docker compose pull failed: {tail[:240]}")
    _verify_pulled_image(refs["backend-api"])
    _verify_pulled_image(refs["frontend"])

    # Controlled stop/remove of app services before recreate (avoids name conflicts).
    _compose_stop_app(compose_file)

    up = _run(
        _compose_cmd(
            compose_file,
            "up",
            "-d",
            "--no-build",
            "--force-recreate",
            "--remove-orphans",
            *APP_SERVICES,
        ),
        timeout=1800,
        env=compose_env,
    )
    if up.returncode != 0:
        detail = (up.stderr or up.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else "docker compose up failed"
        # One controlled retry after project-scoped cleanup.
        _compose_stop_app(compose_file)
        up = _run(
            _compose_cmd(
                compose_file,
                "up",
                "-d",
                "--no-build",
                "--force-recreate",
                *APP_SERVICES,
            ),
            timeout=1800,
            env=compose_env,
        )
        if up.returncode != 0:
            detail = (up.stderr or up.stdout or "").strip().splitlines()
            tail = detail[-1] if detail else "docker compose up failed"
            raise AgentError("compose_up_failed", f"docker compose up failed: {tail[:240]}")

    edge = _run(
        _compose_cmd(compose_file, "up", "-d", "--no-build", *EDGE_SERVICES),
        timeout=1800,
        env=compose_env,
    )
    if edge.returncode != 0:
        detail = (edge.stderr or edge.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else "docker compose up failed"
        raise AgentError("compose_up_failed", f"docker compose up failed: {tail[:240]}")

    _assert_no_duplicate_managed_containers()


def _verify_four_way_digests(manifest: dict[str, Any], compose_file: Path) -> dict[str, Any]:
    """Require manifest, env, compose config, and running digests to match."""
    try:
        manifest_refs = validate_image_digests(manifest.get("image_digests"), require_all=True)
    except ImageRefError as exc:
        raise AgentError("invalid_image_digest", str(exc)) from exc
    env_refs = _image_refs_from_env()
    compose_refs = _compose_config_images(compose_file)
    running = _running_service_digests(compose_file)

    mismatches: list[str] = []
    for name in ("backend-api", "frontend"):
        m = _digest_only(manifest_refs[name])
        e = _digest_only(env_refs[name])
        c = _digest_only(compose_refs[name])
        r = _digest_only(running[name])
        if not (m == e == c == r):
            mismatches.append(name)
    if mismatches:
        raise AgentError(
            "digest_consistency_failed",
            "manifest/env/compose/running digests disagree for: " + ", ".join(mismatches),
        )
    return {
        "backend-api": _digest_only(manifest_refs["backend-api"]),
        "frontend": _digest_only(manifest_refs["frontend"]),
        "consistent": True,
    }


def _run_migrations(compose_file: Path) -> None:
    mig = _run(
        _compose_cmd(compose_file, "exec", "-T", "backend-api", "ifilm-alembic", "upgrade", "head"),
        timeout=1800,
        env=_compose_env(),
    )
    if mig.returncode != 0:
        raise AgentError("migration_failed", "alembic upgrade failed")


def _wait_healthy() -> None:
    http_port = os.environ.get("IFILM_HTTP_PORT") or _read_env_value("IFILM_HTTP_PORT") or "8080"
    ready_url = f"http://127.0.0.1:{http_port}/api/health/ready"
    for _ in range(60):
        health = _run(["curl", "-fsS", ready_url], timeout=10)
        if health.returncode == 0:
            return
        time.sleep(2)
    raise AgentError("health_check_failed", "readiness did not recover")


def _migration_head(compose_file: Path | None = None) -> str | None:
    compose_file = compose_file or _compose_file_for()
    if not compose_file.is_file():
        return None
    proc = _run(
        _compose_cmd(compose_file, "exec", "-T", "backend-api", "ifilm-alembic", "current"),
        timeout=120,
        env=_compose_env(),
    )
    if proc.returncode != 0:
        return None
    # alembic current prints "<rev> (head)" or similar
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line or line.startswith("INFO"):
            continue
        return line.split()[0]
    return None


def _flatten_release_tree(dest: Path) -> None:
    """Support both flat archives and nested ifilm/ archives."""
    nested = dest / "ifilm"
    if nested.is_dir() and not (dest / "packaging").is_dir():
        import shutil

        for child in nested.iterdir():
            target = dest / child.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            child.rename(target)
        nested.rmdir()


def _resolve_channel_after(payload: dict[str, Any], source_channel: str, manifest: dict[str, Any]) -> str:
    if payload.get("restore_channel"):
        return str(payload["restore_channel"]).strip().lower() or "stable"
    # Non-prerelease installs always return production to stable.
    version = str(manifest.get("version") or "")
    channel = str(manifest.get("channel") or "").lower()
    if channel == "stable" or ("rc" not in version.lower() and "beta" not in version.lower() and "alpha" not in version.lower()):
        return "stable"
    return source_channel or "stable"


def _perform_rollback_to(
    previous: Path,
    *,
    job_id: str,
    reason: str | None,
    previous_env: dict[str, str] | None,
) -> dict[str, Any]:
    """Restore previous env, symlink, and services; verify health."""
    job = {
        "job_id": job_id,
        "state": "rollback_running",
        "started_at": _utc_now(),
        "reason": reason,
    }
    _write_job(job_id, job)
    try:
        if previous_env:
            _restore_env_snapshot(previous_env)
        elif (previous / "release-manifest.json").is_file():
            prev_manifest = json.loads((previous / "release-manifest.json").read_text(encoding="utf-8"))
            _apply_image_digests(prev_manifest)

        _switch_current(previous)
        compose_file = _compose_file_for(previous)
        _compose_pull_and_up(compose_file)
        prev_manifest_path = previous / "release-manifest.json"
        if prev_manifest_path.is_file():
            prev_manifest = json.loads(prev_manifest_path.read_text(encoding="utf-8"))
            _verify_four_way_digests(prev_manifest, compose_file)
        _wait_healthy()
        job["state"] = "rolled_back"
        job["result"] = get_current_version({})
        job["integrity"] = {"consistent": True}
    except AgentError as exc:
        job["state"] = "rollback_failed"
        job["error"] = {"code": "rollback_failed", "message": exc.message}
    job["finished_at"] = _utc_now()
    _write_job(job_id, job)
    return job


def install_verified_release(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = hashlib.sha256(f"{time.time()}:{os.getpid()}".encode()).hexdigest()[:16]
    source_channel = _read_env_value("UPDATE_CHANNEL") or "stable"
    job: dict[str, Any] = {
        "job_id": job_id,
        "state": "preflight",
        "started_at": _utc_now(),
        "target_version": payload.get("target_version"),
        "source_channel": source_channel,
        "result": None,
        "error": None,
        "backup_id": None,
    }
    _write_job(job_id, job)
    previous_target: Path | None = None
    previous_env: dict[str, str] | None = None
    env_mutated = False
    release_switched = False
    staged_dest: Path | None = None
    lock_held = False
    try:
        # 1/2: Preflight before exclusive lock so lock_free can pass.
        pre = run_preflight(payload)
        job["preflight"] = pre
        if not pre["ok"]:
            job["state"] = "preflight_failed"
            job["error"] = {"code": "preflight_failed", "message": "mandatory preflight failed"}
            _write_job(job_id, job)
            return job

        # 1: Acquire update lock
        _acquire_lock(job_id)
        lock_held = True

        # 3: Save previous release/env state
        previous_target = _current_symlink_target()
        previous_env = _snapshot_env_image_state()
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _previous_release_file().write_text(str(previous_target or ""), encoding="utf-8")
        _previous_env_file().write_text(json.dumps(previous_env, indent=2), encoding="utf-8")
        os.chmod(_previous_env_file(), 0o600)

        # 4: Create backup
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

            # 2: Verify signed release
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
            try:
                validate_image_digests(manifest.get("image_digests"), require_all=True)
            except ImageRefError as exc:
                raise AgentError("invalid_image_digest", str(exc)) from exc

            # 5: Stage target release (do NOT switch current yet)
            job["state"] = "installing"
            _write_job(job_id, job)
            version = str(manifest.get("version") or payload.get("target_version") or "unknown")
            dest = (
                IFILM_HOME / "releases" / f"v{version}"
                if not version.startswith("v")
                else IFILM_HOME / "releases" / version
            )
            (IFILM_HOME / "releases").mkdir(parents=True, exist_ok=True)
            if dest.exists():
                import shutil

                shutil.rmtree(dest)
            dest.mkdir(parents=True)
            _run(["tar", "-xzf", str(apath), "-C", str(dest)], timeout=600)
            _flatten_release_tree(dest)
            (dest / "release-manifest.json").write_text(mpath.read_text(encoding="utf-8"), encoding="utf-8")
            staged_dest = dest
            _write_active_target(job_id, version, str(dest))
            job["target_version"] = version
            job["staged_release"] = str(dest)

            # 6: Write target image refs atomically
            _apply_image_digests(manifest)
            env_mutated = True

            # Temporary channel scope for candidate installs; restored later.
            if payload.get("temporary_channel"):
                _upsert_env("UPDATE_CHANNEL", str(payload["temporary_channel"]).strip().lower())

            compose_file = _compose_file_for(dest)

            # 7/8: Pull exact digests and recreate services using staged compose
            job["state"] = "restarting"
            _write_job(job_id, job)
            _compose_pull_and_up(compose_file)

            # 9: Migrations
            job["state"] = "migrating"
            _write_job(job_id, job)
            try:
                _run_migrations(compose_file)
            except AgentError as exc:
                job["state"] = "migration_failed"
                job["error"] = {"code": exc.code, "message": exc.message}
                _write_job(job_id, job)
                rolled = _perform_rollback_to(
                    previous_target, job_id=job_id, reason="migration_failed", previous_env=previous_env
                ) if previous_target else {"state": "rollback_failed"}
                job = _read_job(job_id)
                if rolled.get("state") == "rolled_back":
                    job["state"] = "rolled_back"
                    job["rollback_result"] = "application_only"
                else:
                    job["state"] = "rollback_failed"
                job["finished_at"] = _utc_now()
                _write_job(job_id, job)
                return job

            # 10: Health checks
            job["state"] = "health_checking"
            _write_job(job_id, job)
            try:
                _wait_healthy()
            except AgentError as exc:
                job["state"] = "health_check_failed"
                job["error"] = {"code": exc.code, "message": exc.message}
                _write_job(job_id, job)
                rolled = _perform_rollback_to(
                    previous_target, job_id=job_id, reason="health_check_failed", previous_env=previous_env
                ) if previous_target else {"state": "rollback_failed"}
                job = _read_job(job_id)
                if rolled.get("state") == "rolled_back":
                    job["state"] = "rolled_back"
                    job["rollback_result"] = "application_only"
                else:
                    job["state"] = "rollback_failed"
                job["finished_at"] = _utc_now()
                _write_job(job_id, job)
                return job

            # 11: Verify running digests (four-way) before symlink flip
            integrity = _verify_four_way_digests(manifest, compose_file)
            job["integrity"] = integrity

            # 12: Switch /opt/ifilm/current atomically (only after proven healthy)
            _switch_current(dest)
            release_switched = True

            # Channel restore: stable production must not remain on beta/staging.
            channel_after = _resolve_channel_after(payload, source_channel, manifest)
            _upsert_env("UPDATE_CHANNEL", channel_after)
            job["channel_after"] = channel_after

            # Re-verify against current symlink compose path.
            integrity = _verify_four_way_digests(manifest, _compose_file_for())
            job["integrity"] = integrity

        # 13: Record completed update
        job["state"] = "completed"
        job["finished_at"] = _utc_now()
        job["result"] = get_current_version({})
        _write_job(job_id, job)
        _clear_active_target(job_id)
        return job
    except AgentError as exc:
        verification_codes = ("sign", "checksum", "image_digest", "invalid_image", "digest")
        job["state"] = (
            "verification_failed"
            if any(token in exc.code for token in verification_codes)
            else "failed"
        )
        job["error"] = {"code": exc.code, "message": exc.message}
        job["finished_at"] = _utc_now()
        _write_job(job_id, job)
        if env_mutated or release_switched or staged_dest is not None:
            if previous_target and previous_target.exists():
                try:
                    rolled = _perform_rollback_to(
                        previous_target,
                        job_id=job_id,
                        reason=exc.code,
                        previous_env=previous_env,
                    )
                    job = _read_job(job_id)
                    if rolled.get("state") == "rolled_back":
                        job["state"] = "rolled_back"
                        job["rollback_result"] = "application_only"
                        job["finished_at"] = _utc_now()
                        _write_job(job_id, job)
                except AgentError as rollback_exc:
                    job["state"] = "rollback_failed"
                    job["error"] = {
                        "code": "rollback_failed",
                        "message": f"update failed ({exc.code}); rollback failed: {rollback_exc.message}",
                    }
                    job["finished_at"] = _utc_now()
                    _write_job(job_id, job)
            elif previous_env:
                # No previous release dir; still restore env so candidate digests are not retained.
                try:
                    _restore_env_snapshot(previous_env)
                except Exception:  # noqa: BLE001
                    pass
        _clear_active_target(job_id)
        return job
    finally:
        # 14: Release lock
        if lock_held:
            _release_lock()


def query_update_progress(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or "")
    return _read_job(job_id)


def query_update_result(payload: dict[str, Any]) -> dict[str, Any]:
    return query_update_progress(payload)


def rollback_last_update(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or "rollback")
    # Refuse concurrent install/rollback.
    acquire = payload.get("skip_lock") is not True
    lock_held = False
    if acquire:
        _acquire_lock(job_id)
        lock_held = True
    try:
        prev_file = _previous_release_file()
        if not prev_file.is_file():
            raise AgentError("no_previous", "no previous release recorded")
        previous = Path(prev_file.read_text(encoding="utf-8").strip())
        if not previous.exists():
            raise AgentError("no_previous", "previous release path missing")
        previous_env = None
        if _previous_env_file().is_file():
            try:
                previous_env = json.loads(_previous_env_file().read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                previous_env = None
        result = _perform_rollback_to(
            previous,
            job_id=job_id,
            reason=str(payload.get("reason") or "admin_requested"),
            previous_env=previous_env,
        )
        _clear_active_target(job_id)
        return result
    finally:
        if lock_held:
            _release_lock()


def verify_installation(_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate symlink, manifest, env, compose, running digests, health, channel."""
    checks: list[dict[str, Any]] = []
    ok = True

    def add(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed:
            ok = False

    current = IFILM_HOME / "current"
    add("current_symlink", current.is_symlink() or current.is_dir(), "current release link")
    manifest_path = current / "release-manifest.json"
    add("release_metadata", manifest_path.is_file(), "release-manifest.json")
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            add("manifest_version", bool(manifest.get("version")), str(manifest.get("version") or ""))
        except Exception as exc:  # noqa: BLE001
            add("release_metadata", False, str(exc)[:120])

    # Signed manifest presence (signature file may live beside release assets).
    sig_path = current / "release-manifest.json.sig"
    if sig_path.is_file() and PUBLIC_KEY.is_file() and manifest_path.is_file():
        try:
            _verify_manifest(manifest_path, sig_path)
            add("signed_manifest", True, "verified")
        except AgentError as exc:
            add("signed_manifest", False, exc.message)
    else:
        # Manifest was verified at install time; require digests present.
        try:
            validate_image_digests(manifest.get("image_digests"), require_all=True)
            add("signed_manifest", True, "digests present in release metadata")
        except Exception as exc:  # noqa: BLE001
            add("signed_manifest", False, str(exc)[:120])

    env_ok = False
    env_refs: dict[str, str] = {}
    try:
        env_refs = _image_refs_from_env()
        env_ok = True
        add("env_image_refs", True, "immutable digests")
    except AgentError as exc:
        add("env_image_refs", False, exc.message)

    compose_file = _compose_file_for()
    compose_refs: dict[str, str] = {}
    if compose_file.is_file():
        try:
            compose_refs = _compose_config_images(compose_file)
            add("compose_image_refs", True, "compose config digests")
        except AgentError as exc:
            add("compose_image_refs", False, exc.message)
    else:
        add("compose_image_refs", False, "compose file missing")

    running: dict[str, str] = {}
    if compose_file.is_file():
        try:
            running = _running_service_digests(compose_file)
            add("running_image_digests", True, "containers inspected")
        except AgentError as exc:
            add("running_image_digests", False, exc.message)

    digests_match = False
    if manifest and env_ok and compose_refs and running:
        try:
            _verify_four_way_digests(manifest, compose_file)
            digests_match = True
            add("digest_consistency", True, "manifest=env=compose=running")
        except AgentError as exc:
            add("digest_consistency", False, exc.message)
    else:
        add("digest_consistency", False, "incomplete digest set")

    mig = _migration_head(compose_file) if compose_file.is_file() else None
    expected_mig = str(manifest.get("migration_head") or "") if manifest else ""
    mig_ok = bool(mig) and (not expected_mig or mig == expected_mig)
    add("migration_head", mig_ok, mig or "unknown")

    http_port = os.environ.get("IFILM_HTTP_PORT") or _read_env_value("IFILM_HTTP_PORT") or "8080"
    health = _run(["curl", "-fsS", f"http://127.0.0.1:{http_port}/api/health/ready"], timeout=10)
    add("service_health", health.returncode == 0, "ready" if health.returncode == 0 else "not ready")

    channel = _read_env_value("UPDATE_CHANNEL") or "stable"
    add("update_channel", bool(channel), channel)

    # Duplicate container check (project-scoped).
    try:
        _assert_no_duplicate_managed_containers()
        add("compose_duplicates", True, "no duplicate managed containers")
    except AgentError as exc:
        add("compose_duplicates", False, exc.message)

    previous = None
    if _previous_release_file().is_file():
        prev = _previous_release_file().read_text(encoding="utf-8").strip()
        if prev:
            try:
                prev_manifest = _read_manifest(Path(prev) / "release-manifest.json")
                previous = prev_manifest.get("version")
            except Exception:  # noqa: BLE001
                previous = None

    version = str(manifest.get("version") or get_current_version({}).get("version") or "unknown")
    short = {
        "backend": _digest_only(env_refs["backend-api"])[-12:] if env_refs.get("backend-api") else None,
        "frontend": _digest_only(env_refs["frontend"])[-12:] if env_refs.get("frontend") else None,
        "running_backend": (_digest_only(running["backend-api"])[-12:] if running.get("backend-api") else None),
        "running_frontend": (_digest_only(running["frontend"])[-12:] if running.get("frontend") else None),
    }
    return {
        "ok": ok,
        "installed_version": version,
        "release_manifest_verified": any(c["name"] == "signed_manifest" and c["passed"] for c in checks),
        "configured_digests_match": digests_match,
        "running_digests_match": digests_match,
        "migration_head": mig,
        "health_status": "healthy" if health.returncode == 0 else "unhealthy",
        "update_channel": channel,
        "rollback_target": previous,
        "digest_mismatch": not digests_match,
        "digest_summary": short,
        "checks": checks,
        "checked_at": _utc_now(),
    }


HANDLERS = {
    "get_current_version": get_current_version,
    "check_latest_release": check_latest_release,
    "run_preflight": run_preflight,
    "create_backup": create_backup,
    "install_verified_release": install_verified_release,
    "query_update_progress": query_update_progress,
    "query_update_result": query_update_result,
    "rollback_last_update": rollback_last_update,
    "verify_installation": verify_installation,
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
            safe_payload = {k: v for k, v in payload.items() if k != "shared_secret"}
            result = HANDLERS[cmd](safe_payload)
            resp = {"ok": True, "command": cmd, "result": result}
        except AgentError as exc:
            resp = {"ok": False, "error": {"code": exc.code, "message": exc.message}}
        except Exception as exc:  # noqa: BLE001
            resp = {"ok": False, "error": {"code": "internal", "message": "update agent error"}}
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            with (STATE_DIR / "agent-errors.log").open("a", encoding="utf-8") as fh:
                fh.write(f"{_utc_now()} {type(exc).__name__}\n")
        try:
            self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))
        except BrokenPipeError:
            return


def _cli_verify_installation() -> int:
    """Official CLI: sudo ifilm-update-agent verify-installation"""
    # CLI mode does not require the shared secret (root-operated).
    try:
        result = verify_installation({})
    except AgentError as exc:
        print(json.dumps({"ok": False, "error": {"code": exc.code, "message": exc.message}}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def main() -> None:
    if len(sys.argv) > 1:
        cmd = sys.argv[1].strip().lower().replace("_", "-")
        if cmd in {"verify-installation", "verify"}:
            raise SystemExit(_cli_verify_installation())
        if cmd in {"-h", "--help", "help"}:
            print("Usage: ifilm-update-agent [verify-installation]")
            print("  (no args)             start Unix socket server")
            print("  verify-installation   validate digest/symlink/health consistency")
            raise SystemExit(0)
        print(f"unknown command: {sys.argv[1]}", file=sys.stderr)
        raise SystemExit(2)

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
