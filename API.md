# TeleDigest API Reference

Base URL (local): `http://localhost:8000` (or the host/port where the FastAPI app runs).

All API routes are prefixed with `/api`.

---

## Tracks

### GET /api/tracks

Returns digest tracks, newest first, with cursor-based pagination.

**Query parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 20 | Page size (1–100). |
| `cursor` | string | No | — | Opaque cursor from the previous response’s `next_cursor` for the next page. |

**Response:** JSON object:

| Field | Type | Description |
|-------|------|-------------|
| `items` | array | List of track objects (see below). |
| `next_cursor` | string \| null | Cursor to request the next page; `null` if there are no more pages. |
| `has_more` | boolean | Whether more results exist after this page. |

Each element of `items` is a track object:

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Track ID. |
| `title` | string | Track title; when ready, the MP3 filename (e.g. `digest_2026-03-05_21-32_2.mp3`). |
| `channel_name` | string | Channel display name (from Telegram), or "Various channels" if digest uses more than one channel. |
| `channel_id` | integer \| null | Channel ID if track is for a single channel; `null` for full digest. |
| `status` | string | `"progress"` while generating; `"done"` when the MP3 is ready; `"no_content"` when generation ran but there were no new messages to digest (no MP3). |
| `file_url` | string \| null | URL path to the generated audio file (e.g. `/media/digest_xxx.mp3`). |
| `created_at` | string \| null | ISO 8601 datetime when the track was created. |
| `messages_start_at` | string \| null | ISO 8601 datetime of the oldest message in the digest. |
| `messages_end_at` | string \| null | ISO 8601 datetime of the newest message in the digest. |
| `digest_created_at` | string \| null | ISO 8601 datetime when the digest was generated. |
| `channels_used` | array \| null | List of channel display names used for this digest. |
| `transcript_url` | string \| null | URL path to the transcript text file (e.g. `/media/digest_xxx.txt`). |

**Examples:**

```bash
# First page (default limit 20)
curl -X GET "http://localhost:8000/api/tracks"

# Larger page
curl -X GET "http://localhost:8000/api/tracks?limit=50"

# Next page (use next_cursor from previous response)
curl -X GET "http://localhost:8000/api/tracks?limit=20&cursor=eyJjcmVhdGVkX2F0IjoiMjAyNi0wMy0wNi4uLiIsImlkIjoxMH0"
```

---

## Channels (CRUD)

### GET /api/channels

Returns all channels from the database, ordered by `sort_order` then `id`.

**Parameters:** None.

**Response:** JSON array of channel objects (same shape as a single channel below).

---

### GET /api/channels/{channel_id}

Returns a single channel's settings by ID.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `channel_id` | integer | ID of the channel. |

**Response:** One channel object. **404** if not found.

**Channel object fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Channel ID. |
| `username` | string | Telegram channel username (without `@`). |
| `display_name` | string \| null | Optional display name for the channel. |
| `message_limit` | integer \| null | Max number of messages to fetch for this channel. |
| `sort_order` | integer | Order for listing (lower = earlier). |
| `message_selection_mode` | string | `"last_n"` (default) or `"since_last_digest"`. |
| `last_digest_message_at` | string \| null | ISO 8601 UTC datetime of the last message included in a digest for this channel; `null` if never digested. |

**Examples:**

```bash
# List all channels
curl -X GET "http://localhost:8000/api/channels"

# Get a specific channel by ID (e.g. 2)
curl -X GET "http://localhost:8000/api/channels/2"
```

---

### POST /api/channels

Adds a new channel by Telegram username.

**Parameters:** Request body (JSON).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `username` | string | Yes | Telegram channel username (e.g. `"durov"`). Leading/trailing spaces are stripped. |
| `display_name` | string \| null | No | Optional display name. Default: `null`. |
| `message_limit` | integer \| null | No | Max messages to fetch. Default: `null` (use app default). |
| `sort_order` | integer | No | Sort order. Default: `0`. |
| `message_selection_mode` | string \| null | No | `"last_n"` or `"since_last_digest"`. Default: `"last_n"`. |

**Responses:**

- **200:** Channel created; response body is the channel object (same shape as GET /api/channels items).
- **400:** `username` is missing or empty.
- **409:** A channel with that `username` already exists.

