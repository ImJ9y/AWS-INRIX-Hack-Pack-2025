import clsx from "clsx";
import { ReactNode } from "react";

interface MetricBadgeProps {
  label: string;
  value: ReactNode;
  accent?: "green" | "amber" | "red" | "blue";
}

const palette: Record<NonNullable<MetricBadgeProps["accent"]>, string> = {
  blue: "from-sky-500/20 to-blue-500/10 text-sky-200",
  green: "from-emerald-500/20 to-emerald-500/10 text-emerald-200",
  amber: "from-amber-500/20 to-amber-500/10 text-amber-200",
  red: "from-rose-500/20 to-rose-500/10 text-rose-200"
};

export function MetricBadge({ label, value, accent = "blue" }: MetricBadgeProps) {
  return (
    <div
      className={clsx(
        "rounded-2xl border border-white/10 bg-gradient-to-br px-4 py-3 shadow-soft",
        palette[accent]
      )}
    >
      <p className="text-xs uppercase tracking-[0.2em] text-white/70">{label}</p>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
    </div>
  );
}
