# PrepPoint

[![Production-Ready](https://img.shields.io/badge/Production--Ready-Yes-green)](https://github.com/your-username/preppoint)
[![AI-Powered](https://img.shields.io/badge/AI-Powered-blue)](https://github.com/your-username/preppoint)
[![Flask-Backend](https://img.shields.io/badge/Backend-Flask-blue)](https://github.com/your-username/preppoint)
[![MongoDB-Database](https://img.shields.io/badge/Database-MongoDB-green)](https://github.com/your-username/preppoint)
[![License-MIT](https://img.shields.io/badge/License-MIT-yellow)](https://choosealicense.com/licenses/mit/)

---

**PrepPoint** is a production-ready, AI-powered interview preparation platform offering a complete, end to end, immersive experience for candidates. 
🧩 **Core Capabilities:**
- **Resume Analyzer:** Analyzes uploaded resumes and provides detailed feedback, highlighting strengths, weaknesses, and areas for improvement using AI.
- **DSA Practice Module:** Allows users to solve frequently asked data structures and algorithms questions with real-time AI-powered suggestions and scoring.
- **Aptitude Test Module:** Offers a variety of aptitude questions to help candidates prepare for the initial screening rounds of interviews.
- **AI-Driven Mock Interviews:** Simulates real-world interview environments using text-based and voice-based AI agents.
- **Speech & Video Analysis:** Leverages speech technologies (TTS & STT), facial recognition, and behavior tracking to deliver insightful feedback and post-interview analysis.
  
---

## ✨ Key Features

### 🎯 Interview Preparation Modules
- **DSA Test Module:** Practice DSA questions with AI suggestions, scoring, and time-tracking.
- **Resume Analyzer:** Instant resume feedback with AI-generated recommendations.
- **Text-Based AI Interviewer:** Dynamic technical interviews with real-time follow-ups.
- **Voice & Video Interview Module:** Live TTS & STT interview with Live user behaviour tracking and DSA technical rounds.
- **Behavioral and Technical Analysis:** Live video tracking, behavior feedback, and post-interview reports.

### 🔐 Authentication & Security
- Secure user login and session management.
- Admin-controlled system access.

### 🛠️ Admin Dashboard
- Manage users, test questions, results, interviews.
- Monitor system statistics and network usage.
- Add, edit, delete aptitude and technical content.

### 📈 Result Analysis
- In-depth performance tracking.
- Difficulty-based scoring and time analysis.

### 📱 Future Scope
- Mobile App (iOS & Android).
- Push notifications and personal AI coaches.
- Advanced computer vision analytics.
- Voice-only lightweight mock interviews.

---

## 🧰 Tech Stack

🔧 **Backend**

 - **Python + Flask:** Handles server logic, routing, and API integration.
 - **Pymongo:** Interface for database interactions with MongoDB.
 - **Werkzeug:** Secure password hashing and session management.

🎨 Frontend
 -**HTML, CSS, JavaScript:** Core technologies for building user interfaces.
 - **Bootstrap:** Provides responsive, mobile-friendly UI components.
 - **Jinja2:** Templating engine for rendering dynamic content in HTML.

🗄️ Database
 - **MongoDB:** NoSQL database for storing user data, test results, and interview logs.

🤖 AI & Machine Learning
 - **Gemini API & Groq API:** Used for text analysis and generating resume feedback.
 - **Whisper:** Speech-to-text model for processing voice interview responses.

🔊 Speech Processing
 - **Whisper:** Converts spoken responses into text for analysis.
 -**gTTS (Google Text-to-Speech):** Generates AI-spoken questions and feedback.

🧠 Facial Analysis
 - **OpenCV + Haar Cascades:** Detects facial expressions and hand gestures during interviews.
 - **Pillow + NumPy:** Used for image processing and manipulation.

---

## 🚀 Setup Instructions

1. Clone the repository:

    ```bash
    git clone https://github.com/your-username/preppoint.git
    cd preppoint
    ```

2. Create and activate a virtual environment (optional):

    ```bash
    python -m venv venv
    source venv/bin/activate  # Windows: venv\Scripts\activate
    ```

3. Install dependencies:

    ```bash
    pip install -r requirements.txt
    ```

4. Start the server:

    ```bash
    python interviewer.py
    ```

---

## 📂 Project Structure

```
preppoint/
|
|├─ admin.py
|├─ aptitude_test.py
|├─ auth.py
|├─ interviewer.py
|├─ resume_analyzer.py
|├─ speech_interview.py
|├─ static/
|   └─ css/
|├─ templates/
|   └─ *.html
|├─ README.md
└─ requirements.txt
```

---

## 🤝 Contribution Guidelines

Pull requests are welcome! For major changes, please open an issue first to discuss the proposed updates.

---

## 📜 License

Licensed under the [MIT License](https://choosealicense.com/licenses/mit/).

---

> PrepPoint: Redefining Interview Preparation with AI ✨

