# ContentPulse Implementation Audit Report

**Audit date:** 2026-10-05  
**Project:** ContentPulse  
**Scope:** Current repository implementation, workflow, storage, permissions, completed feature work, validation status, and remaining gaps.

## 1. Executive summary

ContentPulse currently implements an end-to-end content intelligence workflow:

> Authentication → workspace setup → organization knowledge → trend discovery → trend analysis → topic selection → content strategy → post generation → design production → approval → finalization → share preparation

The core product is implemented as a multi-tenant FastAPI and Next.js application. Organization-owned records are isolated through `organization_id`, role permissions are enforced on the backend, and significant workflow transitions are represented by explicit statuses and approval records.

### Overall status

| Area | Status | Summary |
|---|---|---|
| Authentication and sessions | Implemented | Local JWT authentication and Supabase Auth integration are supported |
| Organizations/workspaces | Implemented | Creation, settings, membership, invitations, RBAC, and admin deletion are present |
| Organization knowledge base | Implemented | Website crawling, extraction, chunking, search, embeddings, and manual documents are present |
| Trend discovery | Implemented | Source adapters, scheduled/manual discovery, normalization, clustering, deduplication, and scoring are present |
| Trend-to-organization analysis | Implemented | Rule-based and LLM-backed relevance analysis are supported |
| Topic management | Implemented | Shortlisting, rejection, platform recommendations, and strategy approval are present |
| Content generation | Implemented | AI/template generation, editing, versioning, regeneration, variants, and restore are present |
| Design workflow | Implemented | Briefs, designer tasks, signed uploads, creative versions, and submission are present |
| Approval workflow | Implemented | Version-specific approval rounds, comments, changes requested, rejection, approval, and finalization are present |
| Final-post sharing | Implemented with platform limitations | Native file sharing is supported where the browser/platform allows it; URL fallback copies text and opens the platform |
| Direct social publishing API | Not implemented | No OAuth publishing integrations or API-based posting are currently present |
| Workspace deletion | Implemented | Admin-only deletion removes creative objects and cascades organization data |
| Audit logging | Implemented | Organization changes and workflow actions are recorded |

## 2. Product workflow

### Stage 1: Authentication

Users authenticate through either:

- Local email/password authentication with application-issued JWT sessions.
- Supabase Auth when `AUTH_PROVIDER=supabase`.

The application keeps its own linked user record in PostgreSQL. Supabase stores the external authentication identity and session/password-related data when that provider is selected.

### Stage 2: Workspace and team setup

After authentication, a user creates or joins an organization. The organization becomes the active workspace used by organization-scoped API requests.

Workspace features include:

- Organization profile and brand settings.
- Services, products, and expertise.
- Target audience and tracked keywords.
- Platform playbook and platform-specific rules.
- Team invitations and membership management.
- Role assignment and member status management.
- Activity/audit history.

### Stage 3: Knowledge base

The organization can crawl its website or add documents manually. The knowledge pipeline:

1. Fetches pages through the crawler.
2. Extracts page content.
3. Splits content into heading-aware chunks.
4. Stores searchable chunks in PostgreSQL.
5. Optionally creates embeddings in pgvector.
6. Supports keyword and semantic retrieval for downstream analysis and content generation.

The knowledge base grounds relevance analysis and generated copy in the organization's actual services, audience, and brand information.

### Stage 4: Trend discovery

Trend discovery can be triggered manually or scheduled. Enabled source adapters produce normalized `RawTrendItem` records.

The trend pipeline in [`pipeline.py`](D:/ContentPulse/backend/app/services/trends/pipeline.py) performs:

1. **Normalization at the source boundary**  
   Source adapters provide a common item shape with title, topic, description, keywords, category, location, engagement, publication time, source URL, author, and raw source data.

2. **Clustering**  
   `cluster_items` groups related raw items into canonical trend clusters using tracked keywords and normalized keys.

3. **Matching to existing trends**  
   Existing organization trends seen within a 14-day match window are compared using exact keys and `similar_keys`.

4. **Trend creation or update**  
   A new canonical `Trend` is created when no match exists. Existing trends are updated with merged keywords and refreshed timestamps.

5. **Mention upsert**  
   Each source observation is stored as a `TrendMention`. Re-observing the same organization/source/item combination updates engagement, growth, raw data, and last-seen time instead of creating a duplicate.

6. **Growth calculation**  
   Engagement change is normalized by elapsed hours to produce a growth indicator.

7. **Rescoring**  
   Recently active trends are rescored using source diversity, engagement, growth, freshness, location, topic, keywords, and organization profile context.

8. **Persistence**  
   Trend aggregates are stored on `trends`; source-level observations are stored on `trend_mentions`; execution state is stored on `trend_discovery_runs`.

The result is an explainable trend record rather than a raw feed of unprocessed source items.

### Stage 5: Trend analysis and relevance

