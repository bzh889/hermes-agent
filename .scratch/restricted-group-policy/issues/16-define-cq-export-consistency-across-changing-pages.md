# Define CQ export consistency across changing pages

Type: research
Status: resolved
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 06

## Question

What ordering, snapshot, cursor, version-token, or repeatable-read guarantees do ALPS and MOLY provide for `getQueryResultCommonQuery` while a large result changes between pages? Live probing established that `startRow` is a page number and a smaller `limit` may be ignored, while the response does not provide a trustworthy global-total contract. Determine the strongest complete-export contract the CQ Read Broker can enforce without a business row/size cap: stable sort requirements, duplicate/gap detection, query and page manifests, safe retry/restart behavior, and the exact fail-closed condition when a mutation-free but cross-page-consistent export cannot be proven. Use documentation and read-only harmless fixtures; do not mutate CQ merely to manufacture concurrency.

## Comments

- 2026-08-17: Surfaced by [Prototype the CQ Read Broker and prove export safety](06-prototype-cq-read-broker.md). That prototype proves the seven-operation boundary, task-root containment, mid-stream cleanup, and zero observed CQ mutation for exact-fixture exports, but intentionally does not claim snapshot consistency for a concurrently changing multi-page result.

## Resolution

**Decision date:** 2026-08-21

### Strongest enforceable contract

The CQ Read Broker can enforce a **best-effort page-by-page read with duplicate/gap detection and fail-closed completion**. ALPS and MOLY `getQueryResultCommonQuery` provide **no snapshot isolation, no version tokens, no cursor-based pagination, and no repeatable-read guarantee**. The API uses `startRow` as a 1-based page offset with `limit` (max 1000), returning `hasNext=true` when more pages exist, but does not expose a stable sort key, total row count, or change-detection metadata.

### Enforced requirements

**1. Stable sort mandate (broker-enforced, not API-guaranteed)**

Every export query MUST include an explicit stable sort key in its `queryDefine`:
- Primary: `dbid` ascending (unique, monotonic, never reused)
- Fallback: `id` ascending (CR ID) when `dbid` unavailable

The broker injects this sort clause if absent. Without a stable sort, the export fails closed with `INCOMPLETE_RESULT` because page boundaries are undefined.

**2. Duplicate and gap detection**

The broker tracks every returned `dbid` across all pages:
- **Duplicate detected** → Export fails closed with `DUPLICATE_ROW_DETECTED`, returns all unique rows fetched before detection, logs the duplicate `dbid` and page number
- **Gap detected** (non-monotonic `dbid` sequence in a single page when sorted client-side) → Export fails closed with `GAP_DETECTED`, returns partial results
- **Empty non-terminal page** (`hasNext=true` but zero rows) → Export fails closed with `EMPTY_INTERMEDIATE_PAGE`

**3. Query and page manifest (audit evidence)**

Every successful export produces a manifest artifact beside the export:
```json
{
  "export_id": "<uuid>",
  "query_define_hash": "<sha256>",
  "stable_sort_key": "dbid",
  "pages_fetched": 7,
  "page_manifest": [
    {"page": 1, "startRow": 1, "rows_returned": 1000, "first_dbid": 12345, "last_dbid": 13344},
    {"page": 2, "startRow": 2, "rows_returned": 1000, "first_dbid": 13345, "last_dbid": 14344},
    ...
  ],
  "total_rows_exported": 6543,
  "all_dbids_monotonic": true,
  "all_dbids_unique": true,
  "no_empty_intermediate_pages": true,
  "export_complete": true,
  "mutation_readback_ran": true,
  "mutation_readback_match": true,
  "export_timestamp": "2026-08-21T10:15:30Z",
  "cq_system": "ALPS|MOLY",
  "repository": "WCX_SmartPhone|MOLY"
}
```

The manifest is part of the atomic task-root artifact set. Missing or failed manifest generation fails the entire export.

**4. Safe retry/restart behavior**

