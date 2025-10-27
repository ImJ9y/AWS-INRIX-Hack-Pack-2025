import {
  createContext,
  useContext,
  useMemo,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
} from 'react';
import { cn } from '@/lib/utils';

interface TabsContextValue {
  value: string;
  setValue?: (value: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

export interface TabsProps extends HTMLAttributes<HTMLDivElement> {
  value: string;
  onValueChange?: (value: string) => void;
}

export function Tabs({ value, onValueChange, className, children }: TabsProps) {
  const contextValue = useMemo(
    () => ({ value, setValue: onValueChange }),
    [value, onValueChange]
  );
  return (
    <TabsContext.Provider value={contextValue}>
      <div className={cn('w-full', className)}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-2xl border border-border bg-white p-1',
        className
      )}
      {...props}
    />
  );
}

export interface TabsTriggerProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  value: string;
}

export function TabsTrigger({
  value,
  className,
  children,
  ...props
}: TabsTriggerProps) {
  const context = useTabsContext();
  const isActive = context.value === value;
  return (
    <button
      type="button"
      onClick={() => context.setValue?.(value)}
      className={cn(
        'flex-1 rounded-xl px-4 py-2 text-sm font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/10',
        isActive ? 'bg-accent text-white' : 'text-ink-muted hover:text-ink',
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export interface TabsContentProps extends HTMLAttributes<HTMLDivElement> {
  value: string;
}

export function TabsContent({
  value,
  className,
  children,
  ...props
}: TabsContentProps) {
  const context = useTabsContext();
  if (context.value !== value) return null;
  return (
    <div className={cn('mt-4', className)} {...props}>
      {children}
    </div>
  );
}

function useTabsContext() {
  const context = useContext(TabsContext);
  if (!context) {
    throw new Error('Tabs components must be used inside <Tabs>');
  }
  return context;
}
