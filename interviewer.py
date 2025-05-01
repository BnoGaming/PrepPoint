# interviewer.py (Main File)
import os
import requests
import groq
import json
import pdfplumber
import urllib.parse
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from datetime import datetime
from bson.objectid import ObjectId
from bson.json_util import dumps
from dotenv import load_dotenv

# Import authentication blueprint and functions
from auth import auth_bp, login_required, get_user_by_id, is_authenticated

# Import resume analyzer functionality
from resume_analyzer import extract_words_from_pdf, send_to_gemini_api

# Import the speech interview blueprint
from speech_interview import speech_interview_bp

# Import the aptitude test blueprint
from aptitude_test import aptitude_bp

# Import Admin blueprint
from admin import admin_bp, init_admin_user

app = Flask(__name__)
app.secret_key = "unified_app_secret_key"
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}

# Register authentication blueprint
app.register_blueprint(auth_bp, url_prefix='/auth')

# Create uploads folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Register the speech interview blueprint
app.register_blueprint(speech_interview_bp)

# Register the aptitude test blueprint
app.register_blueprint(aptitude_bp)

# Register the admin blueprint
app.register_blueprint(admin_bp, url_prefix='/admin')

os.makedirs('static', exist_ok=True)

# Initialize Groq client
load_dotenv()
client = groq.Client(api_key="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")

# MongoDB connection
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['interview_app']
resume_collection = db['resume_analysis']
transcript_collection = db['interview_transcripts']
users_collection = db['users']
dsa_questions = db['dsa_questions']
aptitude_questions = db['apti_question']


# Define personality for AI interviewer
personality = """
Task: You are John Doe, a Senior Technical Interviewer who conducts smart, adaptive interviews based on a candidate's resume.

Rules:
1. Always ask short, simple questions — no more than one sentence.
2. Focus questions on the candidate’s resume: their skills, tools, projects, and experiences.
3. If the candidate answers correctly and confidently, ask a slightly harder question next.
4. If the candidate struggles, follow up with an easier question on the same topic.
5. Maintain a professional, friendly, and encouraging tone throughout.
6. Mix technical and behavioral questions based on the candidate’s work and project history.
7. Never mention interview structure or scoring; keep the flow natural.

Interview Flow:
- Start with a brief, friendly intro referencing something specific from their resume.
- Begin with a basic question on their strongest skill.
- Increase or decrease difficulty based on the answer.
- Progress through technical questions, projects discussion, and problem-solving scenarios.
- Include questions about their listed work experiences and how they handled challenges.
- End with a detailed summary of the interview and mention the next steps.

You have access to the candidate's resume text, so reference specific projects, technologies, and experiences from it.
Never mention the predefined structure of rounds or scoring system - this is a natural conversation.

Important: Keep all questions short, clear, and no longer than one sentence.
"""

messages = [{"role": "system", "content": f"{personality}"}]

# Initialize admin user during application startup
with app.app_context():
    init_admin_user()

# Helper functions for project 2 (Interview Assistant)
def load_resume_text():
    try:
        with open('resume_text.txt', 'r') as file:
            resume_text = file.read()
            return resume_text
    except FileNotFoundError:
        return ''


def generate_text(user_input=None):
    resume_text = load_resume_text()
    
    # If this is the start of the interview, include resume context
    if len(messages) <= 1:  # Only system message exists
        # First, check if we have a resume to work with
        if resume_text:
            context_message = {
                "role": "system", 
                "content": f"The candidate's resume contains the following information:\n\n{resume_text}\n\nPlease start the interview with a brief introduction and welcome message that references specific elements from their resume to establish rapport."
            }
            messages.append(context_message)
        else:
            # No resume available, conduct a more general interview
            context_message = {
                "role": "system", 
                "content": "No resume has been provided. Please conduct a general technical interview starting with an introduction and asking about the candidate's background and skills."
            }
            messages.append(context_message)
        
    # Add user input if provided
    if user_input:
        messages.append({"role": "user", "content": user_input})
        
    response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages)
    bot_response = response.choices[0].message.content
    
    # Only append assistant response now (user's was added earlier if it existed)
    messages.append({"role": "assistant", "content": bot_response})
    return bot_response

