import { useEffect, useState } from "react";
import { AlertTriangle, Antenna, Brain, CameraOff, Play, ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface AWSStats {
  totalDetections: number;
  totalEmergencies: number;
  peopleCount: number;
  maxSeverity: number;
  emergencyActive: boolean;
}

interface EmergencyAlert {
  type: "emergency_alert" | "emergency_verified" | "emergency_cleared" | "emergency_verifying";
  severity?: number;
  message: string;
  remainingTime?: number;
}

interface Detection {
  id: number;
  bbox: [number, number, number, number];
  center: [number, number];
  velocity: number;
  angle: number;
  severity: number;
}

interface AIAnalysis {
  analysis?: string;
  provider?: string;
  timestamp?: string;
  emergency_data?: {
    severity: number;
    velocity: number;
    angle: number;
    timestamp: string;
  };
  error?: string;
  message?: string;
  gemini_configured?: boolean;
}

const FRAME_WIDTH = 640;
const FRAME_HEIGHT = 360;

export function AWSIntegration() {
  const [connected, setConnected] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [stats, setStats] = useState<AWSStats>({
    totalDetections: 0,
    totalEmergencies: 0,
    peopleCount: 0,
    maxSeverity: 1,
    emergencyActive: false
  });
  const [alerts, setAlerts] = useState<EmergencyAlert[]>([]);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [videoFrame, setVideoFrame] = useState<string | null>(null);
  const [tab, setTab] = useState("detections");
  const [lastError, setLastError] = useState<string | null>(null);
  const [aiAnalysis, setAIAnalysis] = useState<AIAnalysis | null>(null);
  const [aiLoading, setAILoading] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const pollBackend = async () => {
      try {
        const statusResponse = await fetch("http://localhost:5001/api/status");
        if (!statusResponse.ok) throw new Error("Status offline");
        const statusData = await statusResponse.json();
        if (cancelled) return;
        setConnected(true);
        setLastError(null);
        setCameraActive(Boolean(statusData.camera_active));

        if (statusData.camera_active) {
          const [frameResponse, detectionsResponse, aiResponse] = await Promise.all([
            fetch("http://localhost:5001/api/latest_frame"),
            fetch("http://localhost:5001/api/detections"),
            fetch("http://localhost:5001/api/ai_analysis")
          ]);
          if (frameResponse.ok) {
            const frameData = await frameResponse.json();
            setVideoFrame(frameData.frame ?? null);
          }
          if (detectionsResponse.ok) {
            const detectionsData = await detectionsResponse.json();
            const mappedStats: AWSStats = {
              totalDetections: detectionsData.stats.total_detections || 0,
              totalEmergencies: detectionsData.stats.total_emergencies || 0,
              peopleCount: detectionsData.stats.current_people_count || 0,
              maxSeverity: detectionsData.stats.max_severity || 1,
              emergencyActive: detectionsData.stats.emergency_active || false
            };
            setStats(mappedStats);

            const mappedDetections: Detection[] = [];
            Object.entries(detectionsData.detections).forEach(([personId, positions]: [string, any]) => {
              if (!Array.isArray(positions) || !positions.length) return;
              const lastPosition = positions[positions.length - 1];
              const prevPosition = positions.length > 1 ? positions[positions.length - 2] : lastPosition;
              const velocity = Math.sqrt(Math.pow(lastPosition[0] - prevPosition[0], 2) + Math.pow(lastPosition[1] - prevPosition[1], 2)) / 10;
              const angle = (Math.atan2(lastPosition[1] - prevPosition[1], lastPosition[0] - prevPosition[0]) * 180) / Math.PI;
              mappedDetections.push({
                id: Number(personId),
                bbox: [lastPosition[0] - 25, lastPosition[1] - 25, lastPosition[0] + 25, lastPosition[1] + 25],
                center: lastPosition,
                velocity: Math.min(velocity, 10),
                angle: Math.abs(angle),
                severity: detectionsData.stats.max_severity
              });
            });
            setDetections(mappedDetections);

            if (mappedStats.maxSeverity >= 8) {
              addAlert({
                type: "emergency_alert",
                severity: mappedStats.maxSeverity,
                message: `High severity detected (${mappedStats.maxSeverity}/10).`
              });
            } else if (mappedStats.maxSeverity >= 5) {
              addAlert({
                type: "emergency_verifying",
                severity: mappedStats.maxSeverity,
                message: `Moderate severity detected (${mappedStats.maxSeverity}/10).`
              });
            }
          }
          
          // Get AI analysis
          if (aiResponse.ok) {
            const aiData = await aiResponse.json();
            if (aiData.analysis || aiData.error || aiData.message) {
              setAIAnalysis(aiData);
            }
          }
        } else {
          setDetections([]);
        }
      } catch (error) {
        setConnected(false);
        setLastError("Unable to reach the local AWS bridge.");
      }
    };

    const interval = setInterval(pollBackend, 800);
    pollBackend();

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const startCamera = async () => {
    try {
      const response = await fetch("http://localhost:5001/api/start_camera", {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      const result = await response.json();
      if (!response.ok || !result.success) {
        throw new Error("Start failed");
      }
      addAlert({ type: "emergency_cleared", message: "Camera started." });
      setCameraActive(true);
    } catch (error) {
      addAlert({ type: "emergency_alert", message: "Unable to start camera." });
    }
  };

  const stopCamera = async () => {
    try {
      const response = await fetch("http://localhost:5001/api/stop_camera", {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      const result = await response.json();
      if (!response.ok || !result.success) {
        throw new Error("Stop failed");
      }
      addAlert({ type: "emergency_cleared", message: "Camera stopped." });
      setCameraActive(false);
      setVideoFrame(null);
    } catch (error) {
      addAlert({ type: "emergency_alert", message: "Unable to stop camera." });
    }
  };

  const addAlert = (alert: EmergencyAlert) => {
    setAlerts((prev) => [alert, ...prev].slice(0, 4));
  };

  const handleCameraToggle = (checked: boolean) => {
    if (!connected) return;
    if (checked) {
      void startCamera();
    } else {
      void stopCamera();
    }
  };

  const getAlertStyle = (type: EmergencyAlert["type"]) => {
    switch (type) {
      case "emergency_alert":
        return "border-danger/30 bg-danger/5 text-danger";
      case "emergency_verified":
        return "border-warn/30 bg-warn/5 text-warn";
      case "emergency_cleared":
        return "border-success/30 bg-success/5 text-success";
      case "emergency_verifying":
        return "border-warn/30 bg-warn/5 text-warn";
      default:
        return "border-border bg-slate-50 text-ink";
    }
  };

  const statusBadge = connected ? "bg-success/10 text-success" : "bg-danger/10 text-danger";

  return (
    <Card className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-ink">AWS camera bridge</p>
          <p className="text-xs text-ink-muted">Python edge service + SNS dispatch</p>
        </div>
        <div className={cn("inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium", statusBadge)}>
          <Antenna size={20} />
          {connected ? "Connected" : "Offline"}
        </div>
      </header>

      <div className="rounded-2xl border border-border bg-slate-50 p-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-ink">Camera control</p>
            <p className="text-sm text-ink-muted">Start a remote stream when onsite devices are idle.</p>
          </div>
          <div className="flex items-center gap-3">
            <Switch checked={cameraActive} onCheckedChange={handleCameraToggle} aria-label="Toggle AWS camera" />
            <span className="text-sm font-medium text-ink">{cameraActive ? "Camera active" : "Camera idle"}</span>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <Button size="sm" onClick={startCamera} disabled={!connected || cameraActive} aria-label="Start AWS camera">
            <Play size={20} />
            Start
          </Button>
          <Button size="sm" variant="outline" onClick={stopCamera} disabled={!connected || !cameraActive} aria-label="Stop AWS camera">
            <CameraOff size={20} />
            Stop
          </Button>
        </div>
        {lastError && <p className="mt-3 text-xs text-danger">{lastError}</p>}
      </div>

      <div className="space-y-4">
        <div className="relative aspect-video overflow-hidden rounded-2xl border border-border bg-slate-100">
          {videoFrame ? (
            <>
              <img src={`data:image/jpeg;base64,${videoFrame}`} alt="AWS camera feed" className="h-full w-full object-cover" />
              {detections.map((detection) => {
                const [x1, y1, x2, y2] = detection.bbox;
                const left = (x1 / FRAME_WIDTH) * 100;
                const top = (y1 / FRAME_HEIGHT) * 100;
                const width = ((x2 - x1) / FRAME_WIDTH) * 100;
                const height = ((y2 - y1) / FRAME_HEIGHT) * 100;
                const tone = detection.severity >= 8 ? "border-danger bg-danger/10" : detection.severity >= 5 ? "border-warn bg-warn/10" : "border-success bg-success/10";
                return (
                  <span
                    key={detection.id}
                    className={cn("absolute rounded-xl border p-1 text-[10px] font-semibold text-ink", tone)}
                    style={{ left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%` }}
                  >
                    P{detection.id}
                  </span>
                );
              })}
            </>
          ) : (
            <div className="flex h-full flex-col items-center justify-center text-sm text-ink-muted">
              <CameraOff size={20} />
              Waiting for frame
            </div>
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Stat label="Total detections" value={stats.totalDetections} />
          <Stat label="Emergencies" value={stats.totalEmergencies} />
          <Stat label="People on feed" value={stats.peopleCount} />
          <Stat label="Max severity" value={`${stats.maxSeverity}/10`} />
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList>
          <TabsTrigger value="detections">Detections</TabsTrigger>
          <TabsTrigger value="alerts">Alerts</TabsTrigger>
          <TabsTrigger value="ai">
            <Brain size={16} className="mr-2" />
            AI Analysis
          </TabsTrigger>
        </TabsList>
        <TabsContent value="detections">
          {detections.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border/80 bg-slate-50 p-4 text-sm text-ink-muted">
              No detections on the AWS feed.
            </div>
          ) : (
            <ul className="space-y-3">
              {detections.map((detection) => (
                <li key={detection.id} className="rounded-2xl border border-border bg-white p-4 shadow-sm">
                  <div className="flex items-center justify-between text-sm font-semibold text-ink">
                    <span>Person {detection.id}</span>
                    <span className={cn(
                      "rounded-full px-3 py-1 text-xs font-semibold",
                      detection.severity >= 8
                        ? "bg-danger/10 text-danger"
                        : detection.severity >= 5
                        ? "bg-warn/10 text-warn"
                        : "bg-success/10 text-success"
                    )}>
                      Severity {detection.severity}/10
                    </span>
                  </div>
                  <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-ink-muted">
                    <span>Velocity {detection.velocity.toFixed(2)}</span>
                    <span>Angle {detection.angle.toFixed(1)}°</span>
                    <span>Center ({detection.center[0]}, {detection.center[1]})</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>
        <TabsContent value="alerts">
          {alerts.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border/80 bg-slate-50 p-4 text-sm text-ink-muted">
              No alerts yet.
            </div>
          ) : (
            <ul className="space-y-3">
              {alerts.map((alert, index) => (
                <li key={`${alert.type}-${index}`} className={cn("rounded-2xl border p-4 text-sm", getAlertStyle(alert.type))}>
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{alert.message}</span>
                    <Tooltip content="Maximum severity across tracked people">
                      <ShieldCheck size={20} className="text-ink" />
                    </Tooltip>
                  </div>
                  {alert.remainingTime && <p className="text-xs text-ink-muted">Time left {alert.remainingTime.toFixed(1)}s</p>}
                </li>
              ))}
            </ul>
          )}
        </TabsContent>
        <TabsContent value="ai">
          <AIAnalysisPanel analysis={aiAnalysis} loading={aiLoading} />
        </TabsContent>
      </Tabs>

      <div className="rounded-2xl border border-border bg-slate-50 px-4 py-3 text-xs text-ink-muted">
        <div className="flex items-center gap-2">
          <ShieldCheck size={20} />
          AWS services monitored: S3, DynamoDB, SNS, CloudWatch.
        </div>
      </div>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-border bg-white p-4 shadow-sm">
      <p className="text-xs uppercase tracking-[0.18em] text-ink-muted">{label}</p>
      <p className="mt-2 text-lg font-semibold text-ink">{value}</p>
    </div>
  );
}

function AIAnalysisPanel({ analysis, loading }: { analysis: AIAnalysis | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="rounded-2xl border border-border bg-white p-6 text-center">
        <Sparkles size={32} className="mx-auto mb-3 animate-pulse text-purple-500" />
        <p className="text-sm font-semibold text-ink">Analyzing with Gemini AI...</p>
        <p className="mt-1 text-xs text-ink-muted">Please wait while we process the fall detection</p>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="rounded-2xl border border-dashed border-border/80 bg-slate-50 p-6 text-center">
        <Brain size={32} className="mx-auto mb-3 text-ink-muted" />
        <p className="text-sm font-semibold text-ink">No AI analysis yet</p>
        <p className="mt-1 text-xs text-ink-muted">
          Gemini AI will analyze falls automatically when detected
        </p>
      </div>
    );
  }

  if (analysis.error) {
    return (
      <div className="rounded-2xl border border-danger/30 bg-danger/5 p-6">
        <div className="flex items-start gap-3">
          <AlertTriangle size={24} className="flex-shrink-0 text-danger" />
          <div>
            <p className="text-sm font-semibold text-danger">Analysis Error</p>
            <p className="mt-1 text-xs text-ink-muted">{analysis.error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (analysis.message) {
    return (
      <div className="rounded-2xl border border-border bg-white p-6">
        <div className="flex items-center gap-2 text-sm text-ink-muted">
          <Brain size={20} />
          <span>{analysis.message}</span>
        </div>
        {analysis.gemini_configured === false && (
          <div className="mt-3 rounded-lg bg-warn/10 p-3 text-xs text-warn">
            <p className="font-semibold">WARNING: Gemini API not configured</p>
            <p className="mt-1">Set GOOGLE_API_KEY in backend/.env file to enable AI analysis</p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Emergency Data Summary */}
      {analysis.emergency_data && (
        <div className="rounded-2xl border border-danger/30 bg-danger/5 p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={20} className="text-danger" />
            <p className="text-sm font-semibold text-danger">Emergency Detected</p>
          </div>
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div>
              <p className="text-ink-muted">Severity</p>
              <p className="mt-1 font-semibold text-ink">{analysis.emergency_data.severity}/10</p>
            </div>
            <div>
              <p className="text-ink-muted">Velocity</p>
              <p className="mt-1 font-semibold text-ink">{analysis.emergency_data.velocity.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-ink-muted">Angle</p>
              <p className="mt-1 font-semibold text-ink">{analysis.emergency_data.angle.toFixed(1)}°</p>
            </div>
          </div>
        </div>
      )}

      {/* AI Analysis */}
      {analysis.analysis && (
        <div className="rounded-2xl border border-purple-200 bg-gradient-to-br from-purple-50 to-blue-50 p-6">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles size={20} className="text-purple-600" />
              <p className="text-sm font-semibold text-ink">
                {analysis.provider || "Gemini AI Analysis"}
              </p>
            </div>
            {analysis.timestamp && (
              <p className="text-xs text-ink-muted">
                {new Date(analysis.timestamp).toLocaleTimeString()}
              </p>
            )}
          </div>
          
          <div className="prose prose-sm max-w-none">
            <div className="whitespace-pre-wrap text-sm text-ink leading-relaxed">
              {analysis.analysis}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
