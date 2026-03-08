"""
CUTIE AI - Professional Voice & Chat Assistant
No activation required - Just run and start using!
Fixed voice timeout errors with proper error handling
"""

import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import threading
import time
import os
import datetime
import logging
import queue
import re
import sys

# ==================== RENDER COMPATIBILITY CHECK ====================
# Check if we're on Render (no audio hardware)
IS_RENDER = os.environ.get('RENDER', False) or os.environ.get('IS_RENDER', False)

# Only import audio libraries if not on Render
if not IS_RENDER:
    try:
        import speech_recognition as sr
        import pyttsx3
        import pyautogui
        import pyperclip
        import screen_brightness_control as sbc
        AUDIO_AVAILABLE = True
    except ImportError as e:
        print(f"⚠️ Audio libraries not available: {e}")
        AUDIO_AVAILABLE = False
else:
    # On Render - audio features disabled
    AUDIO_AVAILABLE = False
    print("📢 Running on Render - Audio features disabled")

# ==================== CONFIGURATION ====================
GROQ_API_KEY = "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"  # You'll add this on Render
USER_NAME = "khanki magi"

app = Flask(__name__)
CORS(app)

# Initialize components
conversation_history = []
voice_system_active = True
voice_thread = None
command_queue = queue.Queue()
voice_feedback_queue = queue.Queue()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== BANGLA ACCENT VOICE SETUP ====================
class BanglaAccentVoice:
    """Custom voice class to create Bangla-accented English speech"""
    
    def __init__(self):
        self.engine = None
        self.bangla_voice_id = None
        if AUDIO_AVAILABLE:
            self.setup_voice()
        else:
            print("📢 Running in headless mode - voice disabled")
    
    def setup_voice(self):
        """Initialize TTS engine and find best voice for Bangla accent"""
        try:
            self.engine = pyttsx3.init()
            
            # Configure for Bangla accent
            self.engine.setProperty('rate', 150)  # Slightly slower for accent clarity
            self.engine.setProperty('volume', 0.95)
            
            # Get available voices
            voices = self.engine.getProperty('voices')
            
            # Priority order for Bangla accent:
            # 1. Any voice with 'Bangla'/'Bengali' in name
            # 2. Indian English voices (give best Bangla accent)
            # 3. Default voice with pitch modification
            
            bangla_voice_candidates = []
            indian_voices = []
            
            for voice in voices:
                voice_name = voice.name.lower()
                voice_id = voice.id.lower()
                voice_lang = voice.languages[0] if voice.languages else ''
                
                # Check for Bangla/Bengali specific voices
                if any(term in voice_name or term in voice_id or term in str(voice_lang) 
                       for term in ['bangla', 'bengali', 'bn_', 'bn-', 'ben']):
                    bangla_voice_candidates.append(voice)
                
                # Check for Indian English voices
                elif any(term in voice_name or term in voice_id 
                        for term in ['india', 'indian', 'hi-', 'en-in']):
                    indian_voices.append(voice)
            
            # Select best available voice
            if bangla_voice_candidates:
                self.bangla_voice_id = bangla_voice_candidates[0].id
                logger.info(f"Found Bangla voice: {bangla_voice_candidates[0].name}")
            elif indian_voices:
                self.bangla_voice_id = indian_voices[0].id
                logger.info(f"Using Indian English voice: {indian_voices[0].name}")
            else:
                # Use default voice with pitch modification for Bangla accent effect
                self.bangla_voice_id = voices[0].id if voices else None
                logger.info("Using default voice with accent modification")
            
            if self.bangla_voice_id:
                self.engine.setProperty('voice', self.bangla_voice_id)
            
        except Exception as e:
            logger.error(f"Voice setup error: {e}")
            self.engine = None
    
    def add_bangla_accent(self, text):
        """Modify text to sound more like Bangla-accented English"""
        
        # Common Bangla accent phonetic replacements
        accent_rules = [
            # 'v' becomes 'bh' or 'b' in Bangla accent
            (r'\b(v\w*)', lambda m: 'bh' + m.group(0)[1:] if len(m.group(0)) > 1 else 'bhi'),
            (r'(\w*)v(\w*)', lambda m: m.group(1) + 'bh' + m.group(2)),
            
            # 'w' becomes 'u' or 'o' in Bangla accent
            (r'\b(w\w*)', lambda m: 'o' + m.group(0)[1:]),
            (r'(\w*)w(\w*)', lambda m: m.group(1) + 'u' + m.group(2)),
            
            # 'th' often becomes 't' or 'd'
            (r'th', 't'),
            (r'TH', 'T'),
            
            # 'z' becomes 'j'
            (r'z', 'j'),
            (r'Z', 'J'),
            
            # 'a' at end becomes 'ah'
            (r'a\b', 'ah'),
            
            # 'er' at end becomes 'ar'
            (r'er\b', 'ar'),
            (r'ERS\b', 'ars'),
            
            # 'ing' becomes 'ink' or 'ing' with nasal
            (r'ing\b', 'eeng'),
            
            # Common word transformations
            (r'\bthe\b', 'dha'),
            (r'\band\b', 'aar'),
            (r'\bis\b', 'hish'),
            (r'\bare\b', 'aar'),
            (r'\bfor\b', 'phaar'),
            (r'\byou\b', 'tumi'),
            (r'\byour\b', 'tomar'),
            (r'\bmy\b', 'amar'),
            (r'\bhello\b', 'nomoskar'),
        ]
        
        # Apply accent rules
        modified_text = text
        for pattern, replacement in accent_rules:
            try:
                if callable(replacement):
                    modified_text = re.sub(pattern, replacement, modified_text, flags=re.IGNORECASE)
                else:
                    modified_text = re.sub(pattern, replacement, modified_text, flags=re.IGNORECASE)
            except:
                pass
        
        return modified_text
    
    def speak(self, text, use_bangla_accent=True):
        """Speak text with optional Bangla accent"""
        if not AUDIO_AVAILABLE or not self.engine:
            print(f"CUTIE: {text}")
            return
        
        try:
            if use_bangla_accent:
                # Split into sentences and apply accent
                sentences = re.split(r'[.!?]+', text)
                for sentence in sentences:
                    if sentence.strip():
                        # Check if text contains Bangla script
                        if re.search(r'[\u0980-\u09FF]', sentence):
                            # If it has Bangla characters, speak normally
                            self.engine.say(sentence.strip())
                        else:
                            # Apply Bangla accent to English
                            accented = self.add_bangla_accent(sentence.strip())
                            self.engine.say(accented.strip())
                        self.engine.runAndWait()
                        time.sleep(0.1)  # Small pause between sentences
            else:
                # Normal speech
                self.engine.say(text)
                self.engine.runAndWait()
                
        except Exception as e:
            logger.error(f"Speech error: {e}")
            print(f"CUTIE: {text}")
    
    def speak_bangla_mix(self, text):
        """Mix Bangla and English naturally"""
        if not AUDIO_AVAILABLE or not self.engine:
            print(f"CUTIE: {text}")
            return
            
        try:
            # Detect Bangla words and handle them specially
            words = text.split()
            for word in words:
                if re.search(r'[\u0980-\u09FF]', word):
                    # This is Bangla - could use a Bangla TTS if available
                    # For now, we'll just say it with modified accent
                    self.engine.say(word)
                else:
                    # English with Bangla accent
                    accented = self.add_bangla_accent(word)
                    self.engine.say(accented)
                self.engine.runAndWait()
                time.sleep(0.05)
        except Exception as e:
            logger.error(f"Mixed speech error: {e}")

