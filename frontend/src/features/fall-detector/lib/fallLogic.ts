import {
  DetectorState,
  FallEvent,
  FallFeatures,
  NormalizedLandmark,
  PoseFrame,
  Severity,
  StateUpdate
} from "../types";

export const TILT_THRESHOLD_DEG = 60;
export const DROP_THRESHOLD = 0.3;
export const VEL_THRESHOLD = 0.45;
export const STILLNESS_THRESHOLD_S = 4;
export const COOLDOWN_MS = 10_000;
export const SUSPECT_WINDOW_MS = 800;

const STILLNESS_LOOKBACK_MS = 5_000;

export const INITIAL_STATE: DetectorState = {
  status: "idle",
  suspectSince: null,
  lastConfirmed: null,
  cooldownUntil: null
};

const SHOULDER_LEFT = 11;
const SHOULDER_RIGHT = 12;
const HIP_LEFT = 23;
const HIP_RIGHT = 24;
const NOSE = 0;

function midpoint(a?: NormalizedLandmark, b?: NormalizedLandmark) {
  if (!a || !b) return undefined;
  return {
    x: (a.x + b.x) / 2,
    y: (a.y + b.y) / 2,
    z: ((a.z ?? 0) + (b.z ?? 0)) / 2
  };
}

export function computeFeatures(prevFrames: PoseFrame[], current: PoseFrame): FallFeatures {
  const recentFrames = prevFrames.filter((f) => current.timestamp - f.timestamp <= 600);
  const headValues = [...recentFrames.map((f) => f.headY), current.headY];
  const headDrop = Math.max(...headValues) - Math.min(...headValues);

  const lastFrame = prevFrames[prevFrames.length - 1];
  let headVelocity = 0;
  if (lastFrame) {
    const dy = current.headY - lastFrame.headY;
    const dt = (current.timestamp - lastFrame.timestamp) / 1000;
    headVelocity = dt > 0 ? dy / dt : 0;
  }
  const normalizedVelocity = Math.max(0, Math.min(1, headVelocity));

  const stillnessSince = computeStillness(prevFrames, current.timestamp);

  const score = (
    (headDrop >= DROP_THRESHOLD ? 2 : 0) +
    (current.torsoTiltDeg >= TILT_THRESHOLD_DEG ? 2 : 0) +
    (normalizedVelocity >= VEL_THRESHOLD ? 1 : 0) +
    (stillnessSince >= STILLNESS_THRESHOLD_S ? 1 : 0)
  );

  const confidence = computeConfidence(current.landmarks);

  return {
    headYDrop: clamp(headDrop, 0, 1),
    headYVelPeak: clamp(normalizedVelocity, 0, 1),
    torsoTiltDeg: Math.min(180, Math.max(0, current.torsoTiltDeg)),
    stillnessSec: stillnessSince,
    confidence,
    score
  };
}

function computeStillness(frames: PoseFrame[], now: number): number {
  let lastMotionTs = now;

  for (let i = frames.length - 1; i > 0; i -= 1) {
    const frame = frames[i];
    const prev = frames[i - 1];
    if (now - frame.timestamp > STILLNESS_LOOKBACK_MS) break;
    const motion =
      Math.abs(frame.headY - prev.headY) +
      Math.abs(frame.hipY - prev.hipY) +
      Math.abs(frame.torsoTiltDeg - prev.torsoTiltDeg) / 180;
    if (motion > 0.015) {
      lastMotionTs = frame.timestamp;
      break;
    }
  }

  return Math.max(0, (now - lastMotionTs) / 1000);
}

function computeConfidence(landmarks: NormalizedLandmark[]): number {
  if (!landmarks.length) return 0;
  const visibility = landmarks.map((l) => l.visibility ?? 0.9);
  const avg = visibility.reduce((acc, value) => acc + value, 0) / visibility.length;
  return clamp(avg, 0, 1);
}

export function classifySeverity(score: number): Severity {
  if (score >= 5) return "Critical";
  if (score >= 4) return "High";
  if (score >= 2) return "Moderate";
  return "Low";
}

export function describe(features: FallFeatures): string {
  const tilt = Math.round(features.torsoTiltDeg);
  const drop = Math.round(features.headYDrop * 100);
  return `Rapid head descent (${drop}% drop) with ${tilt} degrees torso tilt followed by ${features.stillnessSec.toFixed(
    1
  )}s stillness.`;
}

export function updateFallState(prevState: DetectorState, features: FallFeatures, now: number): StateUpdate {
  const state: DetectorState = { ...prevState };
  let event: FallEvent | undefined;
  let changed = false;

  const dropHit = features.headYDrop >= DROP_THRESHOLD;
  const tiltHit = features.torsoTiltDeg >= TILT_THRESHOLD_DEG;
  const velHit = features.headYVelPeak >= VEL_THRESHOLD;
  const stillnessHit = features.stillnessSec >= STILLNESS_THRESHOLD_S;
  const severeScore = features.score >= 5;

  if (state.status === "cooldown" && state.cooldownUntil && now >= state.cooldownUntil) {
    state.status = "idle";
    state.cooldownUntil = null;
    changed = true;
  }

  if (state.status === "confirmed" && state.lastConfirmed && now - state.lastConfirmed > 1500) {
    state.status = "cooldown";
    changed = true;
  }

  switch (state.status) {
    case "idle": {
      if ((dropHit && tiltHit) || features.score >= 3) {
        state.status = "suspected";
        state.suspectSince = now;
        changed = true;
      }
      break;
    }
    case "suspected": {
      if (state.suspectSince && now - state.suspectSince > SUSPECT_WINDOW_MS) {
        state.status = "idle";
        state.suspectSince = null;
        changed = true;
      }

      if ((dropHit && tiltHit && velHit) || (severeScore && stillnessHit)) {
        state.status = "confirmed";
        state.lastConfirmed = now;
        state.cooldownUntil = now + COOLDOWN_MS;
        state.suspectSince = null;
        changed = true;

        const severity = classifySeverity(features.score);
        event = {
          id: crypto.randomUUID?.() ?? `${Date.now()}`,
          timestamp: new Date(now).toISOString(),
          severity,
          features,
          description: describe(features)
        };
      }
      break;
    }
    case "cooldown": {
      if (state.cooldownUntil && now >= state.cooldownUntil) {
        state.status = "idle";
        state.cooldownUntil = null;
        changed = true;
      }
      break;
    }
    default:
      break;
  }

  return { state, event, changed };
}

export function landmarksToPoseFrame(
  landmarks: NormalizedLandmark[],
  timestamp: number
): PoseFrame | null {
  if (!landmarks.length) return null;
  const head = landmarks[NOSE];
  const hips = midpoint(landmarks[HIP_LEFT], landmarks[HIP_RIGHT]);
  const shoulders = midpoint(landmarks[SHOULDER_LEFT], landmarks[SHOULDER_RIGHT]);
  if (!head || !hips || !shoulders) return null;

  const torsoVector = {
    x: hips.x - shoulders.x,
    y: hips.y - shoulders.y
  };
  const torsoTiltDeg = Math.abs((Math.atan2(torsoVector.x, torsoVector.y) * 180) / Math.PI);

  return {
    timestamp,
    landmarks,
    headY: head.y,
    hipY: hips.y,
    torsoTiltDeg
  };
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}
