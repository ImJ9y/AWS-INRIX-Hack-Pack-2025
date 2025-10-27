import {
  DetectorState,
  FallEvent,
  FallFeatures,
  NormalizedLandmark,
  PoseFrame,
  Severity,
  StateUpdate,
} from '../types';

export const TILT_THRESHOLD_DEG = 68;
export const DROP_THRESHOLD = 0.38;
export const VEL_THRESHOLD = 0.55;
export const STILLNESS_THRESHOLD_S = 2.5;
export const COOLDOWN_MS = 10_000;
export const SUSPECT_WINDOW_MS = 800;

const STILLNESS_LOOKBACK_MS = 5_000;
const SMOOTHING_WINDOW = 5;
const HEAD_LOOKBACK_MS = 1_200;

export const INITIAL_STATE: DetectorState = {
  status: 'idle',
  suspectSince: null,
  lastConfirmed: null,
  cooldownUntil: null,
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
    z: ((a.z ?? 0) + (b.z ?? 0)) / 2,
  };
}

export function computeFeatures(
  prevFrames: PoseFrame[],
  current: PoseFrame
): FallFeatures {
  const recentFrames = prevFrames.filter(
    f => current.timestamp - f.timestamp <= HEAD_LOOKBACK_MS
  );
  const headSeries = smoothSeries(
    [...recentFrames.map(f => f.headY), current.headY],
    SMOOTHING_WINDOW
  );
  const headDrop = Math.max(...headSeries) - Math.min(...headSeries);

  const velocitySamples = computeVelocitySamples([
    ...recentFrames.slice(-SMOOTHING_WINDOW),
    current,
  ]);
  const avgVelocity = velocitySamples.length
    ? velocitySamples.reduce((sum, value) => sum + value, 0) /
      velocitySamples.length
    : 0;
  const normalizedVelocity = clamp(avgVelocity * 3.5, 0, 1);

  const tiltSeries = smoothSeries(
    [...recentFrames.map(f => f.torsoTiltDeg), current.torsoTiltDeg],
    4
  );
  const smoothedTilt =
    tiltSeries[tiltSeries.length - 1] ?? current.torsoTiltDeg;

  const stillnessSince = computeStillness(prevFrames, current.timestamp);

  const score =
    (headDrop >= DROP_THRESHOLD ? 2 : 0) +
    (smoothedTilt >= TILT_THRESHOLD_DEG ? 2 : 0) +
    (normalizedVelocity >= VEL_THRESHOLD ? 1 : 0) +
    (stillnessSince >= STILLNESS_THRESHOLD_S ? 1 : 0);

  const confidence = computeConfidence(current.landmarks);

  return {
    headYDrop: clamp(headDrop, 0, 1),
    headYVelPeak: normalizedVelocity,
    torsoTiltDeg: Math.min(180, Math.max(0, smoothedTilt)),
    stillnessSec: stillnessSince,
    confidence,
    score,
  };
}

function computeVelocitySamples(frames: PoseFrame[]): number[] {
  if (frames.length < 2) return [];
  const samples: number[] = [];
  for (let i = 1; i < frames.length; i += 1) {
    const curr = frames[i];
    const prev = frames[i - 1];
    const dt = (curr.timestamp - prev.timestamp) / 1000;
    if (dt <= 0) continue;
    const dy = Math.abs(curr.headY - prev.headY);
    samples.push(dy / dt);
  }
  return samples;
}

function smoothSeries(values: number[], window: number): number[] {
  if (values.length <= 1 || window <= 1) return values;
  const result: number[] = [];
  for (let i = 0; i < values.length; i += 1) {
    const start = Math.max(0, i - window + 1);
    const slice = values.slice(start, i + 1);
    const avg = slice.reduce((sum, value) => sum + value, 0) / slice.length;
    result.push(avg);
  }
  return result;
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
    if (motion > 0.02) {
      lastMotionTs = frame.timestamp;
      break;
    }
  }

  return Math.max(0, (now - lastMotionTs) / 1000);
}

function computeConfidence(landmarks: NormalizedLandmark[]): number {
  if (!landmarks.length) return 0;
  const visibility = landmarks.map(l => l.visibility ?? 0.9);
  const avg =
    visibility.reduce((acc, value) => acc + value, 0) / visibility.length;
  return clamp(avg, 0, 1);
}

export function classifySeverity(score: number): Severity {
  if (score >= 5) return 'Critical';
  if (score >= 4) return 'High';
  if (score >= 2) return 'Moderate';
  return 'Low';
}

export function describe(features: FallFeatures): string {
  const tilt = Math.round(features.torsoTiltDeg);
  const drop = Math.round(features.headYDrop * 100);
  return `Rapid head descent (${drop}% drop) with ${tilt} degrees torso tilt followed by ${features.stillnessSec.toFixed(
    1
  )}s stillness.`;
}

export function updateFallState(
  prevState: DetectorState,
  features: FallFeatures,
  now: number
): StateUpdate {
  const state: DetectorState = { ...prevState };
  let event: FallEvent | undefined;
  let changed = false;

  const dropHit = features.headYDrop >= DROP_THRESHOLD;
  const tiltHit = features.torsoTiltDeg >= TILT_THRESHOLD_DEG;
  const velHit = features.headYVelPeak >= VEL_THRESHOLD;
  const stillnessHit = features.stillnessSec >= STILLNESS_THRESHOLD_S;
  const severeScore = features.score >= 5;

  if (
    state.status === 'cooldown' &&
    state.cooldownUntil &&
    now >= state.cooldownUntil
  ) {
    state.status = 'idle';
    state.cooldownUntil = null;
    changed = true;
  }

  if (
    state.status === 'confirmed' &&
    state.lastConfirmed &&
    now - state.lastConfirmed > 1500
  ) {
    state.status = 'cooldown';
    changed = true;
  }

  switch (state.status) {
    case 'idle': {
      if ((dropHit && tiltHit) || features.score >= 3) {
        state.status = 'suspected';
        state.suspectSince = now;
        changed = true;
      }
      break;
    }
    case 'suspected': {
      if (state.suspectSince && now - state.suspectSince > SUSPECT_WINDOW_MS) {
        state.status = 'idle';
        state.suspectSince = null;
        changed = true;
      }

      if ((dropHit && tiltHit && velHit) || (severeScore && stillnessHit)) {
        state.status = 'confirmed';
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
          description: describe(features),
        };
      }
      break;
    }
    case 'cooldown': {
      if (state.cooldownUntil && now >= state.cooldownUntil) {
        state.status = 'idle';
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
  const shoulders = midpoint(
    landmarks[SHOULDER_LEFT],
    landmarks[SHOULDER_RIGHT]
  );
  if (!head || !hips || !shoulders) return null;

  const torsoVector = {
    x: hips.x - shoulders.x,
    y: hips.y - shoulders.y,
  };
  const torsoTiltDeg = Math.abs(
    (Math.atan2(torsoVector.x, torsoVector.y) * 180) / Math.PI
  );

  return {
    timestamp,
    landmarks,
    headY: head.y,
    hipY: hips.y,
    torsoTiltDeg,
  };
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}
