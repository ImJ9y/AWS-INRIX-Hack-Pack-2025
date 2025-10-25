import { FallEvent } from "../types";

const severityStyles: Record<FallEvent["severity"], string> = {
  Low: "bg-emerald-50 text-emerald-700",
  Moderate: "bg-amber-50 text-amber-700",
  High: "bg-orange-50 text-orange-700",
  Critical: "bg-rose-50 text-rose-700"
};

interface EventListProps {
  events: FallEvent[];
}

export function EventList({ events }: EventListProps) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-900">Event Feed</p>
          <p className="text-xs text-slate-500">Newest first • Last 10</p>
        </div>
      </div>
      <div className="max-h-80 space-y-3 overflow-y-auto pr-1">
        {events.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
            No fall events logged yet.
          </p>
        ) : (
          <ul className="space-y-3">
            {events.map((event) => (
              <li
                key={event.id}
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 shadow-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-slate-500">
                    {new Date(event.timestamp).toLocaleTimeString([], { hour12: false })}
                  </span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${severityStyles[event.severity]}`}>
                    {event.severity}
                  </span>
                  <span className="text-xs text-slate-500">Score {event.features.score.toFixed(1)}</span>
                </div>
                <p className="mt-2 text-slate-700">{event.description}</p>
                <dl className="mt-2 grid grid-cols-2 gap-2 text-[0.75rem] text-slate-500 md:grid-cols-4">
                  <div>
                    <dt className="text-slate-400">Tilt</dt>
                    <dd>{event.features.torsoTiltDeg.toFixed(0)}°</dd>
                  </div>
                  <div>
                    <dt className="text-slate-400">Drop</dt>
                    <dd>{Math.round(event.features.headYDrop * 100)}%</dd>
                  </div>
                  <div>
                    <dt className="text-slate-400">Velocity</dt>
                    <dd>{event.features.headYVelPeak.toFixed(2)}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-400">Stillness</dt>
                    <dd>{event.features.stillnessSec.toFixed(1)}s</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
