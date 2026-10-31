import {
  Check,
  Clipboard,
  Eye,
  EyeOff,
  KeyRound,
  LockKeyhole,
  PlugZap,
  ServerCog,
  ShieldAlert,
  Trash2,
  UserRound,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "../components/Badge";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, SectionCard } from "../components/Section";
import { useToast } from "../components/Toast";
import { api, ApiError, getApiKey, setApiKey } from "../lib/api";
import { usePolling } from "../lib/hooks";

export default function SettingsPage() {
  const toast = useToast();
  const ready = usePolling(api.ready, 60_000, []);
  const [key, setKey] = useState(getApiKey());
  const [showKey, setShowKey] = useState(false);
  const [agent, setAgent] = useState(() => {
    try {
      return localStorage.getItem("orbit.agent") || "";
    } catch {
      return "";
    }
  });
  const [testing, setTesting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteMode, setDeleteMode] = useState<"external" | "id">("external");
  const [channel, setChannel] = useState("whatsapp");
  const [externalId, setExternalId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [deleted, setDeleted] = useState<Record<string, number> | null>(null);

  const publicBase =
    ready.data?.public_base_url?.replace(/\/$/, "") ||
    (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ||
    window.location.origin;

  const copy = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.push(`${label} copied.`);
    } catch {
      toast.push("Clipboard access was blocked by the browser.", "error");
    }
  };

  const saveKey = () => {
    setApiKey(key);
    toast.push(key.trim() ? "Admin key saved on this device." : "Admin key cleared.");
  };

  const saveAgent = () => {
    try {
      if (agent.trim()) localStorage.setItem("orbit.agent", agent.trim());
      else localStorage.removeItem("orbit.agent");
      toast.push("Agent name saved.");
    } catch {
      toast.push("Could not save the agent name in this browser.", "error");
    }
  };

  const testConnection = async () => {
    setTesting(true);
    try {
      await api.overview(1);
      toast.push("API reachable and admin key accepted.");
    } catch (caught) {
      toast.push(
        caught instanceof ApiError
          ? caught.status === 401
            ? "The admin key was rejected."
            : caught.message
          : "Connection test failed.",
        "error",
      );
    } finally {
      setTesting(false);
    }
  };

  const deleteData = async () => {
    if (!confirm) return;
    setDeleting(true);
    try {
      const result = await api.deleteCustomer(
        deleteMode === "id"
          ? { customer_id: customerId.trim(), confirm: true }
          : { channel, external_id: externalId.trim(), confirm: true },
      );
      setDeleted(result.deleted);
      setExternalId("");
      setCustomerId("");
      setConfirm(false);
      toast.push("Customer data permanently deleted.");
    } catch (caught) {
      toast.push(caught instanceof ApiError ? caught.message : "Deletion failed.", "error");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Workspace"
        title="Keys, identity, and the exit."
        description="Keep the console connected, name the human behind the reply, and honour deletion requests without a support ticket."
      />

      <div className="grid gap-4 xl:grid-cols-12">
        <div className="space-y-4 xl:col-span-7">
          <SectionCard eyebrow="Access" title="Admin API key">
            <p className="text-[11px] leading-5 text-muted">
              The backend protects dashboard routes when <code>ADMIN_API_KEY</code> is set.
              The key is stored only in this browser&apos;s local storage and sent as{" "}
              <code>X-API-Key</code>.
            </p>
            <div className="mt-4 flex gap-2">
              <div className="relative flex-1">
                <KeyRound
                  size={14}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
                />
                <input
                  type={showKey ? "text" : "password"}
                  value={key}
                  onChange={(event) => setKey(event.target.value)}
                  placeholder="Paste ADMIN_API_KEY"
                  className="field pl-9 pr-10 font-mono text-[12px]"
                  autoComplete="off"
                />
                <button
                  type="button"
                  onClick={() => setShowKey((value) => !value)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted hover:bg-paper hover:text-ink"
                  aria-label={showKey ? "Hide key" : "Show key"}
                >
                  {showKey ? <EyeOff size={13} /> : <Eye size={13} />}
                </button>
              </div>
              <button type="button" onClick={saveKey} className="btn-primary">
                Save
              </button>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void testConnection()}
                disabled={testing}
                className="btn-secondary px-3 py-1.5 text-[11px]"
              >
                <PlugZap size={12} /> {testing ? "Testing…" : "Test connection"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setKey("");
                  setApiKey("");
                  toast.push("Stored key cleared.");
                }}
                className="btn-ghost px-3 py-1.5 text-[11px]"
              >
                Clear key
              </button>
              <span className="ml-auto text-[10px] text-muted">
                {key ? "A key is stored locally" : "No key stored"}
              </span>
            </div>
          </SectionCard>

          <SectionCard eyebrow="Identity" title="Reply as">
            <p className="text-[11px] leading-5 text-muted">
              Human replies in the inbox are attributed to this name. It appears in
              message metadata and on handoff assignments.
            </p>
            <div className="mt-4 flex gap-2">
              <div className="relative flex-1">
                <UserRound
                  size={14}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
                />
                <input
                  value={agent}
                  onChange={(event) => setAgent(event.target.value)}
                  placeholder="e.g. Anika"
                  className="field pl-9"
                />
              </div>
              <button type="button" onClick={saveAgent} className="btn-primary">
                Save
              </button>
            </div>
          </SectionCard>

          <SectionCard eyebrow="Compliance" title="Data & privacy">
            <div className="flex items-start gap-2.5 rounded-xl border border-danger/20 bg-danger-soft/45 p-3.5">
              <ShieldAlert size={16} className="mt-0.5 shrink-0 text-danger" />
              <p className="text-[10px] leading-4 text-ink-soft">
                Permanent deletion removes the customer, every conversation, message,
                handoff, and prediction log we hold. This cannot be undone. Tokens live in
                environment secrets and are never stored in these tables.
              </p>
            </div>

            <div className="mt-4 flex gap-2 rounded-xl border border-line bg-paper p-1">
              {(["external", "id"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setDeleteMode(mode)}
                  className={`flex-1 rounded-lg px-3 py-1.5 text-[11px] font-bold transition-colors ${
                    deleteMode === mode ? "bg-panel text-ink shadow-sm" : "text-muted hover:text-ink"
                  }`}
                >
                  {mode === "external" ? "Channel handle" : "Customer ID"}
                </button>
              ))}
            </div>

            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {deleteMode === "external" ? (
                <>
                  <label className="block">
                    <span className="eyebrow mb-1.5 block">Channel</span>
                    <select
                      value={channel}
                      onChange={(event) => setChannel(event.target.value)}
                      className="field"
                    >
                      <option value="whatsapp">WhatsApp</option>
                      <option value="instagram">Instagram</option>
                    </select>
                  </label>
                  <label className="block">
                    <span className="eyebrow mb-1.5 block">External ID</span>
                    <input
                      value={externalId}
                      onChange={(event) => setExternalId(event.target.value)}
                      placeholder="Phone number or IG-scoped ID"
                      className="field font-mono text-[11px]"
                    />
                  </label>
                </>
              ) : (
                <label className="block sm:col-span-2">
                  <span className="eyebrow mb-1.5 block">Customer ID</span>
                  <input
                    value={customerId}
                    onChange={(event) => setCustomerId(event.target.value)}
                    placeholder="cus_…"
                    className="field font-mono text-[11px]"
                  />
                </label>
              )}
            </div>

            <label className="mt-3 flex items-start gap-2 text-[10px] leading-4 text-muted">
              <input
                type="checkbox"
                checked={confirm}
                onChange={(event) => setConfirm(event.target.checked)}
                className="mt-0.5 h-3.5 w-3.5 accent-[#9C3628]"
              />
              I understand this is a permanent deletion and there is no recovery path.
            </label>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={
                  !confirm ||
                  deleting ||
                  (deleteMode === "id" ? !customerId.trim() : !externalId.trim())
                }
                onClick={() => void deleteData()}
                className="btn-danger px-3 py-2 text-[11px]"
              >
                <Trash2 size={13} /> {deleting ? "Deleting…" : "Delete permanently"}
              </button>
              {deleted && (
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-moss">
                  <Check size={11} /> Removed {deleted.customers} customer,{" "}
                  {deleted.messages} messages
                </span>
              )}
            </div>
          </SectionCard>
        </div>

        <div className="space-y-4 xl:col-span-5">
          <SectionCard
            eyebrow="Runtime"
            title="Connection"
            action={
              <Badge tone={ready.data ? "moss" : "danger"} dot>
                {ready.data ? "Ready" : ready.error ? "Offline" : "Checking"}
              </Badge>
            }
          >
            {ready.error && <ErrorState error={ready.error} onRetry={ready.refresh} />}
            {!ready.error && (
              <dl className="space-y-3 text-[11px]">
                <Row label="API base" value={publicBase} mono />
                <Row label="Environment" value={ready.data?.environment || "—"} />
                <Row label="Queue" value={ready.data?.queue || "—"} />
                <Row label="Outbound" value={ready.data?.outbound_mode || "—"} />
                <Row label="NLU" value={ready.data?.nlu || "—"} />
                <Row label="RAG" value={ready.data?.rag || "—"} />
                <Row label="Rewrite" value={ready.data?.llm || "—"} />
              </dl>
            )}
            <p className="mt-4 border-t border-line pt-3 text-[10px] leading-4 text-muted">
              Set <code>PUBLIC_BASE_URL</code> on the API (or{" "}
              <code>VITE_API_BASE_URL</code> at build time) when the API lives on a
              different host than this dashboard.
            </p>
          </SectionCard>

          <SectionCard eyebrow="Meta" title="Webhook endpoints">
            <div className="space-y-3">
              <Endpoint
                label="WhatsApp Cloud API"
                value={`${publicBase}/webhook/whatsapp`}
                onCopy={() => void copy(`${publicBase}/webhook/whatsapp`, "WhatsApp webhook")}
              />
              <Endpoint
                label="Instagram Messaging"
                value={`${publicBase}/webhook/instagram`}
                onCopy={() => void copy(`${publicBase}/webhook/instagram`, "Instagram webhook")}
              />
            </div>
            <div className="mt-4 flex items-start gap-2 rounded-xl border border-line bg-paper p-3 text-[10px] leading-4 text-muted">
              <LockKeyhole size={13} className="mt-0.5 shrink-0 text-moss" />
              Meta signatures are verified with <code>X-Hub-Signature-256</code>. The
              verify token is read from environment secrets and never displayed here.
            </div>
            <p className="mt-3 text-[10px] leading-4 text-muted">
              For local development, expose the API with{" "}
              <code>docker compose --profile tunnel up</code> or ngrok, then paste the
              public HTTPS URL into the Meta app dashboard.
            </p>
          </SectionCard>

          <SectionCard eyebrow="Open decisions" title="Vendors not chosen">
            <div className="space-y-3">
              <div className="flex gap-2.5">
                <ServerCog size={14} className="mt-0.5 shrink-0 text-muted" />
                <p className="text-[10px] leading-4 text-muted">
                  The LLM provider is intentionally unset. The assistant uses grounded
                  templates and retrieval only until a vendor is selected.
                </p>
              </div>
              <div className="flex gap-2.5">
                <Clipboard size={14} className="mt-0.5 shrink-0 text-muted" />
                <p className="text-[10px] leading-4 text-muted">
                  Hosting is local Docker Compose only. No cloud platform has been assumed.
                </p>
              </div>
              <div className="flex gap-2.5">
                <ShieldAlert size={14} className="mt-0.5 shrink-0 text-muted" />
                <p className="text-[10px] leading-4 text-muted">
                  Do not point production Meta webhooks here until secrets, backups, and a
                  public HTTPS host are in place.
                </p>
              </div>
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line/65 pb-2.5 last:border-0 last:pb-0">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className={`min-w-0 break-all text-right font-semibold text-ink-soft ${mono ? "font-mono text-[10px]" : ""}`}>
        {value}
      </dd>
    </div>
  );
}

function Endpoint({
  label,
  value,
  onCopy,
}: {
  label: string;
  value: string;
  onCopy: () => void;
}) {
  return (
    <div className="rounded-xl border border-line bg-paper p-3">
      <p className="text-[9px] font-bold uppercase tracking-[0.08em] text-muted">{label}</p>
      <div className="mt-1.5 flex items-center gap-2">
        <code className="min-w-0 flex-1 break-all font-mono text-[10px] text-ink-soft">
          {value}
        </code>
        <button
          type="button"
          onClick={onCopy}
          className="shrink-0 rounded-md p-1.5 text-muted hover:bg-panel hover:text-ink"
          aria-label={`Copy ${label} URL`}
        >
          <Clipboard size={12} />
        </button>
      </div>
    </div>
  );
}
