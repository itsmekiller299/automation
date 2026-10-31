import {
  ArrowLeft,
  Check,
  ChevronDown,
  CircleUserRound,
  Clock,
  Filter,
  LifeBuoy,
  RotateCcw,
  Search,
  Send,
  Sparkles,
  UserRoundPlus,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ChannelBadge } from "../components/ChannelBadge";
import { Modal } from "../components/Modal";
import { PageHeader, RefreshButton } from "../components/PageHeader";
import { EmptyState, ErrorState, SkeletonRows } from "../components/Section";
import { useToast } from "../components/Toast";
import { api, ApiError } from "../lib/api";
import {
  ageHours,
  cn,
  confidenceTone,
  formatTime,
  initials,
  intentTone,
  maskExternal,
  relativeTime,
  statusTone,
  titleCase,
} from "../lib/format";
import { useDebounced, usePolling } from "../lib/hooks";
import type { ConversationSummary, Message } from "../lib/types";

const INTENTS = [
  "greeting",
  "order_status",
  "return_refund",
  "product_info",
  "pricing",
  "complaint",
  "human_agent",
  "goodbye",
  "other",
];

const HANDOFF_REASONS = [
  { value: "customer_requested", label: "Customer asked for a person" },
  { value: "low_confidence", label: "Low confidence" },
  { value: "complaint", label: "Complaint or frustration" },
  { value: "out_of_scope", label: "Out of scope" },
  { value: "policy", label: "Policy or refund judgement" },
  { value: "agent_requested", label: "Agent judgement" },
];

function currentAgent(): string {
  try {
    return localStorage.getItem("orbit.agent") || "dashboard";
  } catch {
    return "dashboard";
  }
}

