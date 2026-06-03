# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the project

**With Docker (full stack):**
```bash
docker compose up -d          # start UI + scheduler
docker compose run --rm guild-tracker  # manually trigger a data collection run
```

**Locally (Nix shell):**
```bash
nix-shell                     # enter dev environment with all dependencies
HYPIXEL_API_KEY=<key> DB_NAME=data/guild_data.db python guild_stats.py
DB_NAME=data/guild_data.db streamlit run search_ui.py
```

The `.env` file (gitignored) must contain `HYPIXEL_API_KEY`. `DB_NAME` defaults to `/app/data/guild_data.db` (Docker path) so must be overridden when running locally.

## Architecture

Three scripts share a single SQLite database (`data/guild_data.db`):

- **`guild_stats.py`** — hourly data collector. Fetches guild member list from Hypixel (`/v2/guild`), logs GEXP, then fetches each member's SkyBlock profiles (`/v2/skyblock/profiles`) for skill and catacombs XP. Scheduled via [Ofelia](https://github.com/mcuadros/ofelia) labels on the `guild-tracker` Docker container (`@hourly`).
- **`search_ui.py`** — Streamlit dashboard. Reads from the DB only; never writes except for `CREATE TABLE IF NOT EXISTS` guards on startup.
- **`backfill_gexp.py`** — one-off script to backfill historical GEXP from Hypixel's 7-day `expHistory` field.

## Database schema

- `players` — uuid → username mapping, populated lazily via Mojang API on first encounter.
- `hourly_gexp` — one row per (uuid, hour) with that hour's GEXP snapshot. `UNIQUE(uuid, hour)`, inserted with `INSERT OR IGNORE`.
- `skyblock_stats` — one row per (uuid, profile_id, date) with XP for 9 skills + catacombs. `is_selected=1` marks the player's active profile. Leaderboard and event queries filter on `is_selected=1`.

## Key API details

- Hypixel API key goes in the `Api-Key` header (not a query param).
- SkyBlock skill XP lives at `profiles[].members[uuid].player_data.experience.SKILL_<NAME>` (e.g. `SKILL_FARMING`).
- Catacombs XP lives at `profiles[].members[uuid].dungeons.dungeon_types.catacombs.experience`.
- Active profile is `profiles[].selected == true`; always fall back to `profiles[0]` if none is marked selected.
- Rate limit: 0.5s sleep between per-member SkyBlock calls; 10s sleep on HTTP 429.
