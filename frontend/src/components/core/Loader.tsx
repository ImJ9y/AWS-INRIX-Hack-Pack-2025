interface LoaderProps {
  lines?: number;
}

export function Loader({ lines = 3 }: LoaderProps) {
  return (
    <div className="space-y-3">
      {Array.from({ length: lines }).map((_, index) => (
        <div key={index} className="relative h-4 w-full overflow-hidden rounded-xl bg-slate-100">
          <span className="absolute inset-0 translate-x-[-100%] bg-gradient-to-r from-transparent via-white/60 to-transparent animate-shimmer" />
        </div>
      ))}
    </div>
  );
}
