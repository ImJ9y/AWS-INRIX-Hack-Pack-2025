/**
 * Voice Assistant for Fall Detection
 * Asks the person if they're okay and handles their response
 */

// NLU patterns
const YES_PATTERN = /\b(yes|yeah|yep|please\s*call|call\s*help|help)\b/i;
const NO_PATTERN = /\b(no|nope|don'?t|do\s*not|i'?m\s*ok(?:ay)?|i\s*am\s*ok(?:ay)?|i'?m\s*fine|i\s*am\s*fine|not\s*now|stay)\b/i;

interface SpeechRecognitionResult {
  transcript: string;
  confidence: number;
}

// Browser Speech Recognition types
interface SpeechRecognitionEvent extends Event {
  results: {
    [index: number]: {
      [index: number]: SpeechRecognitionResult;
      isFinal: boolean;
    };
    length: number;
  };
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognition;
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: (event: SpeechRecognitionEvent) => void;
  onerror: (event: SpeechRecognitionErrorEvent) => void;
  onend: () => void;
  start: () => void;
  stop: () => void;
}

declare global {
  interface Window {
    SpeechRecognition: SpeechRecognitionConstructor;
    webkitSpeechRecognition: SpeechRecognitionConstructor;
  }
}

/**
 * Speak text using Web Speech Synthesis API
 */
function speak(text: string): Promise<void> {
  return new Promise((resolve) => {
    if (!('speechSynthesis' in window)) {
      console.error('[voice] Speech synthesis not supported');
      resolve();
      return;
    }

    console.log('[voice] Speaking:', text);

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9; // Slightly slower for clarity
    utterance.pitch = 1.0;
    utterance.volume = 1.0;
    
    utterance.onend = () => {
      console.log('[voice] Finished speaking');
      resolve();
    };
    
    utterance.onerror = (event) => {
      console.error('[voice] Speech error:', event);
      resolve();
    };
    
    // Cancel any ongoing speech first
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  });
}

/**
 * Listen for a single utterance using Web Speech Recognition API
 */
function listenOnce(timeoutMs: number = 6000): Promise<string> {
  return new Promise((resolve) => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    
    if (!SpeechRecognition) {
      console.error('[voice] Speech recognition not supported');
      resolve('');
      return;
    }

    console.log('[voice] Listening for response...');

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    const timeout = setTimeout(() => {
      console.log('[voice] Listening timeout');
      recognition.stop();
      resolve('');
    }, timeoutMs);

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      clearTimeout(timeout);
      const transcript = event.results[0][0].transcript;
      console.log('[voice] Heard:', transcript);
      resolve(transcript);
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      clearTimeout(timeout);
      console.error('[voice] Recognition error:', event.error);
      resolve('');
    };

    recognition.onend = () => {
      clearTimeout(timeout);
    };

    try {
      recognition.start();
      console.log('[voice] Microphone activated');
    } catch (error) {
      clearTimeout(timeout);
      console.error('[voice] Failed to start recognition:', error);
      resolve('');
    }
  });
}

/**
 * Ask the person if they're okay and return their intent
 */
async function askAndGetIntent(maxAttempts: number = 2): Promise<'YES' | 'NO' | ''> {
  const prompt = 
    "I detected a fall. Are you okay? " +
    "Say 'yes' if you want me to call help. " +
    "Say 'no' if you don't want me to call and you'd like me to stay with you.";

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    await speak(prompt);
    console.log(`[voice] Waiting for reply (attempt ${attempt}/${maxAttempts})...`);
    
    const utterance = await listenOnce(6000);
    
    if (!utterance) {
      await speak("I didn't catch that.");
      continue;
    }

    if (YES_PATTERN.test(utterance)) {
      return 'YES';
    }
    
    if (NO_PATTERN.test(utterance)) {
      return 'NO';
    }

    await speak("Sorry, I didn't understand.");
  }

  return '';
}

/**
 * Call the caregiver via Twilio (backend endpoint)
 */
