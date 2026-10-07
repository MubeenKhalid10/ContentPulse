// Mirrors backend Pydantic schemas (backend/app/schemas).

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export type Role = "admin" | "creator" | "viewer";
export type MemberStatus = "active" | "invited" | "disabled";
export type Platform = "linkedin" | "x" | "instagram" | "facebook" | "blog";
export type TrendFrequency = "manual" | "hourly" | "every_6_hours" | "daily";
export type OfferingKind = "service" | "product" | "expertise";

export type Permission =
  | "organization.read"
  | "organization.write"
  | "knowledge.read"
  | "knowledge.write"
  | "trends.read"
  | "trends.manage"
  | "topics.read"
  | "topics.manage"
  | "content.read"
  | "content.generate"
  | "content.edit"
  | "design.read"
  | "design.manage"
  | "design.upload"
  | "design.submit"
  | "approval.read"
  | "approval.manage"
  | "users.manage";

export interface MembershipSummary {
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  role: Role;
}

export interface Me {
  id: string;
  name: string | null;
  email: string;
  organization_id: string | null;
  role: Role | null;
  permissions: Permission[];
  memberships: MembershipSummary[];
}

export interface Session {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: Me;
}

export interface InvitePreview {
  organization_name: string;
  email: string;
  role: Role;
  has_account: boolean;
  expires_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  website_url: string | null;
  description: string | null;
  industry: string | null;
  logo_url: string | null;
  timezone: string;
  created_at: string;
  updated_at: string;
}

export interface OrganizationSettings {
  default_language: string;
  default_timezone: string;
  target_markets: string[];
  target_audience: string | null;
  content_goals: string[];
  enabled_platforms: Platform[];
  enabled_sources: string[];
  tracked_keywords: string[];
  subreddits: string[];
  rss_feeds: string[];
  trend_frequency: TrendFrequency;
  updated_at: string;
}

export interface BrandProfile {
  brand_voice: string | null;
  tone: string | null;
  writing_style: string | null;
  preferred_terms: string[];
  forbidden_terms: string[];
  content_guidelines: string | null;
  cta_guidelines: string | null;
  hashtag_guidelines: string | null;
  brand_colors: string[];
  typography: string | null;
  updated_at: string;
}

export interface OrganizationService {
  id: string;
  kind: OfferingKind;
  name: string;
  description: string | null;
  category: string | null;
  active: boolean;
  created_at: string;
}

export interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name: string | null;
  role: Role;
  status: MemberStatus;
  joined_at: string | null;
  invite_expires_at: string | null;
  created_at: string;
}

export interface InviteResponse {
  member: Member;
  invite_url: string;
  /** True when the invitation was emailed to the invitee. */
  email_sent: boolean;
}

export interface AuditLogEntry {
  id: string;
  user_id: string | null;
  user_name: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  created_at: string;
}

export interface ActivityItem {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  user_name: string | null;
  created_at: string;
}

export interface TopTrend {
  id: string;
  topic: string;
  opportunity_score: number | null;
  sources: string[];
  mention_count: number;
}

export interface DashboardSummary {
  trends_today: number;
  relevant_trends: number;
  shortlisted_topics: number;
  topics_to_review: number;
  drafts: number;
  design_pending: number;
  pending_approval: number;
  approved: number;
  top_trends: TopTrend[];
  recent_activity: ActivityItem[];
}

// --- Knowledge base -----------------------------------------------------------

