# Optimized speech_interview.py

import os
import base64
import json
import time
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, session
from gtts import gTTS
from werkzeug.utils import secure_filename
from auth import login_required
from bson.objectid import ObjectId
from pydub import AudioSegment
import cv2
import numpy as np
from PIL import Image
import io
import threading
import functools
import pyttsx3
from dotenv import load_dotenv

# Create Blueprint for speech interview routes
speech_interview_bp = Blueprint('speech_interview', __name__)

load_dotenv()


# Global storage for interview data
interview_data = {
    'attention_score': 0,
    'speech_clarity': 0,
    'response_times': []
}

camera_analysis = {
    'eye_contact_score': 0,
    'expression_score': 0,
    'posture_score': 0,
    'movement_score': 0,
    'frames_analyzed': 0
}

# Audio response cache to avoid regenerating common phrases
tts_cache = {}

# TTS engine singleton
tts_engine = None

def get_tts_engine():
    """Get or initialize the TTS engine"""
    global tts_engine
    if tts_engine is None:
        tts_engine = pyttsx3.init()
        # Set properties - adjust rate for faster speech
        tts_engine.setProperty('rate', tts_engine.getProperty('rate') * 1)
    return tts_engine

# Lazy initialization of OpenCV face detection (only when needed)
face_cascade = None

def get_face_cascade():
    """Get or initialize the face cascade classifier"""
    global face_cascade
    if face_cascade is None:
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    return face_cascade

def memoize(func):
    """Simple cache decorator for expensive operations"""
    cache = {}
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        key = str(args) + str(kwargs)
        if key not in cache:
            cache[key] = func(*args, **kwargs)
            # Limit cache size to avoid memory issues
            if len(cache) > 100:
                # Remove a random item (simple approach)
                cache.pop(next(iter(cache)))
        return cache[key]
    
    return wrapper

@memoize
def speech_to_text(audio_data):
    """Optimized speech-to-text processing with caching for identical inputs"""
    try:
        import groq
        import tempfile
        import os
        
        # Get Groq API key from environment
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables")
        
        # Initialize Groq client
        client = groq.Client(api_key=groq_api_key)
        
        # Convert base64 to bytes and optimize audio format
        audio_bytes = base64.b64decode(audio_data.split(',')[1])
        
        # Process audio to make it more suitable for STT
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_filename = temp_file.name
            temp_file.write(audio_bytes)
        
        # Optimize audio quality and format
        try:
            sound = AudioSegment.from_file(temp_filename)
            # Normalize audio volume
            sound = sound.normalize()
            # Convert to proper format for STT
            sound = sound.set_channels(1).set_frame_rate(16000)
            sound.export(temp_filename, format="wav")
        except Exception as e:
            print(f"Audio processing error: {e}")
            # Continue with original audio if processing fails
        
        # Open the file for reading
        with open(temp_filename, "rb") as audio_file:
            # Call Groq API with Whisper model for transcription
            response = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file
            )
            
            # Extract transcribed text
            text = response.text
        
        # Clean up temporary file
        os.remove(temp_filename)
        
        return text
    except Exception as e:
        print(f"Speech recognition error: {e}")
        return ""

def text_to_speech(text, speed=1.3):
    """Optimized text-to-speech with caching"""
    try:
        # Check cache first
        cache_key = f"{text}_{speed}"
        if cache_key in tts_cache:
            return tts_cache[cache_key]
        
        # Create a unique filename
        filename = f"speech_{hash(text)}.mp3"
        filepath = os.path.join("static", filename)
        
        # Check if file already exists
        if os.path.exists(filepath):
            return f"/static/{filename}"
        
        # Use pyttsx3 for faster local TTS processing
        try:
            engine = get_tts_engine()
            
            # Save to file
            engine.save_to_file(text, filepath)
            engine.runAndWait()
            
            # Store in cache
            output_path = f"/static/{filename}"
            tts_cache[cache_key] = output_path
            
            # Limit cache size to prevent memory issues
            if len(tts_cache) > 50:
                tts_cache.pop(next(iter(tts_cache)))
                
            return output_path
        except Exception as e:
            print(f"pyttsx3 error: {e}")
            # Fall back to gTTS if pyttsx3 fails
            tts = gTTS(text=text, lang='en')
            filename = f"speech_{hash(text)}.mp3"
            filepath = os.path.join("static", filename)
            tts.save(filepath)
            
            output_path = f"/static/{filename}"
            tts_cache[cache_key] = output_path
            return output_path
    except Exception as e:
        print(f"Text to speech error: {e}")
        return None

