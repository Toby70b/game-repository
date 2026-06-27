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

`pytest` from `lambdas/ddb_import` → **26 pass, 10 fail**. The failures are
**intentional** — each pins an outstanding bug below and turns green once fixed.

## Review comments — fixes to go green

| Failing test(s) | Bug | Fix |
|---|---|---|
| `test_aws_param_store::test_set_writes…`, `test_set_does_not_raise…` | `set_last_import_timestamp` always re-raises | Move the stray `raise` *inside* the `except` (`aws_param_store.py`). |
| `test_steam_api::test_single_page…`, `test_multi_page…`, `test_forwards_modified_since…` | `fetch_games` drops `modified_since` | Forward it: `get_app_list(key, last_appid=…, modified_since=modified_since)` (`steam_api.py`). |
| `test_steam_http_client::test_builds_url…`, `test_omits_last_appid…`, `test_returns_parsed_json` | `last_appid` became a required arg | Restore `last_appid: int \| None = None` (`steam_http_client.py`). |
| `test_steam_http_client::test_omits_if_modified_since_when_none` | `if_modified_since` always sent (even `None`) | Add it to `params` only when not `None`. |
| `test_game_import_service::test_writes_start_of_run_day_watermark…` | watermark written as `now()` | Use midnight UTC of the run day: `datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)` (`game_import_service.py`). |

## Outstanding (not covered by tests / not in scope of this change)

- **Handler wiring** — `ddb_import.py` must construct `AwsParamStore()` and pass `timestamp_store=…` to `GameImportService`, or the lambda `TypeError`s on cold start.
- **Terraform** — add the `LAST_MODIFIED_PARAM` env var, create the SSM parameter **`last_import_job_timestamp` seeded to `0`** (so the first run backfills), and grant `ssm:GetParameter` / `ssm:PutParameter`.
- **Type alignment** — the port types the timestamp as `str` while `AwsParamStore` uses `int`; the `%d` log lines also receive a `str`. Pick one type end-to-end.
- **Backstop** — keep an occasional `if_modified_since=0` full reconcile, since "publishing always bumps `last_modified`" is implied but not documented.
