"use client";

import { useEffect, useState } from "react";
import { Lead, listLeads } from "@/lib/api";
import { formatWhen } from "@/lib/format";

export default function LeadsPage() {
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    listLeads()
      .then(setLeads)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load leads"));
  }, []);

  return (
    <div>
      <h1 className="font-display text-3xl text-cream">Leads</h1>

      {error && (
        <p className="mt-6 rounded-md border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
          {error}
        </p>
      )}

      {leads === null && !error && <p className="mt-8 text-sm text-stone">Loading leads…</p>}

      {leads !== null && leads.length === 0 && (
        <p className="mt-8 rounded-lg border border-line bg-pane px-6 py-10 text-center text-sm text-stone">
          No leads yet.
        </p>
      )}

      {leads !== null && leads.length > 0 && (
        <div className="mt-6 overflow-x-auto rounded-lg border border-line">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead>
              <tr className="border-b border-line bg-pane text-xs uppercase tracking-[0.15em] text-stone">
                <th className="px-4 py-3 font-normal">Name</th>
                <th className="px-4 py-3 font-normal">Phone</th>
                <th className="px-4 py-3 font-normal">Source</th>
                <th className="px-4 py-3 font-normal">Consent</th>
                <th className="px-4 py-3 font-normal">DNC</th>
                <th className="px-4 py-3 font-normal">Created</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr key={lead.id} className="border-b border-line last:border-b-0 hover:bg-pane">
                  <td className="px-4 py-3 text-cream">{lead.name}</td>
                  <td className="px-4 py-3 text-stone">{lead.phone}</td>
                  <td className="px-4 py-3 text-stone capitalize">{lead.source}</td>
                  <td className="px-4 py-3">
                    {lead.consent ? (
                      <span className="text-success">Yes</span>
                    ) : (
                      <span className="text-stone">No</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {lead.dnc ? (
                      <span className="text-danger">DNC</span>
                    ) : (
                      <span className="text-stone">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-stone">{formatWhen(lead.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
