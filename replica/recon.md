# Chameleon: combined-product reconnaissance

Date: 2026-10-07
Platform: responsive web application.
Scope selected by the user: unified studio plus creator tools.
Audience selected by the user: personal/business use, creators and small marketing teams, and agencies.
Status: research deliverable and proposed scope, not an approved implementation specification.

## Executive recommendation

Build an original project-centric creative studio: brief -> script and scenes -> presenter and generated visuals -> captions and edit -> export.

The opportunity is continuity between tools, not reproducing two websites. A generated image should become a scene, an animated clip should retain its source settings, and a finished project should support multiple output formats without starting over.

Support all three audiences through the same project foundation. Recommend proving the individual/creator workflow first, then adding team review and agency client workspaces. This ordering is a proposal, not a user-approved limitation.

## Research boundaries and legal gate

- Only public pages and official documentation were inspected. No accounts were created, credentials requested, paid generations submitted, private APIs inspected, or JavaScript bundles downloaded.
- HeyGen's public terms prohibit using its services to build competitive products or similar functionality, as well as reverse engineering and copying proprietary content. Further HeyGen inspection stopped when that restriction was discovered. Earlier observations below are factual summaries, not permission to replicate the service. Do not select HeyGen as a provider without legal review and appropriate written authorization.
- Magic Hour's terms prohibit copying its platform/content and replicating proprietary models. They explicitly permit supported API integrations in original products, including features offered to paying end users, subject to the terms and commercial-use requirements.
- Neither competitor's branding, copy, stock avatars, templates, demos, model weights, or generated samples may be shipped in Chameleon.
- Legal/commercial approval of each provider is a launch prerequisite. This report is not legal advice.
- No sensitive local data or user assets were submitted to third-party systems.

## Sources

IDs below are used as evidence references throughout this report. All observations are dated above; prices and availability can change.

| ID | Source | URL | Evidence / limitation |
| --- | --- | --- | --- |
| R01 | HeyGen public homepage | https://www.heygen.com/ | Avatar identity consistency, script-driven studio, video agent, collaboration, translation, and verification are advertised; not generation-tested. |
| R02 | HeyGen public pricing | https://www.heygen.com/pricing | Individual Free, Creator, and Pro plans inspected. Business tab not successfully explored. |
| R03 | HeyGen terms | https://www.heygen.com/terms | Explicit competitive-use and copying restrictions; gate on further replication/provider use. |
| R04 | Magic Hour public homepage | https://magichour.ai/ | Outcome-oriented entry points, video/image/audio categories, templates, and free-start messaging. Marketing claims are not independently audited. |
| R05 | Magic Hour public pricing | https://magichour.ai/pricing | Annual cards and credit packs observed. Monthly toggle interaction timed out; monthly prices corroborated by R11. |
| R06 | Talking-photo tool | https://magichour.ai/create/ai-talking-photo | Public empty form: image, audio, mode, resolution, optional prompt, generation CTA. |
| R07 | Image-to-video tool | https://magichour.ai/create/image-to-video | Public empty form: starting image, frame/keyframe controls, model, duration, resolution, audio, credit estimate. |
| R08 | Image-generation tool | https://magichour.ai/create/ai-image-generator | Public empty form: prompt, references, aspect/style/size, model, image count, credit estimate. |
| R09 | Magic Hour documentation | https://docs.magichour.ai/introduction | Web/API distinction; shared library; image, video, audio tools and SDKs documented. |
| R10 | Magic Hour API overview | https://docs.magichour.ai/api-reference/overview | Documented media projects, uploads, voice tools, translation, captions, and details endpoints. Documentation is not an executed API test. |
| R11 | Magic Hour billing documentation | https://docs.magichour.ai/billing/overview | Monthly/annual prices, credit amounts, commercial rights, and web/API concurrency distinctions. |
| R12 | Magic Hour integration lifecycle | https://docs.magichour.ai/integration/overview | Async jobs, polling/webhooks, terminal states, temporary result URLs documented. |
| R13 | Magic Hour terms | https://magichour.ai/terms-of-service | Paid commercial-use arrangements, supported integration permission, likeness rights, platform-copying restrictions. |

### Evidence quality and gaps

