# Fall Detection Improvements

This document outlines the major improvements made to the fall detection system based on best practices from the literature.

## Summary of Changes

### 1. **Pose Keypoints Detection**
- **Changed from**: `yolov8n.pt` (bounding box only)
- **Changed to**: `yolov8n-pose.pt` (17 COCO keypoints)
- **Benefits**:
  - More accurate torso angle calculation (shoulder-to-hip vector)
  - Normalized vertical velocity (scale-invariant)
  - Better ground detection using hip position
  - Reduced false positives from bbox noise

### 2. **Persistent Person Tracking**
- **Enabled**: ByteTrack tracking with `persist=True`
- **Benefits**:
  - Stable person IDs across frames
  - Reduced false spikes from ID swaps
  - Better temporal consistency
  - Enables proper pattern analysis over time

### 3. **EMA Smoothing**
- **Added**: Exponential Moving Average for key signals
  - `v_norm` (normalized velocity): α=0.25
  - `torso_angle`: α=0.2
- **Benefits**:
  - Reduces signal jitter
  - Smoother temporal signals
  - More stable severity assessment

### 4. **FPS-Normalized Temporal Windows**
- **Added**: Dynamic FPS tracking and frame-based thresholds
  - `fall_duration_frames = fps * 0.8` (~0.8s descent)
  - `still_frames_needed = fps * 1.0` (~1.0s stillness)
- **Benefits**:
  - Adapts to actual camera frame rate
  - More robust across different hardware
  - Proper temporal constraint enforcement

### 5. **FSM-Based Temporal Pattern Analysis**
- **Changed from**: Simple stage tracking
- **Changed to**: 3-state FSM with frame counting
  - State 0: None → detect fast descent (v_norm > 0.8)
  - State 1: Descending → torso rotates >70° within fall_duration_frames
  - State 2: Horizontal → wait for stillness (still_frames_needed)
- **Benefits**:
  - Requires complete fall sequence within temporal window
  - Prevents false positives from partial movements
  - Enforces realistic fall timing

### 6. **Ground/Near-Floor Detection**
- **Added**: Hip position relative to frame bottom
  - Near floor: `hip_y > 0.80 * frame_height` OR `bbox_bottom > 0.85 * frame_height`
  - Boosts impact score when near floor AND horizontal (angle > 70°)
- **Benefits**:
  - Confirms lying position
  - Reduces false positives from sitting/bending
  - Mimics ground-plane checks from literature

### 7. **Pose-Based Angle Detection**
- **Changed from**: Bounding box center movement
- **Changed to**: Shoulder-to-hip torso vector angle
- **Benefits**:
  - More accurate body orientation
  - 0° = upright, 90° = lying horizontal
  - Works regardless of camera angle/position

### 8. **Normalized Velocity Calculation**
- **Changed from**: Raw pixel velocity
- **Changed to**: Δ(hip_y) / torso_length (scale-invariant)
- **Benefits**:
  - Works at any distance from camera
  - Consistent thresholds across scenarios
  - Accounts for person size variations

### 9. **Multi-Indicator Validation**
- **Enhanced**: Severity assessment requires 3+ strong indicators
- **Indicators**:
  1. High downward velocity (v_norm > 0.8 × 10 = 8.0 scaled)
  2. Rapid angular change (angular velocity > 10)
  3. Head downward motion (head_score > 1.5)
  4. Body shape change (shape_score > 1.0)
  5. Impact detection (impact_score > 2.0)
  6. Complete pattern (pattern_score > 1.0)
- **Benefits**:
  - Reduces false positives significantly
  - Only triggers when multiple signals agree
  - Higher confidence in emergency detection

### 10. **Enhanced Camera Initialization**
- **Note**: Camera retry logic recommended but not yet implemented
- **Planned**: Multiple backend attempts with different backends (DSHOW, AVFOUNDATION)

## Technical Details

### Pose Keypoint Indices (COCO 17)
- **5**: Left Shoulder
- **6**: Right Shoulder  
- **11**: Left Hip
- **12**: Right Hip

### Torso Calculation
```python
shoulder_mid = ((left_shoulder + right_shoulder) / 2)
hip_mid = ((left_hip + right_hip) / 2)
torso_vector = hip_mid - shoulder_mid
angle_to_vertical = atan2(|torso_vector.x|, |torso_vector.y|)  # degrees
v_norm = Δ(hip_y) / torso_length  # normalized
```

### Thresholds (Recommended Defaults)
- Angle threshold: 70° for horizontal
- Velocity threshold: v_norm > 0.8 (normalized)
- Fall duration: ~0.8s (fall_duration_frames)
- Stillness duration: ~1.0s (still_frames_needed)
- Emergency severity: ≥7/10

## Usage

### Starting with Pose Model
The system now uses `yolov8n-pose.pt` by default. To run:

```bash
cd backend
python3 simple_backend.py
```

### Environment Variables
- `YOLO_IMG_SIZE`: Image size for inference (default: 640)
- `FALL_THRESHOLD_VELOCITY`: Velocity threshold (default: 5.0)
- `FALL_THRESHOLD_ANGLE`: Angle threshold (default: 75)
- `EMERGENCY_SEVERITY_THRESHOLD`: Emergency trigger (default: 7)

### Monitoring
- Live detection data via `/api/detections`
- Debug display shows: `P{pid}: S{severity}/10 V{velocity} A{angle}° Vn{v_norm}`
- Indicators: H↓ (head down), S (shape change), I! (impact), P (pattern detected)

## Next Steps

1. **Evaluate with Real Data**: Collect test clips with various fall scenarios
2. **Tune Thresholds**: Adjust based on precision/recall metrics
3. **Add CloudWatch Metrics**: Track TP/FP/FN rates
4. **S3 Clip Storage**: Automatically save clips for severity ≥ threshold
5. **Camera Robustness**: Implement retry logic with multiple backends

## References

- Ultralytics YOLOv8 Pose Documentation
- ByteTrack for Stable Tracking
- Pose-Based Fall Detection Literature
- Temporal Pattern Analysis Papers
