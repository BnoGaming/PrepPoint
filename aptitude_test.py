# aptitude_test.py
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import random
from auth import login_required
import json

# Create Blueprint for aptitude test routes
aptitude_bp = Blueprint('aptitude', __name__)

# MongoDB connection
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['interview_app']
aptitude_questions = db['apti_question']
aptitude_results = db['aptitude_results']
active_tests = db['active_tests']  # New collection to store active tests

@aptitude_bp.route('/aptitude-test', methods=['GET'])
@login_required
def aptitude_test():
    """Display aptitude test page with questions"""
    user_id = session.get('user_id')
    test_id = session.get('active_test_id')
    test_started = test_id is not None
    
    # Default values
    questions = []
    user_answers = {}
    current_question = 1
    progress = 0
    time_remaining = "30:00"
    
    if test_started:
        # Fetch test data from database instead of session
        active_test = active_tests.find_one({'_id': ObjectId(test_id), 'user_id': user_id})
        
        if active_test:
            questions = active_test.get('questions', [])
            user_answers = active_test.get('user_answers', {})
            current_question = session.get('current_question', 1)
            
            # Calculate progress
            progress = (current_question / len(questions)) * 100 if questions else 0
            
            # Calculate time remaining
            start_time = active_test.get('start_time')
            if start_time:
                elapsed_seconds = (datetime.now() - start_time).total_seconds()
                remaining_seconds = max(0, (30 * 60) - elapsed_seconds)  # 30 minutes in seconds
                minutes = int(remaining_seconds // 60)
                seconds = int(remaining_seconds % 60)
                time_remaining = f"{minutes:02d}:{seconds:02d}"
        else:
            # If test not found, clear session
            if 'active_test_id' in session:
                del session['active_test_id']
            if 'current_question' in session:
                del session['current_question']
            test_started = False
    
    return render_template(
        'aptitude_test.html', 
        test_started=test_started,
        questions=questions,
        user_answers=user_answers,
        current_question=current_question,
        progress=progress,
        time_remaining=time_remaining
    )

@aptitude_bp.route('/aptitude-test/start', methods=['POST'])
@login_required
def start_test():
    """Initialize the aptitude test"""
    user_id = session.get('user_id')
    
    # Clear any existing test session
    if 'active_test_id' in session:
        # Delete the previous test from database
        old_test_id = session['active_test_id']
        active_tests.delete_one({'_id': ObjectId(old_test_id), 'user_id': user_id})
        del session['active_test_id']
    
    if 'current_question' in session:
        del session['current_question']
    
    # Get questions by difficulty
    easy_questions = list(aptitude_questions.find({"difficulty": "easy"}).limit(20))
    medium_questions = list(aptitude_questions.find({"difficulty": "medium"}).limit(15))
    hard_questions = list(aptitude_questions.find({"difficulty": "hard"}).limit(10))
    
    # Randomly select questions based on difficulty distribution
    selected_easy = random.sample(easy_questions, min(10, len(easy_questions)))
    selected_medium = random.sample(medium_questions, min(6, len(medium_questions)))
    selected_hard = random.sample(hard_questions, min(4, len(hard_questions)))
    
    # Combine all selected questions
    selected_questions = selected_easy + selected_medium + selected_hard
    
    # Shuffle questions to mix difficulties
    random.shuffle(selected_questions)
    
    # Prepare question data
    test_questions = []
    for q in selected_questions:
        test_questions.append({
            'id': str(q['_id']),
            'question': q['questions'],
            'options': {
                'A': q.get('A', ''),
                'B': q.get('B', ''),
                'C': q.get('C', ''),
                'D': q.get('D', '')
            },
            'difficulty': q['difficulty'],
            'correct_answer': q['answer'].strip()
        })
    
    # Store test data in database instead of session
    test_data = {
        'user_id': user_id,
        'start_time': datetime.now(),
        'questions': test_questions,
        'user_answers': {},
        'created_at': datetime.now()
    }
    
    # Insert into database and get the ID
    test_id = active_tests.insert_one(test_data).inserted_id
    
    # Store only the test ID in session
    session['active_test_id'] = str(test_id)
    session['current_question'] = 1
    
    return redirect(url_for('aptitude.aptitude_test'))

@aptitude_bp.route('/aptitude-test/submit-answer', methods=['POST'])
@login_required
def submit_answer():
    """Handle individual answer submissions during the test"""
    user_id = session.get('user_id')
    test_id = session.get('active_test_id')
    
    if not test_id:
        return jsonify({'status': 'error', 'message': 'No active test found'}), 400
    
    data = request.json
    question_id = data.get('question_id')
    answer = data.get('answer')
    
    # Validate inputs
    if not question_id or not answer:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400
    
    # Update the answer in the database
    active_tests.update_one(
        {'_id': ObjectId(test_id), 'user_id': user_id},
        {'$set': {f'user_answers.{question_id}': answer}}
    )
    
    return jsonify({'status': 'success'})

@aptitude_bp.route('/aptitude-test/navigate', methods=['POST'])
@login_required
def navigate():
    """Handle navigation between questions"""
    current = session.get('current_question', 1)
    direction = int(request.form.get('direction', 0))
    
    user_id = session.get('user_id')
    test_id = session.get('active_test_id')
    
    if not test_id:
        return redirect(url_for('aptitude.aptitude_test'))
    
    # Get test data to determine total questions
    test_data = active_tests.find_one({'_id': ObjectId(test_id), 'user_id': user_id})
    if not test_data:
        return redirect(url_for('aptitude.aptitude_test'))
    
    total_questions = len(test_data.get('questions', []))
    
    # Calculate new question number
    new_question = current + direction
    if new_question < 1:
        new_question = 1
    if new_question > total_questions:
        new_question = total_questions
    
    # Save current question
    session['current_question'] = new_question
    
    return redirect(url_for('aptitude.aptitude_test'))

@aptitude_bp.route('/aptitude-test/submit', methods=['POST'])
@login_required
def submit_test():
    """Handle final test submission and calculate results"""
    user_id = session.get('user_id')
    test_id = session.get('active_test_id')
    
    if not test_id:
        flash('No active test found', 'danger')
        return redirect(url_for('aptitude.aptitude_test'))
    
    # Get test data from database
    test_data = active_tests.find_one({'_id': ObjectId(test_id), 'user_id': user_id})
    
    if not test_data:
        flash('Test session expired or not found', 'danger')
        return redirect(url_for('aptitude.aptitude_test'))
    
    questions = test_data.get('questions', [])
    user_answers = test_data.get('user_answers', {})
    start_time = test_data.get('start_time')
    
    # Calculate score and statistics
    total_questions = len(questions)
    answered_questions = len(user_answers)
    correct_answers = 0
    
    # Track performance by difficulty
    difficulty_stats = {
        'easy': {'total': 0, 'correct': 0},
        'medium': {'total': 0, 'correct': 0},
        'hard': {'total': 0, 'correct': 0}
    }
    
    # Calculate score
    question_results = []
    for q in questions:
        question_id = q['id']
        difficulty = q['difficulty']
        user_answer = user_answers.get(question_id, '')
        correct_answer = q['correct_answer']
        is_correct = user_answer == correct_answer
        
        # Update statistics
        difficulty_stats[difficulty]['total'] += 1
        if is_correct:
            correct_answers += 1
            difficulty_stats[difficulty]['correct'] += 1
        
        # Store individual question result
        question_results.append({
            'question_id': question_id,
            'question': q['question'],
            'difficulty': difficulty,
            'user_answer': user_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct
        })
    
    # Calculate percentages
    score_percentage = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
    completion_percentage = (answered_questions / total_questions) * 100 if total_questions > 0 else 0
    
    # Calculate performance by difficulty
    for difficulty in difficulty_stats:
        if difficulty_stats[difficulty]['total'] > 0:
            difficulty_stats[difficulty]['percentage'] = (difficulty_stats[difficulty]['correct'] / difficulty_stats[difficulty]['total']) * 100
        else:
            difficulty_stats[difficulty]['percentage'] = 0
    
    # Calculate time taken
    try:
        end_datetime = datetime.now()
        time_taken_seconds = (end_datetime - start_time).total_seconds()
        time_taken_minutes = time_taken_seconds / 60
        
        # Format time taken string
        minutes = int(time_taken_minutes)
        seconds = int((time_taken_minutes - minutes) * 60)
        time_taken_str = f"{minutes:02d}:{seconds:02d}"
    except:
        time_taken_minutes = 0
        time_taken_str = "00:00"
    
    # Create result document for database
    result_doc = {
        'user_id': user_id,
        'date': datetime.now(),
        'total_questions': total_questions,
        'answered_questions': answered_questions,
        'correct_answers': correct_answers,
        'score_percentage': score_percentage,
        'completion_percentage': completion_percentage,
        'difficulty_stats': difficulty_stats,
        'time_taken_minutes': time_taken_minutes,
        'time_taken_str': time_taken_str,
        'question_results': question_results
    }
    
    # Store result in MongoDB
    result_id = aptitude_results.insert_one(result_doc).inserted_id
    
    # Clean up - remove the active test
    active_tests.delete_one({'_id': ObjectId(test_id), 'user_id': user_id})
    
    # Clear test data from session
    if 'active_test_id' in session:
        del session['active_test_id']
    if 'current_question' in session:
        del session['current_question']
    
    return redirect(url_for('aptitude.test_results', result_id=result_id))

@aptitude_bp.route('/aptitude-test/results/<result_id>')
@login_required
def test_results(result_id):
    """Display test results"""
    # Find result in database
    user_id = session.get('user_id')
    try:
        result = aptitude_results.find_one({
            '_id': ObjectId(result_id),
            'user_id': user_id
        })
    except:
        result = None
    
    if not result:
        flash('Result not found or you do not have permission to view it', 'danger')
        return redirect(url_for('dashboard'))
    
    # Calculate counts for tab display
    correct_count = 0
    incorrect_count = 0
    unanswered_count = 0
    
    for qresult in result['question_results']:
        if qresult.get('is_correct'):
            correct_count += 1
        elif qresult.get('user_answer'):
            incorrect_count += 1
        else:
            unanswered_count += 1
    
    return render_template('aptitude_results.html', 
                          result=result, 
                          correct_count=correct_count,
                          incorrect_count=incorrect_count,
                          unanswered_count=unanswered_count)

@aptitude_bp.route('/aptitude-history')
@login_required
def aptitude_history():
    """Display user's aptitude test history"""
    user_id = session.get('user_id')
    
    # Get all user results, sorted by date
    results = list(aptitude_results.find({'user_id': user_id}).sort('date', -1))
    
    # Convert ObjectId to string for each result
    for result in results:
        result['_id'] = str(result['_id'])
        result['date_str'] = result['date'].strftime('%Y-%m-%d %H:%M')
    
    return render_template('aptitude_history.html', results=results)