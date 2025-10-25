import { useEffect, useRef, useState } from "react";
import {
  FilesetResolver,
  PoseLandmarker,
  PoseLandmarkerResult
} from "@mediapipe/tasks-vision";
import { NormalizedLandmark } from "../types";

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

const defaultModelPath = "/models/pose_landmarker_lite.task";
const defaultWasmBase = "/wasm";

export function usePose(video: HTMLVideoElement | null, options: UsePoseOptions): UsePoseReturn {
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
        const wasmBase = options.wasmBaseUrl ?? import.meta.env.VITE_VISION_WASM ?? defaultWasmBase;
        const fileset = await FilesetResolver.forVisionTasks(wasmBase);
        const modelAssetPath = options.modelAssetPath ?? import.meta.env.VITE_POSE_MODEL ?? defaultModelPath;
        const landmarker = await PoseLandmarker.createFromOptions(fileset, {
          baseOptions: {
            modelAssetPath,
            delegate: "GPU"
          },
          runningMode: "VIDEO",
          numPoses: 1,
          minPoseDetectionConfidence: 0.4,
          minTrackingConfidence: 0.4
        });
        if (cancelled) {
          landmarker.close();
          return;
        }
        landmarkerRef.current = landmarker;
        setModelReady(true);
        loop();
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unable to load pose model.";
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

      const result = landmarker.detectForVideo(video, now) as PoseLandmarkerResult;
      const pose = result?.landmarks?.[0];
      if (pose?.length) {
        setLandmarks(pose.map((point) => ({ ...point })));
        const avgConfidence = pose.reduce((sum, item) => sum + (item.visibility ?? 0.9), 0) / pose.length;
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
  }, [video, options.running, options.maxFps, options.modelAssetPath, options.wasmBaseUrl]);

  return { landmarks, fps, modelReady, confidence, error };
}