# Initialize Bangla accent voice
bangla_voice = BanglaAccentVoice()

# ==================== GROQ AI FUNCTIONS ====================
def ask_groq(user_message):
    """Get response from Groq API"""
    
    messages = [
        {"role": "system", "content": f"""You are CUTIE AI, a helpful AI assistant. 
         User's name is {USER_NAME}. Be professional, concise, and helpful. 
         Keep responses under 2-3 sentences for voice responses.
         Use a professional tone but remain friendly.
         You can mix Bangla and English naturally when appropriate."""}
    ]
    
    for msg in conversation_history[-5:]:
        messages.append(msg)
    
    messages.append({"role": "user", "content": user_message})
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 500
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            ai_response = data['choices'][0]['message']['content']
            
            conversation_history.append({"role": "user", "content": user_message})
            conversation_history.append({"role": "assistant", "content": ai_response})
            
            if len(conversation_history) > 20:
                conversation_history[:] = conversation_history[-20:]
            
            return ai_response
        else:
            return f"Error: {response.status_code}"
            
    except Exception as e:
        return f"Error: {str(e)}"

# ==================== VOICE FUNCTIONS (RENDER COMPATIBLE) ====================
def speak(text):
    """Text to speech function with Bangla accent"""
    if AUDIO_AVAILABLE:
        bangla_voice.speak(text)
    else:
        print(f"CUTIE: {text}")

