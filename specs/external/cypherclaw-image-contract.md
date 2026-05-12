# CypherClaw Image API — Integration Contract

REST surface for generating images via Gemini and uploading them to S3.
Returns a public direct-S3 URL ready to embed in marketing content.

**Audience:** internal applications (CTMarketing, etc.) that need to mint images on demand.
**Status:** v1.

## Base URL

The service binds `0.0.0.0:9000` on the cypherclaw host. Reach it via:

- **Tailscale (preferred):** `http://cypherclaw-ts:9000` — alias for `100.74.35.114:9000`. Requires the consumer to be on the same tailnet.
- **LAN (only if on the same physical network):** `http://192.168.1.139:9000`. The IP is dynamic via DHCP — Tailscale is more stable.

The service is **not** exposed to the public internet. Add a reverse proxy on Cloudflare/nginx if you need that.

## Authentication

Bearer token in the `Authorization` header. Keys are issued and rotated by the cypherclaw operator (Anthony) — ask for one before integrating.

```
Authorization: Bearer <your-key>
```

Per-consumer keys exist so any single one can be revoked without disturbing the others. If your key returns 401, it has been rotated; ask for a new one.

`/healthz` is the one endpoint that doesn't require auth (so probes and monitoring can hit it without credentials).

## Endpoints

### `GET /healthz`

Liveness probe. Returns the configured S3 bucket so consumers can sanity-check they're hitting the right deployment.

```json
{
  "status": "ok",
  "bucket": "ctmarketing-cypherclaw-images",
  "region": "us-west-2"
}
```

### `POST /api/v1/jobs`

Submit a generation request. Returns immediately with `status: queued` — the actual image generation is asynchronous.

**Request:**
```json
{
  "project_slug": "ctmarketing-q2-launch",
  "spec_yaml": "prompt: A simple round red apple ...\nsize: 1024x1024\n"
}
```

| Field | Required | Notes |
|---|---|---|
| `project_slug` | yes | Free-form, max 128 chars. Used for grouping in logs and reporting. |
| `spec_yaml` | yes | YAML spec — see "Spec format" below. |

**Response (202 Accepted):**
```json
{
  "job_id": "2a80f6f6-e46b-40de-b63f-b82a7b428b16",
  "status": "queued",
  "project_slug": "ctmarketing-q2-launch",
  "cost_usd": null
}
```

**Errors:**
- `400 invalid spec_yaml: ...` — the YAML is malformed or violates the schema. Fix the YAML and retry.
- `401 missing/invalid bearer token` — auth.

### `GET /api/v1/jobs/{job_id}`

Poll job status. Recommended cadence: 2-3 seconds. Median end-to-end is ~25-40 seconds.

**Response when done:**
```json
{
  "job_id": "2a80f6f6-e46b-40de-b63f-b82a7b428b16",
  "status": "completed",
  "project_slug": "ctmarketing-q2-launch",
  "cost_usd": 0.134,
  "output_urls": [
    "https://ctmarketing-cypherclaw-images.s3.us-west-2.amazonaws.com/jobs/2a80f6f6-e46b-40de-b63f-b82a7b428b16/image.png"
  ],
  "error": null,
  "content_piece_id": null
}
```

**Status values:**
- `queued` — accepted, not yet picked up by worker
- `running` — Gemini is generating
- `completed` — `output_urls` is populated, ready to use
- `failed` — `error` field has the reason

**Errors:**
- `404 job {id} not found` — wrong job_id or > 30 days old (expired)
- `401` — auth.

## Spec format

Two shapes are accepted. Use whichever fits the caller.

**Shape A — single prompt:**
```yaml
prompt: A simple round red apple on a white background, professional product photo lighting
size: 1024x1024
```

**Shape B — structured:**
```yaml
content_piece_id: ctmarketing-q2-launch-hero
images:
  - prompt: A simple round red apple on a white background
    size: 1024x1024
  - prompt: The same apple from a side angle, dramatic shadow
    size: 1024x1024
model: gemini-3-pro-image-preview
```

Shape B can produce multiple images per job — `output_urls` will have one entry per `images:` item.

## Output contract

URLs returned in `output_urls`:

- Direct-from-S3 (no proxy), HTTPS only.
- Public-read via bucket policy. Safe to `<img src=...>` in CTMarketing pages.
- `Cache-Control: public, max-age=31536000, immutable` — content-addressed by `job_id` so caching is safe.
- **Lifecycle: deleted 30 days after creation.** If you need long-term hosting, copy the URL contents to your own bucket once you've consumed the job.
- Bytes are JPEG even though the file is `.png` (Gemini quirk). Browsers don't care because Content-Type is `image/png`. If you sniff bytes, expect JPEG.

## Cost

Each `image:` in the spec costs ~$0.13 in Gemini API spend. Watch your spec sizes — submitting a Shape B with 8 images = ~$1 per job. Bills hit Anthony's Anthropic/Google account; track your usage by `project_slug`.

## Examples

**Minimum viable curl:**
```bash
BASE_URL=http://cypherclaw-ts:9000
KEY=your-bearer-token

# 1. Submit
JOB=$(curl -s -X POST $BASE_URL/api/v1/jobs \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"project_slug":"smoke","spec_yaml":"prompt: A red apple\nsize: 1024x1024\n"}')
JOB_ID=$(echo $JOB | jq -r .job_id)

# 2. Poll
while true; do
  STATUS=$(curl -s $BASE_URL/api/v1/jobs/$JOB_ID \
    -H "Authorization: Bearer $KEY" | jq -r .status)
  echo "$STATUS"
  case $STATUS in completed|failed) break;; esac
  sleep 3
done

# 3. Fetch
curl -s $BASE_URL/api/v1/jobs/$JOB_ID \
  -H "Authorization: Bearer $KEY" | jq -r '.output_urls[]'
```

**Python (httpx):**
```python
import httpx, time

BASE = "http://cypherclaw-ts:9000"
KEY  = "your-bearer-token"
HDRS = {"Authorization": f"Bearer {KEY}"}

# Submit
r = httpx.post(f"{BASE}/api/v1/jobs", json={
    "project_slug": "demo",
    "spec_yaml": "prompt: A red apple\nsize: 1024x1024\n",
}, headers=HDRS)
r.raise_for_status()
job_id = r.json()["job_id"]

# Poll
while True:
    r = httpx.get(f"{BASE}/api/v1/jobs/{job_id}", headers=HDRS)
    job = r.json()
    if job["status"] in ("completed", "failed"):
        break
    time.sleep(3)

assert job["status"] == "completed", job["error"]
print(job["output_urls"])
```

## Live API explorer

Swagger UI is auto-generated and lives at the same base URL: `http://cypherclaw-ts:9000/docs`. It accepts the bearer token via the "Authorize" button at the top right.

Machine-readable OpenAPI spec: `http://cypherclaw-ts:9000/openapi.json` — import this into Postman, Insomnia, or your code-gen tool.

## Operational contacts

- Owner: Anthony (anthony@cascadiantech.com)
- Repo: `cypherclaw/src/cypherclaw/image_api/` (this contract)
- Service: `cypherclaw-image-api.service` on the cypherclaw host
- Logs: `journalctl -u cypherclaw-image-api -f`
