# Disposable verification record

This document records disposable-host verification for the installer and
self-update system. **No secrets are included.**

## PR #40 — transactional updater physical proof (2026-08-04)

Branch: `cursor/updater-transaction-hardening-4873`  
Final head: `e1b94daf88e1f90f005f98616f38a86c5c5c60cd`  
PR: https://github.com/nimroozy/ifilm2026/pull/40 (do not merge automatically)

### Candidate release

| Field | Value |
| --- | --- |
| Tag | `v1.2.1-rc.1` (prerelease) |
| Release URL | https://github.com/nimroozy/ifilm2026/releases/tag/v1.2.1-rc.1 |
| Workflow URL | https://github.com/nimroozy/ifilm2026/actions/runs/30891929117 |
| Commit packaged | `cbcdf09e1d404640db227866197ea6c038a9fcfb` |
| Stable baseline | `v1.2.0` |
| Stable ignores prerelease | Yes — latest stable remains `v1.2.0` |

Release assets present: signed `release-manifest.json` + `.sig`, archive,
`SHA256SUMS`, backend/frontend image refs, SBOMs, Trivy JSON reports.

Immutable digests:

| Release | backend-api | frontend |
| --- | --- | --- |
| `v1.2.0` | `...@sha256:0a5e31a9f69158d4620bd1b361899ca3f325665ca981248d54e5b670f1b34329` | `...@sha256:6886ca57300bb61ad7a27e858b1ef4e37a26287df9cac41d37ae64a087dc7127` |
| `v1.2.1-rc.1` | `...@sha256:2bb7c732976cc8d9cde512f0cf163b9f6f06b1d62f5ae85679de45a81fbc9ced` | `...@sha256:283fe690dd7c2891a510c4ec6f5fb6b84ad0dbc70bd33419ab4bcdd81b7fd465` |

Public-key fingerprint (SHA-256 of DER):  
`e7b365230a5b360f417532cba134fdb91eaa73b814163f3175a3f13d28286612`  
(matches production trust anchor; private key never printed/exported)

### Disposable host

| Field | Value |
| --- | --- |
| Role | Isolated proof stack on Ubuntu 24.04 x86_64 (not production data) |
| OS | Ubuntu 24.04.4 LTS |
| Kernel | 6.8.0-124-generic |
| Arch | x86_64 |
| CPUs | 2 |
| RAM | 3.8 GiB |
| Free disk | ~87 GiB |
| Root FS | **ext4** (`/dev/vda1`) |
| Init | systemd |
| Docker | 29.7.1 |
| Compose | v5.3.1 |
| Proof HTTP port | `18080` |
| Production HTTP port | `8080` (left untouched; ready remained OK) |

Proof isolation (same physical machine as a live demo, **no production data**):

- `DOCKER_HOST=unix:///var/run/docker-ifilm-proof.sock`
- Docker data-root `/var/lib/docker-ifilm-proof`
- Paths `/opt/ifilm-proof`, `/etc/ifilm-proof`, `/var/lib/ifilm-proof`
- Compose project name remains `ifilm` inside the isolated dockerd
- Host-only compose bind rewrite (`_rewrite_proof_volume_sources`) maps proof
  host paths while container mount targets stay `/var/lib/ifilm`, `/run/ifilm`
- **No** `IFILM_ALLOW_OVERLAY_FS` (ext4 + real systemd)

### Pre-proof review (candidate head)

- PR scoped to updater reliability (no product/UI/catalog/migration churn)
- No debug output / secrets printed
- No broad `docker rm -f`; no mutable image tags
- Symlink switches only after health + four-way digest verify
- Env writes atomic (`fsync` + `os.replace`), mode `600`
- Rollback restores env, symlink, Compose state, running digests
- Stale reconciliation cannot overwrite a newer active job
- `UPDATE_CHANNEL` restored after candidate testing
- `verify-installation` exits nonzero for mismatch classes

### Automated suites (final head `e1b94da`)

| Suite | Result |
| --- | --- |
| Backend pytest | 236 passed, 1 skipped |
| Frontend `systemUpdates.test.tsx` | 5 passed |
| Packaging tests | 41 passed |
| CI checks on PR #40 | green (Backend / Frontend / Installer) |

### Clean install baseline (`v1.2.0`)

Public installer against signed `v1.2.0` into proof paths/port.

Verified:

- Signature + checksums
- Env mode `600`
- `/opt/ifilm-proof/current` → `releases/v1.2.0`
- Migration head `014_tmdb_demo_metadata`
- Services healthy on `:18080`
- `verify-installation` OK
- Running digests match `v1.2.0` manifest

Persistence markers (non-production):

- DB row `proof_markers.id=marker-v120` note `disposable-proof`
- File `/var/lib/ifilm-proof/media/originals/PROOF_MARKER.txt` = `disposable-media-marker`

### Stable → signed candidate (`v1.2.0` → `v1.2.1-rc.1`)

Agent job `8f4b180edb0b0806` → `completed`.

Four-way integrity (all agreed on candidate digests):

1. Signed manifest refs
2. `/etc/ifilm-proof/ifilm.env` refs
3. Effective Compose refs
4. Running container digests

Also verified:

- `current` symlink → `v1.2.1-rc.1` only after health
- Persistence markers retained
- Migration head unchanged (`014_tmdb_demo_metadata`)
- `source_channel=stable`, `channel_after=stable` (UPDATE_CHANNEL restored)
- No duplicate iFilm containers / no mixed RC+stable running set
- `verify-installation` passed

