import {
  Activity,
  ArrowUpRight,
  BadgeCheck,
  Check,
  CircleAlert,
  Instagram,
  Loader2,
  LogOut,
  MessageCircle,
  PlugZap,
  RefreshCw,
  Radio,
  ShieldCheck,
  Smartphone,
  Unplug,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";

import { Modal } from "../components/Modal";
import { PortalBrand } from "../components/PortalBrand";
import { ApiError, api, getPortalToken, setPortalToken } from "../lib/api";
import { cn, formatDateTime, relativeTime } from "../lib/format";
import { usePolling } from "../lib/hooks";
import type {
  PortalChannel,
  PortalChannelName,
  PortalConfig,
  PortalEvent,
} from "../lib/types";

const CHANNELS: Array<{
  id: PortalChannelName;
  title: string;
  icon: typeof MessageCircle;
  blurb: string;
  note: string;
}> = [
  {
    id: "whatsapp",
    title: "WhatsApp Business",
    icon: MessageCircle,
    blurb: "Cloud API replies, approved templates, and login confirmations.",
    note: "24-hour service window · template required outside it",
  },
  {
    id: "instagram",
    title: "Instagram Messaging",
    icon: Instagram,
    blurb: "Direct messages handled by the same assistant and handoff queue.",
    note: "24-hour window · no proactive templates on this API",
  },
];

const EVENT_LABELS: Record<string, string> = {
  account_registered: "Workspace created",
  automation_activated: "Automation activated",
  channel_connected: "Channel connected",
  channel_disconnected: "Channel disconnected",
  welcome_message: "Login confirmation",
  phone_verified: "Phone number verified",
  assignment_notification: "Assignment notice",
};

function decodeChannel(state: string): PortalChannelName | null {
  try {
    const encoded = state.split(".")[0].replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(encoded));
    return payload.channel === "instagram" ? "instagram" : "whatsapp";
  } catch {
    return null;
  }
}

function eventTone(status: string): string {
  if (status === "sent" || status === "ok") return "bg-moss-soft text-moss";
  if (status === "failed") return "bg-danger-soft text-danger";
  if (status === "blocked") return "bg-amber-soft text-amber";
  return "bg-ink/[0.055] text-ink-soft";
}