- Observed: public layouts, labels, fields, disabled controls, displayed default values, links, and pricing cards.
- Documented: official descriptions and API capabilities; not proof of output quality, latency, reliability, or plan entitlement for every model.
- Advertised: HeyGen's presenter realism, identity consistency, translation quality, collaboration, and ethical safeguards. Treat these as vendor claims.
- Proposed: every Chameleon screen, schema field, workflow, acceptance criterion, and differentiator below.
- The initial HeyGen homepage request failed; a subsequent navigation rendered public text. Visual media loaded incompletely.
- Several Magic Hour clicks timed out; image prompts appeared disabled in the observed session. The reason was not established. No authentication restriction is inferred from that alone.
- Authenticated editors, completed generation, library contents, actual checkout, team collaboration, errors, mobile behavior, and downloaded results were not tested.
- Marketing pages and public documentation were examined, not independent reviews or benchmarks. No comparative quality winner is claimed.
- No durable reference screenshots are included. A transient HeyGen viewport capture had incomplete rendering and is not suitable for visual acceptance testing.
- Workspace initially contained project instructions but no application implementation or Git repository. No runtime was built or deployed.

## Feature comparison: what is actually supported by evidence

| Capability | HeyGen evidence | Magic Hour evidence | Original Chameleon direction |
| --- | --- | --- | --- |
| Presenter/avatar video | Core marketing focus; Avatar V advertised on homepage | Talking-photo form observed; audio-to-video and lip-sync documented | Presenter scene type using a separately approved provider; consent required |
| Script-first creation | Script-driven AI Studio and editable video agent advertised | Talking-photo guide says script, but current form takes audio | Script -> approved TTS -> presenter clip; keep source text editable |
| Image generation/editing | Not deeply verified in this pass | Public image form plus editing/upscaling/background tools documented | Generate or edit reusable project assets |
| Text/image-to-video | Advertised video tools; depth not tested | Public image-to-video form; text/video transformations documented | Generated B-roll inserted into the same project |
| Translation and dubbing | 175+ languages/dialects advertised; script proofreading listed on Pro pricing | Video translation endpoint documented; language coverage not verified | Localized project variants, gated on language/provider evaluation |
| Captions | Auto captions advertised | Auto subtitle generation documented | Editable transcript, styled captions, and subtitle download |
| Brand/team workflow | Brand kit, comments, tagging, multi-user editing advertised | Teams positioning; actual review workflow not inspected | Brand presets and review roles; real-time editing deferred |
| Discovery/onboarding | Presenter-focused call to action | Task-oriented free starts and tool navigation observed | Guided choices: presenter, cinematic clip, image, or complete project |
| Usage transparency | Individual paid plans display credits | Model/settings-dependent credits and visible estimates | Quote before submit; explicit reservation and settlement history |
| Developer integration | Public developer portal exists; not approved for this use | Async API and SDKs documented; supported integrations permitted by terms | Backend-only adapter; UI never receives provider credentials |

The sites already overlap substantially. The proposed differentiator is editable, traceable project assembly and reliable workflow continuity, not a claim that either competitor lacks these capabilities.

## Pricing observations

USD list prices observed/documented, excluding tax; checkout was not tested.

| Product / plan | Monthly | Annual billing | Usage and conditions |
| --- | --- | --- | --- |
| HeyGen Free | $0 | Not inspected | Pricing lists 3 videos/month, up to 1 minute, 1 custom video avatar, and 30+ languages. |
| HeyGen Creator | $29 | Not inspected | 600 credits; up to 30-minute videos, 1080p, watermark removal, voice cloning, and 175+ languages/dialects listed. |
| HeyGen Pro | $49 starting display | Not inspected | 1,000-credit selected option; 4K and translation proofreading listed. Not all usage options inspected. |
| Magic Hour Creator | $19 | $144/year; $12/month equivalent | 12,000 credits/month equivalent; annual card shows 144K credits/year. |
| Magic Hour Pro | $39 starting tier | $300/year; $25/month equivalent | 25,000 credits/month equivalent; annual selected tier shows 300K/year. Higher credit tiers available. |
| Magic Hour Business | $99 starting tier | $792/year; $66/month equivalent | 70,000 credits/month equivalent; annual selected tier shows 840K/year. Higher credit tiers available. |
| Magic Hour credit packs | One-time | Not applicable | Observed $10/4,000, $30/12,000, $80/32,000 credits. Active offers can change. |

