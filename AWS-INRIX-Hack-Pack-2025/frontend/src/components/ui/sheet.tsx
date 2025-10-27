import { AnimatePresence, motion } from 'framer-motion';
import { ReactNode } from 'react';

interface SheetProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  side?: 'left' | 'right';
  children: ReactNode;
}

export function Sheet({
  open,
  onOpenChange,
  side = 'right',
  children,
}: SheetProps) {
  if (typeof document === 'undefined') return null;
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-40"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => onOpenChange?.(false)}
            aria-hidden
          />
          <motion.div
            initial={{ x: side === 'right' ? 320 : -320 }}
            animate={{ x: 0 }}
            exit={{ x: side === 'right' ? 320 : -320 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className={`absolute inset-y-0 ${side}-0 w-full max-w-sm bg-white p-6 shadow-md`}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
