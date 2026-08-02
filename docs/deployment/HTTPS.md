# Production HTTPS (Let's Encrypt)

Public HTTPS for iFilm uses **host Nginx + Certbot** in front of the compose stack.
This survives application updates because certificates and the edge config live outside
`/opt/ifilm/current`.

## Layout

| Layer | Role |
| --- | --- |
| Host Nginx `:80` / `:443` | ACME challenge, HTTP→HTTPS redirect, TLS termination |
| Compose Nginx `127.0.0.1:8080` | App reverse proxy (`/api`, `/artwork`, SPA) |
| Backend / frontend / workers | Private Docker network only |

## Enable on a host

```bash
# As root — DNS A record must already point at this host
PUBLIC_DOMAIN=ifilm.af \
CERTBOT_EMAIL=ops@your-domain.example \
bash /opt/ifilm/current/packaging/https/enable_https.sh
```

The script:

1. Verifies public DNS matches the host IP
2. Installs `nginx` + `certbot`
3. Opens UFW for OpenSSH / 80 / 443
4. Binds compose Nginx to `127.0.0.1:8080` (`IFILM_HTTP_BIND`)
5. Issues a Let's Encrypt certificate (webroot)
6. Installs `/etc/nginx/sites-available/ifilm`
7. Configures renew deploy hook (`systemctl reload nginx`)
8. Updates `/etc/ifilm/ifilm.env` public URLs to `https://…`
9. Rewrites absolute `http://domain:8080` artwork URLs in Postgres

## Env keys

| Key | Value after enable |
| --- | --- |
| `HTTPS_MODE` | `provided` |
| `IFILM_HTTP_BIND` | `127.0.0.1` |
| `IFILM_HTTP_PORT` | `8080` |
| `PUBLIC_DOMAIN` | e.g. `ifilm.af` |
| `CORS_ORIGINS` | `["https://ifilm.af","https://www.ifilm.af"]` |
| `HLS_PUBLIC_BASE_URL` | `https://ifilm.af/api/stream` |
| `DEMO_PUBLIC_BASE_URL` | `https://ifilm.af` |

## Certificate paths

- Full chain: `/etc/letsencrypt/live/<domain>/fullchain.pem`
- Private key: `/etc/letsencrypt/live/<domain>/privkey.pem`

## Renewal

```bash
systemctl status certbot.timer
certbot renew --dry-run
openssl x509 -in /etc/letsencrypt/live/ifilm.af/fullchain.pem -noout -dates -subject
```

Deploy hook: `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`

## Verification

```bash
curl -I http://ifilm.af                 # 301 → https
curl -I https://ifilm.af                # 200
curl -fsS https://ifilm.af/api/health/ready
ss -lntp | grep -E ':(80|443|8080)\b'   # 8080 on 127.0.0.1 only
```

External clients must **not** reach `:8080` after cutover.

## Update / rollback notes

- App updates replace `/opt/ifilm/current` only; host Nginx + Let's Encrypt persist.
- After update, ensure `IFILM_HTTP_BIND=127.0.0.1` remains in `/etc/ifilm/ifilm.env`
  (the update agent recreates compose with that env file).
- Rollback of the app release does not remove certificates.
