export function Navbar() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-white/95 backdrop-blur">
      <div className="container flex h-16 items-center justify-between">
        <div className="flex items-center gap-3 text-sm font-semibold tracking-tight text-ink">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border text-base">CA</span>
          <span>Catch</span>
        </div>
      </div>
    </header>
  );
}
