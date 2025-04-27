# auth.py
import os
from flask import Blueprint, request, redirect, url_for, flash, render_template, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from pymongo import MongoClient
from datetime import datetime
from bson.objectid import ObjectId

# Create Blueprint for authentication routes
auth_bp = Blueprint('auth', __name__)

# MongoDB connection
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['interview_app']
users_collection = db['users']

# Create unique index on email field if it doesn't exist
if 'email_1' not in users_collection.index_information():
    users_collection.create_index('email', unique=True)

# Decorator to require login for protected routes
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Basic validation
        if not name or not email or not password:
            flash('All fields are required', 'danger')
            return render_template('register.html')
            
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('register.html')
        
        # Check if user already exists
        existing_user = users_collection.find_one({'email': email})
        if existing_user:
            flash('Email already registered', 'danger')
            return render_template('register.html')
        
        # Create new user
        new_user = {
            'name': name,
            'email': email,
            'password': generate_password_hash(password),
            'created_at': datetime.now(),
            'profile_completed': False
        }
        
        try:
            result = users_collection.insert_one(new_user)
            
            # Log the user in
            session['user_id'] = str(result.inserted_id)
            session['user_name'] = name
            session['user_email'] = email
            
            flash('Registration successful!', 'success')
            return redirect(url_for('auth.profile'))
        except Exception as e:
            flash(f'An error occurred: {e}', 'danger')
    
    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Find user by email
        user = users_collection.find_one({'email': email})
        
        # Check if user exists and password is correct
        if user and check_password_hash(user['password'], password):
            # Store user info in session
            session['user_id'] = str(user['_id'])
            session['user_name'] = user['name']
            session['user_email'] = email
            
            # Redirect to next page if provided, otherwise to dashboard
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    # Clear session data
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('home'))

# # Function to get user by ID (for use in other files)
# def get_user_by_id(user_id):
#     if not user_id:
#         return None
#     try:
#         return users_collection.find_one({'_id': mongo_client.ObjectId(user_id)})
#     except:
#         return None

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session.get('user_id')
    user = users_collection.find_one({'_id': ObjectId(user_id)})
    
    if request.method == 'POST':
        # Update user profile
        updates = {
            'name': request.form.get('name'),
            'email': request.form.get('email'),
            'bio': request.form.get('bio', ''),
            'job_title': request.form.get('job_title', ''),
            'industry': request.form.get('industry', ''),
            'profile_completed': True,
            'updated_at': datetime.now()
        }
        
        # Update password if provided
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_new_password = request.form.get('confirm_new_password')
        
        if current_password and new_password:
            # Verify current password
            if not check_password_hash(user['password'], current_password):
                flash('Current password is incorrect', 'danger')
                return render_template('profile.html', user=user)
                
            if new_password != confirm_new_password:
                flash('New passwords do not match', 'danger')
                return render_template('profile.html', user=user)
                
            updates['password'] = generate_password_hash(new_password)
        
        try:
            users_collection.update_one({'_id': ObjectId(user_id)}, {'$set': updates})
            
            # Update session data
            session['user_name'] = updates['name']
            session['user_email'] = updates['email']
            
            flash('Profile updated successfully', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'An error occurred: {e}', 'danger')
    
    return render_template('profile.html', user=user)

# Function to get user by ID (for use in other files)
def get_user_by_id(user_id):
    if not user_id:
        return None
    try:
        return users_collection.find_one({'_id': ObjectId(user_id)})
    except:
        return None

# Function to check if user is authenticated (for use in templates)
def is_authenticated():
    return 'user_id' in session