Magic Hour's documentation says prepaid subscription/pack credits do not expire. Paid subscriptions, packs, or separately agreed paid usage-based billing permit commercial assets subject to content rights. A pack does not unlock every subscription-gated model, resolution, upload limit, or web concurrency benefit. API generation is not governed by the web concurrency limits, but provider queueing still applies.

Do not compare competitors' credit numbers directly: their units and per-model costs differ. Do not set Chameleon retail prices until measuring cost per accepted output, retries, storage, egress, and rendering. Do not promise unlimited generation.

## Reference screen inventory

These are reference surfaces, not proposed Chameleon routes.

| ID | Screen | Route/source | Purpose | Key components | States actually seen |
| --- | --- | --- | --- | --- | --- |
| S01 | HeyGen landing | R01 | Explain presenter-first offering | Hero, product sections, CTA, trust signals | Public text; incomplete visual rendering |
| S02 | HeyGen individual pricing | R02 | Compare entitlements | Plan cards, billing controls, feature table | Free/Creator/Pro monthly display |
| S03 | Magic Hour landing | R04 | Discover generation tasks | Category nav, outcome cards, demos, templates promotion | Public loaded content |
| S04 | Magic Hour pricing | R05 | Choose credit/plan arrangement | Annual cards, tier options, credit packs | Annual/default selection; toggle timeout |
| S05 | Magic Hour talking photo | R06 | Animate portrait with speech | Image/audio inputs, mode/resolution selects, optional prompt | Empty form; Expressive mode, 480p; interaction timeout |
| S06 | Magic Hour image-to-video | R07 | Animate supplied image | Start/end frames, keyframes, prompt, model/settings, audio switch | Empty form; disabled prompt; displayed 3s/480p and 72-credit estimate |
| S07 | Magic Hour image generation | R08 | Generate images | Prompt/reference controls, aspect/style/size, model/count, intro panel | Empty form; disabled prompt; 9:16, 640px, two-image 10-credit CTA |
| S08 | Magic Hour developer docs | R09-R12 | Explain API integration | Docs navigation, media reference, job lifecycle, billing | Public documentation |

Terms pages are recorded as sources, not creative-product screens. Displayed estimates are contextual snapshots, not universal model prices.

## Proposed Chameleon screen map

Original routes and UX proposals; none of these have been implemented.

| ID | Screen | Proposed route | Main components | Required states |
| --- | --- | --- | --- | --- |
| C01 | Product landing | `/` | Original messaging, examples, outcome CTA | Desktop/mobile, media fallback |
| C02 | Pricing | `/pricing` | Plans, estimated usage, restrictions | Loading, billing period, unavailable checkout |
| C03 | Sign in / register | `/auth` | Account forms, recovery link | Invalid credentials, verification, rate-limited |
| C04 | Workspace home | `/app` | Recent projects, task shortcuts, workspace switch | Empty, loading, populated, denied |
| C05 | Create project | `/app/projects/new` | Brief, format, starting mode | Validating, saved draft, invalid input |
| C06 | Studio | `/app/projects/:id/studio` | Scene list, preview, script, properties, generation drawer | Draft, saving, conflict, asset unavailable |
| C07 | Asset library | `/app/assets` | Search/filter/grid, upload | Empty, upload/scan failure, denied |
| C08 | Image generator | `/app/tools/image` | Prompt, references, capability settings | Invalid, estimated cost, queued, failure, result |
| C09 | Image editor | `/app/tools/image-edit` | Asset and instruction, result comparison | Missing asset, unsupported settings, result |
| C10 | Video generator | `/app/tools/video` | Text/image modes, motion/settings | Invalid media, quoted, queued, failed, complete |
| C11 | Presenter creator | `/app/tools/presenter` | Approved portrait, script/voice, consent | Consent missing, preview, queued, failed, complete |
| C12 | Lip-sync tool | `/app/tools/lip-sync` | Video/audio selection, settings | Duration mismatch, moderation, results |
| C13 | Voice and audio | `/app/audio` | Approved voices, script, audio upload | Unsupported language, estimate, preview, error |
| C14 | Generation detail | `/app/jobs/:id` | Honest state, inputs, cost, result actions | Queued, processing, complete, error, canceled |
| C15 | Captions | `/app/projects/:id/captions` | Transcript editor, timing, styles | Processing, editable, overlap/invalid timing |
| C16 | Localization | `/app/projects/:id/localize` | Languages, script review, linked variants | Unsupported language, review needed, failed |
| C17 | Export setup | `/app/projects/:id/export` | Format, crop, quality, quote | Invalid settings, cost change, render queued |
| C18 | Export result | `/app/exports/:id` | Preview, download, expiry/re-render | Rendering, failed, ready, access revoked |
| C19 | Templates | `/app/templates` | Original/licensed templates and filters | Empty, preview, applying, missing entitlement |
| C20 | Brand kit | `/app/brand` | Licensed logo/fonts/colors, presets | Saving, invalid asset, access denied |
| C21 | Review | `/app/projects/:id/review` | Versioned preview, comments, approval | Pending, changes requested, approved, revoked |
| C22 | Workspace members | `/app/settings/members` | Invites and role controls | Pending invitation, expired, denied |
| C23 | Billing and usage | `/app/settings/billing` | Balance, immutable usage history, checkout | Pending/failed payment, exhausted credit |
| C24 | Agency clients | `/app/clients` | Client folders/workspaces, brand mapping | Empty, isolated clients, archived, denied |