### Forced health-failure rollback

Method (not function mocks): apply valid `v1.2.1-rc.1` digests, recreate Compose,
then inject `iptables REJECT` on TCP `18080` so real `_wait_healthy` fails;
then real `_perform_rollback_to`.

| Check | Result |
| --- | --- |
| Update does not complete / symlink not flipped to candidate | Pass |
| Previous env refs restored (`0a5e31a9` / `6886ca57`) | Pass |
| Previous `current` symlink (`v1.2.0`) | Pass |
| Previous Compose + running digests restored | Pass |
| Persistence markers remain | Pass |
| Job `healthfail-proof` state `rolled_back` | Pass |
| `verify-installation` OK against `v1.2.0` | Pass |
| No leftover REJECT/DROP rule; no partial candidate app digests | Pass |

Elapsed health wait under REJECT: ~120.6s (60 retries × 2s).

### Compose conflict proof

Injected project-labeled `ifilm-backend-api-conflict` plus unrelated
`unrelated-proof-nginx`. Updater removed only iFilm-managed leftovers; project
name stayed `ifilm`; unrelated nginx kept; single `backend-api`; rerun idempotent.

### API restart / stale job proof

Newer `active_target` (`job-new` → `1.2.1-rc.1`) remained authoritative.
Stale installing job `staleapi001` (`9.9.9-fake`) could not complete, change
symlink, or overwrite env image refs when queried.

### Interrupted env write

Simulated crash during `os.replace` left original `/etc/ifilm-proof/ifilm.env`
intact, mode `600`, secrets present (not printed).

### Real rollback (`v1.2.1-rc.1` → `v1.2.0`)

Job `rollback-proof` → `rolled_back`. Env/Compose/running digests and symlink
matched `v1.2.0`; markers preserved; health + `verify-installation` OK.

### Admin integrity UI / verify gate

`verify-installation` fields exercised for System Updates integrity surface:

- installed version, manifest verification, configured/running digest match,
  migration head, health, rollback target

Deliberate bad env digest:

- `digest_mismatch=true`, exit nonzero, `ok=false`
- update blocked (`update_blocked=true`)
- response JSON contained **no** secrets and **no** filesystem paths
- correct env restored afterward; verify OK

### Proof-driven code fixes on the branch

1. Always clear project-scoped app container leftovers on recreate (`19858dc`)
2. Map `subprocess.TimeoutExpired` to returncode `124` so hung health curls
   become `health_check_failed` instead of bypassing rollback (`e1b94da`)
3. mypy fix for integrity `digest_summary` typing (`cbcdf09`) — required for
   the signed candidate workflow

### Ready gate

All required physical scenarios passed; no BLOCKER/HIGH remaining for the
signed-candidate disposable proof; CI green. PR marked Ready for Review;
**not** merged automatically.

### Deviations (PR #40)

1. Cloud-agent VM alone could not pull GHCR or provide systemd/ext4; proof used
   an isolated dockerd + `*-proof` paths on a disposable Ubuntu 24.04 host that
   shares metal with a live demo on `:8080`. Production `/opt/ifilm` and
   `/var/lib/ifilm` were never used as proof data.
2. Host-only `_rewrite_proof_volume_sources` keeps container paths canonical
   while binding proof host directories (not shipped in git).
3. Forced-health used iptables REJECT against a valid signed candidate rather
   than publishing a separate failhealth tag (allowed: “publish **or** use”).
4. First DROP-based health attempt hung on curl timeout before `e1b94da`;
   re-run used REJECT + timeout→124 mapping.

---

## Historical record (PR #14 / earlier candidates)

Earlier disposable proofs (`v0.1.x-test`, Actions-signed `v0.1.4-candidate` /
`v0.1.5-candidate`) remain valid history for installer bootstrap evolution.
Summary:

- Signing scheme: Ed25519 (`openssl pkeyutl` with `-rawin`)
- Trust anchor fingerprint: `e7b365230a5b360f417532cba134fdb91eaa73b814163f3175a3f13d28286612`
- Revoked fingerprint (do not trust): `8c04b9141a9fe72346edf9e1f6bc27b0fbef3dc728d6e61124fb897e74ac1e26`
  — see `KEY_ROTATION_EMERGENCY_2026-08-01.md`
- Overlay/no-systemd disposable runs required `IFILM_ALLOW_OVERLAY_FS=1` and are
  **not** the normal production deployment path

### Supported OS matrix

| Platform | Claim | Evidence |
| --- | --- | --- |
| Ubuntu 24.04 x86_64 | **Verified / supported** | PR #40 ext4+systemd proof + earlier disposable runs |
| Ubuntu 22.04 | **Experimental / unverified** | Requires `IFILM_ALLOW_UNVERIFIED_OS=1` |
| Debian 12 | **Experimental / unverified** | Requires `IFILM_ALLOW_UNVERIFIED_OS=1` |
| Other OS/arch | Rejected | Installer hard-fail |
| Overlay FS / no-systemd | Explicit opt-in only | Not normal production deployment |

## Rollback classification reminder

Automatic rollback restores previous immutable release symlink/images/config.
It does **not** automatically restore PostgreSQL for irreversible migrations.
Manifest field `rollback_compatibility` must be trusted.
