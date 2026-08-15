"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { PipecatClient, RTVIEvent, type TransportState } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

type Line = { role: "agent" | "you"; text: string };

const LIVE_STATES: TransportState[] = ["connecting", "connected", "ready"];

function statusLabel(state: TransportState): string {
  switch (state) {
    case "initializing":
    case "initialized":
    case "authenticating":
    case "connecting":
      return "Connecting…";
    case "connected":
    case "ready":
      return "Live — start speaking";
    case "disconnecting":
      return "Ending…";
    case "error":
      return "Something went wrong";
    default:
      return "Ready when you are";
  }
}

export default function DemoPage() {
  const clientRef = useRef<PipecatClient | null>(null);
  const [state, setState] = useState<TransportState>("disconnected");
  const [lines, setLines] = useState<Line[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight });
  }, [lines]);

  // A call left running when the visitor navigates away keeps a pipeline (and
  // its vendor connections) alive on the server, so always tear it down.
  useEffect(() => {
    return () => {
      clientRef.current?.disconnect().catch(() => {});
      clientRef.current = null;
    };
  }, []);

  const append = useCallback((role: Line["role"], text: string) => {
    const clean = text.trim();
    if (!clean) return;
    setLines((prev) => {
      const last = prev[prev.length - 1];
      // The agent streams a reply in fragments; keep it as one bubble.
      if (last?.role === role && role === "agent") {
        return [...prev.slice(0, -1), { role, text: `${last.text} ${clean}`.trim() }];
      }
      return [...prev, { role, text: clean }];
    });
  }, []);

  const start = async () => {
    setError("");
    setLines([]);
    try {
      const client = new PipecatClient({
        transport: new SmallWebRTCTransport(),
        enableMic: true,
        enableCam: false,
        callbacks: {
          onTransportStateChanged: (s) => setState(s),
          onError: (message) => setError(String(message)),
        },
      });
      clientRef.current = client;

      client.on(RTVIEvent.UserTranscript, (data) => {
        if (data.final) append("you", data.text);
      });
      client.on(RTVIEvent.BotTranscript, (data) => append("agent", data.text));

      await client.connect({
        webrtcRequestParams: {
          endpoint: `${API_URL}/api/webrtc/offer`,
          requestData: { visitor_name: name.trim() || undefined },
        },
      });
    } catch (err) {
      setError(
        err instanceof Error
          ? `${err.message} — allow microphone access and make sure the agent server is running.`
          : "Could not start the call.",
      );
      setState("error");
    }
  };

  const stop = async () => {
    await clientRef.current?.disconnect().catch(() => {});
    clientRef.current = null;
    setState("disconnected");
  };

  const live = LIVE_STATES.includes(state);

  return (
    <main className="flex min-h-screen flex-col">
      <header className="border-b border-line">
        <div className="mx-auto flex w-full max-w-4xl items-center justify-between px-6 py-5">
          <Link href="/" className="font-display text-xl tracking-wide text-cream">
            Divyasree <span className="italic text-brass">Whispers of the Wind</span>
          </Link>
          <p className="hidden text-xs uppercase tracking-[0.25em] text-stone sm:block">
            Speak with our consultant
          </p>
        </div>
      </header>

      <section className="mx-auto w-full max-w-4xl flex-1 px-6 py-14">
        <p className="text-xs uppercase tracking-[0.3em] text-brass">Live voice demo</p>
        <h1 className="mt-4 font-display text-4xl leading-tight text-cream sm:text-5xl">
          Talk to Ananya, our
          <span className="italic text-brass"> pre-sales consultant</span>.
        </h1>
        <p className="mt-5 max-w-2xl text-base leading-relaxed text-stone">
          She will introduce the Private Valley, ask what brings you to Nandi Valley, and
          arrange a follow-up with a Property Expert if it sounds like a fit. Speak naturally —
          you can interrupt her at any time, in English or Hindi.
        </p>

        <div className="mt-10 rounded-xl border border-line bg-pane p-8 shadow-[0_30px_80px_-40px_rgba(0,0,0,0.9)]">
          <div className="flex flex-wrap items-end gap-4">
            <label className="flex-1 min-w-[16rem]">
              <span className="text-xs uppercase tracking-[0.15em] text-stone">
                Your name (optional)
              </span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={live}
                placeholder="So she can greet you properly"
                className="mt-2 w-full rounded-md border border-line bg-raised px-4 py-3 text-cream outline-none placeholder:text-stone/60 focus:border-brass disabled:opacity-50"
              />
            </label>
            {live ? (
              <button
                onClick={stop}
                className="rounded-md border border-danger px-6 py-3 text-danger transition hover:bg-danger/10"
              >
                End call
              </button>
            ) : (
              <button
                onClick={start}
                className="rounded-md bg-brass px-6 py-3 font-medium text-ink transition hover:opacity-90"
              >
                Start the call
              </button>
            )}
          </div>

          <p className="mt-5 flex items-center gap-2 text-sm text-stone">
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                live ? "animate-pulse bg-success" : state === "error" ? "bg-danger" : "bg-stone/50"
              }`}
            />
            {statusLabel(state)}
          </p>
          {error && <p className="mt-3 text-sm text-danger">{error}</p>}

          {(lines.length > 0 || live) && (
            <div
              ref={transcriptRef}
              className="mt-8 max-h-96 space-y-4 overflow-y-auto border-t border-line pt-6"
            >
              {lines.length === 0 && (
                <p className="text-sm italic text-stone">Listening…</p>
              )}
              {lines.map((line, i) => (
                <div key={i} className={line.role === "you" ? "text-right" : ""}>
                  <p className="text-xs uppercase tracking-[0.15em] text-stone">
                    {line.role === "you" ? "You" : "Ananya"}
                  </p>
                  <p
                    className={`mt-1 inline-block max-w-[85%] rounded-lg px-4 py-2 text-left text-cream ${
                      line.role === "you" ? "bg-raised" : "bg-brass-soft"
                    }`}
                  >
                    {line.text}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

        <p className="mt-8 text-sm text-stone">
          Prefer a phone call?{" "}
          <Link href="/" className="text-brass underline underline-offset-4">
            Request one here
          </Link>
          .
        </p>
      </section>
    </main>
  );
}
