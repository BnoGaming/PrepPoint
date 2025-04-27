# admin.py
from flask import Blueprint, request, redirect, url_for, flash, render_template, session
from werkzeug.security import check_password_hash
from functools import wraps
from pymongo import MongoClient
from datetime import datetime

# Create Blueprint for admin routes
admin_bp = Blueprint('admin', __name__)

# MongoDB connection
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['interview_app']
users_collection = db['users']
admin_collection = db['admins']
aptitude_questions = db['apti_question']

# Decorator to require admin access
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or 'is_admin' not in session or not session['is_admin']:
            flash('Admin access required', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Find admin by email
        admin = admin_collection.find_one({'email': email})
        
        # Check if admin exists and password is correct
        if admin and check_password_hash(admin['password'], password):
            # Store admin info in session
            session['user_id'] = str(admin['_id'])
            session['user_name'] = admin['name']
            session['user_email'] = email
            session['is_admin'] = True
            
            flash('Admin login successful', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid admin credentials', 'danger')
    
    return render_template('admin_login.html')

@admin_bp.route('/logout')
def admin_logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('admin.admin_login'))

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    # Get system statistics
    user_count = users_collection.count_documents({})
    
    # Get other collection counts
    resume_count = db.resume_analysis.count_documents({})
    interview_count = db.interview_transcripts.count_documents({})
    dsa_count = db.dsa_submissions.count_documents({})
    aptitude_count = db.aptitude_results.count_documents({})
    
    # Get latest user registrations
    latest_users = list(users_collection.find().sort('created_at', -1).limit(5))
    
    # Calculate storage usage by collection
    storage_stats = {
        'users': db.command('collStats', 'users')['size'] / (1024 * 1024),  # MB
        'resumes': db.command('collStats', 'resume_analysis')['size'] / (1024 * 1024),
        'interviews': db.command('collStats', 'interview_transcripts')['size'] / (1024 * 1024),
        'dsa': db.command('collStats', 'dsa_submissions')['size'] / (1024 * 1024),
        'aptitude': db.command('collStats', 'aptitude_results')['size'] / (1024 * 1024),
    }
    
    # Get monthly statistics for growth chart
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    monthly_stats = []
    for i in range(6):  # Last 6 months
        month = (current_month - i) % 12
        year = current_year if month <= current_month else current_year - 1
        if month == 0:
            month = 12
            year -= 1
            
        # Start and end of month
        start_date = datetime(year, month, 1)
        end_month = month + 1 if month < 12 else 1
        end_year = year if month < 12 else year + 1
        end_date = datetime(end_year, end_month, 1)
        
        # Count users registered in this month
        user_count_month = users_collection.count_documents({
            'created_at': {'$gte': start_date, '$lt': end_date}
        })
        
        # Count interviews conducted in this month
        interview_count_month = db.interview_transcripts.count_documents({
            'date': {'$gte': start_date, '$lt': end_date}
        })
        
        monthly_stats.append({
            'month': start_date.strftime('%b %Y'),
            'users': user_count_month,
            'interviews': interview_count_month
        })
    
    monthly_stats.reverse()  # To show oldest to newest
    
    return render_template('admin_dashboard.html', 
                          user_count=user_count,
                          resume_count=resume_count,
                          interview_count=interview_count,
                          dsa_count=dsa_count,
                          aptitude_count=aptitude_count,
                          latest_users=latest_users,
                          storage_stats=storage_stats,
                          monthly_stats=monthly_stats)

# User management routes
@admin_bp.route('/users')
@admin_required
def users():
    all_users = list(users_collection.find().sort('created_at', -1))
    
    # Add statistics to each user
    for user in all_users:
        user['resume_count'] = db.resume_analysis.count_documents({'user_id': str(user['_id'])})
        user['interview_count'] = db.interview_transcripts.count_documents({'user_id': str(user['_id'])})
        user['dsa_count'] = db.dsa_submissions.count_documents({'user_id': str(user['_id'])})
        user['aptitude_count'] = db.aptitude_results.count_documents({'user_id': str(user['_id'])})
        
    return render_template('admin_users.html', users=all_users)

@admin_bp.route('/user/<user_id>')
@admin_required
def view_user(user_id):
    user = users_collection.find_one({'_id': mongo_client.ObjectId(user_id)})
    
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('admin.users'))
    
    # Get user statistics
    user_stats = {
        'resume_analyses': list(db.resume_analysis.find({'user_id': user_id}).sort('date', -1)),
        'interview_transcripts': list(db.interview_transcripts.find({'user_id': user_id}).sort('date', -1)),
        'dsa_submissions': list(db.dsa_submissions.find({'user_id': user_id}).sort('date', -1)),
        'aptitude_results': list(db.aptitude_results.find({'user_id': user_id}).sort('date', -1))
    }
    
    # Calculate storage usage for this user
    storage_usage = {
        'resumes': sum(len(str(doc)) for doc in user_stats['resume_analyses']) / 1024,  # KB
        'interviews': sum(len(str(doc)) for doc in user_stats['interview_transcripts']) / 1024,
        'dsa': sum(len(str(doc)) for doc in user_stats['dsa_submissions']) / 1024,
        'aptitude': sum(len(str(doc)) for doc in user_stats['aptitude_results']) / 1024
    }
    storage_usage['total'] = sum(storage_usage.values())
    
    return render_template('admin_user_detail.html', user=user, user_stats=user_stats, storage_usage=storage_usage)

