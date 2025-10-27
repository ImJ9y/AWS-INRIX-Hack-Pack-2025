import { AnimatePresence, motion } from 'framer-motion';
import { ReactNode, createContext, useContext } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';

interface DialogContextValue {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
}

const DialogContext = createContext<DialogContextValue | null>(null);

export interface DialogProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  children: ReactNode;
}

export function Dialog({ open, onOpenChange, children }: DialogProps) {
  return (
    <DialogContext.Provider value={{ open, onOpenChange }}>
      {children}
    </DialogContext.Provider>
  );
}

export interface DialogContentProps {
  className?: string;
  children: ReactNode;
}

export function DialogContent({ className, children }: DialogContentProps) {
  const context = useDialog();
  if (typeof document === 'undefined') return null;
  return createPortal(
    <AnimatePresence>
      {context.open && (
        <motion.div
          className="fixed inset-0 z-50"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => context.onOpenChange?.(false)}
            aria-hidden
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 16 }}
            transition={{ duration: 0.18 }}
            className={cn(
              'relative mx-auto mt-24 w-full max-w-lg rounded-2xl border border-border bg-white p-6 shadow-md',
              className
            )}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}

function useDialog() {
  const context = useContext(DialogContext);
  if (!context) {
    throw new Error('Dialog components must be used within <Dialog>');
  }
  return context;
}