First vertical slice: C01-C08, C10-C11, C13-C15, C17-C18, C23. Other screens are phased proposals, not necessary to prove the core loop.

## Flows

Reference click counts are incomplete because no generation was submitted. Counts below for Chameleon are proposed navigation/submit budgets, excluding typing, file selection, authentication, and waiting; they are not measured competitor baselines.

### F01 - Create a complete short video

C04 -> C05 -> C06 -> C17 -> C18.
Target: at most 6 primary actions from home to queued export using defaults.
Script and presenter/visual jobs are managed inside C06.
Edges: unsupported format, consent missing, generation failure, stale quote, export failure.

### F02 - Generate an image and reuse it

Reference: S03 links to S07; subsequent generation was not tested.
Proposal: C04 -> C08 -> C14 -> C06.
Target: at most 4 primary actions to queue an image and insert the completed asset.
Edges: invalid prompt, unsafe content, insufficient credits, partial multi-image results.

### F03 - Animate an image

Reference: S06 displays upload -> motion prompt -> generate, but clicks were not completed.
Proposal: C07 -> C10 -> C14 -> C06.
Target: at most 4 primary actions with a saved asset.
Edges: unsupported start/end/reference combination, corrupt image, duration/resolution mismatch.

### F04 - Create a talking presenter

Reference: S05 has photo/audio inputs; guide describes script, but script input was not observed.
Proposal: C11 -> C13 within presenter workflow -> C14 -> C06.
Target: at most 5 primary actions after consent and voice selection.
Edges: missing/revoked consent, unsupported language, speech duration too long, unsafe likeness use.

### F05 - Caption and export to social formats

C06 -> C15 -> C17 -> C18.
Target: at most 4 primary actions after transcript review.
Edges: caption timing errors, crop cutting off presenter/text, missing font license, failed render.

### F06 - Create a localized variant

C06 -> C16 -> C14 -> C15 -> C17 -> C18.
Target: at most 6 primary actions after translated-script review.
Edges: unsupported locale, changed speaking duration, dubbing drift, source-version change.

### F07 - Team/client review

C04 -> C24 when applicable -> C06 -> C21 -> C17.
Target: at most 5 navigation/submit actions, excluding asynchronous review.
Edges: reviewer cannot edit, expired invitation/link, revision after approval, client isolation.

### F08 - Recover a failed generation or exhausted balance

C14 -> C23 if needed -> C14 -> C06.
Target: at most 4 primary actions after explicit payment/quote confirmation.
Edges: duplicate payment/webhook, ambiguous provider timeout, retry cost, already completed job.

## Reusable components

