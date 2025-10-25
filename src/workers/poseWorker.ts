/**
 * Optional web worker stub for offloading pose inference.
 *
 * This file is provided for future experimentation. Today the main thread handles inference,
 * but you can move the MediaPipe graph here and communicate via postMessage + OffscreenCanvas.
 */
self.addEventListener("message", () => {
  // TODO: Move PoseLandmarker to a worker when OffscreenCanvas is available.
});
