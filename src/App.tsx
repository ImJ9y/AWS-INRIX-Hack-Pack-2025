import { FallDetector } from "./components/FallDetector";

function App() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 text-white">
      <div className="mx-auto max-w-6xl space-y-8 px-4 py-10">
        <header className="space-y-2">
          <p className="text-sm uppercase tracking-[0.3em] text-sky-200">On-device safety</p>
          <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Real-time Fall Detection
          </h1>
          <p className="max-w-2xl text-base text-white/70">
            Uses your webcam plus an on-device pose model to detect rapid descents, torso tilt, and post-impact stillness.
            Everything stays in the browser — no uploads, no backend.
          </p>
        </header>
        <FallDetector />
      </div>
    </div>
  );
}

export default App;
