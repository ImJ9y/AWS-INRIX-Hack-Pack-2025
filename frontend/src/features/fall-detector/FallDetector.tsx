import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, Camera, RotateCcw, Upload, Stethoscope, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tooltip } from "@/components/ui/tooltip";
import { Loader } from "@/components/core/Loader";
import { Metric } from "@/components/core/Metric";
import { cn } from "@/lib/utils";
import { fadeIn } from "@/styles/motion";
import { usePose, useWebcam } from "./hooks";
import { INITIAL_STATE, computeFeatures, landmarksToPoseFrame, updateFallState } from "./lib/fallLogic";
import { DetectorState, FallEvent, FallFeatures, PoseFrame } from "./types";

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

interface ClipStats {
  maxVelocity: number;
  maxTorsoTilt: number;
  maxHeadDrop: number;
  minConfidence: number;
  avgConfidence: number;
  confidenceSum: number;
  frameCount: number;
  velocitySpikes: number[];
  tiltRecoveryTime: number;
  lastHighTiltFrame: number;
}

function generateClipSummary(stats: ClipStats, fps: number): string[] {
  const lines: string[] = [];
  
  // Analyze confidence stability
  const confidenceVariation = 1 - stats.minConfidence;
  if (confidenceVariation < 0.15) {
    lines.push(`Posture confidence remained excellent (${(stats.avgConfidence * 100).toFixed(0)}% average) throughout the recording.`);
  } else if (confidenceVariation < 0.3) {
    lines.push(`Posture confidence held steady for most frames (min: ${(stats.minConfidence * 100).toFixed(0)}%).`);
  } else {
    lines.push(`Confidence fluctuated during playback; lowest point was ${(stats.minConfidence * 100).toFixed(0)}%.`);
  }
  
  // Analyze velocity patterns
  if (stats.velocitySpikes.length > 0) {
    const firstSpike = stats.velocitySpikes[0];
    const approximateFrame = Math.round(firstSpike);
    if (stats.velocitySpikes.length === 1) {
      lines.push(`Single velocity spike detected (${stats.maxVelocity.toFixed(2)}) around frame ${approximateFrame}.`);
    } else if (stats.velocitySpikes.length <= 3) {
      lines.push(`${stats.velocitySpikes.length} velocity spikes detected; first spike at frame ${approximateFrame}.`);
    } else {
      lines.push(`Multiple velocity spikes detected (${stats.velocitySpikes.length} total); review from frame ${approximateFrame} onward.`);
    }
  } else if (stats.maxVelocity > 0.8) {
    lines.push(`Peak velocity of ${stats.maxVelocity.toFixed(2)} detected, but below alert threshold.`);
  } else {
    lines.push("No significant velocity changes detected throughout clip.");
  }
  
  // Analyze torso tilt and recovery
  if (stats.maxTorsoTilt > 45) {
    if (stats.tiltRecoveryTime > 0) {
      lines.push(`Significant torso tilt (${stats.maxTorsoTilt.toFixed(0)}°) detected; recovered to baseline in ${stats.tiltRecoveryTime.toFixed(1)}s.`);
    } else {
      lines.push(`High torso tilt angle (${stats.maxTorsoTilt.toFixed(0)}°) detected without full recovery during clip.`);
    }
  } else if (stats.maxTorsoTilt > 25) {
    if (stats.tiltRecoveryTime > 0) {
      lines.push(`Moderate torso tilt (${stats.maxTorsoTilt.toFixed(0)}°); stabilized within ${stats.tiltRecoveryTime.toFixed(1)}s.`);
    } else {
      lines.push(`Torso tilt angle reached ${stats.maxTorsoTilt.toFixed(0)}°, within normal movement range.`);
    }
  } else {
    lines.push("Posture remained upright throughout; no significant tilting observed.");
  }
  
  // Add head drop analysis if significant
  if (stats.maxHeadDrop > 0.5) {
    lines.push(`Notable head drop of ${(stats.maxHeadDrop * 100).toFixed(0)}% observed during movement.`);
  }
  
  return lines;
}