**Example:**

```bash
curl -X POST "http://localhost:8000/api/channels" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "durov",
    "display_name": "Durov Channel",
    "message_limit": 50,
    "sort_order": 0,
    "message_selection_mode": "last_n"
  }'
```

Minimal example (only required field):

```bash
curl -X POST "http://localhost:8000/api/channels" \
  -H "Content-Type: application/json" \
  -d '{"username": "durov"}'
```

---

### PATCH /api/channels/{channel_id}

Updates an existing channel by ID. Only provided fields are updated.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `channel_id` | integer | ID of the channel to update. |

**Body parameters (all optional):**

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | string \| null | New Telegram username. Must be unique if provided. |
| `display_name` | string \| null | New display name. |
| `message_limit` | integer \| null | New message limit. |
| `sort_order` | integer \| null | New sort order. |
| `message_selection_mode` | string \| null | New mode: `"last_n"` or `"since_last_digest"`. |

**Responses:**

- **200:** Updated channel object (same shape as GET /api/channels).
- **404:** Channel not found.
- **409:** Another channel already has the given `username`.

**Example:**

```bash
curl -X PATCH "http://localhost:8000/api/channels/1" \
  -H "Content-Type: application/json" \
  -d '{
    "display_name": "Updated Name",
    "message_limit": 100,
    "message_selection_mode": "since_last_digest"
  }'
```

---

### DELETE /api/channels/{channel_id}

Removes a channel by ID.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `channel_id` | integer | ID of the channel to delete. |

**Responses:**

- **200:** `{"ok": true}`.
- **404:** Channel not found.

**Example:**

```bash
curl -X DELETE "http://localhost:8000/api/channels/1"
```

---

## Telegram

### GET /api/telegram/channels

Returns all channels and megagroups the configured Telegram account has access to. Used to discover channels to add via POST /api/channels.

**Parameters:** None.

**Requirements:** `TG_API_ID` and `TG_API_HASH` in `.env`, and a valid `anon.session` (Telethon session).

**Response:** JSON object with key `channels` — array of channel objects (structure depends on Telethon; typically includes identifiers and titles).

**Responses:**

- **200:** `{"channels": [...]}`.
- **502:** Telegram error (e.g. session invalid, network error).
- **503:** Telegram not configured (missing env vars).

**Example:**

```bash
curl -X GET "http://localhost:8000/api/telegram/channels"
```

---

## Generate

### POST /api/generate

Creates a new track with status `"progress"`, enqueues background generation (fetch messages, LLM digest, TTS), and returns the track ID immediately. When generation finishes, the track's status becomes `"done"` and `file_url` is set. The client can poll GET /api/tracks or the track resource to check status and `file_url`.

**Parameters:** Optional request body (JSON).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `channel_id` | integer \| null | No | If set, generation runs only for this channel (single-channel digest). If omitted or `null`, generation uses all channels in the DB (full digest). |

**Behavior:**

- With `channel_id`: that channel must exist; track is created for that channel only.
- Without `channel_id`: at least one channel must exist in the DB; otherwise 400.

**Responses:**

- **200:** `{"track_id": <integer>}`. Generation runs in the background.
- **400:** No channels in DB and no `channel_id` provided, or digest not possible.
- **404:** `channel_id` provided but channel not found.

**Example (full digest — all channels):**

```bash
curl -X POST "http://localhost:8000/api/generate" \
  -H "Content-Type: application/json"
```

With optional empty body:

```bash
curl -X POST "http://localhost:8000/api/generate" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Example (single-channel digest):**

```bash
curl -X POST "http://localhost:8000/api/generate" \
  -H "Content-Type: application/json" \
  -d '{"channel_id": 2}'
```

---

## Media (static)

Generated audio and transcript files are served under `/media/`. They are not part of the `/api` router but are used by the app.

- **Audio:** `GET /media/<filename>.mp3` — e.g. URL from `file_url` in a track.
- **Transcript:** `GET /media/<filename>.txt` — e.g. URL from `transcript_url` in a track.

**Example:**

```bash
curl -O "http://localhost:8000/media/digest_2026-03-05_21-32_2.mp3"
```