export default function PortalHomePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const token = getPortalToken();
  const loader = useCallback(() => api.portalMe(), []);
  const { data, error, loading, refreshing, refresh } = usePolling(loader, 30_000, []);

  const [config, setConfig] = useState<PortalConfig | null>(null);
  const [verifyOpen, setVerifyOpen] = useState(false);
  const [devCode, setDevCode] = useState<string | null>(null);
  const [otp, setOtp] = useState("");
  const [verificationMessage, setVerificationMessage] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);

  const [phoneOpen, setPhoneOpen] = useState(false);
  const [newPhone, setNewPhone] = useState("");
  const [phonePassword, setPhonePassword] = useState("");
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [savingPhone, setSavingPhone] = useState(false);

  const [connectChannel, setConnectChannel] = useState<PortalChannelName | null>(null);
  const [oauthCode, setOauthCode] = useState<string | null>(null);
  const [oauthState, setOauthState] = useState<string | null>(null);
  const [accountId, setAccountId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [connectError, setConnectError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [oauthLoading, setOauthLoading] = useState(false);

  useEffect(() => {
    api.portalConfig().then(setConfig).catch(() => setConfig(null));
  }, []);

  useEffect(() => {
    if (!(error instanceof ApiError) || error.status !== 401) return;
    setPortalToken("");
    navigate("/portal/login", { replace: true });
  }, [error, navigate]);

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    if (!code || !state) return;
    const channel = decodeChannel(state);
    if (!channel) return;
    setOauthCode(code);
    setOauthState(state);
    setConnectChannel(channel);
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams]);

  const channelsById = useMemo(() => {
    const map = new Map<PortalChannelName, PortalChannel>();
    for (const channel of data?.channels || []) map.set(channel.channel, channel);
    return map;
  }, [data?.channels]);

  const latestWelcome = data?.recent_events.find((event) => event.event_type === "welcome_message");
  const connectedCount = data?.channels.length || 0;

  if (!token) return <Navigate to="/portal/login" replace />;

  function openConnect(channel: PortalChannelName) {
    setConnectChannel(channel);
    setOauthCode(null);
    setOauthState(null);
    setAccountId("");
    setDisplayName("");
    setWabaId("");
    setConnectError(null);
  }

  function closeConnect() {
    setConnectChannel(null);
    setOauthCode(null);
    setOauthState(null);
    setConnectError(null);
  }

  async function requestCode() {
    setVerifying(true);
    setVerificationMessage(null);
    try {
      const result = await api.portalRequestPhoneVerification();
      if (result.status === "sent") {
        setDevCode(result.dev_code);
        setVerificationMessage(
          result.dev_code
            ? "Development mode: the code is shown below."
            : "Code sent. Check your messages.",
        );
      } else {
        setVerificationMessage(result.message || "Verification is unavailable right now.");
      }
    } catch (caught) {
      setVerificationMessage(caught instanceof Error ? caught.message : "Could not send the code.");
    } finally {
      setVerifying(false);
    }
  }

  async function confirmCode(event: FormEvent) {
    event.preventDefault();
    setVerifying(true);
    setVerificationMessage(null);
    try {
      await api.portalConfirmPhone(otp.trim());
      setVerifyOpen(false);
      setOtp("");
      setDevCode(null);
      refresh();
    } catch (caught) {
      setVerificationMessage(caught instanceof Error ? caught.message : "Could not verify the code.");
    } finally {
      setVerifying(false);
    }
  }

  async function savePhone(event: FormEvent) {
    event.preventDefault();
    setSavingPhone(true);
    setPhoneError(null);
    try {
      await api.portalSetPhone(newPhone.trim(), phonePassword);
      setPhoneOpen(false);
      setNewPhone("");
      setPhonePassword("");
      refresh();
    } catch (caught) {
      setPhoneError(caught instanceof Error ? caught.message : "Could not save the number.");
    } finally {
      setSavingPhone(false);
    }
  }

  async function startOAuth(channel: PortalChannelName) {
    setOauthLoading(true);
    setConnectError(null);
    try {
      const result = await api.portalOAuthUrl(channel);
      if (result.configured && result.url) {
        window.location.assign(result.url);
        return;
      }
      setConnectError(
        result.message ||
          "Meta OAuth is not configured. Use the local demo connection for now.",
      );
    } catch (caught) {
      setConnectError(caught instanceof Error ? caught.message : "Could not start OAuth.");
    } finally {
      setOauthLoading(false);
    }
  }

  async function connect(event: FormEvent) {
    event.preventDefault();
    if (!connectChannel) return;
    setConnecting(true);
    setConnectError(null);
    try {
      if (oauthCode && oauthState) {
        await api.portalConnect(connectChannel, {
          mode: "oauth",
          authorization_code: oauthCode,
          state: oauthState,
          external_account_id: accountId.trim(),
          display_name: displayName.trim() || undefined,
          waba_id: wabaId.trim() || undefined,
        });
      } else {
        await api.portalConnect(connectChannel, {
          mode: "demo",
          external_account_id: accountId.trim(),
          display_name: displayName.trim() || undefined,
        });
      }
      closeConnect();
      refresh();
    } catch (caught) {
      setConnectError(caught instanceof Error ? caught.message : "Could not connect the channel.");
    } finally {
      setConnecting(false);
    }
  }

  async function disconnect(channel: PortalChannelName) {
    if (!window.confirm(`Disconnect ${channel}? Automation will stop on that channel.`)) return;
    try {
      await api.portalDisconnect(channel);
      refresh();
    } catch (caught) {
      window.alert(caught instanceof Error ? caught.message : "Could not disconnect.");
    }
  }

  async function logout() {
    try {
      await api.portalLogout();
    } catch {
      // The local token is cleared regardless.
    }
    setPortalToken("");
    navigate("/portal/login", { replace: true });
  }

  const activeChannel = connectChannel
    ? CHANNELS.find((channel) => channel.id === connectChannel)
    : null;

  return (
    <div className="min-h-screen bg-paper">
      <div className="mx-auto max-w-[1240px] px-4 pb-16 sm:px-6 lg:px-10">
        <header className="flex h-[80px] items-center justify-between gap-4">
          <PortalBrand />
          <div className="flex items-center gap-2 sm:gap-3">
            <a
              href="/"
              className="hidden items-center gap-1.5 text-[11px] font-semibold text-muted transition-colors hover:text-ink sm:inline-flex"
            >
              Operations console <ArrowUpRight size={12} />
            </a>
            <span className="hidden h-4 w-px bg-line sm:block" />
            <span className="grid h-8 w-8 place-items-center rounded-full border border-line bg-panel text-[10px] font-bold text-ink-soft">
              {data?.user.full_name
                .split(/\s+/)
                .slice(0, 2)
                .map((part) => part[0])
                .join("")
                .toUpperCase() || "…"}
            </span>
            <button type="button" onClick={logout} className="btn-ghost px-2.5 py-2">
              <LogOut size={14} />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </header>

        {loading && !data && (
          <div className="space-y-4">
            <div className="h-[190px] animate-pulse rounded-[24px] bg-line/30" />
            <div className="grid gap-4 md:grid-cols-2">
              <div className="h-[240px] animate-pulse rounded-[24px] bg-line/20" />
              <div className="h-[240px] animate-pulse rounded-[24px] bg-line/20" />
            </div>
          </div>
        )}

        {error && !(error instanceof ApiError && error.status === 401) && (
          <div className="surface mb-5 flex flex-col items-start gap-4 border-danger/20 bg-danger-soft/40 p-6">
            <CircleAlert size={20} className="text-danger" />
            <div>
              <p className="text-sm font-semibold text-ink">The workspace could not load</p>
              <p className="mt-1 text-[12px] leading-5 text-muted">{error.message}</p>
            </div>
            <button type="button" onClick={refresh} className="btn-secondary">
              <RefreshCw size={13} /> Try again
            </button>
          </div>
        )}

        {data && (
          <div className="space-y-5">
            <section className="relative overflow-hidden rounded-[26px] bg-night px-6 py-7 text-paper sm:px-9 sm:py-9">
              <div className="pointer-events-none absolute -right-24 -top-28 h-[300px] w-[300px] rounded-full border border-paper/10" />
              <div className="pointer-events-none absolute -right-6 -top-10 h-[190px] w-[190px] rounded-full border border-clay/35" />
              <div className="relative flex flex-col gap-7 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em]",
                        data.tenant.automation_enabled
                          ? "border-[#9AC7A5]/30 bg-[#9AC7A5]/10 text-[#B9D9C1]"
                          : "border-amber/40 bg-amber/10 text-[#E5C28C]",
                      )}
                    >
                      <span
                        className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          data.tenant.automation_enabled
                            ? "animate-pulse-soft bg-[#9AC7A5]"
                            : "bg-[#E5C28C]",
                        )}
                      />
                      {data.tenant.automation_enabled ? "Automation live" : "Automation paused"}
                    </span>
                    <span className="rounded-full border border-paper/15 px-2.5 py-1 text-[10px] font-semibold text-paper/55">
                      {data.tenant.plan} plan
                    </span>
                  </div>
                  <h1 className="mt-4 max-w-xl font-display text-[40px] leading-[1.02] tracking-tight sm:text-[48px]">
                    {data.tenant.name}
                  </h1>
                  <p className="mt-3 max-w-lg text-[12px] leading-6 text-paper/55">
                    Signed in as {data.user.full_name}
                    {data.user.email ? ` · ${data.user.email}` : ""}. The assistant is
                    answering on {connectedCount === 0 ? "no channels yet" : `${connectedCount} connected channel${connectedCount === 1 ? "" : "s"}`}.
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:min-w-[360px]">
                  <div className="rounded-2xl border border-paper/10 bg-paper/[0.04] p-3.5">
                    <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-paper/35">
                      Channels
                    </p>
                    <p className="mt-2 font-display text-2xl text-paper">{connectedCount}/2</p>
                  </div>
                  <div className="rounded-2xl border border-paper/10 bg-paper/[0.04] p-3.5">
                    <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-paper/35">
                      Login notice
                    </p>
                    <p className="mt-2 text-[12px] font-semibold leading-5 text-paper/85">
                      {latestWelcome?.status === "sent"
                        ? "Delivered"
                        : latestWelcome?.status === "blocked"
                          ? "Needs action"
                          : "Not sent yet"}
                    </p>
                  </div>
                  <div className="col-span-2 rounded-2xl border border-paper/10 bg-paper/[0.04] p-3.5 sm:col-span-1">
                    <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-paper/35">
                      Phone
                    </p>
                    <p className="mt-2 text-[12px] font-semibold leading-5 text-paper/85">
                      {data.user.phone
                        ? data.user.phone_verified
                          ? "Verified"
                          : "Verify now"
                        : "Not added"}
                    </p>
                  </div>
                </div>
              </div>
            </section>

            {data.user.phone && !data.user.phone_verified && (
              <section className="surface flex flex-col gap-4 border-amber/25 bg-amber-soft/45 p-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-amber text-paper">
                    <Smartphone size={15} />
                  </span>
                  <div>
                    <p className="text-[13px] font-semibold text-ink">
                      Confirm {data.user.phone} to unlock login confirmations
                    </p>
                    <p className="mt-1 max-w-2xl text-[11px] leading-5 text-muted">
                      Proactive WhatsApp messages require proof that the number belongs to
                      you. Verify once, then every sign-in can send an approved confirmation.
                    </p>
                  </div>
                </div>
                <button type="button" onClick={() => setVerifyOpen(true)} className="btn-primary shrink-0">
                  <BadgeCheck size={14} /> Verify number
                </button>
              </section>
            )}

            {data.user.phone && data.user.phone_verified && latestWelcome && (
              <section
                className={cn(
                  "surface flex items-start gap-3 p-4 text-[11px] leading-5",
                  latestWelcome.status === "sent"
                    ? "border-moss/20 bg-moss-soft/50 text-moss"
                    : "border-amber/20 bg-amber-soft/40 text-amber",
                )}
              >
                {latestWelcome.status === "sent" ? <Check size={15} /> : <CircleAlert size={15} />}
                <p>
                  <span className="font-semibold">
                    {latestWelcome.status === "sent"
                      ? "Login confirmation delivered."
                      : "Login confirmation was held back."}
                  </span>{" "}
                  {latestWelcome.status === "sent"
                    ? `Sent ${relativeTime(latestWelcome.created_at)} via WhatsApp template.`
                    : `Reason: ${String(latestWelcome.detail.reason || "requirements not met").replace(/_/g, " ")}.`}
                </p>
              </section>
            )}

            <div className="grid gap-4 lg:grid-cols-[1.35fr_0.65fr]">
              <section className="surface overflow-hidden">
                <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
                  <div>
                    <p className="eyebrow">Channel access</p>
                    <h2 className="mt-1 font-display text-[26px] leading-tight text-ink">
                      Connect the front door
                    </h2>
                  </div>
                  <span className="chip">
                    <Radio size={11} /> {connectedCount} live
                  </span>
                </div>
                <div className="divide-y divide-line">
                  {CHANNELS.map((channel) => {
                    const Icon = channel.icon;
                    const connection = channelsById.get(channel.id);
                    return (
                      <div key={channel.id} className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
                        <span
                          className={cn(
                            "grid h-11 w-11 shrink-0 place-items-center rounded-2xl border",
                            connection
                              ? "border-moss/20 bg-moss-soft text-moss"
                              : "border-line bg-paper text-muted",
                          )}
                        >
                          <Icon size={19} strokeWidth={1.7} />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-[13px] font-semibold text-ink">{channel.title}</p>
                            <span
                              className={cn(
                                "rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.1em]",
                                connection ? "bg-moss-soft text-moss" : "bg-paper text-muted",
                              )}
                            >
                              {connection ? "connected" : "not connected"}
                            </span>
                          </div>
                          <p className="mt-1 text-[11px] leading-5 text-muted">
                            {connection
                              ? `${connection.display_name || connection.external_account_id} · ${connection.external_account_id}`
                              : channel.blurb}
                          </p>
                          <p className="mt-1 text-[10px] text-muted/75">{channel.note}</p>
                        </div>
                        {connection ? (
                          <button
                            type="button"
                            onClick={() => disconnect(channel.id)}
                            className="btn-secondary shrink-0 text-danger hover:border-danger/30"
                          >
                            <Unplug size={13} /> Disconnect
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => openConnect(channel.id)}
                            className="btn-primary shrink-0"
                          >
                            <PlugZap size={13} /> Connect
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
                <div className="flex items-start gap-2.5 border-t border-line bg-paper/50 px-5 py-3.5 text-[10px] leading-5 text-muted">
                  <ShieldCheck size={13} className="mt-0.5 shrink-0 text-moss" />
                  Access tokens are encrypted at rest. Orbit never asks for, receives, or
                  stores a Meta account password.
                </div>
              </section>

              <div className="space-y-4">
                <section className="surface p-5">
                  <p className="eyebrow">Account</p>
                  <h2 className="mt-1 font-display text-[24px] leading-tight text-ink">
                    Owner details
                  </h2>
                  <dl className="mt-4 space-y-3 text-[11px]">
                    {[
                      ["Name", data.user.full_name],
                      ["Email", data.user.email || "Not added"],
                      ["Phone", data.user.phone || "Not added"],
                      ["Role", data.user.role],
                      ["Last sign-in", data.user.last_login_at ? formatDateTime(data.user.last_login_at) : "—"],
                    ].map(([label, value]) => (
                      <div key={label} className="flex items-start justify-between gap-4 border-b border-line/70 pb-2.5 last:border-0 last:pb-0">
                        <dt className="shrink-0 font-semibold uppercase tracking-[0.08em] text-muted">{label}</dt>
                        <dd className="text-right font-medium text-ink-soft">{value}</dd>
                      </div>
                    ))}
                  </dl>
                  <button
                    type="button"
                    onClick={() => {
                      setNewPhone(data.user.phone || "");
                      setPhoneError(null);
                      setPhonePassword("");
                      setPhoneOpen(true);
                    }}
                    className="btn-secondary mt-4 w-full"
                  >
                    <Smartphone size={13} />
                    {data.user.phone ? "Change notification number" : "Add a phone number"}
                  </button>
                  <div className="mt-3 rounded-xl border border-line bg-paper/60 p-3 text-[10px] leading-4 text-muted">
                    Activation messages use{" "}
                    <span className="font-semibold text-ink-soft">{config?.welcome_template || "an approved template"}</span>.
                    Template approval happens in Meta&apos;s console.
                  </div>
                </section>

                <section className="surface p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="eyebrow">Audit trail</p>
                      <h2 className="mt-1 font-display text-[24px] leading-tight text-ink">
                        Recent activity
                      </h2>
                    </div>
                    <button
                      type="button"
                      onClick={refresh}
                      className="btn-ghost p-2"
                      aria-label="Refresh activity"
                    >
                      <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
                    </button>
                  </div>
                  <div className="mt-3 max-h-[360px] space-y-2 overflow-auto pr-1">
                    {data.recent_events.length === 0 && (
                      <p className="py-6 text-center text-[11px] text-muted">
                        Activity appears here after your first sign-in.
                      </p>
                    )}
                    {data.recent_events.slice(0, 12).map((event) => (
                      <ActivityRow key={event.id} event={event} />
                    ))}
                  </div>
                </section>
              </div>
            </div>

            <div className="flex flex-col gap-2 border-t border-line pt-5 text-[10px] leading-4 text-muted sm:flex-row sm:items-center sm:justify-between">
              <p className="inline-flex items-center gap-1.5">
                <Activity size={12} /> Workspace {data.tenant.slug} · refreshed{" "}
                {refreshing ? "now" : "every 30s"}
              </p>
              <p>Human handoff stays available from the operations console.</p>
            </div>
          </div>
        )}
      </div>

      <Modal
        open={phoneOpen}
        onClose={() => setPhoneOpen(false)}
        title={data?.user.phone ? "Change notification number" : "Add a notification number"}
        description="Orbit sends login confirmations and assignment notices to this number. Changing it requires re-verification."
      >
        <form onSubmit={savePhone} className="space-y-4">
          <label className="block">
            <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
              WhatsApp number
            </span>
            <input
              className="field"
              value={newPhone}
              onChange={(event) => setNewPhone(event.target.value)}
              placeholder="+91 99000 00001"
              autoComplete="tel"
              required
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
              Current password
            </span>
            <input
              className="field"
              type="password"
              value={phonePassword}
              onChange={(event) => setPhonePassword(event.target.value)}
              placeholder="Confirm it is you"
              autoComplete="current-password"
              required
            />
          </label>
          {phoneError && (
            <p className="rounded-xl border border-danger/20 bg-danger-soft/60 px-3.5 py-2.5 text-[11px] leading-5 text-danger">
              {phoneError}
            </p>
          )}
          <button type="submit" disabled={savingPhone} className="btn-primary w-full">
            {savingPhone ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
            {savingPhone ? "Saving" : "Save number"}
          </button>
        </form>
      </Modal>

      <Modal
        open={verifyOpen}
        onClose={() => setVerifyOpen(false)}
        title="Verify your WhatsApp number"
        description={
          data?.user.phone
            ? `We will send a one-time code to ${data.user.phone}.`
            : "Add a phone number to the workspace first."
        }
      >
        <div className="space-y-4">
          <button
            type="button"
            onClick={requestCode}
            disabled={verifying}
            className="btn-secondary w-full"
          >
            {verifying ? <Loader2 size={14} className="animate-spin" /> : <Smartphone size={14} />}
            Send one-time code
          </button>

          {devCode && (
            <div className="rounded-xl border border-clay/25 bg-clay-soft/50 p-3.5 text-center">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-clay">
                Development code
              </p>
              <p className="mt-1 font-display text-3xl tracking-[0.18em] text-ink">{devCode}</p>
            </div>
          )}

          <form onSubmit={confirmCode} className="flex gap-2">
            <input
              className="field flex-1 text-center font-display text-xl tracking-[0.3em]"
              value={otp}
              onChange={(event) => setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="000000"
              inputMode="numeric"
              maxLength={6}
              required
            />
            <button type="submit" disabled={verifying || otp.length !== 6} className="btn-primary">
              {verifying ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
              Verify
            </button>
          </form>

          {verificationMessage && (
            <p className="text-[11px] leading-5 text-muted">{verificationMessage}</p>
          )}
          <p className="text-[10px] leading-4 text-muted">
            In production this code is delivered by your configured OTP webhook. The
            development code is only returned outside production.
          </p>
        </div>
      </Modal>

      <Modal
        open={Boolean(connectChannel)}
        onClose={closeConnect}
        title={`Connect ${activeChannel?.title || "channel"}`}
        description={
          oauthCode
            ? "Finish the Meta connection with the account id Meta returned to your app."
            : "Choose a real Meta permission flow or a local demo connection."
        }
      >
        <div className="space-y-5">
          {!oauthCode && (
            <div className="rounded-2xl border border-line bg-paper/60 p-4">
              <p className="text-[12px] font-semibold text-ink">Connect with Meta</p>
              <p className="mt-1 text-[11px] leading-5 text-muted">
                Opens Meta&apos;s permission screen. Orbit receives a scoped token, never your
                password. This requires a configured Meta app.
              </p>
              <button
                type="button"
                onClick={() => connectChannel && startOAuth(connectChannel)}
                disabled={oauthLoading}
                className="btn-primary mt-3 w-full"
              >
                {oauthLoading ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
                {config?.meta_oauth_configured ? "Open Meta permissions" : "Check Meta setup"}
              </button>
            </div>
          )}

          {!oauthCode && config?.mock_channel_connect && (
            <div className="flex items-center gap-3">
              <span className="h-px flex-1 bg-line" />
              <span className="text-[9px] font-bold uppercase tracking-[0.16em] text-muted">
                local demo
              </span>
              <span className="h-px flex-1 bg-line" />
            </div>
          )}

          <form onSubmit={connect} className="space-y-3">
            {oauthCode && (
              <p className="rounded-xl border border-moss/20 bg-moss-soft/50 px-3.5 py-2.5 text-[11px] leading-5 text-moss">
                Meta returned an authorization code. Enter the account id from your app
                dashboard to finish the exchange.
              </p>
            )}
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                {connectChannel === "whatsapp" ? "Phone number id" : "Instagram account id"}
              </span>
              <input
                className="field"
                value={accountId}
                onChange={(event) => setAccountId(event.target.value)}
                placeholder={connectChannel === "whatsapp" ? "123456789012345" : "17841400000000000"}
                required
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                Display name <span className="font-medium normal-case tracking-normal">(optional)</span>
              </span>
              <input
                className="field"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="Aurora Living"
              />
            </label>
            {oauthCode && connectChannel === "whatsapp" && (
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                  WABA id <span className="font-medium normal-case tracking-normal">(optional)</span>
                </span>
                <input
                  className="field"
                  value={wabaId}
                  onChange={(event) => setWabaId(event.target.value)}
                  placeholder="WhatsApp Business Account id"
                />
              </label>
            )}

            {connectError && (
              <p className="rounded-xl border border-danger/20 bg-danger-soft/60 px-3.5 py-2.5 text-[11px] leading-5 text-danger">
                {connectError}
              </p>
            )}

            {(oauthCode || config?.mock_channel_connect) && (
              <button type="submit" disabled={connecting} className="btn-primary w-full">
                {connecting ? <Loader2 size={14} className="animate-spin" /> : <PlugZap size={14} />}
                {oauthCode ? "Finish connection" : "Enable demo connection"}
              </button>
            )}
          </form>

          {!oauthCode && !config?.mock_channel_connect && (
            <p className="text-[10px] leading-4 text-muted">
              Demo connections are disabled in this environment. Configure the Meta app id
              and secret to connect a real account.
            </p>
          )}
        </div>
      </Modal>
    </div>
  );
}

function ActivityRow({ event }: { event: PortalEvent }) {
  const label = EVENT_LABELS[event.event_type] || event.event_type.replace(/_/g, " ");
  const reason =
    typeof event.detail.reason === "string"
      ? event.detail.reason.replace(/_/g, " ")
      : null;
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-line/70 bg-panel px-3 py-2.5">
      <span className={cn("mt-0.5 rounded-full px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-[0.08em]", eventTone(event.status))}>
        {event.status}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[11px] font-semibold text-ink">{label}</p>
        <p className="mt-0.5 text-[10px] text-muted">
          {event.channel ? `${event.channel} · ` : ""}
          {relativeTime(event.created_at)}
          {reason ? ` · ${reason}` : ""}
        </p>
      </div>
    </div>
  );
}
