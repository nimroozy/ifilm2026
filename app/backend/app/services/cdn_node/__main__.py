"""CLI: python -m app.services.cdn_node serve | validate"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ifilm-cdn-node")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the node HTTP service (bind from IFILM_CDN_BIND_*)")
    sub.add_parser("validate", help="build the app without binding a socket")
    args = parser.parse_args(argv)
    from app.services.cdn_node.config import NodeRuntimeError, load_node_runtime_config

    try:
        cfg = load_node_runtime_config()
    except NodeRuntimeError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "error": str(exc)}), file=sys.stderr)
        return 2
    if args.command == "validate":
        from app.services.cdn_node.asgi import create_node_app

        app = create_node_app(cfg, start_heartbeat=False)
        print(json.dumps({"ok": True, "node_id": cfg.node_id, "routes": len(app.routes)}))
        return 0
    if args.command == "serve":
        import uvicorn

        from app.services.cdn_node.asgi import create_node_app

        uvicorn.run(
            create_node_app(cfg),
            host=cfg.bind_host,
            port=cfg.bind_port,
            proxy_headers=False,
            server_header=False,
            date_header=True,
            log_level="info",
            access_log=False,
        )
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
