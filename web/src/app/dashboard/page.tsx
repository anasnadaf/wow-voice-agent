"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Call, listCalls } from "@/lib/api";
import { formatDuration, formatWhen } from "@/lib/format";
import { StatusChip } from "@/components/StatusChip";

const POLL_MS = 4000;

export default function CallsPage() {
  const [calls, setCalls] = useState<Call[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const rows = await listCalls();
        if (!cancelled) {
          setCalls(rows);
          setError("");
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load calls");
      }
    };
    load();
    const timer = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <h1 className="font-display text-3xl text-cream">Calls</h1>
        <p className="text-xs uppercase tracking-[0.2em] text-stone">Live · refreshes every 4s</p>
      </div>

      {error && (
        <p className="mt-6 rounded-md border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
          {error}
        </p>
      )}

      {calls === null && !error && <p className="mt-8 text-sm text-stone">Loading calls…</p>}

      {calls !== null && calls.length === 0 && (
        <p className="mt-8 rounded-lg border border-line bg-pane px-6 py-10 text-center text-sm text-stone">
          No calls yet. They will appear here as soon as a lead requests one.
        </p>
      )}

      {calls !== null && calls.length > 0 && (
        <div className="mt-6 overflow-x-auto rounded-lg border border-line">
          <table className="w-full min-w-[42rem] text-left text-sm">
            <thead>
              <tr className="border-b border-line bg-pane text-xs uppercase tracking-[0.15em] text-stone">
                <th className="px-4 py-3 font-normal">Lead</th>
                <th className="px-4 py-3 font-normal">Phone</th>
                <th className="px-4 py-3 font-normal">Status</th>
                <th className="px-4 py-3 font-normal">Duration</th>
                <th className="px-4 py-3 font-normal">Started</th>
                <th className="px-4 py-3 font-normal" />
              </tr>
            </thead>
            <tbody>
              {calls.map((call) => (
                <tr key={call.id} className="border-b border-line last:border-b-0 hover:bg-pane">
                  <td className="px-4 py-3 text-cream">
                    {call.lead?.name ?? call.visitor_name ?? "Web visitor"}
                  </td>
                  <td className="px-4 py-3 text-stone">
                    {call.lead?.phone ?? "browser call"}
                  </td>
                  <td className="px-4 py-3">
                    <StatusChip status={call.status} />
                  </td>
                  <td className="px-4 py-3 text-stone">{formatDuration(call.duration_s)}</td>
                  <td className="px-4 py-3 text-stone">
                    {formatWhen(call.started_at ?? call.created_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/dashboard/calls/${call.id}`}
                      className="text-xs uppercase tracking-[0.15em] text-brass hover:brightness-110"
                    >
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
