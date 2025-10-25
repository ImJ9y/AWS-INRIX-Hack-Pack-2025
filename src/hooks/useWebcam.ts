import { useCallback, useEffect, useRef, useState } from "react";
import { WebcamResolution } from "../types";

const defaultConstraints: MediaStreamConstraints = {
  video: {
    facingMode: "user",
    width: { ideal: 1280 },
    height: { ideal: 720 }
  },
  audio: false
};

export function useWebcam() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolution, setResolution] = useState<WebcamResolution>({ width: 0, height: 0 });

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setReady(false);
  }, []);

  const start = useCallback(async () => {
    if (!navigator?.mediaDevices?.getUserMedia) {
      setError("Camera access is not supported in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia(defaultConstraints);
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {
          // Browsers may block autoplay until there is a user gesture.
        });
        setResolution({
          width: videoRef.current.videoWidth || 1280,
          height: videoRef.current.videoHeight || 720
        });
      }
      setError(null);
      setReady(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to access the webcam.";
      setError(message);
      stop();
    }
  }, [stop]);

  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  return {
    videoRef,
    ready,
    error,
    resolution,
    start,
    stop
  };
}