def save_history_to_json(history, file_path="history.json"):
    with open(file_path, "w") as file:
        json.dump(history, file, indent=4)
        
def save_history_to_mongodb(history, candidate_name=None, user_id=None):
    """Save interview transcript to MongoDB"""
    # Convert the messages list into a more readable format
    transcript = []
    candidate_name = candidate_name or "Anonymous Candidate"
    
    for msg in history:
        if msg["role"] == "system":
            continue  # Skip system messages
        
        transcript.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    
    # Create a document for MongoDB
    doc = {
        "candidate_name": candidate_name,
        "date": datetime.now(),
        "transcript": transcript,
        "message_count": len(transcript),
        "user_id": user_id  # Add user_id to link data to user
    }
    
    # Insert into MongoDB
    result = transcript_collection.insert_one(doc)
    return result.inserted_id

def load_history_from_json(file_path="history.json"):
    try:
        with open(file_path, "r") as file:
            history = json.load(file)
        return history
    except (FileNotFoundError, json.JSONDecodeError):
        return []

# Helper function for file extensions validation
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Calculate profile completion percentage
def calculate_profile_completion(user):
    if not user:
        return 0
    
    fields = ['name', 'email', 'bio', 'job_title', 'industry']
    completed = sum(1 for field in fields if field in user and user[field])

    return int((completed / len(fields)) * 100)

@app.route('/admin')
def admin_redirect():
    if session.get('is_admin'):
        return redirect(url_for('admin.dashboard'))
    else:
        return redirect(url_for('admin.admin_login'))


# API route to get a random DSA question by difficulty
@app.route('/api/dsa-submissions')
@login_required
def api_dsa_submissions():
    user_id = session.get('user_id')
    submissions = list(db.dsa_submissions.find({'user_id': user_id}).sort("date", -1))
    
    # For each submission, get the associated question details
    for submission in submissions:
        try:
            question = db.dsa_questions.find_one({"_id": ObjectId(submission["question_id"])})
            if question:
                submission["question_title"] = question.get("question", "Unknown Question")
                submission["difficulty"] = question.get("difficulty", "Unknown")
            else:
                submission["question_title"] = "Question not found"
                submission["difficulty"] = "Unknown"
        except:
            submission["question_title"] = "Question not found"
            submission["difficulty"] = "Unknown"
            
        # Convert ObjectId to string for JSON serialization
        submission['_id'] = str(submission['_id'])
        submission['date'] = submission['date'].isoformat() if isinstance(submission['date'], datetime) else submission['date']
    
    return jsonify(submissions)

# API route to analyze user's solution
@app.route('/api/analyze-solution', methods=['POST'])
@login_required
def analyze_solution():
    data = request.json
    user_solution = data.get('solution', '')
    question_id = data.get('question_id', '')
    
    # Get the question from MongoDB
    try:
        question = db.dsa_questions.find_one({"_id": ObjectId(question_id)})
    except:
        return jsonify({"error": "Invalid question ID"}), 400
    
    if not question:
        return jsonify({"error": "Question not found"}), 404
    
    # Get the correct solution for comparison
    correct_solution = question.get('answer', '')
    problem_statement = question.get('question', '')
    
    # Create prompt for the AI to analyze the solution
    prompt = f"""
    You are a DSA expert reviewing a user's solution.

Given the problem, a correct reference solution, and the user's solution, perform a detailed comparative analysis.

Problem:
{problem_statement}

Correct Solution:
{correct_solution}

User's Solution:
{user_solution}

Please evaluate the user's solution based on the following criteria:

1.Correctness — Does the solution produce correct results for all cases, including edge cases?
2.Time Complexity — Is the time efficiency optimal or close to the reference solution?
3.Space Complexity — Is the memory usage minimal and justified compared to the correct approach?
4.Code Quality and Readability — Is the code clean, well-structured, and easy to understand?
5.Potential Improvements — Suggest specific logical, performance, or stylistic improvements.

Feedback Formatting Instructions:

Use green tick icons to bullet each point in your feedback.
Strictly dont involve any *, #, **, etc formatting or any other things in response.
Bold the main point of each bullet (e.g., Correctness, Time Complexity).
Avoid using asterisks, hashes, or markdown characters in your output.
Keep the tone constructive and specific.
If the user’s solution is incorrect or suboptimal, provide helpful hints or suggestions without giving away the complete correct solution.
Present the feedback in a clean, professional, and readable format suitable for learners.

    """
    
    # Send to Groq for analysis
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}]
        )
        analysis = response.choices[0].message.content
        
        # Save the submission and analysis to the database
        submission_record = {
            "user_id": session.get('user_id'),
            "question_id": question_id,
            "user_solution": user_solution,
            "analysis": analysis,
            "date": datetime.now()
        }
        db.dsa_submissions.insert_one(submission_record)
        
        return jsonify({"analysis": analysis})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Add route to view past submissions
