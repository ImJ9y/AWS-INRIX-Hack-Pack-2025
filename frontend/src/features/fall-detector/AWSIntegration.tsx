import { useEffect, useState, useRef } from "react";
import clsx from "clsx";

interface AWSStats {
  totalDetections: number;
  totalEmergencies: number;
  peopleCount: number;
  maxSeverity: number;
  emergencyActive: boolean;
}

interface EmergencyAlert {
  type: 'emergency_alert' | 'emergency_verified' | 'emergency_cleared' | 'emergency_verifying';
  severity?: number;
  message: string;
  remainingTime?: number;
  videoUrl?: string;
}

interface Detection {
  id: number;
  bbox: [number, number, number, number];
  center: [number, number];
  velocity: number;
  angle: number;
  severity: number;
  v_norm?: number;
  torso_angle?: number;
  pattern_score?: number;
  near_floor?: boolean;
}

interface CameraData {
  frame: string;
  detections: Detection[];
  stats: AWSStats;
}

export function AWSIntegration() {
  const [connected, setConnected] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [autoStarted, setAutoStarted] = useState(false); // Track if we've auto-started
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
  
  const socketRef = useRef<WebSocket | null>(null);
  const videoRef = useRef<HTMLImageElement | null>(null);

  // Auto-start camera when page loads and backend is connected
  useEffect(() => {
    const autoStartCamera = async () => {
      // Only auto-start once when connected for the first time
      if (!autoStarted && connected) {
        setAutoStarted(true);
        console.log('Auto-starting camera...');
        // Wait a moment for backend to be fully ready
        setTimeout(async () => {
          try {
            const response = await fetch('http://localhost:5001/api/start_camera', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
            });
            const result = await response.json();
            if (result.success) {
              setCameraActive(true);
              console.log('Camera auto-started successfully');
            } else {
              console.log('Camera already running or not available');
            }
          } catch (error) {
            console.error('Failed to auto-start camera:', error);
          }
        }, 1500);
      }
    };
    
    autoStartCamera();
  }, [connected, autoStarted]);

  useEffect(() => {
    // Poll backend for updates instead of WebSocket
    const pollBackend = async () => {
      try {
        // Check if backend is running
        const statusResponse = await fetch('http://localhost:5001/api/status');
        if (statusResponse.ok) {
          const statusData = await statusResponse.json();
          setConnected(true);
          
          // Update camera active state from backend
          setCameraActive(statusData.camera_active || false);
          
          // Get latest frame if camera is active
          if (statusData.camera_active) {
            const frameResponse = await fetch('http://localhost:5001/api/latest_frame');
            if (frameResponse.ok) {
              const frameData = await frameResponse.json();
              if (frameData.frame) {
                setVideoFrame(frameData.frame);
              }
            }
            
            // Get detection data
            const detectionsResponse = await fetch('http://localhost:5001/api/detections');
            if (detectionsResponse.ok) {
              const detectionsData = await detectionsResponse.json();
              
              // Map backend stats to frontend format
              setStats({
                totalDetections: detectionsData.stats.total_detections || 0,
                totalEmergencies: detectionsData.stats.total_emergencies || 0,
                peopleCount: detectionsData.stats.current_people_count || 0,
                maxSeverity: detectionsData.stats.max_severity || 1,
                emergencyActive: detectionsData.stats.emergency_active || false
              });
              
              // Convert backend detection data to frontend format
              const detections: Detection[] = [];
              Object.entries(detectionsData.detections).forEach(([personId, data]: [string, any]) => {
                if (data && data.center && data.center.length >= 2) {
                  detections.push({
                    id: parseInt(personId),
                    bbox: [data.center[0] - 25, data.center[1] - 25, data.center[0] + 25, data.center[1] + 25],
                    center: data.center,
                    velocity: data.velocity || 0,
                    angle: data.angle || 0,
                    severity: data.severity || 1,
                    v_norm: data.v_norm,
                    torso_angle: data.torso_angle,
                    pattern_score: data.pattern_score,
                    near_floor: data.near_floor
                  });
                }
              });
              setDetections(detections);
              
              // Check for high severity and add alerts
              if (detectionsData.stats.max_severity >= 8) {
                addAlert({
                  type: 'emergency_alert',
                  severity: detectionsData.stats.max_severity,
                  message: `HIGH SEVERITY DETECTED! Severity: ${detectionsData.stats.max_severity}/10`
                });
              } else if (detectionsData.stats.max_severity >= 5) {
                addAlert({
                  type: 'emergency_verifying',
                  severity: detectionsData.stats.max_severity,
                  message: `Moderate severity detected. Severity: ${detectionsData.stats.max_severity}/10`
                });
              }
            }
          }
        } else {
          setConnected(false);
        }
      } catch (error) {
        console.error('Error polling backend:', error);
        setConnected(false);
      }
    };

    // Poll every 500ms
    const interval = setInterval(pollBackend, 500);
    
    // Initial poll
    pollBackend();

    return () => {
      clearInterval(interval);
    };
  }, [cameraActive]);

  const startCamera = async () => {
    try {
      const response = await fetch('http://localhost:5001/api/start_camera', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      const result = await response.json();
      if (result.success) {
        setCameraActive(true);
        addAlert({
          type: 'emergency_cleared',
          message: 'Camera started successfully!'
        });
      } else {
        addAlert({
          type: 'emergency_alert',
          message: 'Failed to start camera. Please check if camera is available.'
        });
      }
    } catch (error) {
      console.error('Error starting camera:', error);
      addAlert({
        type: 'emergency_alert',
        message: 'Error connecting to camera service'
      });
    }
  };

  const stopCamera = async () => {
    try {
      const response = await fetch('http://localhost:5001/api/stop_camera', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      const result = await response.json();
      if (result.success) {
        setCameraActive(false);
        setVideoFrame(null);
        addAlert({
          type: 'emergency_cleared',
          message: 'Camera stopped successfully!'
        });
      }
    } catch (error) {
      console.error('Error stopping camera:', error);
    }
  };

  const addAlert = (alert: EmergencyAlert) => {
    setAlerts(prev => [alert, ...prev.slice(0, 4)]);
  };

  const getAlertStyle = (type: EmergencyAlert['type']) => {
    switch (type) {
      case 'emergency_alert':
      case 'emergency_verified':
        return 'bg-red-100 text-red-700 border-red-200';
      case 'emergency_cleared':
        return 'bg-green-100 text-green-700 border-green-200';
      case 'emergency_verifying':
        return 'bg-yellow-100 text-yellow-700 border-yellow-200';
      default:
        return 'bg-gray-100 text-gray-700 border-gray-200';
    }
  };

  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-slate-900">AWS Integration</h3>
          <p className="text-xs text-slate-500">Python backend + AWS services</p>
        </div>
        <div className="flex items-center gap-2">
          <div className={clsx(
            "h-3 w-3 rounded-full",
            connected ? "bg-green-500" : "bg-red-500"
          )} />
          <span className="text-xs text-slate-500">
            {connected ? "Connected" : "Disconnected"}
          </span>
        </div>
      </div>

      {/* Auto-start Status */}
      {autoStarted && cameraActive && (
        <div className="mb-3 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-xs text-green-700">
          Camera auto-started when page loaded. Live data is being streamed!
        </div>
      )}

      {/* Camera Controls */}
      <div className="mb-4 flex gap-2">
        <button
          onClick={startCamera}
          disabled={!connected || cameraActive}
          className={clsx(
            "flex-1 rounded-full px-4 py-2 text-sm font-medium transition-colors",
            connected && !cameraActive
              ? "bg-green-100 text-green-700 hover:bg-green-200"
              : "bg-gray-100 text-gray-400 cursor-not-allowed"
          )}
        >
          {autoStarted && cameraActive ? "Restart Camera" : "Start AWS Camera"}
        </button>
        <button
          onClick={stopCamera}
          disabled={!connected || !cameraActive}
          className={clsx(
            "flex-1 rounded-full px-4 py-2 text-sm font-medium transition-colors",
            connected && cameraActive
              ? "bg-red-100 text-red-700 hover:bg-red-200"
              : "bg-gray-100 text-gray-400 cursor-not-allowed"
          )}
        >
          Stop Camera
        </button>
      </div>

      {/* Video Stream - Hidden */}
      {/* {videoFrame && (
        <div className="mb-4 rounded-2xl overflow-hidden bg-black relative">
          <img
            ref={videoRef}
            src={`data:image/jpeg;base64,${videoFrame}`}
            alt="AWS Camera Feed"
            className="w-full h-48 object-cover"
          />
          <div className="absolute border-2 text-white text-xs p-1 rounded"
            style={{
              left: `${(detection.center[0] - 25) * 100 / 1920}%`, // Assuming 1920px width
              top: `${(detection.center[1] - 25) * 100 / 1080}%`, // Assuming 1080px height
              width: '50px',
              height: '50px',
              borderColor: detection.severity >= 8 ? '#ef4444' : detection.severity >= 5 ? '#f59e0b' : '#10b981',
              backgroundColor: detection.severity >= 8 ? 'rgba(239, 68, 68, 0.3)' : detection.severity >= 5 ? 'rgba(245, 158, 11, 0.3)' : 'rgba(16, 185, 129, 0.3)'
            }}
          >
            <div className="text-center">
              <div className="font-bold">P{detection.id}</div>
              <div className="text-xs">S:{detection.severity}</div>
            </div>
          </div>
        </div>
      )} */}

      {/* AWS Statistics */}
      <div className="mb-4 grid grid-cols-3 gap-3">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2">
          <p className="text-xs text-slate-500">Emergencies</p>
          <p className="text-lg font-semibold text-slate-900">{stats.totalEmergencies}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2">
          <p className="text-xs text-slate-500">People Count</p>
          <p className="text-lg font-semibold text-slate-900">{stats.peopleCount}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2">
          <p className="text-xs text-slate-500">Max Severity</p>
          <p className="text-lg font-semibold text-slate-900">{stats.maxSeverity}/10</p>
        </div>
      </div>

      {/* Pose Detection Status */}
      <div className="mb-4 rounded-2xl border border-blue-200 bg-blue-50 px-3 py-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-blue-700 font-medium">Pose Detection Active</span>
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-blue-500" />
            <span className="text-blue-700">YOLOv8n-Pose + ByteTrack</span>
          </div>
        </div>
        <div className="mt-1 text-xs text-blue-600">
          Enhanced fall detection using torso angle, normalized velocity, and temporal patterns
        </div>
      </div>

      {/* Current Detections */}
      {detections.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-semibold text-slate-900 mb-2">Current Detections</h4>
          <div className="space-y-2">
            {detections.map((detection) => (
              <div
                key={detection.id}
                className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm"
              >
                <div className="flex justify-between items-center">
                  <span className="font-medium">Person {detection.id}</span>
                  <span className={clsx(
                    "rounded-full px-2 py-1 text-xs font-semibold",
                    detection.severity >= 8
                      ? "bg-red-100 text-red-700"
                      : detection.severity >= 5
                      ? "bg-yellow-100 text-yellow-700"
                      : "bg-green-100 text-green-700"
                  )}>
                    Severity {detection.severity}/10
                  </span>
                </div>
                <div className="mt-1 grid grid-cols-2 gap-2 text-xs text-slate-500">
                  <div>Velocity: {detection.velocity.toFixed(2)}</div>
                  <div>Torso Angle: {detection.torso_angle?.toFixed(1) || detection.angle.toFixed(1)} degrees</div>
                  <div>Norm Velocity: {detection.v_norm?.toFixed(2) || 'N/A'}</div>
                  <div>Pattern Score: {detection.pattern_score?.toFixed(1) || 'N/A'}</div>
                  {detection.near_floor && <div className="col-span-2 text-orange-600 font-medium">Near Floor</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Emergency Alerts */}
      {alerts.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-slate-900 mb-2">Emergency Alerts</h4>
          <div className="space-y-2 max-h-32 overflow-y-auto">
            {alerts.map((alert, index) => (
              <div
                key={index}
                className={clsx(
                  "rounded-lg border px-3 py-2 text-sm font-medium",
                  getAlertStyle(alert.type)
                )}
              >
                {alert.message}
                {alert.remainingTime && (
                  <div className="text-xs mt-1">
                    Time remaining: {alert.remainingTime.toFixed(1)}s
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AWS Services Status */}
      <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-500">AWS Services</span>
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-green-500" />
            <span className="text-slate-700">S3, DynamoDB, SNS, CloudWatch</span>
          </div>
        </div>
      </div>
    </div>
  );
}