# Database management routes
@admin_bp.route('/dsa-questions')
@admin_required
def dsa_questions():
    questions = list(db.dsa_questions.find())
    return render_template('admin_dsa_questions.html', questions=questions)

@admin_bp.route('/dsa-question/add', methods=['GET', 'POST'])
@admin_required
def add_dsa_question():
    if request.method == 'POST':
        new_question = {
            'question': request.form.get('question'),
            'problem': request.form.get('problem'),
            'difficulty': request.form.get('difficulty'),
            'solution': request.form.get('solution'),
            'tags': request.form.get('tags').split(','),
            'created_at': datetime.now()
        }
        
        db.dsa_questions.insert_one(new_question)
        flash('DSA question added successfully', 'success')
        return redirect(url_for('admin.dsa_questions'))
    
    return render_template('admin_add_dsa_question.html')

@admin_bp.route('/dsa-question/edit/<question_id>', methods=['GET', 'POST'])
@admin_required
def edit_dsa_question(question_id):
    question = db.dsa_questions.find_one({'_id': mongo_client.ObjectId(question_id)})
    
    if not question:
        flash('Question not found', 'danger')
        return redirect(url_for('admin.dsa_questions'))
    
    if request.method == 'POST':
        updated_question = {
            'question': request.form.get('question'),
            'problem': request.form.get('problem'),
            'difficulty': request.form.get('difficulty'),
            'solution': request.form.get('solution'),
            'tags': request.form.get('tags').split(','),
            'updated_at': datetime.now()
        }
        
        db.dsa_questions.update_one(
            {'_id': mongo_client.ObjectId(question_id)},
            {'$set': updated_question}
        )
        
        flash('DSA question updated successfully', 'success')
        return redirect(url_for('admin.dsa_questions'))
    
    return render_template('admin_edit_dsa_question.html', question=question)

@admin_bp.route('/aptitude-questions')
@admin_required
def aptitude_questions():
    questions = list(db.apti_question.find())
    return render_template('admin_aptitude_questions.html', questions=questions)

@admin_bp.route('/aptitude-question/add', methods=['GET', 'POST'])
@admin_required
def add_aptitude_question():
    if request.method == 'POST':
        new_question = {
            'question': request.form.get('question'),
            'options': [
                request.form.get('option1'),
                request.form.get('option2'),
                request.form.get('option3'),
                request.form.get('option4')
            ],
            'correct_answer': int(request.form.get('correct_answer')),
            'category': request.form.get('category'),
            'difficulty': request.form.get('difficulty'),
            'created_at': datetime.now()
        }
        
        db.apti_question.insert_one(new_question)
        flash('Aptitude question added successfully', 'success')
        return redirect(url_for('admin.aptitude_questions'))
    
    return render_template('admin_add_aptitude_question.html')

@admin_bp.route('/aptitude-question/edit/<question_id>', methods=['GET', 'POST'])
@admin_required
def edit_aptitude_question(question_id):
    question = db.apti_question.find_one({'_id': mongo_client.ObjectId(question_id)})
    
    if not question:
        flash('Question not found', 'danger')
        return redirect(url_for('admin.aptitude_questions'))
    
    if request.method == 'POST':
        updated_question = {
            'question': request.form.get('question'),
            'options': [
                request.form.get('option1'),
                request.form.get('option2'),
                request.form.get('option3'),
                request.form.get('option4')
            ],
            'correct_answer': int(request.form.get('correct_answer')),
            'category': request.form.get('category'),
            'difficulty': request.form.get('difficulty'),
            'updated_at': datetime.now()
        }
        
        db.apti_question.update_one(
            {'_id': mongo_client.ObjectId(question_id)},
            {'$set': updated_question}
        )
        
        flash('Aptitude question updated successfully', 'success')
        return redirect(url_for('admin.aptitude_questions'))
    
    return render_template('admin_edit_aptitude_question.html', question=question)

