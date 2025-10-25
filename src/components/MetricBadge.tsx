import clsx from "clsx";
import { ReactNode } from "react";

interface MetricBadgeProps {
  label: string;
  value: ReactNode;
  accent?: "green" | "amber" | "red" | "blue";
}

const palette: Record<NonNullable<MetricBadgeProps["accent"]>, string> = {
  blue: "border-sky-100 text-sky-700",
  green: "border-emerald-100 text-emerald-700",
  amber: "border-amber-100 text-amber-700",
  red: "border-rose-100 text-rose-700"
};

export function MetricBadge({ label, value, accent = "blue" }: MetricBadgeProps) {
  return (
    <div
      className={clsx(
        "rounded-2xl border bg-white px-4 py-3 shadow-sm",
        palette[accent]
      )}
    >
      <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}
