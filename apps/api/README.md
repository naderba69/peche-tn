# Peche TN API

FastAPI hosts the deterministic decision engine locally, in the full-stack Render container through `deploy/render_app.py`, and optionally as one Vercel Python Function through `api/index.py`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
make dev-api
```

- Swagger: <http://localhost:8000/api/docs>
- Health: <http://localhost:8000/api/health>
- Free-data decision: `POST /api/v1/decisions/forecast`
- Deterministic fixture evaluation: `POST /api/v1/decisions/evaluate`
- Corrected Overpass orientation: `POST /api/v1/spots/orientation`
- Gemini key check: `POST /api/v1/gemini/verify`
- Optional Gemini prose: `POST /api/v1/reports/gemini`

Safety is evaluated per hour: a localized hazard becomes an avoid window while a separate gate-passing session can remain recommended. High fouling/turbidity transport proxies are caution-only without field confirmation; critical data gaps, safety hazards inside the candidate window, and high line-holding difficulty remain hard gates.

The deterministic decision path contains no LLM and needs no secret. Gemini is an optional writer: its user-owned key arrives transiently in `X-Gemini-API-Key`, is never stored/logged, and cannot modify decisions or numbers. Google receives a sub-64 kB categorical writer packet without coordinates, raw antecedent hours or raw hourly numbers; all 63 factors and every evaluated hour remain represented compactly. A malformed structured response may be regenerated once; both generations and transport/408/429/5xx backoff share one strict four-request and 40-second total budget. Permanent client errors and semantic violations fail immediately, while browser timeout/cancel always releases the spinner and preserves the deterministic report. A ten-minute process-local TTL cache with single-flight reduces duplicate upstream calls inside each warm server process.
