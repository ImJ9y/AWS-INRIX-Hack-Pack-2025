#!/usr/bin/env python3
"""
AI Image Analyzer for Emergency Fall Detection
Analyzes emergency screenshots and video clips using Google Gemini AI
"""
import os
import base64
import requests
import cv2
from dotenv import load_dotenv

load_dotenv()

class EmergencyImageAnalyzer:
    """Analyzes emergency images using Google Gemini AI"""
    
    def __init__(self):
        """Initialize the Gemini analyzer"""
        self.api_key = os.getenv('GOOGLE_API_KEY')
        if not self.api_key:
            print("⚠️  Warning: GOOGLE_API_KEY not set in .env file")
        
    def analyze_fall_image(self, image_data, severity, velocity, angle, 
                          torso_tilt=None, head_drop=None, stillness=None):
        """
        Analyze emergency fall image with Gemini AI
        
        Args:
            image_data: Image data (bytes or base64 string)
            severity: Fall severity (1-10)
            velocity: Person's velocity
            angle: Body angle
            torso_tilt: Torso tilt angle (degrees) [optional]
            head_drop: Head drop percentage (0-100) [optional]
            stillness: Stillness duration (seconds) [optional]
            
        Returns:
            dict with medical analysis
        """
        # Convert image to base64 if needed
        if isinstance(image_data, bytes):
            image_base64 = base64.b64encode(image_data).decode('utf-8')
        else:
            image_base64 = image_data
        
        # Create medical analysis prompt
        prompt = self._create_medical_prompt(severity, velocity, angle, 
                                            torso_tilt, head_drop, stillness)
        
        return self._analyze_with_gemini(image_base64, prompt)
    
    def _create_medical_prompt(self, severity, velocity, angle, 
                              torso_tilt=None, head_drop=None, stillness=None):
        """Create a medical-level analysis prompt"""
        
        # Build detailed metrics section
        metrics = f"""DETECTED METRICS:
- Fall Severity: {severity}/10
- Impact Velocity: {velocity:.2f}
- Body Angle: {angle:.1f}°"""
        
        if torso_tilt is not None:
            metrics += f"\n- Torso Tilt: {torso_tilt:.1f}°"
        if head_drop is not None:
            metrics += f"\n- Head Drop: {head_drop:.1f}%"
        if stillness is not None:
            metrics += f"\n- Stillness Duration: {stillness:.1f}s"
        
        return f"""You are an emergency medical AI assistant analyzing a fall detection image.

{metrics}

Analyze this emergency image and provide a MEDICAL-LEVEL assessment:

1. BODY POSITION:
   - Describe the person's current body position
   - Note any visible signs of impact or injury
   - Assess body alignment and posture

2. INJURY RISK ASSESSMENT:
   - Potential injury types based on fall characteristics
   - High-risk areas (head, hip, spine, etc.)
   - Severity estimation

3. IMMEDIATE MEDICAL CONCERNS:
   - Critical signs to watch for
   - Potential internal injuries
   - Movement restrictions

4. RECOMMENDED EMERGENCY RESPONSE:
   - Should 911 be called? (Yes/No and why)
   - First aid measures
   - What NOT to do

5. ENVIRONMENTAL FACTORS:
   - Hazards visible in the scene
   - Surface type (hard/soft)
   - Objects that may have caused injury

Provide a clear, concise, professional medical assessment suitable for emergency responders."""

    def _analyze_with_gemini(self, image_base64, prompt):
        """Analyze with Google Gemini"""
        if not self.api_key:
            return {
                "error": "GOOGLE_API_KEY not set",
                "setup_instructions": "Get free API key at: https://makersuite.google.com/app/apikey"
            }
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}"
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_base64
                        }
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 1024
            }
        }
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            # Handle different response formats
            try:
                # Try new format first
                if 'candidates' in result and len(result['candidates']) > 0:
                    candidate = result['candidates'][0]
                    if 'content' in candidate and 'parts' in candidate['content']:
                        analysis = candidate['content']['parts'][0]['text']
                    elif 'output' in candidate:
                        analysis = candidate['output']
                    else:
                        analysis = str(candidate)
                else:
                    analysis = str(result)
            except (KeyError, IndexError) as parse_error:
                # If parsing fails, return the raw response for debugging
                return {
                    "error": f"Response parsing failed: {parse_error}",
                    "raw_response": str(result)[:500]
                }
            
            return {
                "success": True,
                "provider": "Google Gemini 2.5 Flash",
                "analysis": analysis,
                "cost": "FREE"
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "provider": "gemini"
            }
    
    def analyze_video_clip(self, video_frames, severity, velocity, angle,
                          torso_tilt=None, head_drop=None, stillness=None):
        """
        Analyze a video clip (multiple frames) with Gemini
        
        Args:
            video_frames: List of frames (numpy arrays or base64 strings)
            severity: Fall severity (1-10)
            velocity: Person's velocity
            angle: Body angle
            torso_tilt: Torso tilt angle (degrees) [optional]
            head_drop: Head drop percentage (0-100) [optional]
            stillness: Stillness duration (seconds) [optional]
            
        Returns:
            dict with sequential fall description
        """
        # Convert frames to base64 if needed
        frame_base64_list = []
        for frame in video_frames:
            if isinstance(frame, bytes):
                frame_base64 = base64.b64encode(frame).decode('utf-8')
            elif isinstance(frame, str):
                frame_base64 = frame
            else:
                # Assume it's a numpy array from OpenCV
                _, buffer = cv2.imencode('.jpg', frame)
                frame_base64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
            
            frame_base64_list.append(frame_base64)
        
        # Create video analysis prompt
        prompt = self._create_video_analysis_prompt(
            len(frame_base64_list),
            severity, velocity, angle,
            torso_tilt, head_drop, stillness
        )
        
        return self._analyze_video_with_gemini(frame_base64_list, prompt)
    
    def _create_video_analysis_prompt(self, num_frames, severity, velocity, angle,
                                     torso_tilt=None, head_drop=None, stillness=None):
        """Create prompt for video clip analysis"""
        
        metrics = f"""DETECTED METRICS:
- Fall Severity: {severity}/10
- Impact Velocity: {velocity:.2f}
- Body Angle: {angle:.1f}°"""
        
        if torso_tilt is not None:
            metrics += f"\n- Torso Tilt: {torso_tilt:.1f}°"
        if head_drop is not None:
            metrics += f"\n- Head Drop: {head_drop:.1f}%"
        if stillness is not None:
            metrics += f"\n- Stillness Duration: {stillness:.1f}s"
        
        return f"""You are an emergency medical AI assistant analyzing a fall detection video clip.

{metrics}

You are viewing {num_frames} frames from a video clip showing the fall event sequence.

Provide a DETAILED SEQUENTIAL ANALYSIS:

1. **FALL SEQUENCE** (Frame by Frame):
   - Describe what happens in each stage
   - Note body position changes
   - Identify the moment of impact
   - Observe post-fall movement or stillness

2. **INJURY ASSESSMENT**:
   - Which body parts made contact with the ground/surface?
   - Impact force estimation based on fall dynamics
   - Visible signs of injury or distress
   - Areas of highest injury risk

3. **MEDICAL CONCERNS**:
   - Immediate life-threatening conditions to check
   - Potential internal injuries
   - Recommended medical examinations

4. **EMERGENCY RESPONSE**:
   - Should 911 be called immediately? (Yes/No and why)
   - What emergency responders should know
   - First aid steps while waiting
   - Critical "DO NOT" actions

5. **ENVIRONMENTAL FACTORS**:
   - Fall trajectory and cause
   - Surface hardness and hazards
   - Objects that may have contributed

Provide a clear, professional assessment suitable for emergency responders and medical personnel."""
    
    def _analyze_video_with_gemini(self, frame_base64_list, prompt):
        """Analyze multiple frames with Gemini"""
        if not self.api_key:
            return {
                "error": "GOOGLE_API_KEY not set",
                "setup_instructions": "Get free API key at: https://makersuite.google.com/app/apikey"
            }
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}"
        
        # Build parts array with text and images
        parts = [{"text": prompt}]
        
        # Add all frames
        for i, frame_base64 in enumerate(frame_base64_list):
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": frame_base64
                }
            })
            # Add frame label
            parts.append({"text": f"[Frame {i+1}/{len(frame_base64_list)}]"})
        
        payload = {
            "contents": [{
                "parts": parts
            }],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 2048  # More tokens for video analysis
            }
        }
        
        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            
            # Parse response
            if 'candidates' in result and len(result['candidates']) > 0:
                candidate = result['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content']:
                    analysis = candidate['content']['parts'][0]['text']
                else:
                    analysis = str(candidate)
            else:
                analysis = str(result)
            
            return {
                "success": True,
                "provider": "Google Gemini 2.5 Flash (Video Analysis)",
                "analysis": analysis,
                "frames_analyzed": len(frame_base64_list),
                "cost": "FREE"
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "provider": "gemini"
            }


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🤖 GEMINI AI IMAGE ANALYZER")
    print("="*70)
    
    analyzer = EmergencyImageAnalyzer()
    
    print("\n📊 Provider: Google Gemini 2.5 Flash")
    print("💰 Cost: FREE")
    print("🚀 Speed: Fast (~2-5 seconds)")
    print("📈 Quality: Excellent medical analysis")
    
    if analyzer.api_key:
        print(f"\n✅ API Key configured: {analyzer.api_key[:20]}...")
        print("\n💡 Ready to analyze fall detection images!")
    else:
        print("\n❌ API Key NOT configured")
        print("\n🔧 Setup Instructions:")
        print("   1. Go to: https://makersuite.google.com/app/apikey")
        print("   2. Click 'Create API Key'")
        print("   3. Copy your key")
        print("   4. Add to .env file:")
        print("      GOOGLE_API_KEY=your_key_here")
    
    print("\n" + "="*70)
    print("\n📝 Usage:")
    print("   from ai_image_analyzer import EmergencyImageAnalyzer")
    print("   analyzer = EmergencyImageAnalyzer()")
    print("   result = analyzer.analyze_fall_image(image_data, 8, 0.75, 65)")
    print("\n" + "="*70 + "\n")
