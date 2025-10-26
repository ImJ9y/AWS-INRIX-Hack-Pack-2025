import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { usePose, useWebcam } from "./hooks";
import { INITIAL_STATE, computeFeatures, landmarksToPoseFrame, updateFallState } from "./lib/fallLogic";
import { DetectorState, FallEvent, FallFeatures, PoseFrame } from "./types";
import { AWSIntegration } from "./AWSIntegration";

const skeletonConnections: [number, number][] = [
  [0, 1],
  [1, 2],
  [2, 3],
  [3, 7],
  [0, 4],
  [4, 5],
  [5, 6],
  [6, 8],
  [9, 10],
  [11, 13],
  [13, 15],
  [12, 14],
  [14, 16],
  [11, 12],
  [23, 24],
  [11, 23],
  [12, 24]
];

const statusStyles: Record<DetectorState["status"], { label: string; className: string }> = {
  idle: { label: "No fall", className: "bg-emerald-100 text-emerald-700" },
  suspected: { label: "Possible fall", className: "bg-amber-100 text-amber-700" },
  confirmed: { label: "Fall confirmed", className: "bg-rose-100 text-rose-700" },
  cooldown: { label: "Cooldown", className: "bg-sky-100 text-sky-700" }
};

export function FallDetector() {
  const { videoRef, ready, error: cameraError, start, stop, resolution } = useWebcam();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const framesRef = useRef<PoseFrame[]>([]);
  const stateRef = useRef<DetectorState>(INITIAL_STATE);

  const [state, setState] = useState(INITIAL_STATE);
  const [events, setEvents] = useState<FallEvent[]>([]);
  const [features, setFeatures] = useState<FallFeatures | null>(null);
  const [sampleSrc, setSampleSrc] = useState<string | null>(null);
  const [sampleLabel, setSampleLabel] = useState<string | null>(null);

  const replayInputRef = useRef<HTMLInputElement | null>(null);

  const { landmarks, fps, modelReady, confidence, error: poseError } = usePose(videoRef.current, {
    running: Boolean((ready || sampleSrc) && !cameraError),
    maxFps: 30
  });

  useEffect(() => {
    start();
  }, [start]);

  useEffect(() => {
    return () => {
      if (sampleSrc) URL.revokeObjectURL(sampleSrc);
    };
  }, [sampleSrc]);

  useEffect(() => {
    if (!landmarks.length) return;
    const frame = landmarksToPoseFrame(landmarks, performance.now());
    if (!frame) return;

    const history = framesRef.current;
    history.push(frame);
    while (history.length > 400) history.shift();

    const prevFrames = history.slice(-120, -1);
    const computed = computeFeatures(prevFrames, frame);
    setFeatures(computed);

    const update = updateFallState(stateRef.current, computed, Date.now());
    if (update.changed) {
      stateRef.current = update.state;
      setState(update.state);
    }
    if (update.event) {
      setEvents((prev) => [update.event, ...prev].slice(0, 10));
    }
  }, [landmarks]);

  useEffect(() => {
    let raf: number;
    const render = () => {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas) {
        raf = requestAnimationFrame(render);
        return;
      }
      const context = canvas.getContext("2d");
      if (!context) return;
      const width = video.videoWidth || resolution.width || 1280;
      const height = video.videoHeight || resolution.height || 720;
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      context.clearRect(0, 0, canvas.width, canvas.height);
      if (landmarks.length) {
        context.save();
        context.lineWidth = 2;
        context.strokeStyle = "#0ea5e9";
        context.fillStyle = "#fb7185";
        skeletonConnections.forEach(([a, b]) => {
          const startPoint = landmarks[a];
          const endPoint = landmarks[b];
          if (!startPoint || !endPoint) return;
          context.beginPath();
          context.moveTo(startPoint.x * canvas.width, startPoint.y * canvas.height);
          context.lineTo(endPoint.x * canvas.width, endPoint.y * canvas.height);
          context.stroke();
        });
        landmarks.forEach((point) => {
          context.beginPath();
          context.globalAlpha = 0.8;
          context.arc(point.x * canvas.width, point.y * canvas.height, 5, 0, Math.PI * 2);
          context.fill();
        });
        context.restore();
      }
      raf = requestAnimationFrame(render);
    };
    raf = requestAnimationFrame(render);
    return () => cancelAnimationFrame(raf);
  }, [landmarks, resolution.height, resolution.width]);

  const status = statusStyles[state.status];
  const cameraStateMessage = useMemo(() => {
    if (cameraError) return cameraError;
    if (!ready && !sampleSrc) return "Awaiting camera permission...";
    return null;
  }, [cameraError, ready, sampleSrc]);

  const handleReplayClick = () => {
    replayInputRef.current?.click();
  };

  const handleReplayFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    setSampleSrc(url);
    setSampleLabel(file.name);
    stop();
    if (videoRef.current) {
      videoRef.current.srcObject = null;
      videoRef.current.src = url;
      videoRef.current.loop = true;
      videoRef.current.muted = true;
      void videoRef.current.play();
    }
  };

  const exitReplay = async () => {
    if (sampleSrc && videoRef.current) {
      videoRef.current.pause();
      videoRef.current.removeAttribute("src");
      videoRef.current.load();
    }
    setSampleSrc(null);
    setSampleLabel(null);
    await start();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Fall Detection System</h1>
        <p className="text-slate-600">Pose-based AI fall detection with AWS integration</p>
      </div>

      {/* Main Detection Panels */}
      <section className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <div className="rounded-3xl border border-slate-200 bg-white shadow-md">
          <div className="relative aspect-video overflow-hidden rounded-3xl bg-slate-100">
            <video
              ref={videoRef}
              className="h-full w-full object-cover"
              playsInline
              muted
              autoPlay
            />
            <canvas
              ref={canvasRef}
              className={clsx(
                "pointer-events-none absolute inset-0 h-full w-full"
              )}
            />
            <div className="absolute left-4 top-4 flex gap-2">
              <span className={clsx("rounded-full px-3 py-1 text-sm font-medium", status.className)}>
                {status.label}
              </span>
              {modelReady && (
                <span className="rounded-full bg-white/80 px-3 py-1 text-xs text-slate-700">MediaPipe Ready</span>
              )}
            </div>
            <div className="absolute right-4 bottom-4 flex flex-wrap gap-2 text-xs text-slate-800">
              <span className="rounded-full bg-white/80 px-2 py-1 font-mono">FPS {fps.toFixed(0)}</span>
              <span className="rounded-full bg-white/80 px-2 py-1 font-mono">
                Confidence {(confidence * 100).toFixed(0)}%
              </span>
              {sampleSrc && <span className="rounded-full bg-white/80 px-2 py-1">Clip: {sampleLabel}</span>}
            </div>
            {cameraStateMessage && (
              <div className="absolute inset-0 flex flex-col items-center justify-center bg-white/90 text-center">
                <p className="text-lg font-semibold text-slate-900">{cameraStateMessage}</p>
                <p className="mt-2 max-w-sm text-sm text-slate-600">
                  Allow camera access and reload (HTTPS or http://localhost). Processing stays on this machine.
                </p>
              </div>
            )}
          </div>
        </div>
        <div className="flex flex-col gap-4">
          <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-lg font-semibold text-slate-900">{status.label}</p>
                <p className="text-xs text-slate-500">MediaPipe pose detection + AWS pose analysis</p>
              </div>
              <div className="flex flex-col items-end gap-1 text-xs text-slate-500">
                <span className="rounded-full bg-slate-100 px-3 py-1 font-mono text-slate-700">FPS {fps.toFixed(0)}</span>
                <span className="rounded-full bg-slate-100 px-3 py-1 font-mono text-slate-700">
                  Confidence {(confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-sm">
              <button
                type="button"
                onClick={handleReplayClick}
                className="rounded-full border border-slate-300 px-4 py-2 font-medium text-slate-700 hover:bg-slate-100"
              >
                Upload clip
              </button>
              {sampleSrc && (
                <button
                  type="button"
                  onClick={exitReplay}
                  className="rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2 font-medium text-emerald-700"
                >
                  Use camera
                </button>
              )}
            </div>
            <input ref={replayInputRef} type="file" accept="video/*" className="hidden" onChange={handleReplayFile} />
            {poseError && <p className="mt-3 text-xs text-rose-500">Model error: {poseError}</p>}
          </div>
          {features && <MetricsPanel features={features} />}
          <EventsPane events={events} />
          <div className="rounded-3xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500">
            Processing is on-device. AWS backend provides enhanced pose-based analysis.
          </div>
        </div>
      </section>

      {/* AWS Integration Panel */}
      <section>
        <AWSIntegration />
      </section>
    </div>
  );
}

function MetricsPanel({ features }: { features: FallFeatures }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <MetricCard label="Torso tilt" value={`${features.torsoTiltDeg.toFixed(0)} degrees`} tone="amber" />
      <MetricCard label="Head drop" value={`${Math.round(features.headYDrop * 100)}%`} tone="rose" />
      <MetricCard label="Velocity" value={features.headYVelPeak.toFixed(2)} tone="sky" />
      <MetricCard label="Stillness" value={`${features.stillnessSec.toFixed(1)}s`} tone="emerald" />
    </div>
  );
}

function MetricCard({
  label,
  value,
  tone
}: {
  label: string;
  value: string;
  tone: "amber" | "rose" | "sky" | "emerald";
}) {
  const colors: Record<typeof tone, string> = {
    amber: "border-amber-100 text-amber-700",
    rose: "border-rose-100 text-rose-700",
    sky: "border-sky-100 text-sky-700",
    emerald: "border-emerald-100 text-emerald-700"
  };
  return (
    <div className={clsx("rounded-2xl border bg-white px-4 py-3 shadow-sm", colors[tone])}>
      <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}

function EventsPane({ events }: { events: FallEvent[] }) {
  const severityStyles: Record<FallEvent["severity"], string> = {
    Low: "bg-emerald-50 text-emerald-700",
    Moderate: "bg-amber-50 text-amber-700",
    High: "bg-orange-50 text-orange-700",
    Critical: "bg-rose-50 text-rose-700"
  };

  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-900">Event Feed</p>
          <p className="text-xs text-slate-500">Newest first - Last 10</p>
        </div>
      </div>
      <div className="max-h-80 space-y-3 overflow-y-auto pr-1">
        {events.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
            No fall events logged yet.
          </p>
        ) : (
          <ul className="space-y-3">
            {events.map((event) => (
              <li
                key={event.id}
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 shadow-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-slate-500">
                    {new Date(event.timestamp).toLocaleTimeString([], { hour12: false })}
                  </span>
                  <span className={clsx("rounded-full px-2 py-0.5 text-xs font-semibold", severityStyles[event.severity])}>
                    {event.severity}
                  </span>
                  <span className="text-xs text-slate-500">Score {event.features.score.toFixed(1)}</span>
                </div>
                <p className="mt-2 text-slate-700">{event.description}</p>
                <dl className="mt-2 grid grid-cols-2 gap-2 text-[0.75rem] text-slate-500 md:grid-cols-4">
                  <div>
                    <dt className="text-slate-400">Tilt</dt>
                    <dd>{event.features.torsoTiltDeg.toFixed(0)} degrees</dd>
                  </div>
                  <div>
                    <dt className="text-slate-400">Drop</dt>
                    <dd>{Math.round(event.features.headYDrop * 100)}%</dd>
                  </div>
                  <div>
                    <dt className="text-slate-400">Velocity</dt>
                    <dd>{event.features.headYVelPeak.toFixed(2)}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-400">Stillness</dt>
                    <dd>{event.features.stillnessSec.toFixed(1)}s</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