@app.route('/aptitude-test', methods=['GET'])
def aptitude_test():
    return render_template('aptitude_test.html')  # Make sure this template exists

@app.route('/dsa-submissions')
@login_required
def dsa_submissions():
    user_id = session.get('user_id')
    
    # Get the user's past DSA submissions
    submissions = list(db.dsa_submissions.find({"user_id": user_id}).sort("date", -1).limit(10))
    
    # For each submission, get the associated question
    for submission in submissions:
        question = db.dsa_questions.find_one({"_id": ObjectId(submission["question_id"])})
        if question:
            submission["question_title"] = question.get("question", "Unknown Question")
            submission["difficulty"] = question.get("difficulty", "Unknown")
        else:
            submission["question_title"] = "Question not found"
            submission["difficulty"] = "Unknown"
        
        # Convert ObjectId to string
        submission["_id"] = str(submission["_id"])
        submission["date"] = submission["date"].strftime("%Y-%m-%d %H:%M")
    
    return render_template('dsa_submissions.html', submissions=submissions)

@app.route('/dsa-questions')
@login_required
def dsa_questions():
    questions = list(db.dsa_questions.find())
    return render_template('dsa_list.html', questions=questions)

@app.route('/solve-question/<question_id>')
@login_required
def solve_question(question_id):
    question = db.dsa_questions.find_one({'_id': ObjectId(question_id)})
    if not question:
        return "Question not found", 404
    return render_template('solve_question.html', question=question)


# Main home page route
@app.route('/')
def home():
    return render_template('home.html', is_authenticated=is_authenticated())

# User dashboard route
@app.route('/data-viewer')
@login_required
def dashboard():
    user_id = session.get('user_id')
    
    # Get user's data
    user = get_user_by_id(user_id)
    profile_completion = calculate_profile_completion(user)
    
    # Get user's resume analyses
    resume_analyses = list(resume_collection.find({"user_id": user_id}).sort("date", -1).limit(5))
    resume_count = resume_collection.count_documents({"user_id": user_id})
    
    # Get user's interview transcripts
    interview_transcripts = list(transcript_collection.find({"user_id": user_id}).sort("date", -1).limit(5))
    interview_count = transcript_collection.count_documents({"user_id": user_id})

    # Get user's DSA submissions count
    dsa_count = db.dsa_submissions.count_documents({"user_id": user_id})

    apti_count = db.aptitude_results.count_documents({"user_id": user_id})

    
    return render_template('data_viewer.html', 
                          user=user,
                          resume_analyses=resume_analyses,
                          interview_transcripts=interview_transcripts,
                          resume_count=resume_count,
                          interview_count=interview_count,
                          dsa_count=dsa_count,
                          apti_count=apti_count,
                          profile_completion=profile_completion)

