# Image-generation foundation: operator contract

This integration creates **one image**, not a cinematic storytelling system.
Presenter generation remains blocked. It makes no motion, character continuity,
voice-sync, or quality-parity claim.

## Bring your own private media

Uploading images or videos remains a first-class independent path: upload in
**Media assets**, select the private Asset for an image/video scene, then export.
No provider key, active generation tariff, quote, output-origin approval or
generation-storage confirmation is required for this workflow. Existing private
upload/storage configuration is still required. Owner/editor can upload and
create scenes/exports; reviewer/viewer access remains read-only.

The Asset list and scene picker distinguish **Uploaded**, **Generated**, and
**Source unknown** for legacy/unattributed Assets. Only this bounded source label
is public; detailed provenance, uploader identity and storage keys stay private.
Clients cannot forge source labels through upload fields.

Existing upload validation is retained: nonempty bytes, MIME/signature matching,
safe filenames, tenant ownership and a configurable 25 MiB default maximum.
Supported upload image signatures are PNG, JPEG, GIF and WebP, not arbitrary `image/*`
formats. Upload signature checks alone do not prove full image validity; export
also probes/decodes media. Controlled upload-to-export tests mock FFmpeg, so they
do not establish real binary/deployment decoding success.

Uploads are **not sent to Magic Hour**. Character/environment reference images
or image-to-video inputs are future product direction, not an implemented or
approved provider capability. Selecting an uploaded Asset for a scene does not
authorize its transmission to any external provider.

## Default: unavailable, no paid request

The repository does not approve production generation:

| Environment variable | Default | Operator responsibility |
| --- | --- | --- |
| `GENERATION_IMAGE_TARIFF` | `{}` | Verify the official fixed-tuple credit price; configure a versioned, time-bounded JSON tariff. |
| `GENERATION_DOWNLOAD_ORIGINS` | `[]` | Verify and authorize exact HTTPS output origins; no wildcards, paths, credentials, ports other than 443, or IP literals. |
| `GENERATION_STORAGE_CONFIRMED` | false | Verify durable **private** storage, API/worker visibility, backup and publication semantics. |
| `MAGIC_HOUR_API_KEY` | empty | Store credentials in operator-managed environment variables only. |

Malformed pricing/origin JSON fails closed. Approval to write this integration
does not approve these operator gates. Do not copy test credentials or test
tariffs into production.

An active tariff has these JSON fields: `enabled` (boolean), `version`,
`verified_by`, `verified_at`, `valid_until`, and `credits` (integer).
Version and verifier must be nonblank strings of at most 80 and 200 characters,
respectively.
Verification and validity timestamps must be timezone-aware, verification must
not be in the future, and validity must not have elapsed. Assign a new version
when re-verifying or changing a tariff. The implemented tariff accepts only the
currently documented **5-credit** tuple: `z-image-turbo`, `640px`, image count 1,
`general` tool. Ratios are `1:1`, `16:9`, and `9:16`. A changed price/model requires
deliberate contract/code review, not extrapolation from other resolutions.

### Official evidence

