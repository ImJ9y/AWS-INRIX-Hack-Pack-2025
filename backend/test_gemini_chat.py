#!/usr/bin/env python3
"""
Test script for Gemini API - Chat functionality
Sends chat logs to Gemini API and displays responses
"""
import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class GeminiChatTester:
    """Test Gemini API with chat logs"""
    
    def __init__(self):
        """Initialize with API key"""
        self.api_key = os.getenv('GOOGLE_API_KEY')
        self.model = "gemini-2.0-flash-exp"  # Using latest model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        
    def send_chat_message(self, message, chat_history=None):
        """
        Send a chat message to Gemini API
        
        Args:
            message: The user message to send
            chat_history: Optional list of previous messages [{"role": "user"/"model", "parts": [{"text": "..."}]}]
            
        Returns:
            dict with response and metadata
        """
        if not self.api_key:
            return {
                "error": "GOOGLE_API_KEY not set",
                "setup_instructions": "Get free API key at: https://aistudio.google.com/app/apikey",
                "how_to_set": "Create a .env file in the backend/ directory with: GOOGLE_API_KEY=your_key_here"
            }
        
        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
        
        # Build the contents array
        contents = []
        
        # Add chat history if provided
        if chat_history:
            contents.extend(chat_history)
        
        # Add current message
        contents.append({
            "role": "user",
            "parts": [{"text": message}]
        })
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048,
                "topP": 0.95,
                "topK": 40
            }
        }
        
        print(f"\n{'='*70}")
        print(f"📤 SENDING TO GEMINI API")
        print(f"{'='*70}")
        print(f"⏰ Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🤖 Model: {self.model}")
        print(f"💬 Message: {message[:100]}{'...' if len(message) > 100 else ''}")
        print(f"{'='*70}")
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            
            # Show request details
            print(f"\n📊 REQUEST DETAILS:")
            print(f"   URL: {url.split('?')[0]}")
            print(f"   Status Code: {response.status_code}")
            
            response.raise_for_status()
            result = response.json()
            
            # Parse response
            if 'candidates' in result and len(result['candidates']) > 0:
                candidate = result['candidates'][0]
                
                # Extract text
                if 'content' in candidate and 'parts' in candidate['content']:
                    response_text = candidate['content']['parts'][0]['text']
                else:
                    response_text = str(candidate)
                
                # Get finish reason
                finish_reason = candidate.get('finishReason', 'UNKNOWN')
                safety_ratings = candidate.get('safetyRatings', [])
                
                print(f"\n{'='*70}")
                print(f"✅ RESPONSE RECEIVED")
                print(f"{'='*70}")
                print(f"📝 Finish Reason: {finish_reason}")
                print(f"🛡️  Safety: {len(safety_ratings)} ratings checked")
                print(f"{'='*70}")
                print(f"\n💬 GEMINI RESPONSE:")
                print(f"{'-'*70}")
                print(response_text)
                print(f"{'-'*70}\n")
                
                return {
                    "success": True,
                    "response": response_text,
                    "model": self.model,
                    "finish_reason": finish_reason,
                    "safety_ratings": safety_ratings,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                print(f"\n❌ Unexpected response format")
                print(json.dumps(result, indent=2))
                return {
                    "error": "Unexpected response format",
                    "raw_response": result
                }
                
        except requests.exceptions.HTTPError as e:
            error_detail = e.response.text if e.response else str(e)
            print(f"\n❌ HTTP ERROR: {e.response.status_code if e.response else 'Unknown'}")
            print(f"Details: {error_detail}")
            
            return {
                "error": f"HTTP {e.response.status_code if e.response else 'Error'}",
                "details": error_detail
            }
            
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            return {
                "error": str(e),
                "type": type(e).__name__
            }
    
    def interactive_chat(self):
        """Start an interactive chat session"""
        print(f"\n{'='*70}")
        print(f"🚀 GEMINI CHAT TESTER - INTERACTIVE MODE")
        print(f"{'='*70}")
        
        if not self.api_key:
            print("\n❌ ERROR: GOOGLE_API_KEY not set!")
            print("\n🔧 SETUP INSTRUCTIONS:")
            print("   1. Go to: https://aistudio.google.com/app/apikey")
            print("   2. Click 'Create API Key'")
            print("   3. Copy your key")
            print("   4. Create a .env file in the backend/ directory:")
            print("      GOOGLE_API_KEY=your_key_here")
            return
        
        print(f"✅ API Key found: {self.api_key[:20]}...")
        print(f"\n💡 Type your messages and press Enter")
        print(f"💡 Type 'quit' or 'exit' to end the chat")
        print(f"💡 Type 'clear' to clear chat history\n")
        
        chat_history = []
        
        while True:
            try:
                user_input = input("\n👤 You: ").strip()
                
                if not user_input:
                    continue
                    
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("\n👋 Goodbye!")
                    break
                
                if user_input.lower() == 'clear':
                    chat_history = []
                    print("🧹 Chat history cleared!")
                    continue
                
                # Send message
                result = self.send_chat_message(user_input, chat_history)
                
                if result.get('success'):
                    # Add to history
                    chat_history.append({
                        "role": "user",
                        "parts": [{"text": user_input}]
                    })
                    chat_history.append({
                        "role": "model",
                        "parts": [{"text": result['response']}]
                    })
                else:
                    print(f"\n❌ Error: {result.get('error', 'Unknown error')}")
                    
            except KeyboardInterrupt:
                print("\n\n👋 Chat interrupted. Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")


def test_simple_message():
    """Test with a simple message"""
    tester = GeminiChatTester()
    
    print("\n" + "="*70)
    print("TEST 1: Simple Message")
    print("="*70)
    
    result = tester.send_chat_message("Hello! Can you hear me?")
    return result.get('success', False)


def test_chat_conversation():
    """Test a multi-turn conversation"""
    tester = GeminiChatTester()
    
    print("\n" + "="*70)
    print("TEST 2: Multi-turn Conversation")
    print("="*70)
    
    chat_history = []
    
    # Message 1
    message1 = "My name is Alex. What's the capital of France?"
    result1 = tester.send_chat_message(message1, chat_history)
    
    if result1.get('success'):
        chat_history.append({"role": "user", "parts": [{"text": message1}]})
        chat_history.append({"role": "model", "parts": [{"text": result1['response']}]})
        
        # Message 2 - should remember name
        message2 = "What's my name? And what country's capital did I ask about?"
        result2 = tester.send_chat_message(message2, chat_history)
        
        return result2.get('success', False)
    
    return False


def test_fall_detection_chat():
    """Test with fall detection context"""
    tester = GeminiChatTester()
    
    print("\n" + "="*70)
    print("TEST 3: Fall Detection Context")
    print("="*70)
    
    message = """I'm working on a fall detection system. Here's a sample log:
    
FALL DETECTED:
- Time: 2025-10-26 14:30:15
- Severity: 8/10
- Velocity: 2.3 m/s
- Body Angle: 75°
- Stillness: 12 seconds

Can you analyze this and tell me if this seems like a serious fall that requires emergency response?"""
    
    result = tester.send_chat_message(message)
    return result.get('success', False)


if __name__ == "__main__":
    print("\n" + "="*70)
    print("🤖 GEMINI API CHAT TESTER")
    print("="*70)
    print("📅 " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("="*70)
    
    tester = GeminiChatTester()
    
    # Check API key
    if not tester.api_key:
        print("\n❌ GOOGLE_API_KEY not found!")
        print("\n🔧 QUICK SETUP:")
        print("   1. Get API key: https://aistudio.google.com/app/apikey")
        print("   2. Create backend/.env file with:")
        print("      GOOGLE_API_KEY=your_key_here")
        print("\n" + "="*70 + "\n")
        exit(1)
    
    print(f"\n✅ API Key configured: {tester.api_key[:25]}...")
    
    # Show menu
    print("\n" + "="*70)
    print("SELECT TEST MODE:")
    print("="*70)
    print("1. Run automated tests")
    print("2. Interactive chat mode")
    print("3. Exit")
    print("="*70)
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        print("\n🧪 Running automated tests...\n")
        
        tests_passed = 0
        tests_total = 3
        
        if test_simple_message():
            tests_passed += 1
            print("\n✅ Test 1 PASSED")
        else:
            print("\n❌ Test 1 FAILED")
        
        if test_chat_conversation():
            tests_passed += 1
            print("\n✅ Test 2 PASSED")
        else:
            print("\n❌ Test 2 FAILED")
        
        if test_fall_detection_chat():
            tests_passed += 1
            print("\n✅ Test 3 PASSED")
        else:
            print("\n❌ Test 3 FAILED")
        
        print(f"\n{'='*70}")
        print(f"📊 RESULTS: {tests_passed}/{tests_total} tests passed")
        print(f"{'='*70}\n")
        
    elif choice == "2":
        tester.interactive_chat()
    
    else:
        print("\n👋 Goodbye!")