export type CrawlStatus = "pending" | "crawling" | "extracted" | "embedded" | "failed";
export type KnowledgeJobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface KnowledgeJob {
  id: string;
  kind: "crawl" | "reindex";
  status: KnowledgeJobStatus;
  root_url: string | null;
  max_pages: number;
  pages_discovered: number;
  pages_crawled: number;
  pages_indexed: number;
  pages_unchanged: number;
  pages_skipped: number;
  pages_failed: number;
  chunks_created: number;
  warnings: string[];
  error: string | null;
  cancel_requested: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobStarted {
  job_id: string;
  status: KnowledgeJobStatus;
  job: KnowledgeJob;
}

export interface KnowledgeSummary {
  website_url: string | null;
  documents: number;
  indexed_documents: number;
  failed_documents: number;
  excluded_documents: number;
  chunks: number;
  embedded_chunks: number;
  embeddings_enabled: boolean;
  embedding_model: string | null;
  last_crawled_at: string | null;
  active_job: KnowledgeJob | null;
  last_job: KnowledgeJob | null;
}

export interface KnowledgeDocument {
  id: string;
  source_url: string;
  title: string | null;
  document_type: string;
  crawl_status: CrawlStatus;
  crawl_error: string | null;
  excluded: boolean;
  word_count: number;
  chunk_count: number;
  last_crawled_at: string | null;
  updated_at: string;
}

export interface KnowledgeChunk {
  id: string;
  chunk_index: number;
  heading: string | null;
  content: string;
  token_count: number | null;
  embedded: boolean;
}

export interface KnowledgeDocumentDetail extends KnowledgeDocument {
  content: string | null;
  meta: { description?: string | null; language?: string | null; headings?: string[] };
  chunks: KnowledgeChunk[];
}

export interface DocumentPage {
  items: KnowledgeDocument[];
  total: number;
}

export interface KnowledgeSearchResult {
  chunk_id: string;
  document_id: string;
  title: string | null;
  url: string;
  document_type: string;
  heading: string | null;
  snippet: string;
  score: number;
  match: "keyword" | "semantic" | "both";
}

export interface KnowledgeSearchResponse {
  mode: "hybrid" | "keyword";
  results: KnowledgeSearchResult[];
}

// --- Trends -----------------------------------------------------------------------

export type TrendStatus = "new" | "analyzed" | "shortlisted" | "rejected" | "archived";
export type SourceHealth = "unknown" | "healthy" | "degraded" | "rate_limited" | "down";
export type SourcePricing = "free" | "free_tier" | "paid" | "unavailable";
export type RunStatus = "queued" | "running" | "succeeded" | "failed";

export interface SourceResult {
  status: "ok" | "failed" | "not_configured" | "running" | "unknown";
  items: number;
  error: string | null;
  error_kind: string | null;
  mode: string | null;
  duration_ms: number | null;
}

export interface DiscoveryRun {
  id: string;
  status: RunStatus;
  trigger: "manual" | "scheduled";
  sources: string[];
  locations: string[];
  results: Record<string, SourceResult>;
  warnings: string[];
  items_collected: number;
  trends_created: number;
  trends_updated: number;
  mentions_created: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface RunStarted {
  run_id: string;
  status: RunStatus;
  run: DiscoveryRun;
}

export interface TrendSourceInfo {
  key: string;
  name: string;
  description: string;
  pricing: SourcePricing;
  docs_url: string | null;
  env_vars: string[];
  configured: boolean;
  mode: string | null;
  missing: string[];
  note: string | null;
  enabled: boolean;
  health: SourceHealth;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error: string | null;
}

export interface Signal {
  score: number;
  detail: string;
}

export type SignalKey =
  | "popularity"
  | "growth"
  | "freshness"
  | "location_relevance"
  | "source_diversity"
  | "keyword_match"
  | "audience_relevance"
  | "organization_fit";

export interface Trend {
  id: string;
  topic: string;
  title: string | null;
  description: string | null;
  keywords: string[];
  category: string | null;
  locations: string[];
  sources: string[];
  status: TrendStatus;
  first_seen_at: string;
  last_seen_at: string;
  mention_count: number;
  opportunity_score: number | null;
  signals: Partial<Record<SignalKey, Signal>>;
  relevance_level: RelevanceLevel | null;
  relevance_overridden: boolean;
  analyzed_at: string | null;
}

export interface TrendPage {
  items: Trend[];
  total: number;
}

export interface TrendMention {
  id: string;
  source: string;
  title: string | null;
  description: string | null;
  source_url: string | null;
  author: string | null;
  location: string | null;
  category: string | null;
  published_at: string | null;
  detected_at: string;
  last_seen_at: string | null;
  engagement: number | null;
  engagement_label: string | null;
  growth_indicator: number | null;
}

export type RelevanceLevel = "highly_relevant" | "relevant" | "weakly_relevant" | "not_relevant";

export interface AlignmentPassage {
  ref: string;
  chunk_id: string;
  document_id: string;
  title: string | null;
  url: string;
  heading: string | null;
  excerpt: string;
}

export interface ContentAngle {
  title: string;
  angle: string;
  platforms: string[];
  evidence: string[];
}

/** Stored result of organization alignment (spec §15). Empty until analyzed. */
export interface Alignment {
  engine?: "ai" | "rules";
  classification?: RelevanceLevel;
  confidence?: number;
  organization_fit?: number;
  audience_relevance?: number | null;
  matched_services?: string[];
  reason?: string;
  possible_angles?: ContentAngle[];
  unsupported_claims?: string[];
  evidence?: { ref: string; supports: string }[];
  passages?: AlignmentPassage[];
  model?: string;
  prompt?: { name: string; version: number };
  analyzed_at?: string;
}

export interface AnalysisStatus {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  engine: "ai" | "rules" | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface TrendDetail extends Trend {
  alignment: Alignment;
  relevance_confidence: number | null;
  analysis: AnalysisStatus | null;
  mentions: TrendMention[];
  topic_id: string | null;
}

export interface AIStatus {
  configured: boolean;
  engine: "ai" | "rules";
  provider: string | null;
  model: string | null;
}

export interface MarketOption {
  code: string;
  name: string;
}

// --- Topics & strategies (Sprint 5) ------------------------------------------

export type TopicStatus = "new" | "reviewed" | "shortlisted" | "rejected" | "archived";
export type StrategyStatus = "draft" | "approved" | "archived";

export interface TopicAngle {
  title: string;
  angle: string;
  platforms: string[];
  evidence: string[];
}

export interface PlatformFit {
  platform: Platform;
  score: number;
  reasons: string[];
  formats: string[];
}

export interface Topic {
  id: string;
  trend_id: string | null;
  title: string;
  summary: string | null;
  relevance_level: RelevanceLevel | null;
  matched_services: string[];
  recommended_platforms: Platform[];
  status: TopicStatus;
  opportunity_score: number | null;
  strategy_count: number;
  approved_strategy_count: number;
  created_at: string;
  updated_at: string;
}

export interface TopicPage {
  items: Topic[];
  total: number;
  counts: Record<TopicStatus, number>;
}

export interface StrategyFields {
  post_type: string;
  content_angle: string | null;
  objective: string | null;
  target_audience: string | null;
  hook_direction: string | null;
  cta_direction: string | null;
  tone: string | null;
  recommended_format: string | null;
  rationale: string | null;
  details?: StrategyDetails | null;
}

export type SearchIntent = "informational" | "commercial" | "transactional" | "navigational";

/** Blog strategies' SEO plan; empty for social platforms. */
export interface StrategyDetails {
  seo_title?: string | null;
  primary_keyword?: string | null;
  secondary_keywords?: string[];
  search_intent?: SearchIntent | null;
  outline?: string[];
  target_word_count?: number | null;
  featured_image_direction?: string | null;
}

export interface Strategy extends StrategyFields {
  id: string;
  topic_id: string;
  platform: Platform;
  source: "ai" | "rules" | "manual";
  status: StrategyStatus;
  created_by: string | null;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface StrategySuggestion extends StrategyFields {
  platform: Platform;
  source: "ai" | "rules";
  notice: string | null;
}

export interface TopicDetail extends Topic {
  relevance_reason: string | null;
  suggested_angles: TopicAngle[];
  target_audience: string | null;
  platform_fit: PlatformFit[];
  unsupported_claims: string[];
  reviewed_at: string | null;
  trend: TrendDetail | null;
  strategies: Strategy[];
}

export interface PlatformRule {
  platform: Platform;
  post_types: string[];
  objectives: string[];
  affinity_keywords: string[];
  tone: string | null;
  guidance: string | null;
  max_length: number | null;
  hashtag_limit: number | null;
  updated_at: string;
}

// --- Content studio (Sprint 6) -------------------------------------------------

export type PostStatus =
  | "draft"
  | "content_review"
  | "design_pending"
  | "design_in_progress"
  | "design_uploaded"
  | "pending_approval"
  | "changes_requested"
  | "approved"
  | "final"
  | "rejected"
  | "archived";
export type DesignFormat = "text_only" | "single_image" | "carousel" | "infographic" | "video" | "reel";

export interface GenerationStatus {
  job_id: string;
  kind: "generate" | "regenerate" | "variant";
  status: "queued" | "running" | "succeeded" | "failed";
  engine: "ai" | "template";
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

/** Blog posts: SEO details stored with each version. */
export interface BlogMeta {
  seo_title?: string | null;
  meta_title?: string | null;
  meta_description?: string | null;
  slug?: string | null;
  keywords?: string[];
}

export interface PostVersionMeta {
  blog?: BlogMeta;
  engine?: "ai" | "template";
  model?: string;
  prompt?: { name: string; version: number };
  visual_concept?: string | null;
  design_format?: DesignFormat | null;
  evidence?: string[];
  passages?: AlignmentPassage[];
  warnings?: string[];
  corrections?: string[];
  instructions?: string;
  edited_from?: number;
}

export interface PostVersion {
  id: string;
  version_number: number;
  hook: string | null;
  body: string | null;
  cta: string | null;
  hashtags: string[];
  mentions: string[];
  meta: PostVersionMeta;
  source: "ai" | "manual";
  change_note: string | null;
  created_by: string | null;
  created_at: string;
}

export interface Post {
  id: string;
  title: string | null;
  platform: Platform;
  status: PostStatus;
  current_version: number;
  hook: string | null;
  topic: { id: string; title: string; status: TopicStatus } | null;
  content_strategy_id: string | null;
  variant_of_id: string | null;
  generation: GenerationStatus | null;
  created_at: string;
  updated_at: string;
}

export type PostGroup = "drafts" | "design" | "approval" | "approved" | "archived" | "all";

export interface PostPage {
  items: Post[];
  total: number;
  counts: Record<PostGroup, number>;
}

export interface PostDetail extends Post {
  current: PostVersion | null;
  strategy: Strategy | null;
  variants: Post[];
  limits: { max_length: number | null; hashtag_limit: number | null };
  editable: boolean;
  design_task: { id: string; status: DesignTaskStatus } | null;
  review: ReviewSummary | null;
  creatives: CreativeVersion[];
}

// --- Design (Sprint 7) -------------------------------------------------------------

export type DesignTaskStatus = "open" | "assigned" | "in_progress" | "submitted" | "completed" | "cancelled";
export type DesignTaskFilter = "todo" | "submitted" | "done" | "cancelled" | "all";

export interface Person {
  id: string;
  name: string | null;
  email: string;
}

export interface DesignTask {
  id: string;
  status: DesignTaskStatus;
  format: string;
  dimensions: string | null;
  headline: string | null;
  post: {
    id: string;
    title: string | null;
    platform: Platform;
    status: PostStatus;
    current_version: number;
    topic_title: string | null;
  };
  assignee: Person | null;
  creative_versions: number;
  source: "rules" | "ai" | "edited";
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
}

export interface DesignTaskPage {
  items: DesignTask[];
  total: number;
  counts: Record<DesignTaskFilter, number>;
}

export interface CreativeFile {
  id: string;
  file_name: string;
  file_type: string;
  file_size: number | null;
  position: number;
  url: string;
  download_url: string;
}

export interface CreativeVersion {
  version: number;
  note: string | null;
  uploaded_by: Person | null;
  created_at: string;
  files: CreativeFile[];
}

export interface DesignTaskDetail extends DesignTask {
  visual_concept: string | null;
  supporting_text: string | null;
  slide_structure: string[];
  visual_elements: string[];
  brand_requirements: {
    colors?: string[];
    typography?: string | null;
    logo?: boolean;
    requirements?: string[];
    avoid_terms?: string[];
  };
  cta: string | null;
  designer_notes: string | null;
  content: {
    version: number;
    hook: string | null;
    body: string | null;
    cta: string | null;
    hashtags: string[];
    blog?: BlogMeta | null;
  } | null;
  brand: {
    brand_voice: string | null;
    tone: string | null;
    colors: string[];
    typography: string | null;
    content_guidelines: string | null;
    forbidden_terms: string[];
  };
  creatives: CreativeVersion[];
  storage: "s3" | "local";
  max_upload_mb: number;
  allowed_types: string[];
  ai_brief_pending: boolean;
  /** An AI image provider is set up ("Generate image with AI"). */
  ai_images: boolean;
  image_job: { status: JobStatus; error: string | null; version: number | null } | null;
  review: ReviewSummary | null;
}

export interface UploadTicket {
  url: string;
  method: string;
  headers: Record<string, string>;
  storage_key: string;
  expires_at: string;
}

// --- Approvals (Sprint 8) -----------------------------------------------------------

export type ApprovalStatus = "pending" | "approved" | "changes_requested" | "rejected";
export type ApprovalFilter = "pending" | "reviewed" | "approved" | "changes_requested" | "rejected" | "all";

export interface ReviewComment {
  body: string;
  kind: "comment" | "approved" | "changes_requested" | "rejected" | "resubmitted";
  author: Person | null;
  post_version: number;
  creative_version: number | null;
  created_at: string;
}

export interface ReviewSummary {
  request_id: string;
  status: ApprovalStatus;
  round: number;
  post_version: number;
  creative_version: number | null;
  reviewer: Person | null;
  reviewed_at: string | null;
  comments: ReviewComment[];
}

export interface Approval {
  id: string;
  status: ApprovalStatus;
  round: number;
  post: { id: string; title: string | null; platform: Platform; status: PostStatus; current_version: number };
  topic_title: string | null;
  post_version: number;
  creative_version: number | null;
  preview_url: string | null;
  submitted_by: Person | null;
  reviewer: Person | null;
  comment_count: number;
  created_at: string;
  reviewed_at: string | null;
}

export interface ApprovalPage {
  items: Approval[];
  total: number;
  counts: Record<ApprovalFilter, number>;
}

export interface ApprovalComment extends ReviewComment {
  id: string;
  approval_request_id: string;
}

export interface ApprovalDetail extends Approval {
  content: PostVersion | null;
  copy_changed_since: boolean;
  creative: CreativeVersion | null;
  creatives: CreativeVersion[];
  versions: PostVersion[];
  brief: {
    id: string;
    format: string;
    dimensions: string | null;
    headline: string | null;
    visual_concept: string | null;
    slide_structure: string[];
    cta: string | null;
    designer_notes: string | null;
  } | null;
  topic: {
    id: string;
    title: string;
    relevance_level: RelevanceLevel | null;
    relevance_reason: string | null;
    trend_id: string | null;
    sources: string[];
    coverage: { title: string; url: string; source: string }[];
  } | null;
  comments: ApprovalComment[];
  rounds: {
    id: string;
    status: ApprovalStatus;
    post_version: number;
    creative_version: number | null;
    submitted_by: Person | null;
    reviewer: Person | null;
    created_at: string;
    reviewed_at: string | null;
  }[];
  strategy_id: string | null;
}