def system_control(command):
    """Execute system commands - DISABLED ON RENDER"""
    if IS_RENDER:
        return "System commands disabled on cloud server"
    
    cmd = command.lower()
    
    # Volume control
    if "volume up" in cmd or "vol barhao" in cmd:
        for _ in range(5):
            pyautogui.press("volumeup")
        return "Volume increased"
    elif "volume down" in cmd or "vol kam karo" in cmd:
        for _ in range(5):
            pyautogui.press("volumedown")
        return "Volume decreased"
    
    # Brightness control
    elif "brightness up" in cmd or "brightness barhao" in cmd:
        try:
            curr = sbc.get_brightness()[0]
            sbc.set_brightness(min(curr + 20, 100))
            return f"Brightness increased"
        except:
            return "Brightness control not available"
    elif "brightness down" in cmd or "brightness kam karo" in cmd:
        try:
            curr = sbc.get_brightness()[0]
            sbc.set_brightness(max(curr - 20, 0))
            return f"Brightness decreased"
        except:
            return "Brightness control not available"
    
    # Open apps
    elif "open " in cmd:
        app_name = cmd.replace("open ", "").strip()
        pyautogui.press("win")
        time.sleep(0.5)
        pyautogui.write(app_name)
        pyautogui.press("enter")
        return f"Opening {app_name}"
    
    # Close window
    elif "close" in cmd or "band karo" in cmd:
        pyautogui.hotkey('alt', 'f4')
        return "Window closed"
    
    # Time
    elif "time" in cmd or "samay" in cmd or "koyta baje" in cmd:
        current_time = datetime.datetime.now().strftime("%I:%M %p")
        return f"Time hocche {current_time}"
    
    # Date
    elif "date" in cmd or "tarikh" in cmd:
        current_date = datetime.datetime.now().strftime("%B %d, %Y")
        return f"Aajker date {current_date}"
    
    # WhatsApp
    elif "whatsapp" in cmd or "message" in cmd:
        return "WHATSAPP_MODE"
    
    # Shutdown
    elif "shutdown" in cmd or "switch off" in cmd or "band kor" in cmd:
        if not IS_RENDER:
            speak("Shutting down in 10 seconds")
            os.system("shutdown /s /t 10")
        return "Shutting down (simulated on Render)"
    
    # Restart
    elif "restart" in cmd or "reboot" in cmd:
        if not IS_RENDER:
            speak("Restarting in 10 seconds")
            os.system("shutdown /r /t 10")
        return "Restarting (simulated on Render)"
    
    # Greetings
    elif any(word in cmd for word in ["hello", "hi", "hey", "nomoskar"]):
        return f"Nomoskar {USER_NAME}, ki obostha?"
    
    return None

