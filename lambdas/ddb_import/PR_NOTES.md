# Incremental import via `if_modified_since` watermark

## Summary

Replaces the appid-ordering cursor — which left holes when a game's store page
went public out of appid order — with an `if_modified_since` watermark stored in
SSM. The write path is now an upsert, so a late-published or renamed game updates
its existing row instead of creating a duplicate.

## Changes vs `master`

| File | Change |
|---|---|
| `src/ports.py` | New `LastImportTimestampStore` port; `GameRepository` exposes `existing_titles` + `upsert_games`; `GameSource.fetch_games` takes `modified_since`. |
| `src/adapters/aws_param_store.py` | **New** SSM-backed watermark store (`get`/`set_last_import_timestamp`). |
| `src/adapters/dynamodb_repo.py` | Snapshot-based upsert: resolve the existing primary key or mint one; `existing_titles` exposes only titles (keeps `game_id` internal). |
| `src/adapters/steam_api.py`, `steam_http_client.py` | Thread `modified_since` through to the Steam call; pagination starts at `last_appid=None` and continues via the response. |
| `src/game_import_service.py` | Read the watermark, pass it as `modified_since`, do new/changed detection, write the new watermark on success. |
| `src/adapters/ddb_import.py` | Lambda handler wiring. |
| `tests/**` | Coverage for the param store, `modified_since` plumbing, upsert, and the service's timestamp behaviour. |

## Altitude / responsibilities

- **Service** decides *whether* and *what* to write (new or title-changed) and owns the watermark lifecycle (read at start, write on success).
- **Adapter** decides *how* — reuse the existing primary key or mint one — and the surrogate `game_id` never leaves persistence.
- **Domain `Game`** is unchanged (no primary key).

## Test status

`pytest` from `lambdas/ddb_import` → **31 pass, 5 fail**. The remaining failures
are all in `test_steam_http_client`.

## Review comments — fixes to go green

Earlier issues are **fixed**: the param-store stray `raise`, the dropped
`modified_since`, the `now()` watermark, and the handler wiring. What's left is
the `get_app_list` signature:

| Failing test(s) | Bug | Fix |
|---|---|---|
| `test_builds_url…`, `test_includes_last_appid_when_provided`, `test_omits_last_appid_when_none`, `test_returns_parsed_json` | `modified_since` is a required positional, so callers that omit it raise `TypeError` | Give it a default: `modified_since: str \| None = None`. |
| `test_omits_if_modified_since_when_none` | `if_modified_since` is added to `params` even when `None` (sent as the literal `"None"`) | Add it only when not `None`, like `last_appid`. |

## Outstanding (not covered by tests / not in scope of this change)

- **Terraform** — add the `LAST_MODIFIED_PARAM` env var, create the SSM parameter **`last_import_job_timestamp` seeded to `0`** (so the first run backfills), and grant `ssm:GetParameter` / `ssm:PutParameter`.
- **Type alignment** — the port types the timestamp as `str` while `AwsParamStore` uses `int`; the `%d` log lines also receive a `str`. Pick one type end-to-end.
- **Backstop** — keep an occasional `if_modified_since=0` full reconcile, since "publishing always bumps `last_modified`" is implied but not documented.