async function callCaregiver(): Promise<void> {
  try {
    console.log('[voice] Attempting to call caregiver via Twilio...');
    
    const response = await fetch('http://localhost:5001/api/call_caregiver', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    
    const data = await response.json();
    
    if (data.success) {
      console.log('[voice] SUCCESS: Caregiver call initiated:', data.call_sid);
    } else {
      console.error('[voice] FAILED to call caregiver:', data.error);
      console.error('[voice] Message:', data.message);
      
      // Alert user if Twilio isn't configured
      if (data.error === 'Twilio not configured') {
        console.warn('[voice] TWILIO NOT CONFIGURED - Set up Twilio credentials in backend/.env');
        console.warn('[voice] See: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, CAREGIVER_PHONE');
      }
    }
  } catch (error) {
    console.error('[voice] Error calling caregiver API:', error);
    console.error('[voice] Make sure the backend is running on http://localhost:5001');
  }
}

/**
 * Wait for a specified time in milliseconds
 */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Main voice assistant flow
 * Called when a fall is detected
 */
export async function startVoiceAssistant(): Promise<void> {
  console.log('[voice] ===== VOICE ASSISTANT STARTING =====');

  // Check if browser supports required APIs
  if (!('speechSynthesis' in window)) {
    console.error('[voice] Speech synthesis not supported in this browser');
    console.error('[voice] Please use Chrome, Edge, or Safari');
    alert('Voice assistant requires Chrome, Edge, or Safari browser');
    return;
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    console.error('[voice] Speech recognition not supported in this browser');
    console.error('[voice] Please use Chrome, Edge, or Safari');
    alert('Voice assistant speech recognition requires Chrome, Edge, or Safari browser');
    return;
  }

  console.log('[voice] Browser supports Web Speech API');
  console.log('[voice] Starting conversation...');

  await sleep(2000);
  // Ask if they're okay
  const intent = await askAndGetIntent(2);

  if (intent === 'YES') {
    console.log('[voice] User wants help - calling caregiver');
    await speak("Okay. Let me call help now.");
    
    // Wait 2 seconds before placing the call
    console.log('[voice] Waiting 2 seconds before placing call...');
    await sleep(2000);
    
    console.log('[voice] Placing call now...');
    await callCaregiver();
    await speak("Help has been alerted. I will stay with you until they arrive.");
    await sleep(2000);
  } else if (intent === 'NO') {
    console.log('[voice] User declined help - providing reassurance');
    // No call - keep talking to them
    await speak("Okay. I'm here with you. Let's take a deep breath together.");
    await sleep(1000);
    await speak("If anything changes and you want me to call help, just say 'call help'.");

    await sleep(2000);
    // Optional: keep listening for a change of mind
    for (let i = 0; i < 3; i++) {
      const utterance = await listenOnce(6000);
      if (utterance && YES_PATTERN.test(utterance)) {
        console.log('[voice] User changed mind - calling caregiver');
        await speak("Understood. Calling help now.");
        await sleep(2000); // Wait 2 seconds before calling
        await callCaregiver();
        break;
      }
    }
    
    await speak("I'm staying with you. You're not alone.");
  } else {
    console.log('[voice] Unclear response - staying cautious');
    // Unclear after retries - don't call, but reassure
    await speak(
      "I couldn't understand. I won't call right now, but I'm staying with you. " +
      "Say 'call help' any time if you need me to call."
    );
    
    for (let i = 0; i < 3; i++) {
      const utterance = await listenOnce(6000);
      if (utterance && YES_PATTERN.test(utterance)) {
        console.log('[voice] User requested help - calling caregiver');
        await speak("Understood. Calling help now.");
        await sleep(2000); // Wait 2 seconds before calling
        await callCaregiver();
        break;
      }
    }
    
    await speak("I'm here with you.");
  }

  console.log('[voice] ===== VOICE ASSISTANT COMPLETED =====');
}