def whatsapp_mode(recognizer, source):
    """Handle WhatsApp message sending - DISABLED ON RENDER"""
    if IS_RENDER:
        return "WhatsApp mode disabled on cloud server"
    
    try:
        speak("Kake message pathate chao?")
        
        # Get name
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=3)
        name = recognizer.recognize_google(audio, language='bn-IN')
        
        speak(f"Ki message pathabe {name} ke?")
        
        # Get message
        audio_msg = recognizer.listen(source, timeout=5, phrase_time_limit=5)
        message = recognizer.recognize_google(audio_msg, language='bn-IN')
        
        speak("WhatsApp khulchi")
        
        # Open WhatsApp
        pyautogui.press("win")
        time.sleep(0.5)
        pyautogui.write("whatsapp")
        pyautogui.press("enter")
        time.sleep(5)
        
        # Search contact
        pyautogui.hotkey('ctrl', 'f')
        time.sleep(1)
        pyautogui.write(name)
        time.sleep(2)
        pyautogui.press("enter")
        time.sleep(1)
        
        # Type and send message
        pyperclip.copy(message)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        pyautogui.press("enter")
        
        return "Message pathano hoyeche"
        
    except sr.WaitTimeoutError:
        return "Shunte paini - abar bolben?"
    except sr.UnknownValueError:
        return "Bujhte parlam na - abar bolben?"
    except Exception as e:
        logger.error(f"WhatsApp error: {e}")
        return "Sorry, message pathate parlam na"

def voice_loop():
    """Main voice control loop - DISABLED ON RENDER"""
    if IS_RENDER or not AUDIO_AVAILABLE:
        logger.info("Voice control disabled on Render")
        return
        
    logger.info("Voice control started - Say 'Hey Cutie' to interact")
    
    r = sr.Recognizer()
    r.energy_threshold = 300
    r.dynamic_energy_threshold = True
    r.pause_threshold = 0.8
    
    # Adjust for ambient noise
    try:
        with sr.Microphone() as source:
            logger.info("Adjusting for ambient noise...")
            r.adjust_for_ambient_noise(source, duration=1)
            logger.info("Ready for voice commands")
    except Exception as e:
        logger.error(f"Microphone error: {e}")
        return
    
    consecutive_errors = 0
    
    while voice_system_active:
        try:
            with sr.Microphone() as source:
                # Listen with longer timeout to reduce errors
                try:
                    audio = r.listen(source, timeout=2, phrase_time_limit=4)
                except sr.WaitTimeoutError:
                    # This is normal - no speech detected
                    consecutive_errors = 0
                    continue
                
                try:
                    # Try Bangla first, then English
                    try:
                        text = r.recognize_google(audio, language='bn-IN')
                        logger.info(f"Heard (Bangla): {text}")
                    except:
                        text = r.recognize_google(audio, language='en-IN')
                        logger.info(f"Heard (English): {text}")
                    
                    consecutive_errors = 0
                    
                    # Check for wake word
                    if "cutie" in text.lower() or "কিউটি" in text.lower():
                        speak("Ha, shunbo")
                        
                        # Listen for command
                        try:
                            audio_cmd = r.listen(source, timeout=3, phrase_time_limit=3)
                            
                            try:
                                cmd_text = r.recognize_google(audio_cmd, language='bn-IN')
                            except:
                                cmd_text = r.recognize_google(audio_cmd, language='en-IN')
                            
                            logger.info(f"Command: {cmd_text}")
                            
                            # Check if it's a system command
                            result = system_control(cmd_text.lower())
                            
                            if result == "WHATSAPP_MODE":
                                response = whatsapp_mode(r, source)
                                speak(response)
                            elif result:
                                speak(result)
                            else:
                                # Ask Groq AI
                                ai_response = ask_groq(cmd_text)
                                speak(ai_response[:200])
                                
                        except sr.WaitTimeoutError:
                            speak("Kichu shuni ni")
                        except sr.UnknownValueError:
                            speak("Bujhte parlam na")
                            
                except sr.UnknownValueError:
                    consecutive_errors += 1
                    if consecutive_errors > 10:
                        logger.warning("Multiple recognition errors - resetting")
                        consecutive_errors = 0
                    continue
                except sr.RequestError as e:
                    logger.error(f"Recognition error: {e}")
                    consecutive_errors += 1
                    continue
                    
        except Exception as e:
            logger.error(f"Voice loop error: {e}")
            time.sleep(1)

