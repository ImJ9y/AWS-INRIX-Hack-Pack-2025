import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

interface DailyChallengeCTAProps {
  title: string;
  description: string;
  actionLabel?: string;
  onStart?: () => void;
}

export function DailyChallengeCTA({
  title,
  description,
  actionLabel = 'Start challenge',
  onStart,
}: DailyChallengeCTAProps) {
  return (
    <Card className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <div>
        <p className="text-xl font-semibold text-ink">{title}</p>
        <p className="text-sm text-ink-muted">{description}</p>
      </div>
      <Button size="lg" onClick={onStart} aria-label={actionLabel}>
        {actionLabel}
      </Button>
    </Card>
  );
}
