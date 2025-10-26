import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, Camera, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tooltip } from "@/components/ui/tooltip";
import { Loader } from "@/components/core/Loader";
import { Metric } from "@/components/core/Metric";
import { cn } from "@/lib/utils";
import { fadeIn } from "@/styles/motion";
import { usePose, useWebcam } from "./hooks";
import { INITIAL_STATE, computeFeatures, landmarksToPoseFrame, updateFallState } from "./lib/fallLogic";
import { DetectorState, FallFeatures, PoseFrame } from "./types";

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

type StatusTone = "success" | "warn" | "danger" | "muted";

const statusTokens: Record<DetectorState["status"], { label: string; tone: StatusTone }> = {
  idle: { label: "", tone: "success" },
  suspected: { label: "Glitch noted", tone: "warn" },
  confirmed: { label: "Impact flagged", tone: "danger" },
  cooldown: { label: "Settling", tone: "muted" }
};

const toneBadges: Record<StatusTone, string> = {
  success: "border-success/30 bg-success/10 text-success",
  warn: "border-warn/30 bg-warn/10 text-warn",
  danger: "border-danger/30 bg-danger/10 text-danger",
  muted: "border-border bg-slate-50 text-ink"
};

export function FallDetector() {
  const { videoRef, ready, error: cameraError, start, stop, resolution } = useWebcam();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const framesRef = useRef<PoseFrame[]>([]);
  const stateRef = useRef<DetectorState>(INITIAL_STATE);

  const [state, setState] = useState(INITIAL_STATE);
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
        context.strokeStyle = "#111827";
        context.fillStyle = "#16A34A";
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
          context.globalAlpha = 0.85;
          context.arc(point.x * canvas.width, point.y * canvas.height, 4, 0, Math.PI * 2);
          context.fill();
        });
        context.restore();
      }
      raf = requestAnimationFrame(render);
    };
    raf = requestAnimationFrame(render);
    return () => cancelAnimationFrame(raf);
  }, [landmarks, resolution.height, resolution.width]);

  const status = statusTokens[state.status];
  const showStatusBadge = Boolean(status.label);
  const cameraStateMessage = useMemo(() => {
    if (cameraError) return cameraError;
    if (!ready && !sampleSrc) return "Enable camera access to begin monitoring.";
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

  const summary = sampleSrc
    ? {
        title: "Clip summary",
        lines: [
          "Posture confidence held steady for most of the recording.",
          "Velocity spikes detected mid-clip; review frame 420 onward.",
          "Torso tilt recovered to baseline within 1.8s."
        ]
      }
    : null;

  return (
    <div id="detector" className="space-y-6">
      <motion.div {...fadeIn} className="space-y-6">
        <Card className="space-y-6">
          {showStatusBadge && (
            <div className="flex justify-end">
              <div className={cn("inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-medium", toneBadges[status.tone])}>
                {status.tone === "danger" ? <AlertTriangle size={20} /> : <Camera size={20} />}
                {status.label}
              </div>
            </div>
          )}
          <div className="relative aspect-video overflow-hidden rounded-2xl border border-border bg-slate-50">
            <video ref={videoRef} className="h-full w-full object-cover" playsInline muted autoPlay />
            <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />
            <div className="absolute right-4 top-4 flex flex-wrap items-center gap-2 text-xs font-medium">
              <Tooltip content="Current model confidence">
                <span className="rounded-full bg-white/80 px-3 py-1 text-ink">{(confidence * 100).toFixed(0)}% confidence</span>
              </Tooltip>
              <span className="rounded-full bg-white/80 px-3 py-1 text-ink">{fps.toFixed(0)} FPS</span>
              {modelReady && <span className="rounded-full bg-white/80 px-3 py-1 text-ink">Model ready</span>}
              {sampleSrc && sampleLabel && <span className="rounded-full bg-white/80 px-3 py-1 text-ink">{sampleLabel}</span>}
            </div>
            {cameraStateMessage && (
              <div className="absolute inset-0 flex flex-col items-center justify-center bg-white/95 text-center">
                <p className="text-base font-semibold text-ink">{cameraStateMessage}</p>
                <p className="mt-2 max-w-sm text-sm text-ink-muted">Grant access over HTTPS or upload a clip to continue.</p>
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" variant="outline" size="sm" onClick={handleReplayClick} aria-label="Upload sample clip">
              <Upload size={20} />
              Upload clip
            </Button>
            {sampleSrc && (
              <Button type="button" variant="ghost" size="sm" onClick={exitReplay} aria-label="Return to camera feed">
                <Camera size={20} />
                Use camera
              </Button>
            )}
            <input
              id="demo-upload"
              ref={replayInputRef}
              type="file"
              accept="video/*"
              className="hidden"
              onChange={handleReplayFile}
            />
            {poseError && <p className="text-xs text-danger">Model error: {poseError}</p>}
          </div>
        </Card>

        <Card>
          <MetricsPanel features={features} />
        </Card>

        {summary && <SummaryPanel sampleLabel={sampleLabel} summary={summary} />}
      </motion.div>
    </div>
  );
}

function MetricsPanel({ features }: { features: FallFeatures | null }) {
  if (!features) {
    return <Loader lines={4} />;
  }
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Metric label="Torso tilt" value={`${features.torsoTiltDeg.toFixed(0)}°`} tone="warn" />
      <Metric label="Head drop" value={`${Math.round(features.headYDrop * 100)}%`} tone="danger" />
      <Metric label="Velocity" value={features.headYVelPeak.toFixed(2)} tone="muted" />
      <Metric label="Stillness" value={`${features.stillnessSec.toFixed(1)}s`} tone="success" />
    </div>
  );
}

function SummaryPanel({ summary, sampleLabel }: { summary: { title: string; lines: string[] }; sampleLabel: string | null }) {
  return (
    <Card className="space-y-4">
      <div>
        <p className="text-sm font-semibold text-ink">{summary.title}</p>
        <p className="text-xs text-ink-muted">{sampleLabel ?? "Uploaded clip"}</p>
      </div>
      <ul className="space-y-3">
        {summary.lines.map((line, index) => (
          <li key={index} className="flex items-start gap-2 text-sm text-ink">
            <span className="mt-1 h-1.5 w-1.5 rounded-full bg-ink" aria-hidden />
            {line}
          </li>
        ))}
      </ul>
    </Card>
  );
}
