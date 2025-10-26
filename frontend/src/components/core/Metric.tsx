import { cn } from "@/lib/utils";

interface MetricProps {
  label: string;
  value: string;
  hint?: string;
  tone?: "success" | "warn" | "danger" | "muted";
}

const toneMap: Record<NonNullable<MetricProps["tone"]>, string> = {
  success: "border-success/20 text-success",
  warn: "border-warn/20 text-warn",
  danger: "border-danger/20 text-danger",
  muted: "border-border text-ink"
};

export function Metric({ label, value, hint, tone = "muted" }: MetricProps) {
  return (
    <div className={cn("rounded-2xl border bg-white p-4 shadow-sm", toneMap[tone])}>
      <p className="text-xs uppercase tracking-[0.18em] text-ink-muted">{label}</p>
      <p className="mt-2 text-lg font-semibold text-ink">{value}</p>
      {hint && <p className="text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}