# Analytics routes
@admin_bp.route('/analytics')
@admin_required
def analytics():
    # Get system overview statistics
    stats = {
        'total_users': users_collection.count_documents({}),
        'active_users': users_collection.count_documents({'last_login': {'$gte': datetime.now().replace(day=1)}}),
        'total_resumes': db.resume_analysis.count_documents({}),
        'total_interviews': db.interview_transcripts.count_documents({}),
        'total_dsa': db.dsa_submissions.count_documents({}),
        'total_aptitude': db.aptitude_results.count_documents({})
    }
    
    # Get monthly growth data for the past 6 months
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    monthly_growth = []
    for i in range(6):  # Last 6 months
        month = (current_month - i) % 12
        year = current_year if month <= current_month else current_year - 1
        if month == 0:
            month = 12
            year -= 1
            
        # Start and end of month
        start_date = datetime(year, month, 1)
        end_month = month + 1 if month < 12 else 1
        end_year = year if month < 12 else year + 1
        end_date = datetime(end_year, end_month, 1)
        
        # Count activities in this month
        month_data = {
            'month': start_date.strftime('%b %Y'),
            'users': users_collection.count_documents({
                'created_at': {'$gte': start_date, '$lt': end_date}
            }),
            'resumes': db.resume_analysis.count_documents({
                'date': {'$gte': start_date, '$lt': end_date}
            }),
            'interviews': db.interview_transcripts.count_documents({
                'date': {'$gte': start_date, '$lt': end_date}
            }),
            'dsa': db.dsa_submissions.count_documents({
                'date': {'$gte': start_date, '$lt': end_date}
            }),
            'aptitude': db.aptitude_results.count_documents({
                'date': {'$gte': start_date, '$lt': end_date}
            })
        }
        
        monthly_growth.append(month_data)
    
    monthly_growth.reverse()  # To show oldest to newest
    
    # Get feature usage per user tier
    feature_usage = {
        'free_users': {
            'count': users_collection.count_documents({'tier': 'free'}),
            'resumes': db.resume_analysis.count_documents({'user_tier': 'free'}),
            'interviews': db.interview_transcripts.count_documents({'user_tier': 'free'}),
            'dsa': db.dsa_submissions.count_documents({'user_tier': 'free'}),
            'aptitude': db.aptitude_results.count_documents({'user_tier': 'free'})
        },
        'premium_users': {
            'count': users_collection.count_documents({'tier': 'premium'}),
            'resumes': db.resume_analysis.count_documents({'user_tier': 'premium'}),
            'interviews': db.interview_transcripts.count_documents({'user_tier': 'premium'}),
            'dsa': db.dsa_submissions.count_documents({'user_tier': 'premium'}),
            'aptitude': db.aptitude_results.count_documents({'user_tier': 'premium'})
        }
    }
    
    return render_template('admin_analytics.html', 
                          stats=stats, 
                          monthly_growth=monthly_growth,
                          feature_usage=feature_usage)

# System management routes
@admin_bp.route('/system')
@admin_required
def system():
    # Get database statistics
    db_stats = db.command("dbStats")
    
    # Format the statistics
    storage_stats = {
        'total_size': db_stats['dataSize'] / (1024 * 1024),  # MB
        'storage_size': db_stats['storageSize'] / (1024 * 1024),  # MB
        'index_size': db_stats['indexSize'] / (1024 * 1024),  # MB
        'collections': db_stats['collections'],
        'objects': db_stats['objects']
    }
    
    # Get collection sizes
    collection_sizes = []
    for collection in db.list_collection_names():
        collection_stats = db.command("collStats", collection)
        collection_sizes.append({
            'name': collection,
            'size': collection_stats['size'] / (1024 * 1024),  # MB
            'count': collection_stats['count']
        })
    
    # Sort by size (largest first)
    collection_sizes.sort(key=lambda x: x['size'], reverse=True)
    
    return render_template('admin_system.html', 
                          storage_stats=storage_stats,
                          collection_sizes=collection_sizes)

@admin_bp.route('/backup')
@admin_required
def backup():
    # Code to generate a database backup
    from datetime import datetime
    import subprocess
    import os
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(os.getcwd(), 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    
    backup_file = os.path.join(backup_dir, f'interview_app_{timestamp}.archive')
    
    # Run mongodump to create backup
    try:
        result = subprocess.run(
            ['mongodump', '--db', 'interview_app', '--archive=' + backup_file],
            check=True,
            capture_output=True
        )
        
        if result.returncode == 0:
            flash(f'Backup created successfully at {backup_file}', 'success')
        else:
            flash(f'Backup failed: {result.stderr.decode()}', 'danger')
    except Exception as e:
        flash(f'Backup failed: {str(e)}', 'danger')
    
    return redirect(url_for('admin.system'))

# Function to initialize admin user (called once during setup)
def init_admin_user():
    # Check if admin user exists
    admin_exists = admin_collection.find_one({'email': 'admin@example.com'})
    
    if not admin_exists:
        from werkzeug.security import generate_password_hash
        
        admin_user = {
            'name': 'Admin',
            'email': 'admin@example.com',
            'password': generate_password_hash('admin123'),  # Change this in production!
            'is_admin': True,
            'created_at': datetime.now()
        }
        
        admin_collection.insert_one(admin_user)
        print("Admin user created!")