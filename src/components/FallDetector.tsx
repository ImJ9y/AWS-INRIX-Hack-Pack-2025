import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { useWebcam } from "../hooks/useWebcam";
import { usePose } from "../hooks/usePose";
import {
  INITIAL_STATE,
  classifySeverity,
  computeFeatures,
  describe,
  landmarksToPoseFrame,
  updateFallState
} from "../lib/fallLogic";
import { EventList } from "./EventList";
import { MetricBadge } from "./MetricBadge";
import { DetectorState, FallEvent, FallFeatures, PoseFrame } from "../types";

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
  idle: { label: "No fall", className: "bg-emerald-500/20 text-emerald-200" },
  suspected: { label: "Possible fall…", className: "bg-amber-500/20 text-amber-200" },
  confirmed: { label: "Fall confirmed", className: "bg-rose-500/20 text-rose-200" },
  cooldown: { label: "Cooldown", className: "bg-blue-500/20 text-blue-200" }
};

export function FallDetector() {
  const { videoRef, ready, error: cameraError, start, stop, resolution } = useWebcam();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const framesRef = useRef<PoseFrame[]>([]);
  const stateRef = useRef<DetectorState>(INITIAL_STATE);

  const [state, setState] = useState(INITIAL_STATE);
  const [events, setEvents] = useState<FallEvent[]>([]);
  const [features, setFeatures] = useState<FallFeatures | null>(null);
  const [showOverlay, setShowOverlay] = useState(true);
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
      setEvents((prev) => [update.event!, ...prev].slice(0, 10));
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
      if (showOverlay && landmarks.length) {
        context.save();
        context.globalAlpha = 0.4;
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        context.restore();
        context.save();
        context.lineWidth = 3;
        context.strokeStyle = "#38bdf8";
        context.fillStyle = "#f97316";
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
        if (features) {
          context.fillStyle = "#f8fafc";
          context.font = "16px 'Inter', sans-serif";
          context.globalAlpha = 0.9;
          const textBg = (x: number, y: number, text: string) => {
            const padding = 6;
            const metrics = context.measureText(text);
            const boxWidth = metrics.width + padding * 2;
            const boxHeight = 24;
            context.fillStyle = "rgba(15, 23, 42, 0.7)";
            context.fillRect(x, y - boxHeight + 4, boxWidth, boxHeight);
            context.fillStyle = "#f8fafc";
            context.fillText(text, x + padding, y);
          };
          textBg(24, 32, `Tilt: ${features.torsoTiltDeg.toFixed(0)}°`);
          textBg(24, 64, `Δy: ${features.headYVelPeak.toFixed(2)}`);
        }
        context.restore();
      }
      raf = requestAnimationFrame(render);
    };
    raf = requestAnimationFrame(render);
    return () => cancelAnimationFrame(raf);
  }, [landmarks, resolution.height, resolution.width, showOverlay, features]);

  const status = statusStyles[state.status];
  const cameraStateMessage = useMemo(() => {
    if (cameraError) return cameraError;
    if (!ready && !sampleSrc) return "Awaiting camera permission…";
    return null;
  }, [cameraError, ready, sampleSrc]);

  const handleDemoEvent = () => {
    const mockFeatures: FallFeatures = {
      headYDrop: 0.48,
      headYVelPeak: 0.6,
      torsoTiltDeg: 72,
      stillnessSec: 4.5,
      confidence: 0.92,
      score: 6
    };
    const severity = classifySeverity(mockFeatures.score);
    const demoEvent: FallEvent = {
      id: crypto.randomUUID?.() ?? `${Date.now()}`,
      timestamp: new Date().toISOString(),
      severity,
      features: mockFeatures,
      description: describe(mockFeatures)
    };
    setEvents((prev) => [demoEvent, ...prev].slice(0, 10));
  };

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
    <section className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-4">
          <div className="relative rounded-3xl border border-white/10 bg-slate-900 shadow-soft">
            <div className="relative aspect-video overflow-hidden rounded-3xl">
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
                  "pointer-events-none absolute inset-0 h-full w-full",
                  showOverlay ? "opacity-100" : "opacity-0"
                )}
              />
              <div className="absolute left-4 top-4 flex gap-2">
                <span className={clsx("rounded-full px-3 py-1 text-sm font-medium", status.className)}>
                  {status.label}
                </span>
                {modelReady && (
                  <span className="rounded-full bg-white/10 px-3 py-1 text-xs text-white/80">
                    Model: loaded
                  </span>
                )}
              </div>
              <div className="absolute right-4 bottom-4 flex flex-wrap gap-2 text-xs text-white/80">
                <span className="rounded-full bg-black/40 px-2 py-1 font-mono">FPS {fps.toFixed(0)}</span>
                <span className="rounded-full bg-black/40 px-2 py-1 font-mono">
                  Confidence {(confidence * 100).toFixed(0)}%
                </span>
                {sampleSrc && (
                  <span className="rounded-full bg-black/40 px-2 py-1">Replay: {sampleLabel}</span>
                )}
              </div>
            </div>
            {cameraStateMessage && (
              <div className="absolute inset-0 flex flex-col items-center justify-center rounded-3xl bg-slate-950/80 text-center">
                <p className="text-lg font-semibold text-white">{cameraStateMessage}</p>
                <p className="mt-2 max-w-sm text-sm text-white/70">
                  Please enable camera permissions and reload over HTTPS (https://localhost). No video ever leaves this device.
                </p>
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-3">
            <label className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/90">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-white/30 bg-transparent"
                checked={showOverlay}
                onChange={(event) => setShowOverlay(event.target.checked)}
              />
              Show overlay
            </label>
            <button
              type="button"
              onClick={handleReplayClick}
              className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-white hover:bg-white/10"
            >
              Replay from sample
            </button>
            {sampleSrc && (
              <button
                type="button"
                onClick={exitReplay}
                className="rounded-2xl border border-emerald-400/40 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-200"
              >
                Use camera feed
              </button>
            )}
            <input
              ref={replayInputRef}
              type="file"
              accept="video/*"
              className="hidden"
              onChange={handleReplayFile}
            />
          </div>
          {features && (
            <div className="grid gap-3 md:grid-cols-2">
              <MetricBadge label="Torso tilt" value={`${features.torsoTiltDeg.toFixed(0)}°`} accent="amber" />
              <MetricBadge label="Head drop" value={`${Math.round(features.headYDrop * 100)}%`} accent="red" />
              <MetricBadge label="Velocity" value={features.headYVelPeak.toFixed(2)} accent="blue" />
              <MetricBadge label="Stillness" value={`${features.stillnessSec.toFixed(1)}s`} accent="green" />
            </div>
          )}
        </div>
        <div className="space-y-4">
          <div className="rounded-3xl border border-white/10 bg-slate-900/60 p-4 shadow-soft">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-white">Detector controls</p>
                <p className="text-xs text-white/60">Overlay, demo events, privacy</p>
              </div>
              <button
                type="button"
                onClick={handleDemoEvent}
                className="rounded-xl bg-rose-500/20 px-3 py-1 text-xs font-semibold text-rose-100 hover:bg-rose-500/30"
              >
                Create demo event
              </button>
            </div>
            <p className="mt-3 text-xs text-white/60">
              All processing happens on-device. No frames leave the browser, and MediaPipe runs locally via WebAssembly.
            </p>
            {poseError && <p className="mt-2 text-xs text-rose-200">Model error: {poseError}</p>}
          </div>
          <EventList events={events} />
        </div>
      </div>
      <footer className="rounded-3xl border border-white/10 bg-slate-900/60 px-4 py-3 text-sm text-white/60">
        All processing happens on-device. No video is uploaded.
      </footer>
    </section>
  );
}
