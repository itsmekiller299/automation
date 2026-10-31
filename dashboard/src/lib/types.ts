export type Channel = "whatsapp" | "instagram";

export interface Customer {
  id: string;
  channel: Channel;
  external_id: string;
  display_name: string | null;
  opted_in: boolean;
  created_at: string;
  last_seen_at: string;
}

export interface Handoff {
  id: string;
  conversation_id: string;
  channel?: Channel | null;
  reason: string;
  priority: "low" | "normal" | "high" | "urgent";
  status: "open" | "assigned" | "resolved";
  assigned_to: string | null;
  note: string | null;
  source: string;
  created_at: string;
  resolved_at: string | null;
  customer_name: string | null;
  last_message: string | null;
}

export interface ConversationSummary {
  id: string;
  channel: Channel;
  status: "bot" | "needs_human" | "resolved";
  customer: Customer;
  last_intent: string | null;
  last_confidence: number | null;
  assigned_agent: string | null;
  bot_identified: boolean;
  last_message_preview: string | null;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
  open_handoff: Handoff | null;
}

export interface Entity {
  type: string;
  value?: string;
  start?: number;
  end?: number;
  score?: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  direction: "inbound" | "outbound";
  channel: Channel;
  text: string;
  message_type: string;
  intent: string | null;
  confidence: number | null;
  entities: Entity[];
  external_message_id: string | null;
  delivery_status: string | null;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: Message[];
}

export interface Overview {
  days: number;
  conversations: number;
  active_conversations: number;
  needs_human: number;
  inbound_messages: number;
  outbound_messages: number;
  bot_resolved: number;
  handoffs: number;
  handoff_rate: number;
  resolution_rate: number;
  avg_confidence: number | null;
  open_handoffs: number;
  pending_feedback: number;
}

export interface IntentStat {
  intent: string;
  count: number;
  share: number;
  avg_confidence: number | null;
}

export interface ConfidenceBucket {
  bucket: string;
  count: number;
}

export interface VolumePoint {
  date: string;
  inbound: number;
  outbound: number;
}

export interface Drift {
  flagged: boolean;
  current_window: {
    start: string;
    end: string;
    samples: number;
    avg_confidence: number | null;
    distribution: Record<string, number>;
  };
  previous_window: {
    start: string;
    end: string;
    samples: number;
    avg_confidence: number | null;
    distribution: Record<string, number>;
  };
  total_variation: number;
  confidence_delta: number;
  intent_shift: Record<string, number>;
  thresholds: {
    total_variation: number;
    confidence_delta: number;
    min_samples: number;
  };
  note: string;
}

export interface FeedbackItem {
  id: string;
  prediction_id: string;
  message_id: string | null;
  utterance: string;
  predicted_intent: string;
  corrected_intent: string;
  agent: string | null;
  status: string;
  created_at: string;
}

export interface FeedbackResponse {
  items: FeedbackItem[];
  intents: string[];
}

export interface EvaluationReport {
  available: boolean;
  hint?: string;
  report?: {
    generated_at: string;
    model_version: string;
    backend: string;
    split: string;
    records: number;
    temperature: number;
    calibration: {
      ece_uncalibrated: number;
      ece_calibrated: number;
      nll_calibrated: number;
    };
    intent: {
      accuracy: number;
      macro_f1: number;
      weighted_f1: number;
      per_intent: Record<
        string,
        { precision: number; recall: number; f1: number; support: number }
      >;
    };
    entities: {
      precision: number;
      recall: number;
      f1: number;
      per_type: Record<
        string,
        { precision: number; recall: number; f1: number; support: number }
      >;
    };
    handoff_simulation: {
      threshold: number;
      handoff_rate: number;
      accuracy_above_threshold: number;
      accuracy_below_threshold: number;
    };
    target: { macro_f1: number; met: boolean };
    common_confusions: Array<{
      actual: string;
      predicted: string;
      count: number;
    }>;
    data_note: string;
  };
}

export interface Ready {
  status: string;
  environment: string;
  queue: string;
  outbound_mode: string;
  nlu: string;
  rag: string;
  llm: string;
  public_base_url: string;
  brand: string;
}

export type PortalChannelName = "whatsapp" | "instagram";

export interface PortalUser {
  id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  role: string;
  welcome_opt_in: boolean;
  phone_verified: boolean;
  last_login_at: string | null;
}

export interface PortalTenant {
  id: string;
  name: string;
  slug: string;
  plan: string;
  automation_enabled: boolean;
  activated_at: string | null;
}

export interface PortalChannel {
  channel: PortalChannelName;
  external_account_id: string;
  display_name: string | null;
  status: string;
  connected_at: string;
  token_expires_at: string | null;
}

export interface PortalEvent {
  id: string;
  event_type: string;
  status: string;
  channel: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface PortalActivation {
  status: "sent" | "blocked" | "failed" | "skipped";
  reason: string | null;
  channel: string | null;
}

export interface PortalAuth {
  token: string;
  expires_at: string;
  user: PortalUser;
  tenant: PortalTenant;
  activation: PortalActivation | null;
  phone_verification_required: boolean;
}

export interface PortalMe {
  user: PortalUser;
  tenant: PortalTenant;
  channels: PortalChannel[];
  recent_events: PortalEvent[];
}

export interface PortalConfig {
  enabled: boolean;
  meta_oauth_configured: boolean;
  mock_channel_connect: boolean;
  welcome_template: string;
  brand: string;
}

export interface PortalOAuthUrl {
  channel: PortalChannelName;
  configured: boolean;
  url: string | null;
  mock_allowed: boolean;
  message: string | null;
}

export interface PhoneVerification {
  status: "sent" | "already_verified" | "unavailable" | "rate_limited";
  phone: string | null;
  dev_code: string | null;
  message: string | null;
}
