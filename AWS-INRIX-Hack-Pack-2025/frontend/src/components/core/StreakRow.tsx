import { Card } from '@/components/ui/card';

interface StreakRowProps {
  streakLength: number;
  mondayStart?: boolean;
  activity?: number[]; // 0..1 intensity per day
}

const defaultActivity = [1, 1, 0, 1, 1, 0, 0, 1, 1, 1, 0, 1, 1, 0];

export function StreakRow({
  streakLength,
  mondayStart = true,
  activity = defaultActivity,
}: StreakRowProps) {
  const days = mondayStart
    ? ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    : ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const weeks: number[][] = [];
  for (let i = 0; i < activity.length; i += 7) {
    weeks.push(activity.slice(i, i + 7));
  }

  return (
    <Card className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-ink-muted">
            Streak
          </p>
          <p className="text-2xl font-semibold leading-tight text-ink">
            Day {streakLength} streak
          </p>
          <p className="text-sm text-ink-muted">
            Consistent motion monitoring keeps the model sharp.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-success/20 bg-success/5 px-3 py-1 text-sm font-medium text-success">
          <span className="h-2 w-2 rounded-full bg-success" aria-hidden />
          On track
        </div>
      </div>
      <div className="space-y-2">
        <div className="grid grid-cols-7 text-center text-xs font-medium text-ink-muted">
          {days.map(day => (
            <span key={day}>{day}</span>
          ))}
        </div>
        <div className="space-y-1">
          {weeks.map((week, idx) => (
            <div key={idx} className="grid grid-cols-7 gap-2">
              {week.map((value, cellIdx) => (
                <span
                  key={`${idx}-${cellIdx}`}
                  className={`h-8 rounded-xl border ${value ? 'border-success/40 bg-emerald-50' : 'border-border bg-slate-50'}`}
                  aria-label={`${days[cellIdx]} ${value ? 'active' : 'inactive'}`}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
