import { ArrowRight, Clock3, Loader2, Lock, MessagesSquare, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { PortalFrame } from "../components/PortalBrand";
import { ApiError, api, getPortalToken, setPortalToken } from "../lib/api";

export default function PortalLoginPage() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (getPortalToken()) return <Navigate to="/portal" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const auth = await api.portalLogin(identifier, password);
      setPortalToken(auth.token);
      navigate("/portal", { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not sign in.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PortalFrame>
      <div className="grid w-full overflow-hidden rounded-[28px] border border-line bg-panel shadow-lift lg:grid-cols-[1.06fr_0.94fr]">
        <section className="relative isolate overflow-hidden bg-night p-8 text-paper sm:p-11 lg:p-14">
          <div className="pointer-events-none absolute -right-28 -top-24 h-[360px] w-[360px] rounded-full border border-paper/10" />
          <div className="pointer-events-none absolute -right-10 -top-6 h-[230px] w-[230px] rounded-full border border-clay/40" />
          <div className="pointer-events-none absolute -bottom-32 -left-24 h-[300px] w-[300px] rounded-full border border-paper/[0.07]" />
          <span className="grid h-9 w-9 place-items-center rounded-full border border-paper/20 bg-paper/[0.05]">
            <span className="h-2 w-2 rounded-full bg-clay" />
          </span>
          <p className="mt-10 text-[10px] font-bold uppercase tracking-[0.2em] text-paper/45">
            A quieter front desk
          </p>
          <h1 className="mt-4 max-w-md font-display text-[42px] leading-[1.02] tracking-tight text-paper sm:text-[54px]">
            Your channels, awake the moment you arrive.
          </h1>
          <p className="mt-6 max-w-sm text-[13px] leading-6 text-paper/55">
            Sign in to activate the assistant, confirm your WhatsApp number, and connect
            Instagram through Meta&apos;s permission screen.
          </p>

          <div className="mt-10 space-y-4 border-t border-paper/10 pt-7">
            {[
              {
                icon: MessagesSquare,
                title: "Official channels only",
                detail: "WhatsApp Cloud API and Instagram Messaging. No stored channel passwords.",
              },
              {
                icon: ShieldCheck,
                title: "Consent before contact",
                detail: "Proactive messages need opt-in, a verified number, and an approved template.",
              },
              {
                icon: Clock3,
                title: "Honest about windows",
                detail: "Outside 24 hours, WhatsApp falls back to an approved template.",
              },
            ].map((item) => (
              <div key={item.title} className="flex gap-3.5">
                <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full border border-paper/15 text-paper/70">
                  <item.icon size={13} strokeWidth={1.7} />
                </span>
                <div>
                  <p className="text-[12px] font-semibold text-paper/90">{item.title}</p>
                  <p className="mt-0.5 text-[11px] leading-5 text-paper/45">{item.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="p-8 sm:p-11 lg:p-14">
          <p className="eyebrow">Welcome back</p>
          <h2 className="mt-2 font-display text-[38px] leading-none tracking-tight text-ink">
            Sign in
          </h2>
          <p className="mt-3 max-w-sm text-[12px] leading-5 text-muted">
            Use the phone number or email on your account. Signing in activates automation
            and sends your confirmation when everything is in place.
          </p>

          <form className="mt-8 space-y-4" onSubmit={submit}>
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                Phone or email
              </span>
              <input
                className="field"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                placeholder="+91 99000 00001"
                autoComplete="username"
                required
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                Password
              </span>
              <input
                className="field"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Your password"
                autoComplete="current-password"
                required
              />
            </label>

            {error && (
              <p className="rounded-xl border border-danger/20 bg-danger-soft/60 px-3.5 py-2.5 text-[12px] leading-5 text-danger">
                {error}
              </p>
            )}

            <button type="submit" disabled={loading} className="btn-primary w-full py-2.5">
              {loading ? <Loader2 size={15} className="animate-spin" /> : <Lock size={14} />}
              {loading ? "Signing in" : "Sign in and activate"}
              {!loading && <ArrowRight size={14} className="ml-auto" />}
            </button>
          </form>

          <p className="mt-6 text-[12px] text-muted">
            New here?{" "}
            <Link to="/portal/register" className="font-semibold text-clay hover:text-ink">
              Create a workspace
            </Link>
          </p>

          <div className="mt-10 rounded-2xl border border-line bg-paper/70 p-4">
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted">
              Security note
            </p>
            <p className="mt-2 text-[11px] leading-5 text-muted">
              Orbit never collects your Instagram or WhatsApp login. Channel access is granted
              with a scoped Meta token that you can revoke at any time.
            </p>
          </div>
        </section>
      </div>
    </PortalFrame>
  );
}
