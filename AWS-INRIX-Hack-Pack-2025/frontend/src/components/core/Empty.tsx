import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Inbox } from 'lucide-react';

interface EmptyProps {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export function Empty({
  title,
  description,
  actionLabel,
  onAction,
  className,
}: EmptyProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border/80 bg-white p-8 text-center',
        className
      )}
    >
      <Inbox size={20} className="text-ink-muted" aria-hidden />
      <div>
        <p className="text-sm font-semibold text-ink">{title}</p>
        <p className="text-sm text-ink-muted">{description}</p>
      </div>
      {actionLabel && (
        <Button size="sm" onClick={onAction} aria-label={actionLabel}>
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
