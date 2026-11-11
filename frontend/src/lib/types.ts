// Hand-written mirrors of the backend Pydantic models. Nothing infers across the HTTP
// boundary, so every field here is kept in sync with backend/models/*.py by hand.

export type ListingType = "goods" | "services";
export type ListingStatus = "draft" | "active" | "paused" | "reserved" | "traded" | "archived";
export type WantStatus = "open" | "fulfilled" | "closed";
export type ExchangeStatus =
  | "discovered"
  | "proposed"
  | "pending_approval"
  | "approved"
  | "payment_pending"
  | "ready_for_fulfillment"
  | "fulfillment_in_progress"
  | "completed"
  | "rejected"
  | "cancelled"
  | "disputed"
  | "expired";
export type ApprovalStatus = "pending" | "approved" | "changes_requested";
export type ApprovalDecision = "approved" | "changes_requested";
export type FulfilmentStatus = "pending" | "confirmed";
export type PaymentStatus = "created" | "approved" | "captured" | "failed" | "refunded" | "cancelled" | "pending";
export type NotificationType =
  | "match"
  | "cycle"
  | "exchange"
  | "approval"
  | "payment"
  | "fulfilment"
  | "payout"
  | "review"
  | "system";

export interface MessageResponse {
  message: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// ---- users -------------------------------------------------------------------------------
export interface UserMe {
  id: string;
  name: string;
  email: string;
  paypal_email: string | null;
  role: "trader" | "admin";
  bio: string;
  location: string;
  skills: string[];
  created_at: string;
}

export interface UserPublic {
  id: string;
  name: string;
  bio: string;
  location: string;
  skills: string[];
  created_at: string;
}

export interface UserBrief {
  id: string;
  name: string;
  location: string;
}

export interface SessionResponse {
  user: UserMe | null;
}

// ---- listings ----------------------------------------------------------------------------
export interface ListingBrief {
  id: string;
  title: string;
  type: ListingType;
  category: string;
  estimated_value: number;
  currency: string;
}

export interface Listing {
  id: string;
  owner_id: string;
  owner: UserBrief | null;
  title: string;
  description: string;
  type: ListingType;
  category: string;
  condition: string;
  estimated_value: number;
  currency: string;
  tags: string[];
  location: string;
  status: ListingStatus;
  ai_assisted: boolean;
  in_active_exchange: boolean;
  created_at: string;
  updated_at: string;
}

export type ListingPage = Page<Listing>;

export interface ListingPayload {
  title: string;
  description: string;
  type: ListingType;
  category: string;
  condition: string;
  estimated_value: number;
  currency: string;
  tags: string[];
  location: string;
  status: ListingStatus;
  ai_assisted?: boolean;
}

// ---- wants -------------------------------------------------------------------------------
export interface Want {
  id: string;
  user_id: string;
  title: string;
  description: string;
  category: string;
  target_type: "goods" | "services" | "any";
  min_value: number;
  max_value: number;
  currency: string;
  keywords: string[];
  listing_id: string | null;
  min_condition?: string | null;
  location_preference?: "any" | "local";
  offered_listing: ListingBrief | null;
  status: WantStatus;
  created_at: string;
  updated_at: string;
}

export interface WantPayload {
  title: string;
  description: string;
  category: string;
  target_type: "goods" | "services" | "any";
  min_value: number;
  max_value: number;
  currency: string;
  keywords: string[];
  listing_id: string | null;
  min_condition?: string | null;
  location_preference?: "any" | "local";
}

export interface WantListResponse {
  wants: Want[];
  listing_options: ListingBrief[];
}

// ---- matches -----------------------------------------------------------------------------
export interface Match {
  id: string;
  user_id: string;
  want_id: string;
  candidate_listing_id: string;
  candidate_listing: ListingBrief | null;
  offered_listing: ListingBrief | null;
  score: number;
  semantic_score: number;
  value_score: number;
  category_score: number;
  location_score: number;
  compatible: boolean;
  reasons: string[];
  explanation: string | null;
  explanation_generated_at: string | null;
  dismissed: boolean;
  created_at: string;
}

export type MatchPage = Page<Match>;

export interface MatchExplanationResponse {
  match_id: string;
  explanation: string;
  generated_at: string;
  model: string;
  cached: boolean;
}

// ---- graph / cycles ----------------------------------------------------------------------
export interface GraphEdge {
  from_user: string;
  to_user: string;
  listing_id: string;
  listing_title: string;
  satisfies_want_id: string;
  value: number;
  currency: string;
  semantic_score: number;
}

export interface CycleParticipant {
  user_id: string;
  user_name: string;
  gives_listing_id: string;
  gives_listing_title: string;
  gives_value: number;
  receives_listing_id: string;
  receives_listing_title: string;
  receives_value: number;
  balance_amount: number;
  currency: string;
}

export interface Cycle {
  key: string;
  cycle_type: number;
  participant_ids: string[];
  participants: CycleParticipant[];
  total_value: number;
  total_imbalance: number;
  mean_semantic_score: number;
  id: string;
  status: string;
  min_edge_score: number;
  avg_edge_score: number;
  rank: number;
  reasons: string[];
  edges: GraphEdge[];
}

export interface CycleListResponse {
  cycles: Cycle[];
  candidate_count: number;
  generated_at: string;
}

export interface GraphStats {
  nodes: number;
  edges: number;
  two_cycles: number;
  three_cycles: number;
  generated_at: string;
  note: string | null;
}

// ---- exchanges ---------------------------------------------------------------------------
export interface ExchangeParticipant {
  id: string;
  exchange_id: string;
  user_id: string;
  user: UserBrief | null;
  gives_listing_id: string;
  gives_listing: ListingBrief | null;
  receives_listing_id: string;
  receives_listing: ListingBrief | null;
  value_given: number;
  value_received: number;
  balance_amount: number;
  currency: string;
  approval_status: ApprovalStatus;
  approved_revision: number | null;
  changes_note: string | null;
  fulfilment_status: FulfilmentStatus;
  fulfilled_at: string | null;
  created_at: string;
}

export interface ExchangeApproval {
  id: string;
  exchange_id: string;
  participant_id: string;
  user_id: string;
  revision: number;
  decision: ApprovalDecision;
  note: string;
  created_at: string;
}

export interface Offer {
  id: string;
  exchange_id: string;
  revision: number;
  from_user_id: string;
  from_user_name: string;
  to_user_id: string;
  message: string;
  proposed_changes: Record<string, unknown>;
  status: string;
  created_at: string;
}

export interface PaymentSummary {
  required: number;
  captured: number;
  total_due: number;
  total_captured: number;
  currency: string;
  all_verified: boolean;
}

export interface Exchange {
  id: string;
  cycle_type: number;
  status: ExchangeStatus;
  revision: number;
  participant_ids: string[];
  participants: ExchangeParticipant[];
  currency: string;
  value_summary: Record<string, number>;
  payment_summary: PaymentSummary;
  approvals_current: number;
  approvals_required: number;
  is_participant: boolean;
  my_participant: ExchangeParticipant | null;
  cycle_key: string;
  revised_at: string | null;
  expires_at: string | null;
  dispute: Dispute | null;
  status_before_dispute: string | null;
  allowed_actions: ExchangeAction[];
  created_by: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface ExchangeBrief {
  id: string;
  cycle_type: number;
  status: ExchangeStatus;
  revision: number;
  currency: string;
  my_role: string | null;
  counterparties: UserBrief[];
  total_value: number;
  created_at: string;
  updated_at: string;
}

export interface ExchangeListResponse {
  exchanges: ExchangeBrief[];
}

export type ExchangeAction =
  | "approve"
  | "counteroffer"
  | "reject"
  | "cancel"
  | "pay"
  | "confirm_fulfilment"
  | "complete"
  | "dispute"
  | "resolve_dispute";

export interface Dispute {
  opened_by: string;
  reason: string;
  opened_at: string | null;
  resolved_by: string[];
  resolution: Record<string, unknown> | null;
}

export interface ExchangeEvent {
  id: string;
  exchange_id: string;
  actor_id: string | null;
  kind: string;
  from_status: string;
  to_status: string;
  revision: number;
  note: string;
  created_at: string;
}

export interface CounterofferPayload {
  agreed_values: Record<string, number>;
  message: string;
}

export interface ExchangeDetail {
  exchange: Exchange;
  approvals: ExchangeApproval[];
  offers: Offer[];
  events: ExchangeEvent[];
}

export interface FulfilmentResponse {
  participant: ExchangeParticipant;
  exchange_status: ExchangeStatus;
}

// ---- payments ----------------------------------------------------------------------------
export interface Payment {
  id: string;
  exchange_id: string;
  participant_id: string;
  user_id: string;
  amount: number;
  currency: string;
  provider: string;
  environment: string;
  paypal_order_id: string | null;
  paypal_capture_id: string | null;
  status: PaymentStatus;
  verified: boolean;
  verification_source: string | null;
  authorized_at: string | null;
  captured_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaymentInitResponse {
  payment: Payment;
  approval_url: string;
  paypal_order_id: string;
  environment: string;
}

export interface PaymentConfigStatus {
  configured: boolean;
  environment: string;
  detail: string;
  escrow_note: string;
}

export interface PaymentListResponse {
  payments: Payment[];
}

// ---- notifications -----------------------------------------------------------------------
export interface Notification {
  id: string;
  user_id: string;
  type: NotificationType;
  title: string;
  body: string;
  link: string;
  read: boolean;
  created_at: string;
}

export type NotificationPage = Page<Notification>;

export interface UnreadCountResponse {
  unread: number;
  items: Notification[];
}

// ---- ai ----------------------------------------------------------------------------------
export interface AIStatus {
  available: boolean;
  provider: string;
  model: string;
  detail: string;
  embeddings_model: string;
  embeddings_provider: string;
}

export interface ExtractedListing {
  title: string;
  description: string;
  type: ListingType;
  category: string;
  condition: string;
  estimated_value: number;
  currency: string;
  tags: string[];
  key_attributes: Record<string, unknown>;
  confidence: number;
  warnings: string[];
}

export interface ExtractListingResponse {
  extraction: ExtractedListing;
  model: string;
  generated_at: string;
  disclaimer: string;
}

export interface DealSummaryResponse {
  exchange_id: string;
  summary: string;
  open_questions: string[];
  negotiation_suggestions: string[];
  model: string;
  generated_at: string;
  disclaimer: string;
}

// --- AI listing intelligence (mirrors backend/models/ai.py) ---
export type ValueBasis = "stated_by_user" | "ai_estimate" | "none";
export type AttributeValue = string | number | boolean;

export interface SuggestedWant {
  title: string;
  category: string;
  target_type: "goods" | "services" | "any";
  reason: string;
}

export interface ListingAnalysis {
  name: string;
  category: string;
  listing_type: ListingType;
  description: string;
  condition: string | null;
  attributes: Record<string, AttributeValue>;
  estimated_value: number | null;
  value_basis: ValueBasis;
  currency: string | null;
  keywords: string[];
  suggested_wants: SuggestedWant[];
  confidence: number;
  warnings: string[];
}

export interface AnalyzeListingResponse {
  analysis: ListingAnalysis;
  model: string;
  generated_at: string;
  valuation_verified: false;
  disclaimer: string;
}

export interface EmbeddingStatus {
  provider: string;
  model: string;
  version: string;
  dim: number;
  store: string;
  total: number;
  current: number;
  stale: number;
}

// --- Payouts (mirrors backend/models/payouts.py) ---
export type PayoutStatus = "pending" | "processing" | "success" | "unclaimed" | "failed" | "blocked";

export interface Payout {
  id: string;
  exchange_id: string;
  participant_id: string;
  user_id: string;
  amount: number;
  currency: string;
  receiver_email: string;
  receiver_source: "paypal_email" | "login_email";
  sender_batch_id: string;
  paypal_batch_id: string | null;
  paypal_item_id: string | null;
  paypal_transaction_status: string | null;
  status: PayoutStatus;
  trigger: "automatic" | "claim";
  verified: boolean;
  verification_source: string | null;
  attempts: number;
  last_error: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PayoutListResponse {
  payouts: Payout[];
  note: string;
}

// --- Reviews & reputation (mirrors backend/models/reviews.py) ---
export interface ReviewCreate {
  rating: number;
  comment: string;
  exchange_id?: string | null;
}

export interface Review {
  id: string;
  author: UserBrief | null;
  subject_id: string;
  exchange_id: string | null;
  rating: number;
  comment: string;
  verified: boolean;
  created_at: string;
}

export interface ReviewableExchange {
  exchange_id: string;
  cycle_type: number;
  completed_at: string | null;
}

export interface Reputation {
  user_id: string;
  name: string;
  completed_trades: number;
  verified_review_count: number;
  unverified_review_count: number;
  average_rating: number | null;
  reviews: Review[];
  reviewable_exchanges: ReviewableExchange[];
  viewer_can_review_unverified: boolean;
  note: string;
}
