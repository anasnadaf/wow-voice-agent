import type { CallStatus } from "@/lib/api";

const STYLES: Record<CallStatus, string> = {
  requested: "border-line text-stone",
  ringing: "border-brass/50 text-brass",
  in_progress: "border-success/50 text-success",
  completed: "border-success/40 text-success",
  failed: "border-danger/50 text-danger",
  no_answer: "border-line text-stone",
  busy: "border-line text-stone",
};

const LABELS: Record<CallStatus, string> = {
  requested: "Requested",
  ringing: "Ringing",
  in_progress: "In progress",
  completed: "Completed",
  failed: "Failed",
  no_answer: "No answer",
  busy: "Busy",
};

export const LIVE_STATUSES: CallStatus[] = ["requested", "ringing", "in_progress"];

export function StatusChip({ status }: { status: CallStatus }) {
  const live = status === "ringing" || status === "in_progress";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs ${
        STYLES[status] ?? "border-line text-stone"
      }`}
    >
      {live && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {LABELS[status] ?? status}
    </span>
  );
}