| Component | Variants / behavior | Required states | Surfaces |
| --- | --- | --- | --- |
| App shell | Personal/team/client workspace, responsive navigation | Loading, access denied, mobile | C04-C24 |
| Task launcher | Presenter, image, video, complete project | Keyboard focus, capability unavailable | C04-C05 |
| Media uploader | Image/audio/video; existing library selection | Validating, upload, scanning, invalid/rejected | C07-C13 |
| Prompt/script editor | Creative prompt or timed spoken script | Dirty, saved, disabled with reason, error | C06, C08-C13 |
| Capability selector | Model, duration, resolution, format | Supported, incompatible, entitlement locked | C08-C13, C17 |
| Cost confirmation | Quote, reservation, balance | Changed price, expired quote, insufficient credit | C08-C14, C17, C23 |
| Job status card | Poll-backed state and explicit retry/cancel | Queued, processing, complete, error, canceled | C06-C18 |
| Asset card/grid | Media type, source/provenance, actions | Loading, unavailable, selected, denied | C04, C07-C14 |
| Scene list and preview | Presenter, generated clip, image, text/audio | Draft, saving, missing media, reorder | C06 |
| Consent panel | Likeness/voice purpose and rights confirmation | Missing, recorded, revoked, review needed | C11-C13 |
| Transcript editor | Word/timing edits, caption styling | Loading, invalid timing, unsaved | C15-C16 |
| Review controls | Comments tied to revision, approval | Pending, changes requested, obsolete approval | C21 |
| Notification | Actionable success/error, persistent job failure | Screen-reader announcement, dismiss/retry | All app screens |

## Inferred conceptual model

This is a proposed Chameleon model, not a reconstruction of either company's internal database. Entity confidence indicates strength of product need, not schema verification.

| Entity | Proposed fields | Evidence and confidence |
| --- | --- | --- |
| User | id, email, account_status | Public sign-in entry points R01/R04; high |
| Workspace | id, name, owner_id, kind | User's multi-audience scope and R01 team claims; medium |
| Membership | workspace_id, user_id, role, invitation_state | Required for team/client isolation; proposed, medium |
| Client | id, agency_workspace_id, name, client_workspace_id | User agency scope; proposed, medium |
| Project | id, workspace_id, title, status, format, revision | R09/R10 media-project concepts; high for concept |
| Scene | id, project_id, order, kind, script, timing, settings | R01 scene/script claims and unified workflow; proposed, medium |
| Asset | id, workspace_id, type, storage_key, metadata, provenance | R06-R10 inputs/results and shared library; high |
| GenerationJob | id, workspace_id, project_id, scene_id, provider, tool, provider_job_id, status, input_snapshot, error | R10/R12 async jobs; high |
| ConsentRecord | id, workspace_id, subject_ref, asset_id, purpose, evidence_key, recorded_at, revoked_at | R13 likeness responsibilities; proposed safeguard, high |
| VoiceProfile | id, workspace_id, provider_voice_ref, language, consent_id | R10 voice generator/cloner; medium |
| CaptionTrack | id, project_id, revision, language, segments, style | R10 subtitles and localization; medium |
| LocaleVariant | id, source_project_id, source_revision, language, translated_script, review_state | R10 translation plus proposed review; medium |
| BrandKit | id, workspace_id, logo_asset_id, colors, licensed_font_refs | R01 brand-kit claim and marketing workflow; medium |
| Template | id, owner_workspace_id, license_record, scene_schema, tags | R04 template marketing; original schema proposed, medium |
| Review | id, project_id, revision, author_id, timestamp, comment, decision | R01 collaboration claim; proposed versioning, medium |
| UsageLedgerEntry | id, workspace_id, job_id, external_event_id, kind, amount, quote_snapshot, created_at | R11 credit economy; proposed accounting, high |
| Export | id, project_id, revision, format, settings, status, output_asset_id, error | R12 result/download lifecycle; proposed assembly, high |

17 entities. Relationships: Workspace has memberships, projects, assets, brand kits, and usage entries; Project has ordered scenes, jobs, captions, locale variants, reviews, and exports. Scenes reference assets/jobs. Client links an agency workspace to an isolated client workspace. Every cross-workspace lookup must be authorized.

Snapshots and revision references preserve what produced each output. Provider result URLs are not durable asset storage: R12 documents 24-hour URLs. Copy only user-authorized generated results into controlled object storage with a retention policy.

## Feature matrix and phasing

See [features.csv](./features.csv): 18 must, 12 should, 6 could, and 4 skip rows.
All deliverable features start `clone=no`; excluded items use `clone=skip`. The column name is inherited from the recon format, not a permission to copy protected material.

