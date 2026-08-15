"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError, requestCall } from "@/lib/api";

const E164_RE = /^\+[1-9]\d{7,14}$/;

function RequestCallForm() {
  const [name, setName] = useState("");
  const [code, setCode] = useState("+91");
  const [number, setNumber] = useState("");
  const [consent, setConsent] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [serverError, setServerError] = useState("");

  const validate = (): string | null => {
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = "Please tell us your name.";
    const phone = `${code.trim()}${number.replace(/[\s-]/g, "")}`;
    if (!/^\+\d{1,3}$/.test(code.trim())) next.phone = "Country code should look like +91.";
    else if (!E164_RE.test(phone)) next.phone = "Please enter a valid phone number.";
    if (!consent) next.consent = "We can only call you with your consent.";
    setErrors(next);
    return Object.keys(next).length === 0 ? phone : null;
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError("");
    const phone = validate();
    if (!phone) return;
    setSubmitting(true);
    try {
      await requestCall(name.trim(), phone);
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setServerError("You have requested a few calls already — please try again in an hour.");
      } else if (err instanceof ApiError && err.status === 403) {
        setServerError("This number has opted out of calls. Reach us at sales@divyasree.com.");
      } else {
        setServerError(err instanceof Error ? err.message : "Something went wrong.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <div className="flex h-full min-h-[24rem] flex-col items-center justify-center gap-5 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full border border-brass text-brass">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M5 12.5l4.5 4.5L19 7.5"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <h3 className="font-display text-3xl text-cream">You&apos;ll receive a call shortly</h3>
        <p className="max-w-xs text-sm leading-relaxed text-stone">
          Our advisor is dialling {name.trim() ? name.trim().split(" ")[0] : "you"} at{" "}
          <span className="text-cream">{`${code}${number}`}</span>. Keep your phone close.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
      <div>
        <p className="text-xs uppercase tracking-[0.25em] text-brass">Private preview</p>
        <h3 className="mt-2 font-display text-3xl text-cream">Request a call</h3>
        <p className="mt-2 text-sm leading-relaxed text-stone">
          Share your number and our advisory team will call you within minutes.
        </p>
      </div>

      <label className="block">
        <span className="mb-2 block text-xs uppercase tracking-[0.2em] text-stone">Full name</span>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Aarav Sharma"
          autoComplete="name"
          className="w-full rounded-md border border-line bg-ink px-4 py-3 text-cream placeholder:text-stone/50 outline-none transition focus:border-brass"
        />
        {errors.name && <span className="mt-1.5 block text-sm text-danger">{errors.name}</span>}
      </label>

      <label className="block">
        <span className="mb-2 block text-xs uppercase tracking-[0.2em] text-stone">Phone</span>
        <div className="flex gap-2">
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            aria-label="Country code"
            className="w-20 rounded-md border border-line bg-ink px-3 py-3 text-center text-cream outline-none transition focus:border-brass"
          />
          <input
            type="tel"
            value={number}
            onChange={(e) => setNumber(e.target.value.replace(/[^\d\s-]/g, ""))}
            placeholder="98765 43210"
            autoComplete="tel-national"
            inputMode="numeric"
            className="flex-1 rounded-md border border-line bg-ink px-4 py-3 tracking-wide text-cream placeholder:text-stone/50 outline-none transition focus:border-brass"
          />
        </div>
        {errors.phone && <span className="mt-1.5 block text-sm text-danger">{errors.phone}</span>}
      </label>

      <label className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--brass)]"
        />
        <span className="text-sm leading-relaxed text-stone">
          I agree to receive a call from the Whispers of the Wind advisory team about villa plots
          at Nandi Valley.
        </span>
      </label>
      {errors.consent && <span className="-mt-4 block text-sm text-danger">{errors.consent}</span>}

      {serverError && (
        <p className="rounded-md border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
          {serverError}
        </p>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="rounded-md bg-brass px-6 py-3.5 text-sm font-medium uppercase tracking-[0.2em] text-ink transition hover:brightness-110 disabled:opacity-60"
      >
        {submitting ? "Connecting…" : "Call me"}
      </button>
    </form>
  );
}

const STATS: Array<[string, string]> = [
  ["74%", "open space across the estate"],
  ["20,000 sq.ft.", "clubhouse with resort amenities"],
  ["₹92.4L+", "villa plots, all-inclusive"],
];

export default function LandingPage() {
  return (
    <main className="flex min-h-screen flex-col">
      <header className="border-b border-line">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-5">
          <p className="font-display text-xl tracking-wide text-cream">
            Divyasree <span className="italic text-brass">Whispers of the Wind</span>
          </p>
          <p className="hidden text-xs uppercase tracking-[0.25em] text-stone sm:block">
            Nandi Valley · North Bengaluru
          </p>
        </div>
      </header>

      <section className="mx-auto grid w-full max-w-6xl flex-1 gap-14 px-6 py-16 lg:grid-cols-[1.15fr_1fr] lg:gap-20 lg:py-24">
        <div className="flex flex-col justify-center">
          <p className="text-xs uppercase tracking-[0.3em] text-brass">
            Private Valley villa plots
          </p>
          <h1 className="mt-5 font-display text-5xl leading-[1.08] text-cream sm:text-6xl">
            Where the valley
            <br />
            <span className="italic text-brass">whispers</span>, build a life
            <br />
            that listens.
          </h1>
          <p className="mt-7 max-w-lg text-base leading-relaxed text-stone">
            A limited collection of villa plots folded into the Private Valley beneath Nandi
            Hills — minutes from the airport corridor, a world away from the city. Craft your
            villa amid 74% open space, with a 20,000 sq.ft. clubhouse at the heart of the
            estate.
          </p>

          <dl className="mt-12 grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3">
            {STATS.map(([value, label]) => (
              <div key={label} className="bg-pane px-6 py-5">
                <dt className="sr-only">{label}</dt>
                <dd className="font-display text-3xl text-brass">{value}</dd>
                <dd className="mt-1 text-xs uppercase tracking-[0.15em] text-stone">{label}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="flex items-center">
          <div className="w-full space-y-4">
            <Link
              href="/demo"
              className="flex items-center justify-between gap-4 rounded-xl border border-brass bg-brass-soft px-8 py-6 transition hover:bg-brass/20"
            >
              <span>
                <span className="block font-display text-xl text-cream">
                  Speak with our consultant now
                </span>
                <span className="mt-1 block text-sm text-stone">
                  A live voice conversation, right in your browser
                </span>
              </span>
              <span aria-hidden className="text-2xl text-brass">
                &rarr;
              </span>
            </Link>

            <div className="rounded-xl border border-line bg-pane p-8 shadow-[0_30px_80px_-40px_rgba(0,0,0,0.9)] sm:p-10">
              <p className="mb-6 text-xs uppercase tracking-[0.2em] text-stone">
                Or request a call back
              </p>
              <RequestCallForm />
            </div>
          </div>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-2 px-6 py-6 text-xs text-stone sm:flex-row sm:items-center sm:justify-between">
          <p>Divyasree Developers · Whispers of the Wind, Nandi Valley, North Bengaluru</p>
          <p>RERA registered · Site visits by appointment</p>
        </div>
      </footer>
    </main>
  );
}
