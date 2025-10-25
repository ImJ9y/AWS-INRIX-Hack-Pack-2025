import { FallDetector } from "./features/fall-detector/FallDetector";

function App() {
  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-6xl px-4 py-10">
        <FallDetector />
      </div>
    </main>
  );
}

export default App;
