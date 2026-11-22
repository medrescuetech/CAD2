# CAD2 Deployment

Flask + Flask-SocketIO app. `run_direct.py` boots a production server via
`socketio.run` (eventlet worker, shipped in requirements.txt). No gunicorn
needed; put nginx/Apache in front for TLS.

## Quick start

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
SECRET_KEY=<random-64-hex> FLASK_ENV=production PORT=5000 ./venv/bin/python run_direct.py
```

`SECRET_KEY` is mandatory in production (startup aborts without it).
The database is created and seeded (admin user, code sets) on first boot.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SECRET_KEY` | yes | — | Flask session/signing key |
| `DATABASE_URL` | no | `sqlite:///app.db` | e.g. `postgresql://user:pw@host/cad` |
| `FLASK_ENV` | no | `development` | set `production` |
| `PORT` | no | `5000` | listen port |
| `BASE_URL` | no | — | external URL for links in notifications |
| `CAD_MAP_ENABLED` | no | off | `1` enables the map panel on CAD Main |
| `PCR_ENABLED` | no | off | `1` enables PCR push integration |
| `PCR_CLIENT` | w/ PCR | — | `{client}` path segment at pcr.akgmed.org |
| `PCR_API_KEY` | w/ PCR | — | `pcrk_<keyid>_<secret>` |
| `PCR_BASE_URL` | no | `https://pcr.akgmed.org` | PCR API root |
| `PCR_REQUIRE_SIGNING` | no | off | `1` sends HMAC-SHA256 body signature |
| `PCR_STORE_CALLER` | no | off | `1` includes caller name/number in PCR jobs |
| `PCR_POLL_S` | no | `5` | outbox flush interval seconds |
| `PCR_TIMEOUT_S` | no | `15` | HTTP timeout per PCR call |
| `SMTP_SERVER`/`SMTP_PORT`/`SMTP_SENDER`/`SMTP_PASSWORD` | no | — | outbound mail |
| `SKIP_WEBSOCKET_INIT` | no | off | `1` disables Socket.IO (worker/CLI use) |

## systemd unit

```ini
[Unit]
Description=CAD2 dispatch system
After=network.target

[Service]
WorkingDirectory=/opt/cad2
Environment=SECRET_KEY=<random-64-hex>
Environment=FLASK_ENV=production
Environment=PORT=5000
Environment=DATABASE_URL=postgresql://cad:pw@localhost/cad
ExecStart=/opt/cad2/venv/bin/python run_direct.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Tests

```bash
SECRET_KEY=test ./venv/bin/pytest -o addopts='-q'
```

## Screens

`/call-taker` intake & routing · `/event-cad` event workspaces, location packs,
response rules · `/cad-main` dispatch console (units board, transfers, map) ·
`/cad-reports` incident query + CSV exports.
