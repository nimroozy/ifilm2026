"""Default-deny firewall / egress PLAN for operator review (Phase 9).

Never applied automatically. Guidance only (nftables + ufw notes).
"""

from __future__ import annotations

from app.services.branch_cache.deploy.inventory import StagingInventoryV1


def render_firewall_plan(inventory: StagingInventoryV1) -> str:
    origin_ip = inventory.origin.pinned_resolved_ipv4
    origin_port = inventory.origin.port
    mgmt = inventory.management_access_placeholder
    resolvers = ", ".join(inventory.dns_resolver_placeholders)
    return f"""# Phase 9 one-node staging egress PLAN (NOT APPLIED)

This document is an operator-review artifact. The Phase 9 package never
executes firewall commands, never opens host ports, and never publishes a
public media listener.

## Policy intent

- Default deny (inbound and outbound)
- Allow established/related return traffic
- DNS only to explicitly supplied resolvers (placeholders until reviewed): {resolvers}
- HTTPS (TCP) only to the single pinned origin IP/port: {origin_ip}:{origin_port}
- Management access source CIDR is a required placeholder: {mgmt}
- Time sync (NTP/chrony) only to operator-approved servers (placeholder)
- No public bind for branch-cache media; service bind remains {inventory.bind_host}

## nftables sketch (review only — do not paste-run without change control)

```
table inet ifilm_branch_staging {{
  chain input {{
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    iif lo accept
    # tcp dport <mgmt_ssh> ip saddr {mgmt} accept
  }}
  chain output {{
    type filter hook output priority 0; policy drop;
    ct state established,related accept
    oif lo accept
    # dns
    # udp dport 53 ip daddr {{ {resolvers} }} accept
    # tcp dport 53 ip daddr {{ {resolvers} }} accept
    # origin only
    tcp dport {origin_port} ip daddr {origin_ip} accept
  }}
}}
```

## ufw notes (if target host uses ufw)

- Prefer default deny incoming/outgoing
- Do not `ufw allow 80/443` for the branch-cache node media path
- Represent management access as an explicit allow from {mgmt} only after review
- Do not auto-apply from this repository package

## DNS rebinding / multi-A

Preflight requires stable resolution matching pinned IP `{origin_ip}` and
evidence id `{inventory.origin.reviewed_dns_evidence_id}`. If resolution flaps
or returns multiple addresses, plan classification is no-go until re-reviewed.

## Explicit non-goals

- No automatic `nft`/`ufw` invocation from CI or the plan CLI
- No Cloudflare/R2/DNS API calls
- No public media listener
"""
