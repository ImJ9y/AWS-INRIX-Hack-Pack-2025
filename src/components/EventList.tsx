import { FallEvent } from "../types";

const severityStyles: Record<FallEvent["severity"], string> = {
  Low: "bg-emerald-500/10 text-emerald-200",
  Moderate: "bg-amber-500/10 text-amber-200",
  High: "bg-orange-500/10 text-orange-200",
  Critical: "bg-rose-500/10 text-rose-200"
};

interface EventListProps {
  events: FallEvent[];
}

export function EventList({ events }: EventListProps) {
  return (
    <div className="rounded-3xl border border-white/10 bg-slate-900/60 p-4 shadow-soft backdrop-blur">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-white">Event Feed</p>
          <p className="text-xs text-white/60">Newest first • Last 10</p>
        </div>
      </div>
      {events.length === 0 && (
        <p className="rounded-2xl border border-dashed border-white/10 px-4 py-6 text-center text-sm text-white/60">
          No fall events logged yet.
        </p>
      )}
      <ul className="space-y-3">
        {events.map((event) => (
          <li
            key={event.id}
            className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white shadow-sm"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-white/70">
                {new Date(event.timestamp).toLocaleTimeString([], { hour12: false })}
              </span>
              <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${severityStyles[event.severity]}`}>
                {event.severity}
              </span>
              <span className="text-xs text-white/60">Score {event.features.score.toFixed(1)}</span>
            </div>
            <p className="mt-2 text-white/80">{event.description}</p>
            <dl className="mt-2 grid grid-cols-2 gap-2 text-[0.75rem] text-white/70 md:grid-cols-4">
              <div>
                <dt className="text-white/50">Tilt</dt>
                <dd>{event.features.torsoTiltDeg.toFixed(0)}°</dd>
              </div>
              <div>
                <dt className="text-white/50">Drop</dt>
                <dd>{Math.round(event.features.headYDrop * 100)}%</dd>
              </div>
              <div>
                <dt className="text-white/50">Velocity</dt>
                <dd>{event.features.headYVelPeak.toFixed(2)}</dd>
              </div>
              <div>
                <dt className="text-white/50">Stillness</dt>
                <dd>{event.features.stillnessSec.toFixed(1)}s</dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </div>
  );
}
