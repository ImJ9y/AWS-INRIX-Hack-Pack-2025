# On-Device Fall Detector

Browser-only React + TypeScript experience built with Vite. It taps the laptop webcam plus the MediaPipe Pose Landmarker (WASM) to track a skeleton, apply deterministic fall heuristics, and log events — no backend and no uploads.

## Quick start

```bash
pnpm install
pnpm dev -- --https
```

Open https://localhost:5173, grant camera permission, and move quickly toward the camera followed by stillness to trigger the fall detector. All inference stays on-device.

### Requirements

- Recent Chrome, Edge, or Safari with HTTPS (camera APIs require secure origins).
- Webcam access granted to the page.
- MediaPipe Tasks assets placed under `public/`:
  - Copy `pose_landmarker_lite.task` (or another model) into `public/models/`.
  - Copy the `vision_wasm_internal.{js,wasm}` files from `@mediapipe/tasks-vision` into `public/wasm/`.
- Update `.env` (see `.env.example`) if you use different paths.

## Project structure

```
src/
├── App.tsx                // layout + hero
├── components/
│   ├── FallDetector.tsx   // video/canvas overlay, state machine, controls
│   ├── EventList.tsx      // rolling feed of fall events
│   └── MetricBadge.tsx    // compact KPI chips
├── hooks/
│   ├── useWebcam.ts       // getUserMedia lifecycle + error handling
│   └── usePose.ts         // MediaPipe initialization + inference loop
├── lib/fallLogic.ts       // heuristics, scoring, state machine, descriptions
├── types.ts               // shared types, events, severities
└── workers/poseWorker.ts  // optional worker stub
```

## Features

- Requests 1280×720 front-facing camera stream and handles permission/no-camera errors with clear messaging.
- Runs MediaPipe Pose Landmarker WASM locally (~15–30 FPS) and exposes model readiness, confidence, and FPS readouts.
- Canvas overlay draws the skeleton, torso tilt, and head velocity annotations with a toggle to hide visuals.
- Deterministic heuristics score rapid drops, torso tilt, impact velocity, and stillness; state machine debounces events with cooldowns.
- Confirmed falls create feed entries showing timestamp, severity (Low → Critical), per-metric values, and deterministic descriptions.
- Demo tooling: inject mock events or replay inference from a local video clip when no camera is available.
- Privacy-forward UI with explicit “on-device only” footer copy.

## Replay & debugging

Use the “Replay from sample” control to select a short MP4/WebM clip. The app swaps the webcam feed for the uploaded file (still on-device) so you can reproduce scenarios without standing up.

## Notes

- The optional `poseWorker.ts` stub shows where to offload inference to a Web Worker if you need more headroom.
- No analytics, no backend calls, and no data persistence are included by design.
- TailwindCSS powers the UI chrome; canvas drawing handles the skeleton with `requestAnimationFrame` cadence.
