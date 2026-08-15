"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CallDetail, Qualification, fetchRecordingObjectUrl, getCall } from "@/lib/api";
import { formatDuration, formatOffset, formatWhen } from "@/lib/format";
import { LIVE_STATUSES, StatusChip } from "@/components/StatusChip";

const POLL_MS = 4000;

const CHECKPOINTS: Array<{ key: keyof Qualification; label: string }> = [
  { key: "intent", label: "Intent" },
  { key: "geography", label: "Geography" },
  { key: "budget", label: "Budget" },
  { key: "timeline", label: "Timeline" },
];

function QualificationCard({ q }: { q: Qualification | null }) {
  return (
    <section className="rounded-lg border border-line bg-pane p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xs uppercase tracking-[0.2em] text-stone">Qualification</h2>
        {q?.disposition && (
          <span className="rounded-full border border-brass/50 bg-brass-soft px-3 py-1 text-xs uppercase tracking-[0.15em] text-brass">
            {q.disposition.replace(/_/g, " ")}
          </span>
        )}
      </div>

      {!q ? (
        <p className="mt-4 text-sm text-stone">
          Not yet qualified — the card fills in after the agent completes its checkpoints.
        </p>
      ) : (
        <>
          <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {CHECKPOINTS.map(({ key, label }) => {
              const value = q[key] as string | null;
              return (
                <div
                  key={key}
                  className={`rounded-md border px-4 py-3 ${
                    value ? "border-line bg-raised" : "border-dashed border-line"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${value ? "bg-success" : "bg-stone/40"}`}
                    />
                    <span className="text-xs uppercase tracking-[0.15em] text-stone">{label}</span>
                  </div>
                  <p className={`mt-1.5 text-sm ${value ? "text-cream" : "italic text-stone/70"}`}>
                    {value ?? "Not established"}
                  </p>
                </div>
              );
            })}
          </div>

          {q.summary && (
            <div className="mt-5">
              <h3 className="text-xs uppercase tracking-[0.15em] text-stone">Summary</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-cream">{q.summary}</p>
            </div>
          )}

          {q.next_action && (
            <div className="mt-4 rounded-md border border-brass/40 bg-brass-soft px-4 py-3">
              <h3 className="text-xs uppercase tracking-[0.15em] text-brass">Next action</h3>
              <p className="mt-1 text-sm text-cream">{q.next_action}</p>
            </div>
          )}

          <div className="mt-5 flex flex-wrap gap-x-6 gap-y-1 text-xs text-stone">
            {q.language && <span>Language: {q.language}</span>}
            {q.sentiment && <span>Sentiment: {q.sentiment}</span>}
          </div>
        </>
      )}
    </section>
  );
}

export default function CallDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [call, setCall] = useState<CallDetail | null>(null);
  const [error, setError] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const statusRef = useRef<string>("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await getCall(id);
        if (!cancelled) {
          setCall(data);
          statusRef.current = data.status;
          setError("");
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load call");
      }
    };
    load();
    const timer = setInterval(() => {
      if (!statusRef.current || (LIVE_STATUSES as string[]).includes(statusRef.current)) {
        load();
      }
    }, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [id]);

  const recordingUrl = call?.recording_url ?? null;
  useEffect(() => {
    if (!recordingUrl) return;
    let objectUrl = "";
    let cancelled = false;
    fetchRecordingObjectUrl(recordingUrl)
      .then((url) => {
        objectUrl = url;
        if (!cancelled) setAudioUrl(url);
      })
      .catch(() => {
        /* recording pane simply stays hidden */
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [recordingUrl]);

  if (error) {
    return (
      <div>
        <BackLink />
        <p className="mt-6 rounded-md border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
          {error}
        </p>
      </div>
    );
  }

  if (!call) {
    return (
      <div>
        <BackLink />
        <p className="mt-6 text-sm text-stone">Loading call…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <BackLink />
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          <h1 className="font-display text-3xl text-cream">
            {call.lead?.name ?? call.visitor_name ?? "Web visitor"}
          </h1>
          <StatusChip status={call.status} />
        </div>
        <p className="mt-1.5 text-sm text-stone">
          {call.lead?.phone ?? "browser call"}
          {" · "}
          {formatWhen(call.started_at ?? call.created_at)}
          {call.duration_s != null && ` · ${formatDuration(call.duration_s)}`}
          {call.language && ` · ${call.language}`}
        </p>
      </div>

      {audioUrl && (
        <section className="rounded-lg border border-line bg-pane p-6">
          <h2 className="text-xs uppercase tracking-[0.2em] text-stone">Recording</h2>
          <audio controls src={audioUrl} className="mt-4 w-full" />
        </section>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.2fr_1fr] lg:items-start">
        <section className="rounded-lg border border-line bg-pane p-6">
          <h2 className="text-xs uppercase tracking-[0.2em] text-stone">Transcript</h2>
          {call.turns.length === 0 ? (
            <p className="mt-4 text-sm text-stone">
              No transcript yet — turns stream in while the call is underway.
            </p>
          ) : (
            <ol className="mt-5 flex flex-col gap-4">
              {call.turns.map((turn) => (
                <li
                  key={turn.id}
                  className={`flex ${turn.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-lg px-4 py-3 ${
                      turn.role === "user"
                        ? "rounded-br-sm bg-raised"
                        : "rounded-bl-sm border border-brass/30 bg-brass-soft"
                    }`}
                  >
                    <div className="flex items-baseline justify-between gap-4">
                      <span
                        className={`text-[0.65rem] uppercase tracking-[0.15em] ${
                          turn.role === "user" ? "text-stone" : "text-brass"
                        }`}
                      >
                        {turn.role === "user" ? "Lead" : "Agent"}
                      </span>
                      <span className="font-mono text-[0.65rem] text-stone">
                        {formatOffset(turn.t_offset_ms)}
                      </span>
                    </div>
                    <p className="mt-1 text-sm leading-relaxed text-cream">{turn.text}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

        <QualificationCard q={call.qualification} />
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/dashboard"
      className="text-xs uppercase tracking-[0.2em] text-stone transition hover:text-cream"
    >
      ← All calls
    </Link>
  );
}
