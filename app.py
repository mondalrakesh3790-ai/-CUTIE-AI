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

# ==================== CHECK RENDER ENVIRONMENT ====================
# Check if we're running on Render
ON_RENDER = os.environ.get('RENDER', False)

# Only import GUI/screen-dependent libraries when NOT on Render
if not ON_RENDER:
    import speech_recognition as sr
    import pyttsx3
    import pyautogui
    import pyperclip
    import screen_brightness_control as sbc
else:
    print("🎤 Running on Render: Voice and GUI features are disabled.")
    print("💬 Chat interface will work normally!")
    # Create dummy modules to prevent import errors
    sr = None
    pyttsx3 = None
    pyautogui = None
    pyperclip = None
    sbc = None

# ==================== CONFIGURATION ====================
GROQ_API_KEY = "YOUR_API_KEY_HERE"  # Add your Groq API key here
USER_NAME = "Rakesh"

app = Flask(__name__)
CORS(app)

# Initialize components
conversation_history = []
voice_system_active = not ON_RENDER  # Disable voice on Render
voice_thread = None
command_queue = queue.Queue()
voice_feedback_queue = queue.Queue()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize TTS engine (only if not on Render)
tts_engine = None
if not ON_RENDER:
    try:
        tts_engine = pyttsx3.init()
        tts_engine.setProperty('rate', 170)
        tts_engine.setProperty('volume', 0.9)
        # Get male voice if available
        voices = tts_engine.getProperty('voices')
        if len(voices) > 0:
            tts_engine.setProperty('voice', voices[0].id)  # Male voice
    except Exception as e:
        logger.error(f"TTS init error: {e}")
        tts_engine = None

# Available Groq models
GROQ_MODELS = {
    "llama-3.3-70b": "llama-3.3-70b-versatile",
    "llama-3.1-8b": "llama-3.1-8b-instant",
    "mixtral": "mixtral-8x7b-32768",
    "gemma2": "gemma2-9b-it"
}

DEFAULT_MODEL = GROQ_MODELS["llama-3.1-8b"]

# ==================== GROQ AI FUNCTIONS ====================
def ask_groq(user_message):
    """Get response from Groq API"""
    
    messages = [
        {"role": "system", "content": f"""You are CUTIE AI, a helpful AI assistant. 
         User's name is {USER_NAME}. Be professional, concise, and helpful. 
         Keep responses under 2-3 sentences for voice responses.
         Use a professional tone but remain friendly."""}
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
                "model": DEFAULT_MODEL,
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

# ==================== VOICE FUNCTIONS (Only work locally) ====================
def speak(text):
    """Text to speech function - disabled on Render"""
    if ON_RENDER:
        # On Render, just log the message
        print(f"CUTIE: {text}")
        return
    
    try:
        if tts_engine:
            tts_engine.say(text)
            tts_engine.runAndWait()
        else:
            print(f"CUTIE: {text}")
    except Exception as e:
        logger.error(f"Speech error: {e}")

def system_control(command):
    """Execute system commands - disabled on Render"""
    if ON_RENDER:
        # On Render, return message that this feature isn't available
        if any(word in command.lower() for word in ["volume", "brightness", "open", "close", "shutdown", "restart"]):
            return "System control commands are only available when running locally, not on Render."
        return None
    
    cmd = command.lower()
    
    # Volume control
    if "volume up" in cmd:
        for _ in range(5):
            pyautogui.press("volumeup")
        return "Volume increased"
    elif "volume down" in cmd:
        for _ in range(5):
            pyautogui.press("volumedown")
        return "Volume decreased"
    
    # Brightness control
    elif "brightness up" in cmd:
        try:
            curr = sbc.get_brightness()[0]
            sbc.set_brightness(min(curr + 20, 100))
            return "Brightness increased"
        except:
            return "Brightness control not available"
    elif "brightness down" in cmd:
        try:
            curr = sbc.get_brightness()[0]
            sbc.set_brightness(max(curr - 20, 0))
            return "Brightness decreased"
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
    elif "time" in cmd or "samay" in cmd:
        current_time = datetime.datetime.now().strftime("%I:%M %p")
        return f"The time is {current_time}"
    
    # Date
    elif "date" in cmd or "tarikh" in cmd:
        current_date = datetime.datetime.now().strftime("%B %d, %Y")
        return f"Today's date is {current_date}"
    
    # WhatsApp
    elif "whatsapp" in cmd or "message" in cmd:
        if ON_RENDER:
            return "WhatsApp messaging is only available when running locally."
        return "WHATSAPP_MODE"
    
    # Shutdown
    elif "shutdown" in cmd or "switch off" in cmd:
        speak("Shutting down in 10 seconds")
        os.system("shutdown /s /t 10")
        return "Shutting down"
    
    # Restart
    elif "restart" in cmd:
        speak("Restarting in 10 seconds")
        os.system("shutdown /r /t 10")
        return "Restarting"
    
    # Greetings
    elif any(word in cmd for word in ["hello", "hi", "hey"]):
        return f"Hello {USER_NAME}, how can I help you?"
    
    return None

def whatsapp_mode(recognizer, source):
    """Handle WhatsApp message sending - only works locally"""
    if ON_RENDER:
        return "WhatsApp mode is not available on Render"
    
    try:
        speak("Who should I send the message to?")
        
        # Get name
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=3)
        name = recognizer.recognize_google(audio, language='en-IN')
        
        speak(f"What message should I send to {name}?")
        
        # Get message
        audio_msg = recognizer.listen(source, timeout=5, phrase_time_limit=5)
        message = recognizer.recognize_google(audio_msg, language='en-IN')
        
        speak("Opening WhatsApp")
        
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
        
        return "Message sent successfully"
        
    except sr.WaitTimeoutError:
        return "Listening timeout - please try again"
    except sr.UnknownValueError:
        return "Could not understand audio - please try again"
    except Exception as e:
        logger.error(f"WhatsApp error: {e}")
        return "Sorry, I couldn't send the message"

