interface NavbarProps {
  onReset?: () => void;
}

export function Navbar({ onReset }: NavbarProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-white/95 backdrop-blur">
      <div className="container flex h-16 items-center justify-between">
        <button
          type="button"
          onClick={onReset}
          className="flex items-center gap-3 text-sm font-semibold tracking-tight text-ink transition hover:text-ink/70"
          aria-label="Reset Catch console"
        >
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border text-base">
            CA
          </span>
          <span>Catch</span>
        </button>
      </div>
    </header>
  );
}