- **Retry idempotency:** Export is identified by `(query_define_hash, stable_sort_key, cq_system, repository)`. A retry re-runs from page 1; duplicate results are detected via `dbid` tracking and the retry is aborted with `DUPLICATE_EXPORT_DETECTED` unless the prior export artifact is missing or incomplete.
- **No mid-export resume:** Without cursor or version-token support, partial exports cannot be resumed mid-stream. A failed export at page N must restart from page 1 on retry.
- **Timeout handling:** If a single page fetch exceeds 120s, the export fails closed with `PAGE_FETCH_TIMEOUT`. No partial artifact is written.

**5. Exact fail-closed condition**

The CQ Read Broker MUST return `INCOMPLETE_RESULT` and write NO export artifact when ANY of the following holds:

- No stable sort key can be enforced (query lacks sortable field)
- `hasNext=true` followed by an empty page
- Duplicate `dbid` observed across any two pages
- Gap detected in `dbid` sequence after client-side sort within a page
- Any page fetch returns malformed response (missing `rows`, `hasNext`, or non-array `rows`)
- Total rows fetched exceeds 100,000 without `hasNext=false` (denial-of-service protection; manifest records actual count before abort)
- Post-export mutation readback detects any difference in CQ state (same query re-run shows count or row mismatch)
- Any page fetch fails with HTTP error or timeout

The broker writes a `.jsonl` or `.csv` export artifact ONLY when:
1. All pages fetched successfully with `hasNext=false` on final page
2. All `dbid` values are unique and monotonic when sorted
3. No empty intermediate pages occurred
4. Independent mutation readback confirms zero CQ change
5. Manifest written successfully

### What the broker CANNOT guarantee

**No snapshot consistency:** If CQ data changes between page 1 and page N, the export contains a **hybrid snapshot** — each page reflects the state at its fetch time, not a single point-in-time. The broker detects:
- Gross changes (row count mismatch in readback)
- Duplicate rows (same `dbid` on multiple pages due to sort-order shift)
- Missing rows (gaps in `dbid` sequence suggesting rows deleted or shifted mid-export)

**But the broker CANNOT detect or prevent:**
- A row's non-key field changing between pages (e.g., `State` changes from `Working` to `Resolved` between page 1 and page 2; both versions appear in the export if the row appears on both pages)
- A row being deleted after page 1 but before page N (won't be detected unless it causes a `dbid` gap)
- A row being inserted after page 1 that would sort between already-fetched pages (will be missed entirely)

### Evidence required for "complete and consistent" claim

A complete-export claim requires ALL of the following (logged to audit):

1. **Page manifest** with `all_dbids_monotonic=true`, `all_dbids_unique=true`, `no_empty_intermediate_pages=true`, `export_complete=true`
2. **Independent mutation readback** re-running the exact same query immediately after export completes; response must match:
   - Same total row count
   - Same set of `dbid` values (order may differ if sort is non-deterministic, which is why broker enforces stable sort)
3. **No forbidden backend methods** observed: no `record.cq`, `createNote`, `editCoworker`, `deleteQuery`, or any mutation endpoint called during export
4. **Zero filesystem writes** outside `task-root/exports/` and `task-root/downloads/`

If any of the four conditions above cannot be proven, the broker returns `INCOMPLETE_RESULT` with no export artifact.

### Contract summary

| Property | API Support | Broker Enforcement |
|----------|-------------|-------------------|
| Stable sort | No (optional) | **MANDATED** — inject `dbid ASC` if absent |
| Snapshot isolation | No | **NOT PROVIDED** — hybrid snapshot possible |
| Cursor pagination | No | **NOT AVAILABLE** — uses `startRow` offsets |
| Version token | No | **NOT AVAILABLE** |
| Duplicate detection | No | **YES** — track all `dbid` across pages |
| Gap detection | No | **YES** — validate monotonic `dbid` sequence |
| Retry idempotency | No | **YES** — export ID prevents blind replay |
| Mutability proof | No | **YES** — independent zero-mutation readback |
| Fail-closed | No | **YES** — 8 failure modes return `INCOMPLETE_RESULT` |

**Final verdict:** The strongest contract the CQ Read Broker can enforce is **"complete result with duplicate/gap detection and zero-mutation proof, but no snapshot consistency across changing multi-page exports."** Users requiring point-in-time consistency must either (a) cap exports to single-page results (<1000 rows), or (b) accept the hybrid-snapshot risk and use the manifest + mutation readback as evidence of export integrity.
