import type {
  ConfidenceBucket,
  ConversationDetail,
  ConversationSummary,
  Drift,
  EvaluationReport,
  FeedbackResponse,
  Handoff,
  IntentStat,
  Message,
  Overview,
  PhoneVerification,
  PortalAuth,
  PortalChannel,
  PortalChannelName,
  PortalConfig,
  PortalEvent,
  PortalMe,
  PortalOAuthUrl,
  Ready,
  VolumePoint,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const API_KEY_STORAGE = "orbit.apiKey";
const PORTAL_TOKEN_STORAGE = "orbit.portalToken";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getApiKey(): string {
  try {
    return localStorage.getItem(API_KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

export function setApiKey(value: string): void {
  try {
    if (value.trim()) {
      localStorage.setItem(API_KEY_STORAGE, value.trim());
    } else {
      localStorage.removeItem(API_KEY_STORAGE);
    }
  } catch {
    // Private browsing can reject storage; the request still works unsigned.
  }
}

export function getPortalToken(): string {
  try {
    return localStorage.getItem(PORTAL_TOKEN_STORAGE) || "";
  } catch {
    return "";
  }
}

export function setPortalToken(value: string): void {
  try {
    if (value.trim()) localStorage.setItem(PORTAL_TOKEN_STORAGE, value.trim());
    else localStorage.removeItem(PORTAL_TOKEN_STORAGE);
  } catch {
    // Ignore storage failures; the session simply will not persist.
  }
}

function query(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(
    ([, value]) => value !== undefined && value !== null && value !== "",
  );
  if (!entries.length) return "";
  return `?${new URLSearchParams(entries.map(([key, value]) => [key, String(value)]))}`;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const apiKey = getApiKey();
  if (apiKey) headers.set("X-API-Key", apiKey);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    throw new ApiError("Cannot reach the API. Is the backend running?", 0);
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string") detail = payload.detail;
      else if (Array.isArray(payload?.detail)) detail = "The request was rejected.";
    } catch {
      // Keep the status text.
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function portalRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = getPortalToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: "include" });
  } catch {
    throw new ApiError("Cannot reach the API. Is the backend running?", 0);
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string") detail = payload.detail;
      else if (Array.isArray(payload?.detail)) {
        detail = payload.detail.map((item: { msg?: string }) => item.msg).join(", ");
      }
    } catch {
      // Keep the status text.
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function download(path: string, filename: string): Promise<void> {  const headers = new Headers();
  const apiKey = getApiKey();
  if (apiKey) headers.set("X-API-Key", apiKey);
  const response = await fetch(`${API_BASE}${path}`, { headers });
  if (!response.ok) {
    throw new ApiError("Export failed. Check your API key.", response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  ready: () => request<Ready>("/readyz"),
  overview: (days: number) => request<Overview>(`/api/analytics/overview${query({ days })}`),
  intents: (days: number) => request<IntentStat[]>(`/api/analytics/intents${query({ days })}`),
  confidence: (days: number) =>
    request<ConfidenceBucket[]>(`/api/analytics/confidence${query({ days })}`),
  volume: (days: number) => request<VolumePoint[]>(`/api/analytics/volume${query({ days })}`),
  drift: () => request<Drift>("/api/analytics/drift"),

  conversations: (params: {
    status?: string;
    channel?: string;
    q?: string;
    limit?: number;
    offset?: number;
  }) => request<ConversationSummary[]>(`/api/conversations${query(params)}`),
  conversation: (id: string) =>
    request<ConversationDetail>(`/api/conversations/${encodeURIComponent(id)}`),
  reply: (id: string, text: string, agent?: string) =>
    request<Message>(`/api/conversations/${encodeURIComponent(id)}/reply`, {
      method: "POST",
      body: JSON.stringify({ text, agent }),
    }),
  resolveConversation: (id: string, note?: string, agent?: string) =>
    request<ConversationSummary>(`/api/conversations/${encodeURIComponent(id)}/resolve`, {
      method: "POST",
      body: JSON.stringify({ note, agent }),
    }),
  reopenConversation: (id: string) =>
    request<ConversationSummary>(`/api/conversations/${encodeURIComponent(id)}/reopen`, {
      method: "POST",
    }),
  assignConversation: (id: string, agent: string) =>
    request<ConversationSummary>(`/api/conversations/${encodeURIComponent(id)}/assign`, {
      method: "POST",
      body: JSON.stringify({ agent }),
    }),
  manualHandoff: (
    id: string,
    body: { reason: string; priority: string; note?: string; agent?: string },
  ) =>
    request<Handoff>(`/api/conversations/${encodeURIComponent(id)}/handoff`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  handoffs: (params: { status?: string; priority?: string; limit?: number }) =>
    request<Handoff[]>(`/api/handoffs${query(params)}`),
  assignHandoff: (id: string, agent: string) =>
    request<Handoff>(`/api/handoffs/${encodeURIComponent(id)}/assign`, {
      method: "POST",
      body: JSON.stringify({ agent }),
    }),
  resolveHandoff: (id: string, note?: string, agent?: string) =>
    request<Handoff>(`/api/handoffs/${encodeURIComponent(id)}/resolve`, {
      method: "POST",
      body: JSON.stringify({ note, agent }),
    }),

  feedback: (status = "pending") =>
    request<FeedbackResponse>(`/api/feedback${query({ status })}`),
  correctMessageIntent: (messageId: string, correctedIntent: string, agent?: string) =>
    request<{ status: string; feedback_id: string | null }>(
      `/api/messages/${encodeURIComponent(messageId)}/feedback`,
      {
        method: "POST",
        body: JSON.stringify({ corrected_intent: correctedIntent, agent }),
      },
    ),
  markFeedbackExported: (id: string) =>
    request<{ status: string; id: string }>(
      `/api/feedback/${encodeURIComponent(id)}/mark-exported`,
      { method: "POST" },
    ),
  downloadFeedback: () => download("/api/feedback/export", "retraining-queue.jsonl"),
  evaluation: () => request<EvaluationReport>("/api/model/evaluation"),

  deleteCustomer: (body: {
    customer_id?: string;
    channel?: string;
    external_id?: string;
    confirm: boolean;
  }) =>
    request<{ status: string; deleted: Record<string, number> }>("/api/privacy/delete", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  portalConfig: () => portalRequest<PortalConfig>("/api/portal/config"),
  portalRegister: (body: {
    business_name: string;
    full_name: string;
    email?: string;
    phone?: string;
    password: string;
    welcome_opt_in: boolean;
  }) =>
    portalRequest<PortalAuth>("/api/portal/auth/register", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  portalLogin: (identifier: string, password: string) =>
    portalRequest<PortalAuth>("/api/portal/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
    }),
  portalLogout: () => portalRequest<void>("/api/portal/auth/logout", { method: "POST" }),
  portalMe: () => portalRequest<PortalMe>("/api/portal/me"),
  portalActivity: (limit = 50) =>
    portalRequest<PortalEvent[]>(`/api/portal/activity?limit=${limit}`),
  portalRequestPhoneVerification: () =>
    portalRequest<PhoneVerification>("/api/portal/phone/verification/request", {
      method: "POST",
    }),
  portalSetPhone: (phone: string, password: string) =>
    portalRequest<PortalMe>("/api/portal/phone", {
      method: "POST",
      body: JSON.stringify({ phone, password }),
    }),
  portalConfirmPhone: (code: string) =>
    portalRequest<PortalMe>("/api/portal/phone/verification/confirm", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  portalOAuthUrl: (channel: PortalChannelName) =>
    portalRequest<PortalOAuthUrl>(`/api/portal/channels/oauth-url?channel=${channel}`),
  portalConnect: (
    channel: PortalChannelName,
    body: {
      mode: "oauth" | "demo";
      authorization_code?: string;
      state?: string;
      external_account_id?: string;
      display_name?: string;
      waba_id?: string;
    },
  ) =>
    portalRequest<PortalChannel>(`/api/portal/channels/${channel}/connect`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  portalDisconnect: (channel: PortalChannelName) =>
    portalRequest<void>(`/api/portal/channels/${channel}/disconnect`, { method: "POST" }),
};
