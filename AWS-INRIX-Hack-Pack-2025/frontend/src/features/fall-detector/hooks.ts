import { useCallback, useEffect, useRef, useState } from 'react';
import {
  FilesetResolver,
  PoseLandmarker,
  PoseLandmarkerResult,
} from '@mediapipe/tasks-vision';
import { NormalizedLandmark, WebcamResolution } from './types';

const defaultConstraints: MediaStreamConstraints = {
  video: {
    facingMode: 'user',
    width: { ideal: 1280 },
    height: { ideal: 720 },
  },
  audio: false,
};

export function useWebcam() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolution, setResolution] = useState<WebcamResolution>({
    width: 0,
    height: 0,
  });

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
    setReady(false);
  }, []);

  const start = useCallback(async () => {
    if (!navigator?.mediaDevices?.getUserMedia) {
      setError('Camera access is not supported in this browser.');
      return;
    }

    try {
      const stream =
        await navigator.mediaDevices.getUserMedia(defaultConstraints);
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {
          // Some browsers block autoplay until a user gesture occurs.
        });
        setResolution({
          width: videoRef.current.videoWidth || 1280,
          height: videoRef.current.videoHeight || 720,
        });
      }
      setError(null);
      setReady(true);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Unable to access the webcam.';
      setError(message);
      stop();
    }
  }, [stop]);

  useEffect(() => () => stop(), [stop]);

  return { videoRef, ready, error, resolution, start, stop };
}

export interface UsePoseOptions {
  running: boolean;
  maxFps?: number;
  modelAssetPath?: string;
  wasmBaseUrl?: string;
}

interface UsePoseReturn {
  landmarks: NormalizedLandmark[];
  fps: number;
  modelReady: boolean;
  confidence: number;
  error: string | null;
}

const defaultModelPath = '/models/pose_landmarker_lite.task';
const defaultWasmBase = '/wasm';

export function usePose(
  video: HTMLVideoElement | null,
  options: UsePoseOptions
): UsePoseReturn {
  const [landmarks, setLandmarks] = useState<NormalizedLandmark[]>([]);
  const [fps, setFps] = useState(0);
  const [modelReady, setModelReady] = useState(false);
  const [confidence, setConfidence] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const landmarkerRef = useRef<PoseLandmarker | null>(null);
  const rafRef = useRef<number>();
  const lastInferenceRef = useRef(0);
  const frameCounterRef = useRef({ frames: 0, lastStamp: performance.now() });

  useEffect(() => {
    let cancelled = false;

    async function init() {
      if (landmarkerRef.current) return;
      try {
        const wasmBase =
          options.wasmBaseUrl ??
          import.meta.env.VITE_VISION_WASM ??
          defaultWasmBase;
        const fileset = await FilesetResolver.forVisionTasks(wasmBase);
        const modelAssetPath =
          options.modelAssetPath ??
          import.meta.env.VITE_POSE_MODEL ??
          defaultModelPath;
        const landmarker = await PoseLandmarker.createFromOptions(fileset, {
          baseOptions: {
            modelAssetPath,
            delegate: 'GPU',
          },
          runningMode: 'VIDEO',
          numPoses: 1,
          minPoseDetectionConfidence: 0.4,
          minTrackingConfidence: 0.4,
        });
        if (cancelled) {
          landmarker.close();
          return;
        }
        landmarkerRef.current = landmarker;
        setModelReady(true);
        loop();
      } catch (err) {
        const message =
          err instanceof Error ? err.message : 'Unable to load pose model.';
        setError(message);
      }
    }

    const loop = () => {
      rafRef.current = requestAnimationFrame(loop);
      if (!options.running) return;
      const landmarker = landmarkerRef.current;
      if (!landmarker || !video) return;
      if (video.readyState < 2) return;

      const now = performance.now();
      const minInterval = 1000 / (options.maxFps ?? 30);
      if (now - lastInferenceRef.current < minInterval) return;
      lastInferenceRef.current = now;

      const result = landmarker.detectForVideo(
        video,
        now
      ) as PoseLandmarkerResult;
      const pose = result?.landmarks?.[0];
      if (pose?.length) {
        setLandmarks(pose.map(point => ({ ...point })));
        const avgConfidence =
          pose.reduce((sum, item) => sum + (item.visibility ?? 0.9), 0) /
          pose.length;
        setConfidence(Math.min(1, Math.max(0, avgConfidence)));
      } else {
        setLandmarks([]);
        setConfidence(0);
      }

      const counters = frameCounterRef.current;
      counters.frames += 1;
      if (now - counters.lastStamp >= 1000) {
        setFps(counters.frames);
        counters.frames = 0;
        counters.lastStamp = now;
      }
    };

    init();

    return () => {
      cancelled = true;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      landmarkerRef.current?.close();
      landmarkerRef.current = null;
    };
  }, [
    video,
    options.running,
    options.maxFps,
    options.modelAssetPath,
    options.wasmBaseUrl,
  ]);

  return { landmarks, fps, modelReady, confidence, error };
}
