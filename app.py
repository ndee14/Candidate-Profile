from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import pyodbc
import os
import json
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
import logging
import google.generativeai as genai
from dotenv import load_dotenv
import pdfplumber
from PIL import Image
import pytesseract

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Configure Gemini AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_available = True
else:
    gemini_available = False
    print("⚠️ Gemini API key not found. Using rule-based generation.")

# Database Configuration
DB_CONFIG = {
    'server': 'NONTOSLAPTOP',  # Your server name from the screenshot
    'database': 'MindWorxProfiles',
    'username': '',  # Empty for Windows Authentication
    'password': '',  # Empty for Windows Authentication
    'driver': '{ODBC Driver 17 for SQL Server}'
}


class DatabaseManager:
    def __init__(self):
        self.connection_string = (
            f"DRIVER={DB_CONFIG['driver']};"
            f"SERVER={DB_CONFIG['server']};"
            f"DATABASE={DB_CONFIG['database']};"
            f"Trusted_Connection=yes;"  # Use Windows Authentication
        )

    def get_connection(self):
        """Get database connection using Windows Authentication"""
        try:
            return pyodbc.connect(self.connection_string)
        except pyodbc.Error as e:
            print(f"Database connection error: {e}")
            raise

    def save_candidate(self, candidate_data, file_paths, questionnaire_data, generated_profile):
        """Save candidate with all data to database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            candidate_id = str(uuid.uuid4())

            cursor.execute('''
                INSERT INTO candidate_profiles 
                (candidate_id, full_name, email, phone, location, current_role, professional_summary,
                 cv_file_path, transcript_file_path, qualifications_file_path, picture_file_path,
                 questionnaire_answers, generated_profile)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                candidate_id,
                candidate_data.get('full_name', ''),
                candidate_data.get('email', ''),
                candidate_data.get('phone', ''),
                candidate_data.get('location', ''),
                candidate_data.get('current_role', ''),
                candidate_data.get('professional_summary', ''),
                file_paths.get('cv', ''),
                file_paths.get('transcript', ''),
                file_paths.get('qualifications', ''),
                file_paths.get('picture', ''),
                json.dumps(questionnaire_data),
                json.dumps(generated_profile)
            ))

            conn.commit()
            return candidate_id

        except Exception as e:
            print(f"Error saving candidate: {e}")
            raise
        finally:
            conn.close()

    def get_candidate(self, candidate_id):
        """Get candidate data by ID"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT full_name, email, phone, location, current_role, professional_summary,
                       cv_file_path, transcript_file_path, qualifications_file_path, picture_file_path,
                       questionnaire_answers, generated_profile
                FROM candidate_profiles 
                WHERE candidate_id = ?
            ''', (candidate_id,))

            row = cursor.fetchone()
            if row:
                return {
                    'personal_info': {
                        'name': row[0],
                        'email': row[1],
                        'phone': row[2],
                        'location': row[3],
                        'title': row[4],
                        'summary': row[5]
                    },
                    'file_paths': {
                        'cv': row[6],
                        'transcript': row[7],
                        'qualifications': row[8],
                        'picture': row[9]
                    },
                    'questionnaire_answers': json.loads(row[10]) if row[10] else {},
                    'generated_profile': json.loads(row[11]) if row[11] else {}
                }
            return None

        except Exception as e:
            print(f"Error retrieving candidate: {e}")
            return None
        finally:
            conn.close()


class ProfileGenerator:
    def __init__(self):
        if gemini_available:
            try:
                self.model = genai.GenerativeModel('gemini-pro')
            except Exception as e:
                print(f"Error initializing Gemini: {e}")
                self.model = None
        else:
            self.model = None

    def extract_text_from_pdf(self, file_path):
        """Extract text from PDF files"""
        if not file_path or not os.path.exists(file_path):
            return ""

        try:
            text = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
            return text
        except Exception as e:
            print(f"PDF extraction error: {e}")
            return ""

    def extract_text_from_image(self, file_path):
        """Extract text from images using OCR"""
        if not file_path or not os.path.exists(file_path):
            return ""

        try:
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image)
            return text
        except Exception as e:
            print(f"Image OCR error: {e}")
            return ""

    def generate_with_gemini(self, extracted_texts, questionnaire_data):
        """Generate profile using Gemini AI"""
        if not self.model:
            return self.generate_fallback(questionnaire_data)

        prompt = f"""
        Create a professional profile in JSON format using this information:

        EXTRACTED DOCUMENT CONTENT:
        CV: {extracted_texts.get('cv', '')[:3000]}
        Transcripts: {extracted_texts.get('transcript', '')[:2000]}
        Qualifications: {extracted_texts.get('qualifications', '')[:2000]}

        QUESTIONNAIRE RESPONSES:
        {json.dumps(questionnaire_data, indent=2)}

        Return ONLY valid JSON in this exact structure:
        {{
            "personal_info": {{
                "name": "Full Name",
                "title": "Job Title", 
                "email": "email@example.com",
                "phone": "Phone Number",
                "location": "City, Country",
                "summary": "Professional summary here"
            }},
            "skills": {{
                "technical": ["Skill1", "Skill2", "Skill3"],
                "soft": ["Skill1", "Skill2", "Skill3"]
            }},
            "experience": [
                {{
                    "position": "Job Title",
                    "company": "Company Name", 
                    "period": "2020 - Present",
                    "description": "Job description"
                }}
            ],
            "education": [
                {{
                    "degree": "Degree Name",
                    "institution": "Institution Name",
                    "year": "2020",
                    "description": "Additional details"
                }}
            ],
            "projects": [
                {{
                    "name": "Project Name",
                    "description": "Project description",
                    "technologies": ["Tech1", "Tech2", "Tech3"]
                }}
            ]
        }}
        """

        try:
            response = self.model.generate_content(prompt)
            # Extract JSON from response
            response_text = response.text
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            json_str = response_text[start_idx:end_idx]

            return json.loads(json_str)
        except Exception as e:
            print(f"Gemini generation failed: {e}")
            return self.generate_fallback(questionnaire_data)

    def generate_fallback(self, questionnaire_data):
        """Fallback profile generation"""
        name = questionnaire_data.get('full_name', 'Professional Candidate')

        return {
            "personal_info": {
                "name": name,
                "title": questionnaire_data.get('current_role', 'Professional'),
                "email": questionnaire_data.get('email', ''),
                "phone": questionnaire_data.get('phone', ''),
                "location": questionnaire_data.get('location', ''),
                "summary": questionnaire_data.get('professional_summary', 'Experienced professional.')
            },
            "skills": {
                "technical": [s.strip() for s in questionnaire_data.get('technical_skills', '').split(',') if
                              s.strip()],
                "soft": [s.strip() for s in questionnaire_data.get('soft_skills', '').split(',') if s.strip()]
            },
            "experience": [
                {
                    "position": questionnaire_data.get('current_role', 'Professional'),
                    "company": "Previous Company",
                    "period": "2020 - Present",
                    "description": "Responsible for various professional duties."
                }
            ],
            "education": [
                {
                    "degree": "Bachelor's Degree",
                    "institution": "University",
                    "year": "2020",
                    "description": "Relevant educational background"
                }
            ],
            "projects": [
                {
                    "name": "Professional Project",
                    "description": "Significant project demonstrating skills and experience",
                    "technologies": ["Technology 1", "Technology 2"]
                }
            ]
        }


# Initialize components
db_manager = DatabaseManager()
profile_generator = ProfileGenerator()


def allowed_file(filename):
    """Check if file extension is allowed"""
    allowed_extensions = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'}
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in allowed_extensions


def save_uploaded_file(file, file_type):
    """Save uploaded file and return path"""
    if file and allowed_file(file.filename):
        filename = f"{file_type}_{secure_filename(file.filename)}"
        folder_path = app.config['UPLOAD_FOLDER']
        os.makedirs(folder_path, exist_ok=True)

        file_path = os.path.join(folder_path, filename)
        file.save(file_path)
        return file_path
    return None


@app.route('/')
def index():
    """Home page with upload form"""
    return render_template('index.html', gemini_available=gemini_available)


@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle file uploads and generate profile"""
    try:
        # Get form data
        candidate_data = {
            'full_name': request.form.get('full_name', ''),
            'email': request.form.get('email', ''),
            'phone': request.form.get('phone', ''),
            'location': request.form.get('location', ''),
            'current_role': request.form.get('current_role', ''),
            'professional_summary': request.form.get('professional_summary', '')
        }

        # Get questionnaire data
        questionnaire_data = {
            'full_name': candidate_data['full_name'],
            'email': candidate_data['email'],
            'phone': candidate_data['phone'],
            'location': candidate_data['location'],
            'current_role': candidate_data['current_role'],
            'professional_summary': candidate_data['professional_summary'],
            'technical_skills': request.form.get('technical_skills', ''),
            'soft_skills': request.form.get('soft_skills', ''),
            'years_experience': request.form.get('years_experience', ''),
            'projects_description': request.form.get('projects', '')
        }

        # Save uploaded files
        file_paths = {}
        extracted_texts = {}

        # CV file
        if 'cv' in request.files:
            cv_file = request.files['cv']
            cv_path = save_uploaded_file(cv_file, 'cv')
            if cv_path:
                file_paths['cv'] = cv_path
                extracted_texts['cv'] = profile_generator.extract_text_from_pdf(cv_path)

        # Transcript file
        if 'transcript' in request.files:
            transcript_file = request.files['transcript']
            transcript_path = save_uploaded_file(transcript_file, 'transcript')
            if transcript_path:
                file_paths['transcript'] = transcript_path
                extracted_texts['transcript'] = profile_generator.extract_text_from_pdf(transcript_path)

        # Additional qualifications file
        if 'qualifications' in request.files:
            qual_file = request.files['qualifications']
            qual_path = save_uploaded_file(qual_file, 'qualifications')
            if qual_path:
                file_paths['qualifications'] = qual_path
                extracted_texts['qualifications'] = profile_generator.extract_text_from_pdf(qual_path)

        # Picture file
        if 'picture' in request.files:
            picture_file = request.files['picture']
            picture_path = save_uploaded_file(picture_file, 'picture')
            if picture_path:
                file_paths['picture'] = picture_path

        # Generate profile
        generated_profile = profile_generator.generate_with_gemini(extracted_texts, questionnaire_data)

        # Save to database
        candidate_id = db_manager.save_candidate(
            candidate_data,
            file_paths,
            questionnaire_data,
            generated_profile
        )

        session['candidate_id'] = candidate_id
        return redirect(url_for('view_profile', candidate_id=candidate_id))

    except Exception as e:
        logging.error(f"Error processing upload: {e}")
        return render_template('error.html', error=str(e)), 500


@app.route('/profile/<candidate_id>')
def view_profile(candidate_id):
    """Display generated profile"""
    try:
        candidate_data = db_manager.get_candidate(candidate_id)
        if not candidate_data:
            return "Profile not found", 404

        # Use generated profile for display
        profile_data = candidate_data['generated_profile']

        # Get photo URL
        photo_url = url_for('static', filename='default-avatar.png')
        if candidate_data['file_paths'].get('picture'):
            photo_filename = os.path.basename(candidate_data['file_paths']['picture'])
            photo_url = f"/uploads/{photo_filename}"

        return render_template(
            'profile.html',
            profile=profile_data,
            photo_url=photo_url,
            now=datetime.now()
        )

    except Exception as e:
        logging.error(f"Error displaying profile: {e}")
        return render_template('error.html', error=str(e)), 500


@app.route('/uploads/<filename>')
def serve_uploaded_file(filename):
    """Serve uploaded files"""
    return redirect(url_for('static', filename=os.path.join('uploads', filename)))


# Create upload directory
def init_upload_dirs():
    """Initialize upload directories"""
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('static/uploads', exist_ok=True)


if __name__ == '__main__':
    init_upload_dirs()
    print("🚀 MindWorx Profile Generator Starting...")
    print(f"🤖 Gemini AI: {'Enabled' if gemini_available else 'Disabled'}")
    app.run(debug=True, host='0.0.0.0', port=5000)