* [Image request parameters](https://docs.magichour.ai/api-reference/image-projects/ai-image-generator.md)
* [Models and starting credit prices](https://docs.magichour.ai/api-reference/models.md)
* [Billing overview](https://docs.magichour.ai/billing/overview.md)
* [Resolution/plan limits](https://docs.magichour.ai/billing/resolution-limits.md)
* [API index](https://docs.magichour.ai/api-reference/overview.md)
* [Documentation inventory](https://docs.magichour.ai/llms.txt)
* [Image details](https://docs.magichour.ai/api-reference/image-projects/get-image-details.md)
* [Output expiry and refresh](https://docs.magichour.ai/integration/inputs-and-outputs.md)

These sources were reviewed for the Task 7 proposal. No documented non-generating
per-request guaranteed quote endpoint was found. Five credits is the documented
starting price at the lowest supported resolution, **an estimate, not a maximum
or currency quote**. Generation is charged on creation. Reported actual credits
are post-submit, nullable when unavailable, and do not replace the accepted
estimate. Observed discrepancies disable quotations under the affected tariff
version until operator review. The example output host in documentation is not
an exhaustive download-origin authorization.

## Authenticated API and consent

All endpoints use existing authenticated sessions/CSRF and tenant membership.
Owner/editor can quote, submit, and retry saving; other members are read-only.
Foreign scope/quote/job identifiers are hidden with 404. Quote/submit accepts
canonical image inputs only, rejects unknown fields, and validates workspace,
project, and scene consistency.

* `GET /api/jobs/capabilities/?workspace_id=ID` reports authoritative availability,
  write capability, fixed parameters, and safe unavailable reasons.
* `POST /api/jobs/image-generation/quote/` accepts `workspace_id`, optional
  `project_id`/`scene_id`, `prompt`, optional `name`, and optional `aspect_ratio`.
  Defaults are canonicalized. Success returns `quote_id`, tenant/context,
  parameters, `estimated_credits`, `unit=provider_credits`, `pricing_version`,
  public evidence basis, issuance/expiry timestamps, and `price_guaranteed=false`.
  Unavailable pricing/storage/origins/provider configuration returns no quote.
* `POST /api/jobs/image-generation/` requires the identical inputs plus `quote_id`
  and bounded `Idempotency-Key`. A quote expires after at most five minutes or
  tariff validity, whichever is earlier. The server rejects expired, changed,
  foreign, or reused-conflicting contracts before starting generation.
* `GET /api/jobs/ID/` exposes curated state and only a verified same-workspace
  generated `asset_id`; never provider download URLs, signed tokens, local
  paths, raw provider errors/payloads, or internal provenance.
* `POST /api/jobs/ID/asset-ingestion/retry/` accepts no inputs and only resets an
  eligible transient save failure. It never submits generation.

The connected UI displays the server estimate, parameters, basis, version and
expiry before an explicit Generate click. Input/context/session changes invalidate
the quote. Late responses cannot restore an obsolete quote. Stale/change responses
require reviewing a fresh quote and another click; no automatic paid retry.
An unresolved attempt persists its exact request and key in browser session
storage. “Resolve existing attempt” reuses that identity instead of regenerating.
Storage failure prevents the UI from starting an untracked paid attempt.

Database membership/quote locks serialize acceptance and key reuse, and a consumed
quote resolves to its original job even after expiry/config changes. A consumed
quote remains consumed if its job is deleted. Worker dispatch rechecks current
requester authorization, scope and pricing before durably claiming a submission.
Revocation after that claim cannot cancel a request already in flight.

## Completion is not readiness

`status=completed` means the provider finished. Independently:
`asset_status=pending|ingesting|ready|failed` describes private saving. Only
`ready` and an owned generated Asset make a job usable in scenes/exports. The UI
keeps polling after provider completion, distinguishes saved/failed results, and
refreshes the Asset picker on readiness. Retry saving does not retry generation.

Ingestion fetches fresh details for the **existing** provider project; expired
signed URLs are refreshed through a details GET, not a paid POST. It only accepts
one provider-returned, unexpired output URL. Exact-origin authorization, public
A/AAAA validation, rejection of mixed unsafe answers and transition addresses,
one-time resolution, pinned TCP peer, original-hostname TLS, and a hard deadline
prevent redirection or DNS rebinding to private destinations. No redirects,
proxies, user credentials, or authorization forwarding are used.

Downloads stream in bounded chunks: at most 25 MiB or the upload cap if lower,
60 seconds total, bounded DNS/connect/idle waits, and strict content-length and
identity-encoding handling. PNG/JPEG/WebP must match existing signatures and MIME,
then pass file-only FFprobe/FFmpeg decoding with time, allocation, thread, format,
frame and dimension limits. Install and verify both binaries before approving
storage; their absence fails saving, not validation open.

Private publication uses existing storage/Asset helpers, requester/tenant
provenance, checksum verification, and a one-to-one generated Asset/job link.
Leases fence competing workers. Stored candidates are durably registered before
writes and can be checksum-verified/reused after a crash without provider access.
Candidate cleanup survives job/workspace deletion and does not delete adopted or
published files. Beat recovery processes pending work, expired leases and
unreferenced candidates. Run Celery worker **and beat**.

Railway API and worker services do not automatically share filesystems. Before
`GENERATION_STORAGE_CONFIRMED=true`, verify a genuinely durable private shared
storage topology, correct tenant reads, synchronous publication/checksum semantics,
bounded storage operations, restore behavior and deployment binary availability.
Do not expose `PRIVATE_MEDIA_ROOT` through a public static/media route.

## Recovery: never repeat a paid POST

Unknown paid-submission outcomes remain reconciliation-only. Check provider
history/support before using existing `reconcile_generation_job` to attach the
confirmed project or close local tracking. Polling exhaustion is resumed through
`poll_generation_jobs --resume-job ID`, not another submission. These operator
actions require independent authorization; none were exercised against a provider
while implementing this feature.

For transient saving failures, use the authenticated retry-save endpoint. For
policy/media/storage-confirmation failure, correct and verify configuration/media
first. An operator can schedule same-project saving with:

```powershell
Set-Location 'C:\Software Projects\Chameleon\backend'
& '<approved-python-executable>' manage.py recover_generated_asset JOB_ID --workspace-id WORKSPACE_ID --note 'Evidence of the reviewed correction'
```

This command requires a failed save for a completed image job, confirmed storage
and authorized origins, records a private evidence note, and schedules recovery
without a provider request. Beat later performs only saving/details GETs. Do not
include secrets or signed URLs in notes. `recover_ingestions` and
`recover_submission_dispatches` are also registered scheduled tasks; do not turn
their recoveries into blanket paid retries.

## Validation and deployment limits

Behavioral tests cover server gating/canonicalization/expiry/version/idempotency,
tenant/RBAC/public projection, revoked queued permissions, no paid retry,
SSRF/redirect/streaming bounds, refreshed outputs, lease/candidate recovery and
unique Assets. PostgreSQL-specific transactional tests verify real concurrency;
SQLite runs intentionally skip them. `CHAMELEON_TEST_DATABASE_URL` opts into an
explicit isolated PostgreSQL test database; do not point it at production.

Frontend validation: `npm --prefix 'frontend' run test -- --run`,
`run typecheck`, `run build`; mocked browser flow: `run test:e2e`.
Use `PLAYWRIGHT_CHANNEL=msedge` where an approved local Edge installation replaces
downloaded Chromium. The smoke mocks APIs; it proves browser flow, not a provider
or deployed-storage integration.

No paid calls, real provider output downloads, or operator activation were used
for implementation validation. Actual binary decoding, provider output origins,
tariff verification, storage topology, webhook configuration and a separately
authorized live/deployment acceptance check remain production prerequisites.
The detailed Task 7 fix2 report records exact suites, RED/GREEN evidence and
pre-existing full PostgreSQL-suite failures.
