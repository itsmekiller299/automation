import { Check, Loader2, Lock, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { PortalFrame } from "../components/PortalBrand";
import { ApiError, api, getPortalToken, setPortalToken } from "../lib/api";

const STEPS = [
  {
    title: "Create the workspace",
    detail: "Business name, owner account, and a password only you know.",
  },
  {
    title: "Prove the number",
    detail: "A one-time code unlocks proactive WhatsApp confirmations.",
  },
  {
    title: "Connect Meta",
    detail: "Grant scoped access to WhatsApp Business and Instagram.",
  },
];

export default function PortalRegisterPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    business_name: "",
    full_name: "",
    email: "",
    phone: "",
    password: "",
    confirm: "",
  });
  const [optIn, setOptIn] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (getPortalToken()) return <Navigate to="/portal" replace />;

  function update(key: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (form.password.length < 10) {
      setError("Use at least 10 characters for the password.");
      return;
    }
    if (form.password !== form.confirm) {
      setError("The passwords do not match.");
      return;
    }
    if (!form.email.trim() && !form.phone.trim()) {
      setError("Add an email address or a phone number.");
      return;
    }
    setLoading(true);
    try {
      const auth = await api.portalRegister({
        business_name: form.business_name.trim(),
        full_name: form.full_name.trim(),
        email: form.email.trim() || undefined,
        phone: form.phone.trim() || undefined,
        password: form.password,
        welcome_opt_in: optIn,
      });
      setPortalToken(auth.token);
      navigate("/portal", { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not create the workspace.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PortalFrame
      wide
      aside={
        <p className="text-[12px] text-muted">
          Already have an account?{" "}
          <Link to="/portal/login" className="font-semibold text-clay hover:text-ink">
            Sign in
          </Link>
        </p>
      }
    >
      <div className="grid gap-5 py-4 lg:grid-cols-[0.82fr_1.18fr]">
        <section className="relative overflow-hidden rounded-[24px] bg-night p-8 text-paper sm:p-10">
          <div className="pointer-events-none absolute -right-24 -top-20 h-[260px] w-[260px] rounded-full border border-clay/30" />
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-paper/40">
            Three calm steps
          </p>
          <h1 className="mt-3 font-display text-[40px] leading-[1.04] tracking-tight">
            Open the front desk.
          </h1>
          <p className="mt-4 max-w-sm text-[12px] leading-6 text-paper/55">
            One workspace for the assistant, your team, and the channels your customers
            already use.
          </p>

          <ol className="mt-9 space-y-6">
            {STEPS.map((step, index) => (
              <li key={step.title} className="flex gap-4">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-paper/20 font-display text-base text-paper/80">
                  {index + 1}
                </span>
                <div>
                  <p className="text-[12px] font-semibold text-paper/90">{step.title}</p>
                  <p className="mt-1 text-[11px] leading-5 text-paper/45">{step.detail}</p>
                </div>
              </li>
            ))}
          </ol>

          <div className="mt-10 flex items-start gap-2.5 border-t border-paper/10 pt-5 text-[11px] leading-5 text-paper/45">
            <ShieldCheck size={15} className="mt-0.5 shrink-0 text-paper/60" />
            Password sign-in is for your Orbit account only. Meta handles channel access on
            its own permission screen.
          </div>
        </section>

        <section className="surface p-7 sm:p-9">
          <p className="eyebrow">New workspace</p>
          <h2 className="mt-1.5 font-display text-[34px] leading-none tracking-tight text-ink">
            Create your account
          </h2>

          <form className="mt-7 space-y-4" onSubmit={submit}>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                  Business name
                </span>
                <input
                  className="field"
                  value={form.business_name}
                  onChange={(event) => update("business_name", event.target.value)}
                  placeholder="Aurora Living"
                  required
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                  Your name
                </span>
                <input
                  className="field"
                  value={form.full_name}
                  onChange={(event) => update("full_name", event.target.value)}
                  placeholder="Siva Kumar"
                  autoComplete="name"
                  required
                />
              </label>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                  Email
                </span>
                <input
                  className="field"
                  type="email"
                  value={form.email}
                  onChange={(event) => update("email", event.target.value)}
                  placeholder="you@business.com"
                  autoComplete="email"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                  WhatsApp number
                </span>
                <input
                  className="field"
                  value={form.phone}
                  onChange={(event) => update("phone", event.target.value)}
                  placeholder="+91 99000 00001"
                  autoComplete="tel"
                />
              </label>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                  Password
                </span>
                <input
                  className="field"
                  type="password"
                  value={form.password}
                  onChange={(event) => update("password", event.target.value)}
                  placeholder="At least 10 characters"
                  autoComplete="new-password"
                  required
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                  Confirm password
                </span>
                <input
                  className="field"
                  type="password"
                  value={form.confirm}
                  onChange={(event) => update("confirm", event.target.value)}
                  placeholder="Repeat it"
                  autoComplete="new-password"
                  required
                />
              </label>
            </div>

            <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-line bg-paper/60 p-3.5">
              <input
                type="checkbox"
                checked={optIn}
                onChange={(event) => setOptIn(event.target.checked)}
                className="mt-0.5 h-4 w-4 accent-clay"
              />
              <span className="text-[11px] leading-5 text-muted">
                <span className="font-semibold text-ink">
                  Send me WhatsApp confirmations about this workspace.
                </span>{" "}
                You can withdraw consent at any time. Messages use an approved template and
                stop outside Meta&apos;s rules.
              </span>
            </label>

            {error && (
              <p className="rounded-xl border border-danger/20 bg-danger-soft/60 px-3.5 py-2.5 text-[12px] leading-5 text-danger">
                {error}
              </p>
            )}

            <button type="submit" disabled={loading} className="btn-primary w-full py-2.5">
              {loading ? <Loader2 size={15} className="animate-spin" /> : <Lock size={14} />}
              {loading ? "Creating workspace" : "Create workspace"}
              {!loading && <Check size={14} className="ml-auto" />}
            </button>
          </form>
        </section>
      </div>
    </PortalFrame>
  );
}
