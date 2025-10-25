export type Severity = "Low" | "Moderate" | "High" | "Critical";

export interface FallFeatures {
  headYDrop: number;
  headYVelPeak: number;
  torsoTiltDeg: number;
  stillnessSec: number;
  confidence: number;
  score: number;
}

export interface FallEvent {
  id: string;
  timestamp: string;
  severity: Severity;
  features: FallFeatures;
  description: string;
}

export type DetectorStatus = "idle" | "suspected" | "confirmed" | "cooldown";

export interface DetectorState {
  status: DetectorStatus;
  suspectSince: number | null;
  lastConfirmed: number | null;
  cooldownUntil: number | null;
}

export interface StateUpdate {
  state: DetectorState;
  event?: FallEvent;
  changed: boolean;
}

export interface NormalizedLandmark {
  x: number;
  y: number;
  z?: number;
  visibility?: number;
}

export interface PoseFrame {
  timestamp: number;
  landmarks: NormalizedLandmark[];
  headY: number;
  hipY: number;
  torsoTiltDeg: number;
}

export interface WebcamResolution {
  width: number;
  height: number;
}
