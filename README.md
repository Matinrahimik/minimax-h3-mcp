"""HomeBooks MiniMax H3 / H3-Max video MCP (official V2 API).

Private stdio MCP for **MiniMax-H3** and **MiniMax-H3-Max**. It talks only to the
official V2 endpoints. It does **not** wrap or replace the Hailuo `minimax-mcp`
package (T2V-01 / I2V-01).

No paid generate until Matin asks. Unit tests mock HTTP only.

## Official API

- Create: https://platform.minimax.io/docs/api-reference/video-generation-v2-create
- Query: https://platform.minimax.io/docs/api-reference/video-generation-v2-query
- Host: `https://api.minimax.io` (override with `MINIMAX_API_HOST`)

```
POST /v2/video_generation
Authorization: Bearer $MINIMAX_API_KEY
Content-Type: application/json
```

```
GET /v2/query/video_generation/{task_id}
```

Statuses: `queued` | `running` | `succeeded` | `failed` | `cancelled`.

On succeeded, `task.content.url` is time-limited. `minimax_h3_wait_for_video`
downloads the mp4 to `/workspace/minimax-h3-output/`.

## Model capabilities

| | MiniMax-H3 | MiniMax-H3-Max |
| --- | --- | --- |
| Modes | T2V, I2V first/last frame, reference-to-video | T2V + I2V first/last **only** (no `reference_image` / `reference_video` / `reference_audio`) |
| resolution | `768P` \| `2K` | `480P` \| `768P` (no `2K`; default `768P`) |
| duration | 4–15 s | 5–15 s (no 4) |

### content[]

Must include one non-empty `text` (max 7000 characters).

- `type`: `text` | `image_url` | `video_url` | `audio_url`
- `image_url` / `video_url` / `audio_url`: `{ "url": "..." }`
- `role`: `first_frame` | `last_frame` | `reference_image` | `reference_video` | `reference_audio`

I2V (`first_frame` / `last_frame`) and reference (`reference_*`) cannot be mixed.

Limits (documented and count-validated; remote clip duration is enforced by MiniMax):

- Image: first ≤ 1, last ≤ 1, `reference_image` ≤ 9; JPG/JPEG/PNG/WEBP/HEIC/HEIF; ≤ 30 MB
- Video (reference only): ≤ 3 clips, per-clip 2–15 s, total ≤ 15 s; ≤ 50 MB; mp4/mov
- Audio (reference only): ≤ 3 clips, per-clip 2–15 s, total ≤ 15 s; ≤ 15 MB; wav/mp3
- Total request body ≤ 64 MB

### Ratio

- T2V (text only): `ratio` **required**, cannot be `adaptive`
- I2V: ratio is always adaptive (other values ignored)
- R2V: ratio optional, default `adaptive`
- Values: `adaptive` | `21:9` | `16:9` | `4:3` | `1:1` | `3:4` | `9:16`

Optional create field: `callback_url`.

## MCP tools

1. `minimax_h3_create_video` — official create surface; rejects illegal combos; returns `task_id`
2. `minimax_h3_get_task` — `task_id` → status + usage + url
3. `minimax_h3_wait_for_video` — poll ~12s until terminal, download mp4, return path + usage

## Local install (HomeBooks box)

Target: `/home/box/mcp-servers/minimax-h3/`

```bash
cd /home/box/mcp-servers/minimax-h3
python3 -m venv .venv
.venv/bin/pip install -e .
```

### AddMcpServer

```json
{
  "name": "minimax-h3",
  "command": "/home/box/mcp-servers/minimax-h3/.venv/bin/python",
  "args": ["/home/box/mcp-servers/minimax-h3/run.py"]
}
```

`run.py` loads secrets into the environment, then execs the stdio server. It does
**not** hardcode an agent id.

### Secret resolution

1. `MINIMAX_API_KEY` env
2. `/home/box/agent-data/connector-secrets/<id>/minimax.json` if `MINIMAX_AGENT_ID` is set (field `api_key`)
3. any `.../connector-secrets/*/minimax.json` with `api_key`

PAYG MiniMax key file shape: `{"api_key":"..."}`.

Optional: `MINIMAX_API_HOST` (default `https://api.minimax.io`),
`MINIMAX_H3_OUTPUT_DIR` (default `/workspace/minimax-h3-output`).

Set `MINIMAX_H3_TEST_MODE=1` to refuse live HTTP unless an httpx client is injected.

## Tests

```bash
MINIMAX_H3_TEST_MODE=1 python -m pytest
```

HTTP is mocked. Tests never call paid generate.
