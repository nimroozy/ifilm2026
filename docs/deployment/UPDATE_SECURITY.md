# Update security

## Threat controls

| Threat | Control |
| --- | --- |
| Unsigned release | Ed25519 manifest signature required |
| Checksum tampering | SHA-256 of archive verified against signed manifest |
| Downgrade / replay | Newer-version and minimum-version checks |
| Arbitrary Git/URL source | Allowlist: GitHub release asset hosts only |
| Root shell from web app | No shell from API; typed UDS protocol only |
| `shell=True` | Forbidden; fixed argv arrays only |
| Concurrent updates | DB active-job lock + agent lock file |
| Low-privilege admins | `system_updates.*` permissions; Super Admin default |
| CSRF / recent-auth | Password re-auth on install/backup/rollback |
| Secret leakage | Redaction helpers; API omits env/credentials/keys |
| Malicious release notes HTML | Escaped before API response |
| Mutable image tags | Digest pinning in manifest |
| Socket abuse | Root-owned socket, shared secret, mode 660 |
| Path traversal | Agent ignores client-supplied filesystem paths |

## Update agent

Service: `ifilm-update-agent.service`

Allowed commands only:

- get_current_version
- check_latest_release
- run_preflight
- create_backup
- install_verified_release
- query_update_progress
- query_update_result
- rollback_last_update

## Troubleshooting

- `update agent is not available`: check systemd unit (or supervised process) and `/run/ifilm/update-agent.sock`
- `invalid_signature`: wrong public key or tampered manifest (Ed25519 verify requires `-rawin`)
- `concurrent_update` / `lock_free` failed: wait for the active job or clear a *stale* agent lock under `/var/lib/ifilm/update-agent` after confirming no agent is running
- Backend must receive `CORS_ORIGINS` as JSON from the env file (not Compose-interpolated)

## Disposable security checks

Recorded on the disposable host: low-privilege admin → 403 on version/install; wrong re-auth password → 401; stable channel excludes prereleases; checksum-mismatched signed release refused; UDS mode configurable via `UPDATE_AGENT_SOCKET_MODE`.