1. Foundation and vertical slice: account/workspace isolation, owned uploads, image generation, presenter/voice integration, generated clips, scene assembly, captions, export, job recovery, usage accounting.
2. Creator depth: editing/upscaling/background tools, start/end references, lip sync, original templates, brand presets, multi-format export.
3. Team/agency workflow: invitations, versioned review, isolated client spaces, localized variants, batch operations.
4. Optional expansion after validation: developer API, automation, consented custom voices, advanced timeline/realtime functionality.

## Architecture constraints for the next phase

Honor the workspace stack: React + Vite + TypeScript, Tailwind, Zustand, React Router; Django 5 + DRF or FastAPI + SQLAlchemy/Alembic; PostgreSQL; Celery + Redis; Railway. Backend framework selection remains unapproved. Do not introduce Next.js, Vercel, or Supabase.

Use external licensed inference services behind backend adapters rather than attempting to reproduce proprietary models. Magic Hour is a documented integration candidate, not a tested/contracted dependency. Evaluate a presenter provider separately for identity consistency, supported locales, consent, retention, unit cost, and commercial license.

Railway hosts the app, API, workers, database, and Redis. Durable media storage and its region/retention need selection. Media assembly requires a separate worker capability and measured resource limits; third-party inference is not instantaneous frontend functionality.

Required controls: session/JWT auth, RBAC, CSRF where cookie authentication applies, TLS, parameterized database access, server-only environment secrets, workspace isolation, upload validation, controlled URL ingestion, per-user quotas, likeness/voice consent, explicit provider errors, idempotent job/billing events, and auditable usage.

## Three hardest parts and evaluation gates

1. Media quality and continuity: presenter realism, speech timing, identity consistency, generated B-roll, captions, crop, and output codecs. Benchmark licensed providers on the same authorized sample set; measure acceptance rate, lip-sync, latency, and cost per accepted output.
2. Reliable job and money lifecycle: async provider jobs, partial results, late/duplicate webhooks, ambiguous timeouts, credit reservation/settlement, and durable media storage. No blind paid retries or fictional percentage progress.
3. Editable assembly across tools: maintain scene/source revisions and selective regeneration without losing user edits. Localization and format variants must reference a specific source revision.

Proposed acceptance checks for a future implementation:

- A user completes F01 using actual provider results, reloads the project, edits one scene, and downloads a playable export.
- Supported first-slice formats are explicitly chosen and tested; proposed defaults are 9:16 and 16:9, up to 60 seconds, 1080p assembly where source entitlements allow. Provider limits take precedence and must be disclosed.
- Invalid settings/uploads, insufficient balance, provider rejection, timeout, and export failure produce actionable errors.
- Duplicate submissions/webhooks do not create duplicate local charges; ambiguous remote outcomes reconcile before retry.
- A revoked-consent asset cannot be newly generated or shared under that authorization.
- A user from workspace A cannot access workspace B's project, asset, job, signed download, or billing history.
- Python unittest covers jobs/accounting/authorization; Vitest covers form state and studio logic; Playwright covers the core workflow, failure recovery, persistence, and mobile navigation.

These are proposed checks, not tests run during this documentation-only recon.

## Out of scope

- Competitor visual replicas, branding, proprietary copy, avatar catalogs, templates, demos, model weights, private endpoints, and scraped media.
- Unauthorized impersonation, unconsented voice/face cloning, and abusive face swapping.
- Recreating proprietary foundation/avatar models or promising equivalent quality without evidence.
- Native mobile apps, a full professional NLE, live interactive avatars, simultaneous collaborative editing, and a public creator marketplace in the first release.
- Unverified "100+ tools", "all languages", "unlimited", instant generation, or enterprise-compliance claims.
- Selecting providers, purchasing credits, implementing billing, deploying, or building app code during this recon.

## Size and next step

8 reference screens; 24 proposed application screens; 8 proposed flows; 17 conceptual entities.
Full combined scope: XL, requiring staged delivery. A focused working vertical slice is L due to paid media integrations, assembly, authorization, and job/accounting reliability; this is complexity sizing, not a delivery-date commitment.

Next step: `/replica-architect` for an original Chameleon architecture and approved first-slice scope. Resolve backend framework, licensed providers, storage/retention, unit economics, export limits, and agency rollout before implementation.