@app.route('/api/aptitude-results', methods=['GET'])
@login_required
def get_aptitude_results():
    user_id = session.get('user_id')
    results = list(db.aptitude_results.find({'user_id': user_id}).sort('date', -1))
    
    # Convert ObjectId to string for JSON serialization
    for result in results:
        result['_id'] = str(result['_id'])
        
    return jsonify(results)

# Routes for project 1 (Resume Analyzer)
@app.route('/resume-analyzer', methods=['GET', 'POST'])
@login_required
def resume_analyzer():
    if request.method == 'POST':
        # Check if file was uploaded
        if 'resume' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
            
        file = request.files['resume']
        candidate_name = request.form.get('candidate_name', session.get('user_name', 'Anonymous'))
        
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Process the PDF
            extracted_text = extract_words_from_pdf(file_path)
            
            if extracted_text:
                analysis = send_to_gemini_api(extracted_text)
                if analysis:
                    # Store the analysis in session for the results page
                    session['analysis'] = analysis
                    
                    # Store in MongoDB with user_id
                    doc = {
                        "candidate_name": candidate_name,
                        "date": datetime.now(),
                        "filename": filename,
                        "analysis": analysis,
                        "extracted_text": extracted_text[:1000],  # Store a preview of the extracted text
                        "user_id": session.get('user_id')  # Link to user
                    }
                    resume_collection.insert_one(doc)
                    
                    return redirect(url_for('resume_results'))
                else:
                    flash('Failed to get analysis from Gemini API', 'danger')
            else:
                flash('Could not extract text from the PDF', 'danger')
        else:
            flash('Only PDF files are allowed', 'danger')
    
    return render_template('resume_analyzer.html')

@app.route('/resume-results')
@login_required
def resume_results():
    analysis = session.get('analysis', None)
    if not analysis:
        flash('No analysis found. Please upload a resume first.', 'warning')
        return redirect(url_for('resume_analyzer'))
    
    # Handle error in analysis
    if isinstance(analysis, dict) and "error" in analysis:
        flash(f'Error in analysis: {analysis["error"]}', 'danger')
        return render_template('resume_results.html', 
                               analysis=analysis.get("raw_text", "No analysis available"),
                               is_raw=True)
    
    # For properly structured JSON responses
    if isinstance(analysis, dict):
        return render_template('resume_results.html', 
                               analysis=analysis,
                               is_structured=True)
    
    # For legacy text responses, use the old parsing method
    sections = {
        'strengths': '',
        'weaknesses': '',
        'mistakes': '',
        'rating': ''
    }
    
    current_section = None
    for line in analysis.split('\n'):
        if '1.' in line and 'Strengths' in line:
            current_section = 'strengths'
            sections['strengths'] += line.replace('1.', '').replace('Strengths', '').replace(':', '').strip() + '\n'
        elif '2.' in line and 'Weakness' in line:
            current_section = 'weaknesses'
            sections['weaknesses'] += line.replace('2.', '').replace('Weakness', '').replace(':', '').strip() + '\n'
        elif '3.' in line and 'Mistakes' in line:
            current_section = 'mistakes'
            sections['mistakes'] += line.replace('3.', '').replace('Mistakes/Areas', '').replace(':', '').strip() + '\n'
        elif '4.' in line and 'Give rating' in line or 'Rating=' in line:
            current_section = 'rating'
            if 'Rating=' in line:
                sections['rating'] = line.split('Rating=')[1].strip()
            else:
                sections['rating'] += line.replace('4.', '').replace('Give rating as', '').replace(':', '').strip() + '\n'
        elif current_section:
            sections[current_section] += line.strip() + '\n'
    
    # Clean up the sections
    for key in sections:
        sections[key] = sections[key].strip()
        
    # Extract rating as a number
    rating_text = sections['rating']
    rating = None
    import re
    rating_match = re.search(r'\[(\d+\.?\d*)/10\]', rating_text)
    if rating_match:
        rating = float(rating_match.group(1))
    
    return render_template('resume_results.html', 
                           analysis=analysis, 
                           sections=sections,
                           rating=rating,
                           is_structured=False)