Users with trend/topic review permissions can analyze a trend against the organization. The analysis uses:

- Organization services and brand profile.
- Target audience and tracked keywords.
- Knowledge-base retrieval.
- LLM analysis when configured.
- A deterministic rule-based fallback when no LLM is configured.

The result includes relevance level, confidence, matched services, reasoning, content angles, and claims to avoid. A reviewer can override relevance and shortlist or reject the trend.

### Stage 6: Topic and strategy management

Relevant trends can become topic candidates. Content managers can:

- Review topic candidates.
- Shortlist or reject topics.
- Generate platform recommendations from the editable playbook.
- Create platform-specific content strategies.
- Edit strategy details.
- Approve or archive strategies.

The strategy is the bridge between a selected trend and a platform-specific post.

### Stage 7: Content generation

An approved strategy can generate a platform-specific post. Generation can use AI or a deterministic template fallback.

The content workflow supports:

- Hook, body, CTA, hashtags, and mentions.
- Knowledge-base-grounded copy.
- Brand and platform-rule checks.
- Manual editing.
- Regeneration with instructions.
- Variant creation.
- Version restoration.
- Immutable copy versions.
- Sending the post to design.

Every meaningful save or regeneration creates a new `PostVersion`; prior versions are retained for history and review traceability.

### Stage 8: Design workflow

Sending a post to design creates a design brief. The brief contains the post-derived creative direction and can be refined by AI when configured.

Designers can:

- View available design tasks.
- Accept or work on assigned tasks.
- Upload image, PDF, and video assets.
- Create new creative versions through each upload.
- Submit the finished creative for approval.

Creative file bytes are not stored in PostgreSQL. The database stores metadata and storage keys; the actual objects are stored in local storage by default or an S3-compatible backend when configured.

### Stage 9: Approval and finalization

The approval system records the exact copy version and creative version submitted for review.

The reviewer can:

- Approve.
- Request changes with comments and scope.
- Reject.
- Add comments.
- Finalize an approved submission.

`FINAL` is the approved and locked post state. Approval rounds preserve the history of the versions that were reviewed, preventing later edits from silently changing what was approved.

### Stage 10: Share preparation

Final posts show a Share action to users with `content.read`, including viewers and admins.

The share action:

- Assembles hook, body, CTA, and hashtags into a caption.
- Selects the creative version associated with the final approval round when available.
- Downloads signed creative URLs in browsers that support native file sharing.
- Uses the browser share sheet with text and files when supported.
- Otherwise copies the caption and opens the selected platform's composer or home page.

This is share preparation, not direct publishing. Social platforms do not uniformly allow a redirect URL to attach local or signed media files.

## 3. User roles and permissions

| Role | Main responsibility | Current capabilities |
|---|---|---|
| Admin | Owns workspace governance and final decisions | Full organization, team, knowledge, trends, topics, content, design, approval, finalization, sharing, and deletion access |
| Content manager | Converts intelligence into content | Reviews trends, manages topics, creates/approves strategies, generates and edits posts, comments on approvals |
| Designer | Produces visual assets | Reads content/design context, works on design tasks, uploads creatives, submits designs |
| Viewer | Consumes approved information | Read-only access to organization, knowledge, trends, topics, content, design, and approval data; can share finalized posts |

Backend permissions are authoritative. Frontend controls are only a usability layer and do not replace server-side authorization.

## 4. Storage architecture

### PostgreSQL and pgvector

PostgreSQL stores application data, including:

- Application users linked to authentication identities.
- Organizations and memberships.
- Brand profiles, services, audiences, and platform playbooks.
- Knowledge documents, pages, chunks, and embeddings.
- Trends and trend mentions.
- Trend discovery runs and source configuration.
- Relevance analyses and topic candidates.
- Content strategies.
- Posts and immutable post versions.
- Design briefs and creative metadata.
- Approval requests, rounds, comments, and decisions.
- Audit records.

### Supabase Auth

When enabled, Supabase Auth stores the external authentication identity and provider-managed authentication data. The application still keeps its linked user and organization membership records in PostgreSQL.

### Creative object storage

Creative media uses the storage abstraction in [`backend/app/storage/__init__.py`](D:/ContentPulse/backend/app/storage/__init__.py):

- Local signed storage is the default when `S3_BUCKET` is not configured.
- S3-compatible object storage is used when `S3_BUCKET` is configured.
- Uploads use short-lived signed targets.
- Downloads use short-lived signed URLs.
- Workspace deletion removes organization creative objects before deleting the organization record.

### Redis and workers

Redis is part of the application infrastructure for background work and scheduled processing. Long-running operations such as discovery, crawling, analysis, and generation are represented with queued/running/succeeded/failed job states.

## 5. Implemented feature audit

### Workspace deletion

Implemented behavior:

