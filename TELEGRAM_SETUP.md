# Why "Telegram token" doesn't work here

This app **does not use a bot token** (the kind you get from [@BotFather](https://t.me/BotFather)).  
It uses a **user account session**: you log in with your phone number and a one-time code, and Telethon saves that as a session file.

## What the app actually uses

| What            | Purpose |
|-----------------|--------|
| **TG_API_ID**   | From [my.telegram.org](https://my.telegram.org) → "API development tools". Required. |
| **TG_API_HASH**| Same place. Required. |
| **anon.session**| A **user** session file: created by logging in once with phone + code (and 2FA if you have it). |

There is no env var or config for a "bot token". A bot token cannot list "channels the user has access to" — that API requires a **user** session.

## Why you get 503 on GET /api/telegram/channels

1. **No `anon.session`**  
   The backend has never been logged in, or the session file is missing (e.g. not mounted in Docker).

2. **Session not authorized**  
   The file exists but is empty/expired/invalid. You need to log in again.

3. **Wrong working directory**  
   The backend looks for `anon.session` in its **current working directory**. If you run in Docker, that is usually `/app`. The login script must write the session in the same place the server reads it (run the script inside the container, or mount a volume so the host’s session file is visible at `/app/anon.session`).

## Fix: create a user session once

1. Ensure **TG_API_ID** and **TG_API_HASH** are set in `.env` (from [my.telegram.org](https://my.telegram.org)).
2. Run the login script so it creates **anon.session** in the same directory the backend uses:
   - **Local:** from backend root: `PYTHONPATH=. python -m scripts.telegram_login`
   - **Docker:** `docker exec -it teledigest python -m scripts.telegram_login`  
     The session is created inside the container. To keep it across rebuilds, add a volume in `docker-compose.yml` for the session (e.g. mount the backend dir or a path where `anon.session` is stored).
3. Restart the backend if it was already running. GET /api/telegram/channels should then return 200.

## If you only have a bot token

Bot tokens are for **bot** accounts. This app needs a **user** account session to list your channels and read messages. Use your own Telegram account (phone + code) via the login script; there is no way to substitute a bot token for that.