@app.route('/view-analysis/<analysis_id>')
@login_required
def view_analysis(analysis_id):
    # Get the analysis by ID and ensure it belongs to the current user
    analysis = resume_collection.find_one({
        '_id': ObjectId(analysis_id),
        'user_id': session.get('user_id')
    })
    
    if not analysis:
        flash('Analysis not found or you do not have permission to view it', 'danger')
        return redirect(url_for('dashboard'))
    
    return render_template('view_analysis.html', analysis=analysis)

# Routes for project 2 (Interview Assistant)
@app.route('/upload_resume', methods=['POST'])
@login_required
def upload_resume():
    resume_file = request.files['resume']
    candidate_name = request.form.get('candidate_name', session.get('user_name', 'Anonymous'))
    session['candidate_name'] = candidate_name
    
    resume_file_path = Path(__file__).parent / "uploaded_resume.pdf"
    resume_file.save(resume_file_path)

    # Parse the resume using pdfplumber
    with pdfplumber.open(resume_file_path) as pdf:
        resume_text = ''
        for page in pdf.pages:
            resume_text += page.extract_text()

    # Save the resume text to a file
    with open('resume_text.txt', 'w') as file:
        file.write(resume_text)

    return jsonify({'message': 'Resume uploaded successfully'})

@app.route('/start_interview', methods=['POST'])
@login_required
def start_interview():
    # Reset messages to just the system personality
    global messages
    messages = [{"role": "system", "content": f"{personality}"}]
    
    # Get candidate name from the session or form
    candidate_name = session.get('candidate_name', session.get('user_name', 'Anonymous Candidate'))
    if 'candidate_name' in request.form:
        candidate_name = request.form['candidate_name']
        session['candidate_name'] = candidate_name
    
    # Generate initial greeting that mentions resume details
    bot_response = generate_text()
    save_history_to_json(messages, "history.json")
    
    return jsonify({'reply': bot_response})


@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    user_input = request.json['message']
    messages.append({"role": "user", "content": user_input})
    bot_response = generate_text()
    save_history_to_json(messages, "history.json")
    return jsonify({'reply': bot_response})

# Add this route to your existing routes in interviewer.py
@app.route('/interview/speech')
@login_required
def speech_analysis():
    """Route for the speech-based interview with facial analysis"""
    return render_template('speech_interview.html')


@app.route('/interview')
@login_required
def interview():
    return render_template('interview.html')


@app.route('/interview/text')
@login_required
def text_chat():
    return render_template('text_chat.html')

@app.route('/end_interview', methods=['POST'])
@login_required
def end_interview():
    # Save the complete interview transcript to MongoDB with user_id
    candidate_name = session.get('candidate_name', session.get('user_name', 'Anonymous Candidate'))
    user_id = session.get('user_id')
    document_id = save_history_to_mongodb(messages, candidate_name, user_id)
    
    return jsonify({
        'message': 'Interview ended and saved to database',
        'document_id': str(document_id)
    })


@app.route('/api/resumes')
@login_required
def api_resumes():
    user_id = session.get('user_id')
    resumes = list(resume_collection.find({'user_id': user_id}).sort("date", -1))
    # Convert ObjectId to string for JSON serialization
    for resume in resumes:
        resume['_id'] = str(resume['_id'])
        resume['date'] = resume['date'].isoformat()
    return jsonify(resumes)

@app.route('/api/transcripts')
@login_required
def api_transcripts():
    user_id = session.get('user_id')
    transcripts = list(transcript_collection.find({'user_id': user_id}).sort("date", -1))
    # Convert ObjectId to string for JSON serialization
    for transcript in transcripts:
        transcript['_id'] = str(transcript['_id'])
        transcript['date'] = transcript['date'].isoformat()
    return jsonify(transcripts)

# Make authentication functions available to templates
@app.context_processor
def inject_auth_functions():
    return {
        'is_authenticated': is_authenticated
    }

if __name__ == "__main__":
    app.run(debug=True)