def voice_loop():
    """Main voice control loop - only runs locally"""
    if ON_RENDER:
        logger.info("Voice loop disabled on Render")
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
                    # Convert speech to text
                    text = r.recognize_google(audio, language='en-IN')
                    logger.info(f"Heard: {text}")
                    consecutive_errors = 0
                    
                    # Check for wake word
                    if "cutie" in text.lower():
                        speak("Yes, listening")
                        
                        # Listen for command
                        try:
                            audio_cmd = r.listen(source, timeout=3, phrase_time_limit=3)
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
                            speak("I didn't hear a command")
                        except sr.UnknownValueError:
                            speak("Could not understand the command")
                            
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
    return render_template('index.html', user_name=USER_NAME)

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        message = data.get('message', '')
        
        if not message:
            return jsonify({"response": "Please say something"})
        
        # Check for system commands
        cmd_result = system_control(message.lower())
        
        if cmd_result == "WHATSAPP_MODE":
            return jsonify({"response": "Please use voice for WhatsApp messages when running locally"})
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
        "voice_active": voice_system_active,
        "time": datetime.datetime.now().isoformat(),
        "on_render": ON_RENDER
    })

# ==================== START APPLICATION ====================
if __name__ == '__main__':
    print("=" * 60)
    print("CUTIE AI - PROFESSIONAL VOICE ASSISTANT")
    print("=" * 60)
    
    if ON_RENDER:
        print("\n🌐 RUNNING ON RENDER")
        print("✅ Voice features are disabled")
        print("✅ Chat interface is ACTIVE")
        print("\n💬 Chat with CUTIE AI normally!")
    else:
        print("\n✅ NO ACTIVATION REQUIRED")
        print("✅ Voice timeout errors FIXED")
        print("\n🎤 VOICE COMMANDS:")
        print("   Wake word: 'Hey Cutie'")
        print("   • System: 'volume up/down', 'brightness up/down'")
        print("   • Apps: 'open chrome', 'close window'")
        print("   • WhatsApp: 'whatsapp message'")
        print("   • Info: 'what's the time?', 'today's date'")
        print("   • Power: 'shutdown', 'restart'")
    
    print("\n🌐 Web Interface: http://localhost:5000" if not ON_RENDER else f"\n🌐 Live URL: https://cutie-ai-gyfu.onrender.com")
    print("=" * 60)
    
    # Start voice control automatically (only if not on Render)
    if not ON_RENDER:
        voice_thread = threading.Thread(target=voice_loop, daemon=True)
        voice_thread.start()
        print("🎤 Voice control is ACTIVE - Say 'Hey Cutie'")
    else:
        print("💬 Chat interface ready - Voice disabled on Render")
    
    print("=" * 60)
    
    # Run Flask app - FIXED FOR RENDER
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
