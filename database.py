# database.py
import pyodbc
import json
import uuid
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()


class Database:
    def __init__(self):
        self.server = os.getenv('DB_SERVER')
        self.database = os.getenv('DB_NAME')
        self.driver = os.getenv('DB_DRIVER')
        self.connection_string = f"""
            DRIVER={{{self.driver}}};
            SERVER={self.server};
            DATABASE={self.database};
            Trusted_Connection=yes;
        """

    def get_connection(self):
        try:
            conn = pyodbc.connect(self.connection_string)
            return conn
        except Exception as e:
            print(f"Database connection error: {e}")
            return None

    def initialize_database(self):
        """Create database and tables if they don't exist"""
        try:
            # First, try to create database if it doesn't exist
            master_conn = pyodbc.connect(
                f"DRIVER={{{self.driver}}};SERVER={self.server};Trusted_Connection=yes;"
            )
            master_conn.autocommit = True
            master_cursor = master_conn.cursor()

            # Create database if it doesn't exist
            master_cursor.execute(f"""
                IF NOT EXISTS(SELECT name FROM sys.databases WHERE name = '{self.database}')
                CREATE DATABASE [{self.database}]
            """)
            master_conn.close()

            # Now create tables
            conn = self.get_connection()
            cursor = conn.cursor()

            # Create Candidates table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='candidates' AND xtype='U')
                CREATE TABLE candidates (
                    candidate_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
                    name NVARCHAR(255),
                    email NVARCHAR(255),
                    phone NVARCHAR(50),
                    location NVARCHAR(255),
                    title NVARCHAR(255),
                    summary TEXT,
                    created_date DATETIME2 DEFAULT GETDATE(),
                    updated_date DATETIME2 DEFAULT GETDATE()
                )
            """)

            # Create Documents table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='documents' AND xtype='U')
                CREATE TABLE documents (
                    document_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
                    candidate_id UNIQUEIDENTIFIER FOREIGN KEY REFERENCES candidates(candidate_id),
                    document_type NVARCHAR(50), -- 'cv', 'academic_transcript', 'professional_photo', 'qualification'
                    file_name NVARCHAR(255),
                    file_path NVARCHAR(500),
                    file_size BIGINT,
                    uploaded_date DATETIME2 DEFAULT GETDATE()
                )
            """)

            # Create Profiles table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='profiles' AND xtype='U')
                CREATE TABLE profiles (
                    profile_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
                    candidate_id UNIQUEIDENTIFIER FOREIGN KEY REFERENCES candidates(candidate_id),
                    personal_info NVARCHAR(MAX),
                    education NVARCHAR(MAX),
                    experience NVARCHAR(MAX),
                    skills NVARCHAR(MAX),
                    projects NVARCHAR(MAX),
                    certifications NVARCHAR(MAX),
                    extraction_method NVARCHAR(50),
                    generated_date DATETIME2 DEFAULT GETDATE()
                )
            """)

            # Create Questionnaire table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='questionnaire_answers' AND xtype='U')
                CREATE TABLE questionnaire_answers (
                    answer_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
                    candidate_id UNIQUEIDENTIFIER FOREIGN KEY REFERENCES candidates(candidate_id),
                    question_text NVARCHAR(500),
                    answer_text NVARCHAR(MAX),
                    answered_date DATETIME2 DEFAULT GETDATE()
                )
            """)

            conn.commit()
            conn.close()
            print("✅ Database initialized successfully")
            return True

        except Exception as e:
            print(f"❌ Database initialization error: {e}")
            return False

    def save_candidate(self, candidate_data):
        """Save candidate personal information"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO candidates (candidate_id, name, email, phone, location, title, summary)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                           candidate_data['candidate_id'],
                           candidate_data.get('name', ''),
                           candidate_data.get('email', ''),
                           candidate_data.get('phone', ''),
                           candidate_data.get('location', ''),
                           candidate_data.get('title', ''),
                           candidate_data.get('summary', ''))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Error saving candidate: {e}")
            return False

    def save_document(self, document_data):
        """Save document information"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO documents (candidate_id, document_type, file_name, file_path, file_size)
                VALUES (?, ?, ?, ?, ?)
            """,
                           document_data['candidate_id'],
                           document_data['document_type'],
                           document_data['file_name'],
                           document_data['file_path'],
                           document_data['file_size'])

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Error saving document: {e}")
            return False

    def save_profile(self, profile_data):
        """Save generated profile"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO profiles (candidate_id, personal_info, education, experience, skills, projects, certifications, extraction_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                           profile_data['candidate_id'],
                           json.dumps(profile_data.get('personal_info', {})),
                           json.dumps(profile_data.get('education', [])),
                           json.dumps(profile_data.get('experience', [])),
                           json.dumps(profile_data.get('skills', {})),
                           json.dumps(profile_data.get('projects', [])),
                           json.dumps(profile_data.get('certifications', [])),
                           profile_data.get('extraction_method', 'unknown'))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Error saving profile: {e}")
            return False

    def save_questionnaire_answer(self, answer_data):
        """Save questionnaire answers"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO questionnaire_answers (candidate_id, question_text, answer_text)
                VALUES (?, ?, ?)
            """,
                           answer_data['candidate_id'],
                           answer_data['question_text'],
                           answer_data['answer_text'])

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Error saving questionnaire answer: {e}")
            return False

    def get_candidate_profile(self, candidate_id):
        """Retrieve candidate profile by ID"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT p.personal_info, p.education, p.experience, p.skills, p.projects, p.certifications
                FROM profiles p
                WHERE p.candidate_id = ?
            """, candidate_id)

            row = cursor.fetchone()
            conn.close()

            if row:
                return {
                    'personal_info': json.loads(row[0]) if row[0] else {},
                    'education': json.loads(row[1]) if row[1] else [],
                    'experience': json.loads(row[2]) if row[2] else [],
                    'skills': json.loads(row[3]) if row[3] else {},
                    'projects': json.loads(row[4]) if row[4] else [],
                    'certifications': json.loads(row[5]) if row[5] else []
                }
            return None
        except Exception as e:
            print(f"❌ Error retrieving profile: {e}")
            return None