"""Nginx access logs must not record raw /api/stream/{token} paths."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = ROOT / "deploy" / "staging" / "nginx" / "nginx.conf"
IFILM_CONF = ROOT / "deploy" / "staging" / "nginx" / "conf.d" / "ifilm.conf"


class NginxLogRedactionTests(unittest.TestCase):
    def test_nginx_conf_defines_loggable_uri_map(self):
        text = NGINX_CONF.read_text(encoding="utf-8")
        self.assertIn("map $uri $loggable_uri", text)
        self.assertIn("/api/stream/[REDACTED]", text)
        self.assertIn("log_format main", text)
        self.assertIn("$loggable_request_line", text)
        # Must not log raw $request (includes path token + query).
        main_block = text.split("log_format main", 1)[1].split(";", 1)[0]
        self.assertNotIn("$request", main_block)
        self.assertIn("map $args $loggable_args", text)

    def test_stream_location_uses_main_access_log(self):
        text = IFILM_CONF.read_text(encoding="utf-8")
        self.assertIn("location /api/stream/", text)
        stream_block = text.split("location /api/stream/", 1)[1].split("location ", 1)[0]
        self.assertIn("access_log /var/log/nginx/access.log main", stream_block)

    def test_redaction_pattern_covers_opaque_tokens(self):
        text = NGINX_CONF.read_text(encoding="utf-8")
        self.assertRegex(
            text,
            re.compile(r"/api/stream/\[A-Za-z0-9_-\]\{16,128\}"),
        )

    def test_simulated_uri_redaction_matches_nginx_map(self):
        """Mirror the nginx map regex so /api/stream/{secret}/… → [REDACTED]."""
        secret = "abcdefghijklmnopqrstuvwx"
        uri = f"/api/stream/{secret}/master.m3u8"
        pattern = re.compile(r"^/api/stream/[A-Za-z0-9_-]{16,128}(/.*)?$")
        m = pattern.match(uri)
        self.assertIsNotNone(m)
        loggable = f"/api/stream/[REDACTED]{m.group(1) or ''}"
        self.assertEqual(loggable, "/api/stream/[REDACTED]/master.m3u8")
        self.assertNotIn(secret, loggable)


if __name__ == "__main__":
    unittest.main()
