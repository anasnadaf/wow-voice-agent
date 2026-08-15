"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { setToken, verifyToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [token, setTokenInput] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await verifyToken(token.trim());
      setToken(token.trim());
      router.push("/dashboard");
    } catch {
      setError("That token was not accepted. Check it and try again.");
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <p className="text-center text-xs uppercase tracking-[0.3em] text-brass">
          Whispers of the Wind
        </p>
        <h1 className="mt-3 text-center font-display text-4xl text-cream">Admin sign in</h1>
        <form
          onSubmit={onSubmit}
          className="mt-8 flex flex-col gap-5 rounded-xl border border-line bg-pane p-8"
        >
          <label className="block">
            <span className="mb-2 block text-xs uppercase tracking-[0.2em] text-stone">
              Access token
            </span>
            <input
              type="password"
              value={token}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="Paste your bearer token"
              autoFocus
              className="w-full rounded-md border border-line bg-ink px-4 py-3 text-cream placeholder:text-stone/50 outline-none transition focus:border-brass"
            />
          </label>
          {error && <p className="text-sm text-danger">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-brass px-6 py-3 text-sm font-medium uppercase tracking-[0.2em] text-ink transition hover:brightness-110 disabled:opacity-60"
          >
            {busy ? "Verifying…" : "Sign in"}
          </button>
          <p className="text-center text-xs text-stone">
            In local dev with no auth configured, submit with an empty field.
          </p>
        </form>
      </div>
    </main>
  );
}