export default function InboxPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(searchParams.get("c"));
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounced(query, 300);
  const [statusFilter, setStatusFilter] = useState("");
  const [channelFilter, setChannelFilter] = useState("");

  const loader = useMemo(
    () => () =>
      api.conversations({
        q: debouncedQuery || undefined,
        status: statusFilter || undefined,
        channel: channelFilter || undefined,
        limit: 80,
      }),
    [debouncedQuery, statusFilter, channelFilter],
  );
  const { data, error, loading, refreshing, updatedAt, refresh } = usePolling(
    loader,
    20_000,
    [debouncedQuery, statusFilter, channelFilter],
  );

  useEffect(() => {
    const fromUrl = searchParams.get("c");
    if (fromUrl && fromUrl !== selectedId) setSelectedId(fromUrl);
  }, [searchParams, selectedId]);

  useEffect(() => {
    if (selectedId || !data?.length) return;
    if (window.matchMedia("(min-width: 1024px)").matches) {
      setSelectedId(data[0].id);
    }
  }, [data, selectedId]);

  const select = (id: string | null) => {
    setSelectedId(id);
    if (id) setSearchParams({ c: id }, { replace: true });
    else setSearchParams({}, { replace: true });
  };

  const selected = data?.find((item) => item.id === selectedId) || null;

  return (
    <div>
      <PageHeader
        eyebrow="Conversations"
        title="Inbox, with the working shown."
        description="Read the thread, inspect what the model believed, and step in without losing context. Automated replies pause the moment a handoff opens."
        actions={<RefreshButton onClick={refresh} refreshing={refreshing} />}
      />

      <div className="surface overflow-hidden">
        <div className="grid lg:h-[calc(100vh-220px)] lg:min-h-[580px] lg:grid-cols-[350px_minmax(0,1fr)]">
          <section
            className={cn(
              "flex min-h-0 flex-col border-line lg:border-r",
              selectedId ? "hidden lg:flex" : "flex",
            )}
          >
            <div className="border-b border-line p-3.5">
              <label className="relative block">
                <Search
                  size={14}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
                />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search name, handle, or ID"
                  className="field py-2 pl-9 text-[12px]"
                />
              </label>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <label className="relative">
                  <Filter
                    size={11}
                    className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted"
                  />
                  <select
                    value={statusFilter}
                    onChange={(event) => setStatusFilter(event.target.value)}
                    className="field appearance-none py-1.5 pl-7 pr-6 text-[11px]"
                  >
                    <option value="">All states</option>
                    <option value="bot">Automated</option>
                    <option value="needs_human">Needs human</option>
                    <option value="resolved">Resolved</option>
                  </select>
                  <ChevronDown
                    size={11}
                    className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted"
                  />
                </label>
                <label className="relative">
                  <select
                    value={channelFilter}
                    onChange={(event) => setChannelFilter(event.target.value)}
                    className="field appearance-none py-1.5 pl-3 pr-6 text-[11px]"
                  >
                    <option value="">All channels</option>
                    <option value="whatsapp">WhatsApp</option>
                    <option value="instagram">Instagram</option>
                  </select>
                  <ChevronDown
                    size={11}
                    className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted"
                  />
                </label>
              </div>
              <div className="mt-2 flex items-center justify-between px-0.5">
                <span className="text-[10px] font-semibold text-muted">
                  {data?.length ?? 0} threads
                </span>
                <span className="text-[10px] text-muted">
                  {updatedAt ? `synced ${relativeTime(new Date(updatedAt).toISOString())}` : "—"}
                </span>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto">
              {error && (
                <div className="p-4">
                  <ErrorState error={error} onRetry={refresh} />
                </div>
              )}
              {!error && loading && (
                <div className="p-4">
                  <SkeletonRows rows={6} />
                </div>
              )}
              {!error && !loading && data?.length === 0 && (
                <EmptyState
                  title="No conversations match"
                  description="Try a different status, channel, or search phrase."
                />
              )}
              {!error &&
                data?.map((conversation) => (
                  <ConversationRow
                    key={conversation.id}
                    conversation={conversation}
                    active={conversation.id === selectedId}
                    onClick={() => select(conversation.id)}
                  />
                ))}
            </div>
          </section>

          <section
            className={cn(
              "min-h-0 min-w-0 flex-col",
              selectedId ? "flex" : "hidden lg:flex",
            )}
          >
            {selectedId ? (
              <ConversationPane
                key={selectedId}
                conversationId={selectedId}
                onBack={() => select(null)}
                onChanged={refresh}
                summary={selected}
              />
            ) : (
              <div className="grid h-full place-items-center p-10">
                <EmptyState
                  title="Choose a conversation"
                  description="Pick a thread on the left to read the exchange, inspect the model's read, and reply as a human."
                  icon={LifeBuoy}
                />
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function ConversationRow({
  conversation,
  active,
  onClick,
}: {
  conversation: ConversationSummary;
  active: boolean;
  onClick: () => void;
}) {
  const waiting = ageHours(conversation.updated_at);
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "relative block w-full border-b border-line/80 px-4 py-3.5 text-left transition-colors",
        active ? "bg-paper" : "hover:bg-paper/55",
      )}
    >
      {active && <span className="absolute inset-y-3 left-0 w-[2px] rounded-full bg-clay" />}
      <div className="flex gap-2.5">
        <span
          className={cn(
            "grid h-9 w-9 shrink-0 place-items-center rounded-full text-[11px] font-bold",
            conversation.channel === "whatsapp"
              ? "bg-moss-soft text-moss"
              : "bg-clay-soft text-clay",
          )}
        >
          {initials(conversation.customer.display_name)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate text-[12px] font-bold text-ink">
              {conversation.customer.display_name || maskExternal(conversation.customer.external_id)}
            </span>
            <span className="shrink-0 text-[9px] text-muted">
              {relativeTime(conversation.last_message_at || conversation.updated_at)}
            </span>
          </div>
          <p className="mt-0.5 line-clamp-1 text-[11px] text-muted">
            {conversation.last_message_preview || "No messages yet"}
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <ChannelBadge channel={conversation.channel} />
            <span
              className={cn(
                "rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.05em]",
                statusTone(conversation.status),
              )}
            >
              {conversation.status === "bot" ? "Automated" : titleCase(conversation.status)}
            </span>
            {conversation.last_intent && (
              <span
                className={cn(
                  "rounded-full px-1.5 py-0.5 text-[9px] font-semibold",
                  intentTone(conversation.last_intent),
                )}
              >
                {conversation.last_intent.replace(/_/g, " ")}
              </span>
            )}
            {conversation.status === "needs_human" && waiting > 1 && (
              <span className="ml-auto inline-flex items-center gap-1 text-[9px] font-bold text-danger">
                <Clock size={9} /> {Math.floor(waiting)}h
              </span>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}

function ConversationPane({
  conversationId,
  summary,
  onBack,
  onChanged,
}: {
  conversationId: string;
  summary: ConversationSummary | null;
  onBack: () => void;
  onChanged: () => void;
}) {
  const toast = useToast();
  const loader = useMemo(() => () => api.conversation(conversationId), [conversationId]);
  const { data, error, loading, refreshing, refresh } = usePolling(loader, 15_000, [
    conversationId,
  ]);
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [modal, setModal] = useState<"assign" | "handoff" | "resolve" | null>(null);
  const [agent, setAgent] = useState("");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("customer_requested");
  const [priority, setPriority] = useState("normal");
  const [actionBusy, setActionBusy] = useState(false);
  const messageEnd = useRef<HTMLDivElement>(null);

  const conversation = data || summary;
  const messages = data?.messages || [];
  const latestInbound = [...messages].reverse().find((message) => message.direction === "inbound");
  const resolved = conversation?.status === "resolved";

  useEffect(() => {
    messageEnd.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  const send = async () => {
    if (!reply.trim() || sending) return;
    setSending(true);
    try {
      await api.reply(conversationId, reply.trim(), currentAgent());
      setReply("");
      toast.push("Reply sent to the customer.");
      refresh();
      onChanged();
    } catch (caught) {
      toast.push(
        caught instanceof ApiError ? caught.message : "The reply could not be sent.",
        "error",
      );
    } finally {
      setSending(false);
    }
  };

  const runAction = async (action: () => Promise<unknown>, success: string) => {
    setActionBusy(true);
    try {
      await action();
      toast.push(success);
      setModal(null);
      setAgent("");
      setNote("");
      refresh();
      onChanged();
    } catch (caught) {
      toast.push(
        caught instanceof ApiError ? caught.message : "That action could not be completed.",
        "error",
      );
    } finally {
      setActionBusy(false);
    }
  };

  return (
    <>
      <header className="border-b border-line px-4 py-3.5 sm:px-5">
        <div className="flex items-start gap-3">
          <button
            type="button"
            onClick={onBack}
            className="btn-ghost -ml-1 p-2 lg:hidden"
            aria-label="Back to conversations"
          >
            <ArrowLeft size={16} />
          </button>
          <span
            className={cn(
              "hidden h-10 w-10 shrink-0 place-items-center rounded-full text-[12px] font-bold sm:grid",
              conversation?.channel === "instagram"
                ? "bg-clay-soft text-clay"
                : "bg-moss-soft text-moss",
            )}
          >
            {initials(conversation?.customer.display_name)}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h2 className="truncate font-display text-[23px] leading-none text-ink">
                {conversation?.customer.display_name || "Unknown customer"}
              </h2>
              {conversation && <ChannelBadge channel={conversation.channel} />}
              {conversation && (
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.06em]",
                    statusTone(conversation.status),
                  )}
                >
                  {conversation.status === "bot" ? "Automated" : titleCase(conversation.status)}
                </span>
              )}
            </div>
            <p className="mt-1 text-[10px] text-muted">
              {conversation
                ? `${maskExternal(conversation.customer.external_id)} · ${
                    conversation.customer.opted_in ? "opted in" : "opted out"
                  } · seen ${relativeTime(conversation.customer.last_seen_at)}`
                : "Loading conversation…"}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={refresh}
              disabled={refreshing}
              className="btn-ghost p-2"
              aria-label="Refresh conversation"
            >
              <RotateCcw size={14} className={cn(refreshing && "animate-spin")} />
            </button>
            <button
              type="button"
              onClick={() => {
                setAgent("");
                setModal("assign");
              }}
              className="btn-secondary hidden px-2.5 py-1.5 text-[11px] sm:inline-flex"
            >
              <UserRoundPlus size={13} /> Assign
            </button>
            {resolved ? (
              <button
                type="button"
                onClick={() =>
                  runAction(() => api.reopenConversation(conversationId), "Conversation reopened.")
                }
                className="btn-secondary px-2.5 py-1.5 text-[11px]"
                disabled={actionBusy}
              >
                <RotateCcw size={13} /> Reopen
              </button>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => {
                    setReason("customer_requested");
                    setPriority("normal");
                    setNote("");
                    setModal("handoff");
                  }}
                  className="btn-secondary px-2.5 py-1.5 text-[11px]"
                >
                  <LifeBuoy size={13} /> Hand off
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setNote("");
                    setModal("resolve");
                  }}
                  className="btn-primary px-2.5 py-1.5 text-[11px]"
                >
                  <Check size={13} /> Resolve
                </button>
              </>
            )}
          </div>
        </div>

        {conversation?.open_handoff && (
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-amber/20 bg-amber-soft/55 px-3 py-2 text-[10px] text-amber">
            <span className="font-bold uppercase tracking-[0.08em]">Human needed</span>
            <span>{titleCase(conversation.open_handoff.reason)}</span>
            <span className="text-amber/70">
              opened {relativeTime(conversation.open_handoff.created_at)}
            </span>
            {conversation.open_handoff.assigned_to && (
              <span className="text-amber/70">
                assigned to {conversation.open_handoff.assigned_to}
              </span>
            )}
            {conversation.assigned_agent && (
              <span className="ml-auto inline-flex items-center gap-1">
                <CircleUserRound size={11} /> {conversation.assigned_agent}
              </span>
            )}
          </div>
        )}
      </header>

      {error && (
        <div className="p-5">
          <ErrorState error={error} onRetry={refresh} />
        </div>
      )}

      {!error && loading && (
        <div className="flex-1 p-5">
          <SkeletonRows rows={7} />
        </div>
      )}

      {!error && !loading && data && (
        <>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-paper/45 px-4 py-5 sm:px-6">
            {messages.length === 0 && (
              <EmptyState
                compact
                title="No messages yet"
                description="This thread exists but has no recorded messages."
              />
            )}
            {messages.map((message, index) => {
              const previous = messages[index - 1];
              const showDay =
                !previous ||
                new Date(`${message.created_at}Z`).toDateString() !==
                  new Date(`${previous.created_at}Z`).toDateString();
              return (
                <div key={message.id}>
                  {showDay && (
                    <div className="my-5 flex items-center gap-3">
                      <span className="h-px flex-1 bg-line" />
                      <span className="text-[9px] font-bold uppercase tracking-[0.12em] text-muted">
                        {new Intl.DateTimeFormat("en", {
                          weekday: "short",
                          day: "numeric",
                          month: "short",
                        }).format(new Date(`${message.created_at}Z`))}
                      </span>
                      <span className="h-px flex-1 bg-line" />
                    </div>
                  )}
                  <MessageBubble
                    message={message}
                    isLatestInbound={latestInbound?.id === message.id}
                    onCorrected={() => {
                      toast.push("Correction added to the retraining queue.");
                      refresh();
                    }}
                  />
                </div>
              );
            })}
            <div ref={messageEnd} />
          </div>

          <footer className="border-t border-line bg-panel p-3.5 sm:p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-[10px] text-muted">
                <Sparkles size={11} className="text-clay" />
                Replying as <strong className="font-semibold text-ink-soft">{currentAgent()}</strong>
              </span>
              <span className="hidden text-[9px] text-muted sm:inline">⌘ + Enter to send</span>
            </div>
            <div className="flex items-end gap-2">
              <textarea
                value={reply}
                onChange={(event) => setReply(event.target.value)}
                onKeyDown={(event) => {
                  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                    event.preventDefault();
                    void send();
                  }
                }}
                rows={2}
                disabled={resolved}
                placeholder={resolved ? "Reopen the conversation to reply." : "Write a reply as a human…"}
                className="field min-h-[52px] flex-1 resize-none py-2.5 text-[12px] leading-5 disabled:bg-paper disabled:text-muted"
              />
              <button
                type="button"
                onClick={() => void send()}
                disabled={!reply.trim() || sending || resolved}
                className="btn-primary h-[52px] px-4"
                aria-label="Send reply"
              >
                <Send size={15} />
              </button>
            </div>
            <p className="mt-1.5 text-[9px] text-muted">
              Replies are delivered through the channel API. WhatsApp messages outside the
              24-hour window use the approved template.
            </p>
          </footer>
        </>
      )}

      <Modal
        open={modal === "assign"}
        onClose={() => setModal(null)}
        title="Assign this conversation"
        description="Assigning an open handoff stops the other agents from picking it up."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setModal(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!agent.trim() || actionBusy}
              onClick={() =>
                runAction(
                  () => api.assignConversation(conversationId, agent.trim()),
                  `Assigned to ${agent.trim()}.`,
                )
              }
            >
              Assign
            </button>
          </>
        }
      >
        <label className="block">
          <span className="eyebrow mb-1.5 block">Agent name</span>
          <input
            value={agent}
            onChange={(event) => setAgent(event.target.value)}
            placeholder="e.g. Anika"
            className="field"
            autoFocus
          />
        </label>
      </Modal>

      <Modal
        open={modal === "handoff"}
        onClose={() => setModal(null)}
        title="Bring in a human"
        description="The bot pauses immediately. Add the context the next agent needs."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setModal(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={actionBusy}
              onClick={() =>
                runAction(
                  () =>
                    api.manualHandoff(conversationId, {
                      reason,
                      priority,
                      note: note.trim() || undefined,
                      agent: agent.trim() || undefined,
                    }),
                  "Handoff opened.",
                )
              }
            >
              Open handoff
            </button>
          </>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="eyebrow mb-1.5 block">Reason</span>
            <select value={reason} onChange={(event) => setReason(event.target.value)} className="field">
              {HANDOFF_REASONS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="eyebrow mb-1.5 block">Priority</span>
            <select
              value={priority}
              onChange={(event) => setPriority(event.target.value)}
              className="field"
            >
              <option value="low">Low</option>
              <option value="normal">Normal</option>
              <option value="high">High</option>
              <option value="urgent">Urgent</option>
            </select>
          </label>
          <label className="block sm:col-span-2">
            <span className="eyebrow mb-1.5 block">Assignee (optional)</span>
            <input
              value={agent}
              onChange={(event) => setAgent(event.target.value)}
              placeholder="Leave blank for the shared queue"
              className="field"
            />
          </label>
          <label className="block sm:col-span-2">
            <span className="eyebrow mb-1.5 block">Note</span>
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={3}
              placeholder="What has been checked? What should the agent know?"
              className="field resize-none"
            />
          </label>
        </div>
      </Modal>

      <Modal
        open={modal === "resolve"}
        onClose={() => setModal(null)}
        title="Close this conversation"
        description="Resolution stops the bot for this thread and closes any open handoff. Reopen it if the customer returns."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setModal(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={actionBusy}
              onClick={() =>
                runAction(
                  () =>
                    api.resolveConversation(conversationId, note.trim() || undefined, currentAgent()),
                  "Conversation resolved.",
                )
              }
            >
              Mark resolved
            </button>
          </>
        }
      >
        <label className="block">
          <span className="eyebrow mb-1.5 block">Resolution note (optional)</span>
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            rows={3}
            placeholder="How was it resolved?"
            className="field resize-none"
            autoFocus
          />
        </label>
      </Modal>
    </>
  );
}