export function FallDetector() {
  const { videoRef, ready, error: cameraError, start, stop, resolution } = useWebcam();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const framesRef = useRef<PoseFrame[]>([]);
  const stateRef = useRef<DetectorState>(INITIAL_STATE);

  const [state, setState] = useState(INITIAL_STATE);
  const [features, setFeatures] = useState<FallFeatures | null>(null);
  const [lastEvent, setLastEvent] = useState<FallEvent | null>(null);
  const [sampleSrc, setSampleSrc] = useState<string | null>(null);
  const [sampleLabel, setSampleLabel] = useState<string | null>(null);
  const [clipEnded, setClipEnded] = useState(false);
  const [fallAnalysis, setFallAnalysis] = useState<string | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [clipAnalysis, setClipAnalysis] = useState<string | null>(null);
  const [clipAnalysisLoading, setClipAnalysisLoading] = useState(false);

  const replayInputRef = useRef<HTMLInputElement | null>(null);
  
  // Track clip statistics for dynamic summary
  const clipStatsRef = useRef({
    maxVelocity: 0,
    maxTorsoTilt: 0,
    maxHeadDrop: 0,
    minConfidence: 1,
    avgConfidence: 0,
    confidenceSum: 0,
    frameCount: 0,
    velocitySpikes: [] as number[],
    tiltRecoveryTime: 0,
    lastHighTiltFrame: 0
  });

  const { landmarks, fps, modelReady, confidence, error: poseError } = usePose(videoRef.current, {
    running: Boolean((ready || sampleSrc) && !cameraError),
    maxFps: 30
  });

  const analyzeWithGemini = async (event: FallEvent, features: FallFeatures) => {
    setAnalysisLoading(true);
    setFallAnalysis(null);
    
    try {
      const message = `As an emergency medicine doctor, analyze this fall detection:

FALL EVENT DETAILS:
- Severity: ${event.severity}
- Time: ${new Date(event.timestamp).toLocaleString()}
- Description: ${event.description}

MEASURED METRICS:
- Torso Tilt: ${features.torsoTiltDeg.toFixed(1)}°
- Head Drop: ${(features.headYDrop * 100).toFixed(1)}%
- Velocity: ${features.headYVelPeak.toFixed(2)}
- Stillness After Fall: ${features.stillnessSec.toFixed(1)}s

Provide a brief medical assessment (2-3 sentences) from a doctor's perspective covering:
1. What likely happened during this fall
2. Potential injuries to watch for
3. Recommended immediate action (call 911 or monitor)

Keep it concise and professional.`;

      const response = await fetch('http://localhost:5001/api/analyze_chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message })
      });

      if (!response.ok) {
        throw new Error('Gemini API unavailable');
      }

      const data = await response.json();
      if (data.success && data.response) {
        setFallAnalysis(data.response);
      } else {
        setFallAnalysis("AI analysis unavailable. Please ensure Gemini API is configured.");
      }
    } catch (error) {
      console.error('Gemini analysis error:', error);
      setFallAnalysis(null); // Hide on error
    } finally {
      setAnalysisLoading(false);
    }
  };

  const analyzeClipWithGemini = async () => {
    setClipAnalysisLoading(true);
    setClipAnalysis(null);
    
    const stats = clipStatsRef.current;
    
    try {
      const message = `As a physical therapist and movement specialist, analyze this video clip's movement patterns:

MOVEMENT ANALYSIS DATA:
- Maximum Velocity: ${stats.maxVelocity.toFixed(2)}
- Maximum Torso Tilt: ${stats.maxTorsoTilt.toFixed(1)}°
- Maximum Head Drop: ${(stats.maxHeadDrop * 100).toFixed(1)}%
- Average Confidence: ${(stats.avgConfidence * 100).toFixed(0)}%
- Minimum Confidence: ${(stats.minConfidence * 100).toFixed(0)}%
- Velocity Spikes: ${stats.velocitySpikes.length}
- Tilt Recovery Time: ${stats.tiltRecoveryTime > 0 ? stats.tiltRecoveryTime.toFixed(1) + 's' : 'N/A'}
- Total Frames Analyzed: ${stats.frameCount}

Provide a brief professional assessment (2-3 sentences) from a doctor's/therapist's perspective covering:
1. What type of movement or activity this appears to be
2. Any concerning patterns or movements observed
3. Overall assessment (normal activity, concerning movement, or potential fall)

Keep it natural, conversational, and professional - like you're explaining to a colleague.`;

      const response = await fetch('http://localhost:5001/api/analyze_chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message })
      });

      if (!response.ok) {
        throw new Error('Gemini API unavailable');
      }

      const data = await response.json();
      if (data.success && data.response) {
        setClipAnalysis(data.response);
      } else {
        setClipAnalysis(null);
      }
    } catch (error) {
      console.error('Clip analysis error:', error);
      setClipAnalysis(null);
    } finally {
      setClipAnalysisLoading(false);
    }
  };

  useEffect(() => {
    start();
  }, [start]);

  useEffect(() => {
    return () => {
      if (sampleSrc) URL.revokeObjectURL(sampleSrc);
    };
  }, [sampleSrc]);

  useEffect(() => {
    if (!sampleSrc) {
      setClipEnded(false);
      // Reset clip stats when switching back to camera
      clipStatsRef.current = {
        maxVelocity: 0,
        maxTorsoTilt: 0,
        maxHeadDrop: 0,
        minConfidence: 1,
        avgConfidence: 0,
        confidenceSum: 0,
        frameCount: 0,
        velocitySpikes: [],
        tiltRecoveryTime: 0,
        lastHighTiltFrame: 0
      };
    }
  }, [sampleSrc]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const handleEnded = () => {
      setClipEnded(true);
      // Analyze clip with Gemini when it ends
      if (sampleSrc && clipStatsRef.current.frameCount > 30) {
        analyzeClipWithGemini();
      }
    };
    video.addEventListener("ended", handleEnded);
    return () => video.removeEventListener("ended", handleEnded);
  }, [sampleSrc, ready]);

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

    // Track statistics for clip summary (only when playing uploaded clips)
    if (sampleSrc) {
      const stats = clipStatsRef.current;
      stats.frameCount++;
      
      // Track max values
      if (computed.headYVelPeak > stats.maxVelocity) {
        stats.maxVelocity = computed.headYVelPeak;
      }
      if (computed.torsoTiltDeg > stats.maxTorsoTilt) {
        stats.maxTorsoTilt = computed.torsoTiltDeg;
        stats.lastHighTiltFrame = stats.frameCount;
      }
      if (computed.headYDrop > stats.maxHeadDrop) {
        stats.maxHeadDrop = computed.headYDrop;
      }
      
      // Track confidence
      if (confidence < stats.minConfidence) {
        stats.minConfidence = confidence;
      }
      stats.confidenceSum += confidence;
      stats.avgConfidence = stats.confidenceSum / stats.frameCount;
      
      // Track velocity spikes (> 1.5)
      if (computed.headYVelPeak > 1.5) {
        stats.velocitySpikes.push(stats.frameCount);
      }
      
      // Track torso tilt recovery
      if (stats.maxTorsoTilt > 30 && computed.torsoTiltDeg < 15) {
        if (stats.tiltRecoveryTime === 0) {
          stats.tiltRecoveryTime = (stats.frameCount - stats.lastHighTiltFrame) / fps;
        }
      }
    }

    const update = updateFallState(stateRef.current, computed, Date.now());
    if (update.changed) {
      stateRef.current = update.state;
      setState(update.state);
    }
    if (update.event) {
      setLastEvent(update.event);
      // Get AI analysis from doctor's perspective
      analyzeWithGemini(update.event, computed);
    }
  }, [landmarks, sampleSrc, confidence, fps]);

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
    
    // Reset clip statistics and analysis
    clipStatsRef.current = {
      maxVelocity: 0,
      maxTorsoTilt: 0,
      maxHeadDrop: 0,
      minConfidence: 1,
      avgConfidence: 0,
      confidenceSum: 0,
      frameCount: 0,
      velocitySpikes: [],
      tiltRecoveryTime: 0,
      lastHighTiltFrame: 0
    };
    setClipAnalysis(null);
    setClipAnalysisLoading(false);
    
    const url = URL.createObjectURL(file);
    setSampleSrc(url);
    setSampleLabel(file.name);
    setClipEnded(false);
    stop();
    if (videoRef.current) {
      videoRef.current.srcObject = null;
      videoRef.current.src = url;
      videoRef.current.loop = false;
      videoRef.current.muted = true;
      videoRef.current.currentTime = 0;
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
    setClipEnded(false);
    await start();
  };

  const replayClip = () => {
    const video = videoRef.current;
    if (!video) return;
    
    // Reset stats and analysis for replay
    clipStatsRef.current = {
      maxVelocity: 0,
      maxTorsoTilt: 0,
      maxHeadDrop: 0,
      minConfidence: 1,
      avgConfidence: 0,
      confidenceSum: 0,
      frameCount: 0,
      velocitySpikes: [],
      tiltRecoveryTime: 0,
      lastHighTiltFrame: 0
    };
    setClipAnalysis(null);
    setClipAnalysisLoading(false);
    
    video.currentTime = 0;
    setClipEnded(false);
    void video.play();
  };

  // Generate dynamic summary based on actual clip statistics
  const summary = sampleSrc && clipStatsRef.current.frameCount > 30
    ? {
        title: "Clip summary",
        lines: generateClipSummary(clipStatsRef.current, fps)
      }
    : null;

  return (
    <div id="detector" className="space-y-6">
      <motion.div {...fadeIn} className="space-y-6">
        <Card className="space-y-6">
          <div className="relative aspect-video overflow-hidden rounded-2xl border border-border bg-slate-50">
            <video ref={videoRef} className="h-full w-full object-cover" playsInline muted autoPlay />
            <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />
            {showStatusBadge && (
              <div
                className={cn(
                  "absolute left-4 top-4 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide",
                  toneBadges[status.tone]
                )}
              >
                {status.tone === "danger" ? <AlertTriangle size={16} /> : <Camera size={16} />}
                {status.label}
              </div>
            )}
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
            {clipEnded && sampleSrc && (
              <Button type="button" variant="ghost" size="sm" onClick={replayClip} aria-label="Replay uploaded clip">
                <RotateCcw size={20} />
                Play again
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

        {summary && <SummaryPanel sampleLabel={sampleLabel} summary={summary} aiAnalysis={clipAnalysis} aiLoading={clipAnalysisLoading} />}
        <FallLogPanel lastEvent={lastEvent!} analysis={fallAnalysis} analysisLoading={analysisLoading} />
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

function SummaryPanel({ summary, sampleLabel, aiAnalysis, aiLoading }: { 
  summary: { title: string; lines: string[] }; 
  sampleLabel: string | null;
  aiAnalysis: string | null;
  aiLoading: boolean;
}) {
  return (
    <Card className="space-y-4">
      <div>
        <p className="text-sm font-semibold text-ink">{summary.title}</p>
        <p className="text-xs text-ink-muted">{sampleLabel ?? "Uploaded clip"}</p>
      </div>
      
      {/* AI Analysis (Doctor's Perspective) */}
      {aiLoading && (
        <div className="rounded-lg border border-purple-200 bg-gradient-to-br from-purple-50 to-blue-50 p-4">
          <div className="flex items-center gap-2">
            <Sparkles size={20} className="animate-pulse text-purple-600" />
            <p className="text-sm font-semibold text-ink">Analyzing clip with AI...</p>
          </div>
        </div>
      )}
      
      {aiAnalysis && !aiLoading && (
        <div className="rounded-lg border border-purple-200 bg-gradient-to-br from-purple-50 to-blue-50 p-4 space-y-2">
          <div className="flex items-center gap-2">
            <Stethoscope size={20} className="text-purple-600" />
            <p className="text-sm font-semibold text-ink">Professional Assessment</p>
          </div>
          <p className="text-sm text-ink leading-relaxed whitespace-pre-wrap">{aiAnalysis}</p>
          <p className="text-xs text-ink-muted italic">⚡ Powered by Gemini AI</p>
        </div>
      )}
      
      {/* Technical Metrics (Collapsible Details) */}
      <details className="group">
        <summary className="cursor-pointer text-xs font-semibold text-ink-muted hover:text-ink">
          📊 Technical Metrics (click to expand)
        </summary>
        <ul className="mt-3 space-y-2">
          {summary.lines.map((line, index) => (
            <li key={index} className="flex items-start gap-2 text-xs text-ink-muted">
              <span className="mt-1 h-1 w-1 rounded-full bg-ink-muted" aria-hidden />
              {line}
            </li>
          ))}
        </ul>
      </details>
    </Card>
  );
}

function FallLogPanel({ lastEvent, analysis, analysisLoading }: { 
  lastEvent: FallEvent | null; 
  analysis: string | null;
  analysisLoading: boolean;
}) {
  if (!lastEvent) {
    return (
      <Card className="space-y-2">
        <p className="text-sm font-semibold text-ink">Fall log</p>
        <p className="text-sm text-ink-muted">No fall captured yet.</p>
      </Card>
    );
  }

  const timeLabel = new Date(lastEvent.timestamp).toLocaleString([], { hour: "2-digit", minute: "2-digit", month: "short", day: "numeric" });
  const severityTone = {
    Low: "bg-success/10 text-success",
    Moderate: "bg-warn/10 text-warn",
    High: "bg-warn/10 text-warn",
    Critical: "bg-danger/10 text-danger"
  }[lastEvent.severity];

  return (
    <Card className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-ink">Fall recorded</p>
          <p className="text-xs text-ink-muted">{timeLabel}</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${severityTone}`}>{lastEvent.severity}</span>
      </div>
      
      {/* Original Description */}
      <div className="rounded-lg border border-border bg-slate-50 p-3">
        <p className="text-xs font-semibold text-ink-muted mb-1">Detection Summary</p>
        <p className="text-sm text-ink">{lastEvent.description}</p>
      </div>

      {/* AI Doctor's Assessment */}
      {analysisLoading && (
        <div className="rounded-lg border border-purple-200 bg-gradient-to-br from-purple-50 to-blue-50 p-4">
          <div className="flex items-center gap-2">
            <Sparkles size={20} className="animate-pulse text-purple-600" />
            <p className="text-sm font-semibold text-ink">Consulting AI doctor...</p>
          </div>
        </div>
      )}

      {analysis && !analysisLoading && (
        <div className="rounded-lg border border-purple-200 bg-gradient-to-br from-purple-50 to-blue-50 p-4 space-y-2">
          <div className="flex items-center gap-2">
            <Stethoscope size={20} className="text-purple-600" />
            <p className="text-sm font-semibold text-ink">Doctor's Assessment</p>
          </div>
          <p className="text-sm text-ink leading-relaxed whitespace-pre-wrap">{analysis}</p>
          <p className="text-xs text-ink-muted italic mt-2">⚡ Powered by Gemini AI</p>
        </div>
      )}
    </Card>
  );
}