- Admin-only backend endpoint.
- Explicit role check in addition to organization membership.
- Confirmation dialog in Settings.
- Permanent-deletion warning.
- Loading and error states.
- Removal of organization creative files through the storage abstraction.
- Organization deletion with database cascades.
- Active organization cleanup.
- Query-cache cleanup.
- Redirect to onboarding after deletion.

### Proxy reset investigation

The reported `ECONNRESET` was investigated. The backend health endpoint returned `200`, and the unauthenticated trends sources endpoint returned the expected `401`, proving that the backend was responding.

The most likely causes were:

- Uvicorn reload/restart during a request.
- Startup timing.
- Database or Docker service restart.
- A stale browser request.
- A backend exception occurring before the proxy received a complete response.

No permanent code change was made because the failure did not reproduce as an active backend defect.

### Final-post sharing

Implemented behavior:

- Final-only Share button.
- Viewer and admin access through `content.read`.
- Caption assembly from the final copy.
- Creative selection tied to the approval round.
- Native Web Share API support when available.
- Platform-specific fallback URLs.
- Clipboard caption fallback.
- User-facing handling for missing copy/media and share cancellation.

Remaining limitation:

- There is no social OAuth integration or server-side publishing.
- Fallback platform behavior requires the user to attach media manually where the platform does not accept media through a URL.

## 6. State machines

### Trend states

`new → analyzed → shortlisted → archived`

Rejected trends can be restored to `new`.

### Topic states

`new → reviewed → shortlisted → archived`

Topics can also be rejected and restored according to the topic workflow.

### Strategy states

`draft → approved → archived`

### Post states

Typical path:

```text
draft
  → content_review
  → design_pending
  → design_in_progress
  → design_uploaded
  → pending_approval
  → approved
  → final
```

Alternative paths include:

- `pending_approval → changes_requested`
- `pending_approval → rejected`
- Revisions returning to writer/designer workflow
- `approved → final`
- Any applicable completed post → `archived`

## 7. Verification completed

The release-validation pass executed the following commands:

- `cd backend; uv run pytest`: **201 passed**.
- `cd backend; uv run ruff check .`: **passed**.
- `cd backend; uv run ruff format --check .`: **passed**.
- `cd backend; uv run alembic current; uv run alembic heads`: **passed**; current and head are both `14801f0e80bc`.
- `cd frontend; npm run typecheck`: **passed**.
- `cd frontend; npm run lint`: **passed**.
- `cd frontend; npm run build`: **passed**.
- `cd frontend; npm run test:e2e`: **3 failed**, blocked by the running API's `AUTH_PROVIDER=supabase` configuration while the existing specs assume local authentication.
- `cd backend; uv run python live.tmp.py`: **passed with warning**; Google Trends, Google News, Hacker News, and Reddit returned 147 items and 34 clusters. Reddit reported provider rate limiting for some requests.
- Auth/RBAC/organization/team focused tests: **25 passed**.
- Docker infrastructure inspection: PostgreSQL/pgvector and Redis containers were healthy.

The retained [`live.tmp.py`](D:/ContentPulse/backend/live.tmp.py) source smoke-test utility was formatted with Ruff and kept because it is useful for real-provider validation. No application architecture or production configuration was changed during this audit.

## 8. Remaining gaps and recommended next work

### High priority

1. Add dedicated backend tests for finalized-post share data:
   - Viewer access.
   - Admin access.
   - Non-member isolation.
   - Non-final post restrictions, if sharing should be backend-gated.
   - Correct creative version selection.

2. Add frontend tests or Playwright coverage for:
   - Share button visibility only for final posts.
   - Viewer access.
   - Native share support.
   - Fallback behavior.
   - Missing media and missing caption cases.

3. Define the production publishing strategy:
   - Keep share preparation only.
   - Or add OAuth connections and platform APIs for actual publishing.

### Medium priority

4. Add explicit user-facing state for share preparation when a platform requires manual media attachment.

5. Add observability around discovery failures, source rate limits, worker failures, and proxy resets.

6. Add retention and cleanup policies for old creative versions and local storage objects.

7. Rerun the Playwright suite against a dedicated local-auth test server/database, or update the E2E harness to explicitly provision its required auth mode. The current failure is an environment/configuration mismatch, not evidence that the registration flow itself is broken under local auth.

### Product decisions still needed

- Should finalized posts remain shareable after archival?
- Should viewers be allowed to download media independently of sharing?
- Should sharing record an audit event?
- Should the system support one-click publishing through OAuth integrations?
- Which social platforms are required for actual publishing, and which media formats should each platform support?

## 9. Conclusion

The core ContentPulse MVP workflow is substantially implemented and traceable from source trend ingestion through final approved content. The strongest implemented areas are multi-tenant storage, RBAC, trend normalization and scoring, immutable content/version history, version-specific approval, and signed creative storage.

The current product endpoint is **final approval plus assisted sharing**. It is not yet a fully automated social publishing platform. The next meaningful milestone is to add focused share tests and decide whether platform OAuth publishing is part of the product scope.