function MessageBubble({
  message,
  isLatestInbound,
  onCorrected,
}: {
  message: Message;
  isLatestInbound: boolean;
  onCorrected: () => void;
}) {
  const toast = useToast();
  const [correcting, setCorrecting] = useState(false);
  const [value, setValue] = useState(message.intent || "other");
  const outbound = message.direction === "outbound";
  const agent = typeof message.meta?.agent === "string" ? message.meta.agent : null;
  const failed = message.delivery_status === "failed";

  const correct = async (next: string) => {
    setValue(next);
    setCorrecting(true);
    try {
      await api.correctMessageIntent(message.id, next, currentAgent());
      onCorrected();
    } catch (caught) {
      toast.push(
        caught instanceof ApiError ? caught.message : "Correction failed.",
        "error",
      );
    } finally {
      setCorrecting(false);
    }
  };

  return (
    <div className={cn("flex", outbound ? "justify-end" : "justify-start")}>
      <div className={cn("max-w-[86%] sm:max-w-[76%]", outbound && "text-right")}>
        <div
          className={cn(
            "mb-1 flex items-center gap-1.5 text-[9px] text-muted",
            outbound && "justify-end",
          )}
        >
          <span className="font-semibold">
            {outbound ? (agent ? `Agent · ${agent}` : "Orbit") : "Customer"}
          </span>
          <span>·</span>
          <span>{formatTime(message.created_at)}</span>
          {failed && <span className="font-bold text-danger">failed</span>}
        </div>
        <div
          className={cn(
            "rounded-2xl px-3.5 py-2.5 text-[12px] leading-5",
            outbound
              ? "rounded-br-[4px] bg-night text-paper/95"
              : "rounded-bl-[4px] border border-line bg-panel text-ink",
          )}
        >
          {message.entities.length > 0 && (
            <div className={cn("mb-1.5 flex flex-wrap gap-1", outbound && "justify-end")}>
              {message.entities.map((entity, index) => (
                <span
                  key={`${entity.type}-${index}`}
                  className={cn(
                    "rounded px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-[0.04em]",
                    outbound ? "bg-paper/10 text-paper/65" : "bg-paper text-muted",
                  )}
                >
                  {entity.type.replace(/_/g, " ")}
                  {entity.value ? ` · ${entity.value}` : ""}
                </span>
              ))}
            </div>
          )}
          <p className="whitespace-pre-wrap text-left">{message.text}</p>
        </div>

        {!outbound && message.intent && (
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[9px] font-semibold",
                intentTone(message.intent),
              )}
            >
              {message.intent.replace(/_/g, " ")}
            </span>
            <span
              className={cn(
                "text-[9px] font-bold tabular-nums",
                confidenceTone(message.confidence),
              )}
            >
              {message.confidence?.toFixed(2)}
            </span>
            {isLatestInbound && (
              <label className="relative ml-1 inline-flex items-center gap-1 text-[9px] text-muted">
                <span>Correct</span>
                <select
                  value={value}
                  disabled={correcting}
                  onChange={(event) => void correct(event.target.value)}
                  className="appearance-none rounded-md border border-line bg-panel py-0.5 pl-1.5 pr-5 text-[9px] font-semibold text-ink-soft"
                >
                  {INTENTS.map((intent) => (
                    <option key={intent} value={intent}>
                      {intent.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
                <ChevronDown
                  size={9}
                  className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-muted"
                />
              </label>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