def analyze_frame(frame_data):
    """Optimized frame analysis"""
    try:
        # Convert base64 to image (more efficient processing)
        image_data = base64.b64decode(frame_data.split(',')[1])
        image = Image.open(io.BytesIO(image_data))
        
        # Resize image for faster processing
        image = image.resize((320, 240), Image.LANCZOS)
        
        # Convert to OpenCV format
        frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        
        # Initialize scores
        eye_contact = 0
        expression = 0
        posture = 0
        movement = 0
        
        # Convert to grayscale for face detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        face_cascade = get_face_cascade()
        faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(30, 30))
        
        if len(faces) > 0:
            # Face detected - good eye contact
            eye_contact = 1
            
            # Get the largest face
            largest_face = max(faces, key=lambda x: x[2] * x[3])
            (x, y, w, h) = largest_face
            
            # Extract face region
            face_roi = gray[y:y+h, x:x+w]
            
            # Simple expression analysis (basic proxy using edge detection)
            edges = cv2.Canny(face_roi, 100, 200)
            expression = min(1.0, np.sum(edges > 0) / (w * h * 0.1))
            
            # Check face position for posture
            frame_center_y = frame.shape[0] // 2
            face_center_y = y + (h // 2)
            
            # If face is centered, good posture
            if abs(face_center_y - frame_center_y) < frame.shape[0] * 0.15:
                posture = 1
            else:
                posture = 0.5
                
            # Previous frame storage for movement detection
            if not hasattr(analyze_frame, "prev_face"):
                analyze_frame.prev_face = largest_face
                movement = 0.5  # Neutral for first frame
            else:
                # Calculate movement as distance between face centers
                prev_center = (analyze_frame.prev_face[0] + analyze_frame.prev_face[2]//2, 
                              analyze_frame.prev_face[1] + analyze_frame.prev_face[3]//2)
                curr_center = (x + w//2, y + h//2)
                
                # Calculate distance
                distance = np.sqrt((prev_center[0] - curr_center[0])**2 + 
                                  (prev_center[1] - curr_center[1])**2)
                
                # Normalize movement (0.5 is ideal - some movement but not too much)
                movement = 1.0 - min(1.0, abs(distance - 10) / 20)
                
                # Update previous face
                analyze_frame.prev_face = largest_face
        else:
            # No face detected - poor scores
            eye_contact = 0
            expression = 0
            posture = 0
            movement = 0
        
        # Update global analysis using thread-safe approach
        with threading.Lock():
            camera_analysis['eye_contact_score'] += eye_contact
            camera_analysis['expression_score'] += expression  
            camera_analysis['posture_score'] += posture
            camera_analysis['movement_score'] += movement
            camera_analysis['frames_analyzed'] += 1
        
        return {
            'eye_contact': eye_contact,
            'expression': expression,
            'posture': posture,
            'movement': movement,
            'feedback': get_realtime_feedback(eye_contact, expression, posture, movement)
        }
    except Exception as e:
        print(f"Frame analysis error: {e}")
        return {
            'error': str(e)
        }

def get_realtime_feedback(eye_contact, expression, posture, movement):
    """Generate real-time feedback for the UI"""
    if eye_contact < 0.5:
        return "Look at the camera"
    elif posture < 0.5:
        return "Improve your posture"
    elif expression < 0.3:
        return "Be more expressive"
    elif movement > 0.8:
        return "Reduce excessive movement"
    elif movement < 0.2:
        return "Use more natural gestures"
    else:
        return "Looking good!"

def generate_feedback():
    """Generate interview feedback with thread safety"""
    try:
        # Calculate average response time
        avg_response_time = 0
        if interview_data['response_times']:
            avg_response_time = sum(interview_data['response_times']) / len(interview_data['response_times'])
        
        # Calculate camera analysis averages
        eye_contact = 0
        expression = 0
        posture = 0
        movement = 0
        
        # Thread-safe access to shared data
        with threading.Lock():
            if camera_analysis['frames_analyzed'] > 0:
                eye_contact = camera_analysis['eye_contact_score'] / camera_analysis['frames_analyzed']
                expression = camera_analysis['expression_score'] / camera_analysis['frames_analyzed'] 
                posture = camera_analysis['posture_score'] / camera_analysis['frames_analyzed']
                movement = camera_analysis['movement_score'] / camera_analysis['frames_analyzed']
        
        # Generate basic feedback
        feedback = {
            "avg_response_time": avg_response_time,
            "speech_clarity": interview_data['speech_clarity'],
            "attention": interview_data['attention_score'],
            "eye_contact": eye_contact,
            "expression": expression,
            "posture": posture,
            "movement": movement,
            "suggestions": []
        }
        
        # Generate personalized suggestions based on metrics
        if avg_response_time > 10:
            feedback["suggestions"].append("Consider preparing more concise answers to common interview questions.")
        elif avg_response_time < 3:
            feedback["suggestions"].append("Try to elaborate more on your answers to provide more context and details.")
        
        # Generate suggestions based on camera analysis
        if eye_contact < 0.6:
            feedback["suggestions"].append("Work on maintaining better eye contact with the interviewer.")
        
        if expression < 0.5:
            feedback["suggestions"].append("Try to be more expressive and engaged during the interview.")
        
        if posture < 0.7:
            feedback["suggestions"].append("Maintain good posture throughout the interview to project confidence.")
        
        if movement < 0.4:
            feedback["suggestions"].append("Your body language appears stiff. Consider using appropriate hand gestures.")
        elif movement > 0.8:
            feedback["suggestions"].append("Try to reduce excessive movement which can be distracting.")
        
        # Add general suggestions
        feedback["suggestions"].append("Practice active listening and maintain engagement throughout the interview.")
        
        # Reset interview data for next interview
        reset_interview_data()
        
        return feedback
    except Exception as e:
        print(f"Feedback generation error: {e}")
        return {"error": f"Error generating feedback: {str(e)}"}

def reset_interview_data():
    """Reset interview data in a thread-safe manner"""
    global interview_data, camera_analysis
    
    with threading.Lock():
        interview_data = {
            'attention_score': 0,
            'speech_clarity': 0,
            'response_times': []
        }
        camera_analysis = {
            'eye_contact_score': 0,
            'expression_score': 0,
            'posture_score': 0,
            'movement_score': 0,
            'frames_analyzed': 0
        }

# Preload common interview phrases
def preload_common_phrases():
    """Preload common interview phrases for faster response"""
    common_phrases = [
        "Tell me a bit about yourself.",
        "What are your strengths and weaknesses?",
        "Thank you for your response.",
        "That's an interesting point.",
        "Could you elaborate on that?",
        "Thank you for completing the interview! Check out your feedback below.",
    ]
    
    # Preload in background thread
    def preload_worker():
        for phrase in common_phrases:
            text_to_speech(phrase)
    
    threading.Thread(target=preload_worker).start()

# Routes
@speech_interview_bp.route('/start_speech_interview', methods=['POST'])
@login_required
def start_speech_interview():
    # Preload common phrases
    preload_common_phrases()
    
    # Reset interview data for new interview
    reset_interview_data()
    
    # This will be the same as in your main app
    from interviewer import messages, personality, generate_text
    
    # Reset messages to just the system personality
    # global messages
    messages = [{"role": "system", "content": f"{personality}"}]
    
    # Get candidate name from the session or form
    candidate_name = session.get('candidate_name', session.get('user_name', 'Anonymous Candidate'))
    if 'candidate_name' in request.form:
        candidate_name = request.form['candidate_name']
        session['candidate_name'] = candidate_name
    
    # Generate initial greeting using Groq AI (this uses your existing generate_text function)
    bot_response = generate_text()
    
    # Convert to speech
    speech_file = text_to_speech(bot_response)
    
    # Save history
    from interviewer import save_history_to_json
    save_history_to_json(messages, "history.json")
    
    return jsonify({
        'text': bot_response,
        'audio': speech_file
    })

@speech_interview_bp.route('/process_speech', methods=['POST'])
@login_required
def process_speech():
    try:
        # Get audio data
        audio_data = request.json['audio']
        start_time = request.json.get('start_time', 0)
        
        # Calculate response time
        if start_time:
            response_time = (time.time() - float(start_time))
            interview_data['response_times'].append(response_time)
        
        # Process speech to text
        user_input = speech_to_text(audio_data)
        
        # Update speech clarity score
        if user_input:
            # Simple metric: longer recognized text generally means better clarity
            interview_data['speech_clarity'] += len(user_input) / 20  # Arbitrary normalization
            interview_data['attention_score'] += 1
        
        # Process with AI (using your existing code)
        from interviewer import messages, generate_text
        messages.append({"role": "user", "content": user_input})
        
        # Generate response from Groq AI
        bot_response = generate_text()
        
        # Start text-to-speech in a separate thread to return text response immediately
        def process_tts():
            speech_file = text_to_speech(bot_response)
            # Save history
            from interviewer import save_history_to_json
            save_history_to_json(messages, "history.json")
            return speech_file
        
        # Process TTS in background
        tts_thread = threading.Thread(target=process_tts)
        tts_thread.start()
        
        # Return recognized text immediately
        return jsonify({
            'text': bot_response,
            'audio': text_to_speech(bot_response),  # This might be cached already
            'recognized_text': user_input
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@speech_interview_bp.route('/process_text', methods=['POST'])
@login_required
def process_text():
    try:
        # Get text input and response time
        user_input = request.json['message']
        response_time = request.json.get('response_time', 0)
        
        # Record response time
        if response_time:
            interview_data['response_times'].append(float(response_time))
        
        # Update attention score
        interview_data['attention_score'] += 1
        
        # Process with AI
        from interviewer import messages, generate_text
        messages.append({"role": "user", "content": user_input})
        
        # Generate response from Groq AI
        bot_response = generate_text()
        
        # Convert response to speech for consistent user experience
        speech_file = text_to_speech(bot_response)
        
        # Save history
        from interviewer import save_history_to_json
        save_history_to_json(messages, "history.json")
        
        return jsonify({
            'text': bot_response,
            'audio': speech_file
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@speech_interview_bp.route('/end_speech_interview', methods=['POST'])
@login_required
def end_speech_interview():
    # Save the complete interview transcript to MongoDB with user_id
    from interviewer import messages, save_history_to_mongodb
    
    candidate_name = session.get('candidate_name', session.get('user_name', 'Anonymous Candidate'))
    user_id = session.get('user_id')
    
    # Generate basic feedback
    feedback = generate_feedback()
    
    # Add feedback to messages
    feedback_message = {
        "role": "system", 
        "content": f"## Interview Feedback\n\n" + 
                  f"Average response time: {feedback.get('avg_response_time', 0):.1f} seconds\n\n" +
                  f"Speech clarity score: {feedback.get('speech_clarity', 0):.1f}\n\n" +
                  "### Suggestions\n" +
                  "\n".join([f"- {s}" for s in feedback.get('suggestions', [])])
    }
    messages.append(feedback_message)
    
    # Save to MongoDB
    document_id = save_history_to_mongodb(messages, candidate_name, user_id)
    
    # Reset interview data
    reset_interview_data()
    
    return jsonify({
        'message': 'Interview ended and saved to database',
        'document_id': str(document_id),
        'feedback': feedback
    })

@speech_interview_bp.route('/process_frame', methods=['POST'])
@login_required
def process_frame():
    try:
        # Get frame data
        frame_data = request.json['frame']
        
        # Analyze frame (in background thread to not block)
        frame_result = analyze_frame(frame_data)
        
        return jsonify(frame_result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@speech_interview_bp.route('/interview_feedback', methods=['GET'])
@login_required
def get_interview_feedback():
    feedback = generate_feedback()
    return jsonify(feedback)