# resume_analyzer.py
import os
import json
import PyPDF2
import requests
from datetime import datetime
from dotenv import load_dotenv

# Predefined API keys
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
api_key = GEMINI_API_KEY

def extract_words_from_pdf(pdf_path):
    """Extract text from a PDF file."""
    words = []
    try:
        with open(pdf_path, 'rb') as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    words.extend(text.split())
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    return " ".join(words)

def send_to_gemini_api(text):
    """Send extracted text to Gemini API for analysis."""
    api_key = GEMINI_API_KEY
    api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    headers = {"Content-Type": "application/json"}
    
    data = {
        "contents": [{
            "parts": [{"text": f"""The following is the text extracted from a candidate's resume:\n{text}\n\n
            Please analyze this resume and provide a structured assessment in the following JSON format:
            {{
                "strengths": [
                    "strength 1",
                    "strength 2",
                    "..."
                ],
                "weaknesses": [
                    "weakness 1 (excluding formatting issues)",
                    "weakness 2 (excluding formatting issues)",
                    "..."
                ],
                "areas_for_improvement": [
                    "improvement 1 (excluding formatting issues)",
                    "improvement 2 (excluding formatting issues)",
                    "..."
                ],
                "rating": "X/10",
                "summary": "A brief overall assessment of the resume."
            }}
            
            Important notes:
            - Do not mention anything about formatting issues since the formatting was changed during extraction
            - Focus on content quality and professional presentation
            - Provide actionable feedback in each category
            - For rating, use a scale of 1-10 where 10 is excellent
            - Ensure the response is in proper JSON format
            """}]
        }]
    }

    try:
        response = requests.post(f"{api_url}?key={api_key}", headers=headers, json=data)
        response.raise_for_status()
        response_text = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "No content found")
        
        # Try to parse as JSON (the model doesn't always return perfect JSON)
        try:
            # First, find JSON content if it's embedded in text
            import re
            json_match = re.search(r'({[\s\S]*})', response_text)
            if json_match:
                json_str = json_match.group(1)
                return json.loads(json_str)
            else:
                return json.loads(response_text)
        except json.JSONDecodeError:
            # If JSON parsing fails, return as text
            return {"error": "Could not parse response as JSON", "raw_text": response_text}
    except requests.exceptions.RequestException as e:
        print(f"Error sending data to Gemini API: {e}")
        return None