# ==================== FLASK ROUTES ====================
@app.route('/')
def home():
    return jsonify({
        "status": "CUTIE AI is running",
        "message": "Welcome to CUTIE AI - Bangla Accent Voice Assistant",
        "features": {
            "voice_active": AUDIO_AVAILABLE and not IS_RENDER,
            "bangla_accent": True,
            "system_commands": not IS_RENDER
        },
        "user": USER_NAME,
        "time": datetime.datetime.now().isoformat()
    })

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        message = data.get('message', '')
        
        if not message:
            return jsonify({"response": "Kichu bolen"})
        
        # Check for system commands
        cmd_result = system_control(message.lower())
        
        if cmd_result == "WHATSAPP_MODE":
            return jsonify({"response": "WhatsApp mode requires local machine with microphone"})
        elif cmd_result:
            return jsonify({"response": cmd_result})
        else:
            # Get AI response
            response = ask_groq(message)
            return jsonify({"response": response})
    
    except Exception as e:
        return jsonify({"response": f"Error: {str(e)}"})

@app.route('/status')
def status():
    return jsonify({
        "voice_active": AUDIO_AVAILABLE and not IS_RENDER,
        "time": datetime.datetime.now().isoformat(),
        "environment": "render" if IS_RENDER else "local"
    })

# ==================== START APPLICATION ====================

if __name__ == '__main__':
    print("=" * 60)
    print("CUTIE AI - BANGLA ACCENT VOICE ASSISTANT")
    print("=" * 60)
    
    if IS_RENDER:
        print("\n📢 RUNNING ON RENDER - Audio features disabled")
        print("✅ Web interface available at / endpoint")
        print("✅ Chat API available at /chat")
    else:
        print("\n✅ BANGLA ACCENT VOICE ACTIVE")
        print("✅ NO ACTIVATION REQUIRED")
        print("✅ Voice timeout errors FIXED")
        print("\n🎤 VOICE COMMANDS (Bangla/English mixed):")
        print("   Wake word: 'Hey Cutie' or 'কিউটি'")
        print("   • System: 'volume up/down', 'vol barhao/kam karo'")
        print("   • Apps: 'open chrome', 'close window'")
        print("   • WhatsApp: 'whatsapp message'")
        print("   • Time: 'koyta baje?', 'time?', 'samay?'")
        print("   • Date: 'tarikh?', 'date?'")
        print("   • Power: 'shutdown', 'band kor'")
    
    print("\n🌐 Web Interface: http://localhost:5000")
    print("=" * 60)
    
    if not IS_RENDER and AUDIO_AVAILABLE:
        # Test Bangla accent
        print("\n🔊 Testing Bangla accent:")
        test_phrases = [
            "Hello, how are you?",
            "What is the time now?",
            "Open Chrome browser",
            "Nomoskar, ki khobor?"
        ]
        for phrase in test_phrases:
            print(f"   • {phrase} -> {bangla_voice.add_bangla_accent(phrase)}")
        print("=" * 60)
        
        # Start voice control automatically
        voice_thread = threading.Thread(target=voice_loop, daemon=True)
        voice_thread.start()
        print("🎤 Voice control is ACTIVE - Say 'Hey Cutie'")
        print("=" * 60)
    else:
        print("📢 Running in headless mode - voice features disabled")
        print("=" * 60)
    
    # Run Flask app - FIXED FOR RENDER
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)  # debug=False for Render
