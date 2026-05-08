import zlib
import json
import re
import bcrypt
import pandas as pd
import streamlit as st
import gspread
import streamlit_authenticator as stauth
import streamlit.components.v1 as components
import google.generativeai as genai
from datetime import datetime
from google.oauth2.service_account import Credentials
from audio_recorder_streamlit import audio_recorder

# ==========================================\
# 0. MULTI-TENANT PROGRAM CONFIGURATION
# ==========================================\
PROGRAM_CONFIG = {
    "PGY2_EM": {
        "program_name": "PGY2 Emergency Medicine",
        "sheet_name": "01_MASTER_SHEET_EM",
        "standards_tab": "ASHP_Standards",
        "evaluation_column": "ASHP Objective",
        "learner_column": "Resident Name",
        "standards_column": "ASHP Standards",
        "learner_id_column": "Learner_ID",
        "env_type": "clinical",
        "target_goals": {                                  # <--- ADD THIS BLOCK
            "R1.1.1 (Therapeutic Regimens)": 10,
            "R1.1.8 (Patient Outcomes)": 10,
            "R5.1.1 (Medical Emergencies)": 5,
            "E7.1.1 (Pre-hospital Teamwork)": 3
        },
        "nomenclature": {
            "learner": "Resident",
            "educator": "Preceptor",
            "director": "Residency Program Director",
            "committee": "Residency Advisory Committee (RAC)",
            "committee_short": "RAC",
            "eval_system": "PharmAcademic",
            "accreditation": "ASHP"
        },
        "eval_settings": {
            "grading_scale": ["ACHR", "ACH", "SP", "NI"],
            "entrustment_scale": ["1 - Knows", "2 - Knows How", "3 - Shows How", "4 - Does"],
            "rotations": ["CORE - 1 - EM", "CORE - 2 - EM", "CORE - 3 - ICU", "ELEC - Tox"] 
        }
    },
    "APPE_CLINICAL": {
        "program_name": "University of Arizona APPE",
        "sheet_name": "02_MASTER_SHEET_APPE",
        "standards_tab": "APPE_Standards",
        "evaluation_column": "AACP EPA Evaluated",
        "learner_column": "Student Name",
        "standards_column": "EPA Description",
        "learner_id_column": "Learner_ID",
        "env_type": "clinical", # NEW: AI Context flag
        "nomenclature": {
            "learner": "Student",
            "educator": "Preceptor",
            "director": "Course Coordinator",
            "committee": "Curriculum Committee",
            "committee_short": "CC",
            "eval_system": "CoreELMS",
            "accreditation": "ACPE"
        },
        "eval_settings": {
            "grading_scale": ["Exceeds Expectations", "Meets Expectations", "Needs Improvement", "Fail"],
            "entrustment_scale": ["1 - Observe", "2 - Assist", "3 - Perform with Guidance", "4 - Perform Independently"],
            "rotations": ["Ambulatory Care", "Acute Care", "Community", "Hospital"]
        }
    },
    "NAPLEX_PREP": {
        "program_name": "NAPLEX Readiness Program",
        "sheet_name": "https://docs.google.com/spreadsheets/d/1aag5kr_cxun18AyCs_E0-dzRtkGWmgrRYDEbveKG-yw/edit?usp=sharing", # Update with NAPLEX specific sheet URL
        "standards_tab": "NAPLEX_Competencies",
        "evaluation_column": "Competency Area",
        "learner_column": "Student Name",
        "standards_column": "Competency Statement",
        "learner_id_column": "Learner_ID",
        "env_type": "academic", # NEW: AI Context flag
        "show_upcoming_schedule": False,
        "nomenclature": {
            "learner": "Candidate",
            "educator": "Academic Coach",
            "director": "Exam Coordinator",
            "committee": "Curriculum Board",
            "committee_short": "CC",
            "eval_system": "RxBricks Tracker",
            "accreditation": "NABP"
        },
        "eval_settings": {
            "grading_scale": ["Competent", "Borderline", "Deficient"],
            "entrustment_scale": ["Calculation", "Brand/Generic", "Clinical Scenario"],
            "rotations": ["Foundations", "Ambulatory Care", "Acute Care", "Calculations"]
        }
    },
    "ABCGTBIO": {
        "program_name": "ABCGTBIO",
        "sheet_name": "03_MASTER_SHEET_ABCGTBIO",
        "standards_tab": "ABCGTBIO_Standards",
        "evaluation_column": "Course Module",
        "learner_column": "Learner Name",
        "standards_column": "EPA Description",
        "learner_id_column": "Learner_ID",
        "env_type": "clinical",
        "show_upcoming_schedule": False,
        "nomenclature": {
            "learner": "Learner",
            "educator": "Faculty",
            "director": "Course Coordinator",
            "committee": "Curriculum Committee",
            "committee_short": "CC",
            "eval_system": "Evaluation",
            "accreditation": "HYMR"
        },
        "eval_settings": {
            "grading_scale": ["Exceeds Expectations", "Meets Expectations", "Needs Improvement", "Fail"],
            "entrustment_scale": ["1 - Observe", "2 - Assist", "3 - Perform with Guidance", "4 - Perform Independently"],
            "rotations": ["Ambulatory Care", "Acute Care", "Community", "Hospital"]
        }
    }
}
# 1. SETTINGS & CONFIG
st.set_page_config(page_title="RxBricks: Trust Verification", layout="wide", page_icon="🧱")

# --- ENVIRONMENT SELECTION ---
st.sidebar.subheader("🌐 Active Environment")
selected_env_key = st.sidebar.selectbox(
    "Select Program Module:",
    options=list(PROGRAM_CONFIG.keys()),
    format_func=lambda x: PROGRAM_CONFIG[x]["program_name"]
)
active_config = PROGRAM_CONFIG[selected_env_key]
active_sheet_name = active_config["sheet_name"]
st.sidebar.divider()

# ==========================================\
# API CONNECTION MANAGERS (DRY APPROACH)
# ==========================================\
@st.cache_resource
def get_gspread_client():
    """Initializes Google Sheets client once and caches it."""
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(json.loads(st.secrets["raw_google_json"]), scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Failed to authenticate with Google: {e}")
        return None

def get_gemini_model():
    """Initializes Gemini model centrally."""
    if "GEMINI_API_KEY" not in st.secrets:
        st.error("🚨 Missing GEMINI_API_KEY in Streamlit secrets.")
        return None
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    return genai.GenerativeModel('gemini-2.5-flash')

# ==========================================\
# 1. THE BACKEND DATA FUNCTIONS
# ==========================================\
def log_evaluation_to_sheet(preceptor, resident, rotation, objective, criteria, grade, comment, action_plan, narrative, ai_quality_grade="", pharmacademic_text=""):
    client = get_gspread_client()
    if not client: return False
    
    try:
        # NEW: Handle URLs for HYMR module
        if "http" in active_sheet_name:
            sheet = client.open_by_url(active_sheet_name).worksheet("3_Evaluation_Log")
        else:
            sheet = client.open(active_sheet_name).worksheet("3_Evaluation_Log")
            
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        row_data = [
            timestamp, preceptor, resident, rotation, objective,
            criteria, grade, comment, action_plan, narrative,
            ai_quality_grade, pharmacademic_text
        ]
        sheet.append_row(row_data)
        get_evaluation_log.clear() 
        return True
    except Exception as e:
        st.error(f"Error writing to Google Sheets: {e}")
        return False

def clean_headers(header_list):
    """Sanitizes Google Sheet headers to prevent PyArrow duplicate crashes."""
    seen = {}
    cleaned = []
    for i, h in enumerate(header_list):
        base_name = str(h).strip()
        if not base_name:
            base_name = f"Unnamed_Col_{i}"
        
        if base_name in seen:
            seen[base_name] += 1
            cleaned.append(f"{base_name}_{seen[base_name]}")
        else:
            seen[base_name] = 0
            cleaned.append(base_name)
    return cleaned

@st.cache_data(ttl=60)
def get_evaluation_log(sheet_name):
    client = get_gspread_client()
    if not client: return pd.DataFrame()
    
    try:
        # NEW: Handle URLs for HYMR module
        if "http" in sheet_name:
            sheet = client.open_by_url(sheet_name).worksheet("3_Evaluation_Log")
        else:
            sheet = client.open(sheet_name).worksheet("3_Evaluation_Log")
            
        # ULTIMATE FIX: Bypass gspread's strict header validation and sanitize
        raw_data = sheet.get_all_values()
        if raw_data and len(raw_data) > 0:
            headers = clean_headers(raw_data.pop(0)) # <--- APPLIED HERE
            df = pd.DataFrame(raw_data, columns=headers)
        else:
            df = pd.DataFrame()
        
        if not df.empty:
            df.replace("", pd.NA, inplace=True)
            df.dropna(how='all', inplace=True)
            if 'Timestamp' in df.columns:
                df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Failed to load evaluation log: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_all_data(sheet_name, standards_tab_name):
    client = get_gspread_client()
    if not client: 
        return tuple(pd.DataFrame() for _ in range(7))
    try:
        if "http" in sheet_name:
            spreadsheet = client.open_by_url(sheet_name)
        else:
            spreadsheet = client.open(sheet_name)
    except Exception as e:
        st.error(f"⚠️ Failed to open spreadsheet. Ensure it is shared with the service account. Details: {e}")
        return tuple(pd.DataFrame() for _ in range(7))
        
    def fetch_sheet(ws_name):
        try:
            # ULTIMATE FIX: Bypass gspread's strict header validation and sanitize
            raw_data = spreadsheet.worksheet(ws_name).get_all_values()
            if raw_data and len(raw_data) > 0:
                headers = clean_headers(raw_data.pop(0)) # <--- APPLIED HERE
                return pd.DataFrame(raw_data, columns=headers)
            return pd.DataFrame()
        except Exception as e:
            st.warning(f"🚨 Data Parsing Error in tab '{ws_name}': {e}")
            return pd.DataFrame()

    curr = fetch_sheet("1_Curriculum")
    resp = pd.DataFrame()
    sched = fetch_sheet("4_Schedule")
    user_db = fetch_sheet("3_Users")
    assign_df = fetch_sheet("5_Assignments")
    rotation_tasks_df = fetch_sheet("7_Rotation_Task_Mapping")
    ashp_df = fetch_sheet(standards_tab_name)
    quiz_df = fetch_sheet("Quiz_Bank")
    
    # --- NEW: AUTOMATED SQL-STYLE "JOIN" ---
    rubric_df = fetch_sheet("Master_Rubric")
    
    # We must join on 'Topic' because 'Module_ID' does not exist in 1_Curriculum
    if not curr.empty and not rubric_df.empty and 'Topic' in curr.columns and 'Topic' in rubric_df.columns:
        # Pull the specific actionable columns we need from the Rubric for the AI Scribe
        rubric_subset = rubric_df[['Topic', 'Actionable_Activity', 'Scribe_Signals', 'ASHP_Objective', 'Miller_Level']]
        
        # Merge them into the Curriculum dataframe
        curr = pd.merge(curr, rubric_subset, on='Topic', how='left')
    # ---------------------------------------

    dataframes = [curr, resp, sched, user_db, assign_df, rotation_tasks_df, ashp_df, quiz_df] 

    for df in dataframes:
        if not df.empty:
            df.replace("", pd.NA, inplace=True)
            df.dropna(how='all', inplace=True)
            
    if not sched.empty:
        if 'Start Date' in sched.columns:
            sched['Start Date'] = pd.to_datetime(sched['Start Date'], errors='coerce')
        if 'End Date' in sched.columns:
            sched['End Date'] = pd.to_datetime(sched['End Date'], errors='coerce')
    
    return curr, resp, sched, user_db, assign_df, rotation_tasks_df, ashp_df, quiz_df
        
curriculum_df, eval_df, schedule_df, users_df, assignments_df, rotation_tasks_df, ashp_standards_df, quiz_bank_df = load_all_data(active_sheet_name, active_config["standards_tab"])

def save_schedule_to_sheet(sheet_name, updated_df):
    """Writes the recalculated schedule back to the 4_Schedule tab."""
    try:
        client = get_gspread_client()
        if "http" in sheet_name:
            sheet = client.open_by_url(sheet_name)
        else:
            sheet = client.open(sheet_name)
            
        worksheet = sheet.worksheet("4_Schedule")
        worksheet.clear()
        worksheet.update([updated_df.columns.values.tolist()] + updated_df.values.tolist())
        st.cache_data.clear() 
        return True
    except Exception as e:
        st.error(f"Failed to update schedule: {e}")
        return False

from datetime import timedelta

def recalculate_cascade(schedule_df, learner_column, learner_id, exam_date_str, max_hours=8.0):
    """The Kaplan-style dynamic schedule recalculator."""
    if pd.isna(exam_date_str) or not exam_date_str:
        return schedule_df, "No Exam Date set. Cannot recalculate."
        
    try:
        exam_date = pd.to_datetime(exam_date_str)
        today = pd.to_datetime(datetime.now().date())
    except Exception:
        return schedule_df, "Invalid Exam Date format. Use YYYY-MM-DD."

    if exam_date <= today:
        return schedule_df, "Exam date is in the past or today. Good luck!"

    # 1. Identify tasks for THIS learner that need rescheduling (Missed or Pending)
    learner_mask = schedule_df[learner_column] == learner_id
    incomplete_mask = schedule_df['Status'].isin(['Missed', 'Pending', '']) | schedule_df['Status'].isna()
    target_mask = learner_mask & incomplete_mask
    
    tasks_to_schedule = schedule_df[target_mask].copy()
    if tasks_to_schedule.empty:
        return schedule_df, "No pending or missed tasks to recalculate."

    # 2. Sort by Priority Tier (High Yield first, then Med, then Low)
    priority_map = {'High Yield': 3, 'Med Yield': 2, 'Low Yield': 1}
    tasks_to_schedule['Priority_Score'] = tasks_to_schedule['Priority_Tier'].map(priority_map).fillna(2)
    
    # Ensure Estimated_Hours is numeric
    tasks_to_schedule['Estimated_Hours'] = pd.to_numeric(tasks_to_schedule['Estimated_Hours'], errors='coerce').fillna(2.0)
    tasks_to_schedule = tasks_to_schedule.sort_values(by=['Priority_Score', 'Estimated_Hours'], ascending=[False, True])

    # 3. Calculate remaining available days
    available_days = pd.date_range(start=today + timedelta(days=1), end=exam_date - timedelta(days=1))
    if len(available_days) == 0:
        return schedule_df, "CRITICAL: No study days left before the exam!"

    # 4. Bin-packing: Distribute tasks into remaining days without exceeding max_hours
    day_loads = {day: 0.0 for day in available_days}
    
    for idx, row in tasks_to_schedule.iterrows():
        hours = row['Estimated_Hours']
        assigned_day = None
        
        # Find the first available day that can fit this topic
        for day in available_days:
            if day_loads[day] + hours <= max_hours:
                assigned_day = day
                break
        
        # If it doesn't fit anywhere safely, apply compression/triage rules
        if assigned_day is None:
            if row['Priority_Tier'] == 'Low Yield':
                schedule_df.loc[idx, 'Status'] = 'Skipped (Triage)' # Drop low yield
            else:
                # Force High/Med yield into the day with the least load (even if it goes over max_hours)
                min_day = min(day_loads, key=day_loads.get)
                schedule_df.loc[idx, 'Start Date'] = min_day.strftime('%Y-%m-%d')
                schedule_df.loc[idx, 'Status'] = 'Pending'
                day_loads[min_day] += hours
        else:
            schedule_df.loc[idx, 'Start Date'] = assigned_day.strftime('%Y-%m-%d')
            schedule_df.loc[idx, 'Status'] = 'Pending'
            day_loads[assigned_day] += hours

    return schedule_df, "Schedule successfully recalibrated."

def render_progress(col_target, items, working_df, eval_col):
    with col_target:
        for item in items:
            objective_name = item[0]
            target_amount = item[1] 
            
            objective_code = str(objective_name).split(' ')[0] if pd.notna(objective_name) else ""
            
            if eval_col in working_df.columns:
                current_count = len(working_df[working_df[eval_col].astype(str).str.contains(objective_code, na=False, regex=False)])
            else:
                current_count = 0 
                
            progress_val = min(current_count / target_amount, 1.0) if target_amount > 0 else 0.0
            
            st.markdown(f"**{objective_name[:40]}...**")
            st.progress(progress_val)
            st.caption(f"{current_count} / {target_amount} Logged")
# ==========================================\
# 2. AI ENGINES
# ==========================================\

def generate_preceptor_prime(learner_name, recent_evals_df):
    """Generates a dynamic Optimus-style Preceptor Prime briefing."""
    model = get_gemini_model()
    if not model: return "AI model unavailable."
    
    if recent_evals_df.empty:
        return f"No recent evaluation data on file for {learner_name}. Focus on establishing baseline clinical competencies and workflow autonomy today."

    # Extract the most recent feedback to feed the prompt
    recent_evals_df = recent_evals_df.sort_values(by='Timestamp', ascending=False).head(4)
    
    context_string = ""
    for _, row in recent_evals_df.iterrows():
        obj = row.get('ASHP Objective', row.get('Objective', 'Clinical Action'))
        grade = row.get('Grade', 'N/A')
        comment = row.get('Comment', row.get('Action Plan', 'No comment.'))
        context_string += f"- Action: {obj} | Grade: {grade} | Feedback: {comment}\n"

    prompt = f"""
    You are an expert Clinical Coaching AI known as "Preceptor Prime".
    Review the recent clinical evaluations for the resident, {learner_name}, and create a hyper-condensed briefing.
    
    Your goal is to prime the attending preceptor's attention BEFORE the shift starts.
    1. Acknowledge what the resident has recently mastered or done well.
    2. Give the preceptor a specific, advanced clinical behavior, nuance, or "blind spot" to watch for today based on their recent feedback or logical next steps in mastery.
    
    Constraints:
    - MAXIMUM of 2 sentences.
    - Make it punchy, highly actionable, and professional.
    
    Recent Performance Context:
    {context_string}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Ready to evaluate {learner_name}."

def generate_learner_prime(learner_name, schedule_context, recent_evals_text):
    """Generates a dynamic Daily Mission prompt for the learner's voice journal."""
    model = get_gemini_model()
    if not model: return "Focus on establishing your clinical workflow today, and record any significant patient interventions."
    
    prompt = f"""
    You are an expert Clinical Coaching AI acting as a mentor for a pharmacy resident/student, {learner_name}.
    They are about to start their shift or study session.
    
    Your goal is to give them a specific "Daily Mission" to focus on and later dictate into their clinical voice journal.
    
    1. Acknowledge what they are scheduled for today OR acknowledge a recent area of growth based on their past feedback.
    2. Give them a highly specific prompt on what clinical behavior, task-switching, or patient interaction to focus on and record today.
    
    Constraints:
    - MAXIMUM of 2 sentences.
    - Tone should be motivational, highly actionable, and focused on clinical mastery.
    - Do not sound robotic; sound like a seasoned, encouraging preceptor.
    
    Today's Schedule/Focus: {schedule_context}
    Recent Feedback Context: {recent_evals_text}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return "Keep an eye out for complex clinical scenarios today, and record your thought process on any major interventions."

def generate_ai_evaluation(raw_dictation, learner_name, config, available_topics, proven_bricks=None):
    model = get_gemini_model()
    if not model: return None
    
    nom = config["nomenclature"]
    eval_sys = nom["eval_system"]
    env_type = config.get("env_type", "clinical")
    
    if env_type == "academic":
        role_context = f"an expert Academic Coach evaluating foundational knowledge, exam study rationale, and calculation accuracy."
    else:
        role_context = f"an expert Clinical Preceptor evaluating direct patient care and clinical autonomy."
    
    evidence_text = "No specific clinical signals detected by the system."
    if proven_bricks:
        evidence_text = "DETERMINISTIC EVIDENCE FOUND BY SYSTEM AUDIT:\n"
        for brick in proven_bricks:
            evidence_text += f"- Objective: {brick.get('ASHP_Objective', 'N/A')} | Evidence Used: {brick['Matched_Evidence']}\n"
    
    # Pass the actual curriculum topics to Gemini so it maps exactly to your sheet
    topics_list_str = ", ".join([str(t) for t in available_topics if str(t).strip()])
    
    prompt = f"""
    You are {role_context}.
    
    STRICT HIPAA RULE: You are an AI Clinical Scribe. If the raw dictation contains any patient names, dates of birth, or medical record numbers (MRNs) that were not previously caught, you must immediately redact them and replace them with [PATIENT IDENTIFIER REDACTED] in your final narrative and comments.
    
    First, evaluate the quality of the raw {nom['educator'].lower()} dictation. 
    Second, act as a data-classifier. Based on the dictation context, infer the most likely Rotation, Objective, Entrustment Level, and Interaction Type.
    
    Context:
    * {nom['learner']} Name: {learner_name}
    
    {evidence_text}
    
    Raw {nom['educator']} Dictation:
    {raw_dictation}
    
    CLASSIFICATION LISTS (You MUST pick one exact match from these lists):
    - Valid Rotations: {config['eval_settings'].get('rotations', ['Default'])}
    - Valid Objectives (Topics): {topics_list_str}
    - Valid Grades: {config['eval_settings']['grading_scale']}
    - Valid Interaction Types: ["Clinical Scenario / Bedside Care", "Topic Discussion / Review", "Case Presentation", "Journal Club / Literature Review", "Project / Admin Review"]
    
    Output Requirements:
    Return ONLY a strict JSON object with exactly these 9 keys:
    1. "InferredRotation": String (Must exactly match one of the Valid Rotations)
    2. "InferredObjective": String (Must match one of the Valid Objectives, or summarize in 3 words if completely missing)
    3. "InferredGrade": String (Must exactly match one of the Valid Grades)
    4. "InferredInteraction": String (Must exactly match one of the Valid Interaction Types)
    5. "QualityGrade": String ("Green", "Yellow", or "Red"). Red means the dictation was lazy or lacked appropriate context.
    6. "QualityFeedback": String (1 short sentence of direct coaching to the {nom['educator'].lower()} explaining *why* their dictation scored that grade).
    7. "Comment": A 1-2 sentence professional assessment. Ground this comment in the DETERMINISTIC EVIDENCE FOUND if any is provided.
    8. "ActionPlan": 1-2 sentences detailing specific next steps.
    9. "Narrative": A comprehensive synthesis paragraph ready for {eval_sys}.
    """
        
    try:
        response = model.generate_content(
            prompt, 
            generation_config=genai.GenerationConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        st.error(f"AI Formatting Error: {str(e)}")
        return None

def generate_ce_micro_lesson(raw_dictation, mission_dict):
    """Evaluates the case against specific curriculum standards and generates CE."""
    model = get_gemini_model()
    if not model: return None
    
    prompt = f"""
    You are an expert Clinical Pharmacist Preceptor acting as an evaluator for a Continuing Education (CE) module.
    
    The learner encountered a patient case today. You must rigorously evaluate if their dictated clinical actions 
    satisfy the following daily mission and programmatic standards:
    - Topic: {mission_dict.get('topic')}
    - SPECIFIC DAILY MISSION: "{mission_dict.get('actionable_prompt')}"
    - REQUIRED KEYWORDS/SIGNALS: {mission_dict.get('signals')}
    
    Raw Case Dictation from the Learner:
    {raw_dictation}
    
    Output Requirements:
    Return ONLY a strict JSON object with exactly these 4 keys:
    1. "StandardMet": Boolean (True ONLY if their dictation clearly proves they accomplished the SPECIFIC DAILY MISSION and utilized concepts related to the REQUIRED KEYWORDS/SIGNALS. False otherwise).
    2. "Feedback": String (If True, validate how their action met the mission. If False, provide direct coaching on what clinical reasoning or specific keywords were missing to fulfill the mission).
    3. "LearningPearls": Array of 3 Strings (Provide high-yield clinical pearls specifically related to the intersection of their case and the Topic).
    4. "CEQuestions": Array of 2 Objects (Generate 2 multiple-choice questions to test their knowledge. Format: "Question", "Options" (array of 4), "CorrectAnswer", and "Explanation").
    """
        
    try:
        response = model.generate_content(
            prompt, 
            generation_config=genai.GenerationConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        st.error(f"AI Microlearning Error: {str(e)}")
        return None

def generate_admin_document(doc_type, raw_notes, config, context=""):
    model = get_gemini_model()
    if not model: return None
    
    nom = config["nomenclature"]
    prog_name = config["program_name"]
    
    try:
        if doc_type == "COMMITTEE":
            prompt = (
                f"You are an expert {nom['director']}.\n"
                f"Take these rough meeting notes and format them strictly into the following {nom['committee_short']} Meeting Minutes template.\n"
                "Use Markdown tables for the structured data. Ensure a professional, objective tone.\n\n"
                f"Meeting Date/Time Context: {context}\n\n"
                "TEMPLATE STRUCTURE TO FOLLOW:\n"
                f"# {prog_name} - {nom['committee']} Meeting Minutes\n"
                "**Location:** Virtual / Microsoft Teams\n\n"
                "## Attendance\n"
                "(List Present and Regrets based on notes)\n\n"
                "## Agenda Items and Discussion Summary\n"
                "(Create a Markdown table with columns: # | Topic | Presenter/Lead | Summary of Discussion)\n\n"
                "## Decisions Made\n"
                "(Create a Markdown table with columns: Decision Summary | Proposer | Seconder | Outcome)\n\n"
                "## Action Items\n"
                "(Create a Markdown table with columns: # | Action Item | Assigned To | Due Date | Status)\n\n"
                f"RAW NOTES TO PROCESS:\n{raw_notes}"
            )
        elif doc_type == "ACCREDITATION":
            prompt = (
                f"You are an expert {nom['director']} responding to an {nom['accreditation']} accreditation survey.\n"
                f"Take the cited standard and the raw notes regarding the program's corrective action, and format it into a formal {nom['accreditation']} Progress Report response.\n\n"
                f"Cited {nom['accreditation']} Standard/Area: {context}\n\n"
                "Format the output strictly as follows, using highly professional, accreditation-standard language:\n\n"
                f"### {nom['accreditation']} Standard / Principle Cited:\n"
                "[Insert Standard Here]\n\n"
                "### Program's Response & Action Plan:\n"
                "[Synthesize the raw notes into a formal, clear description of exactly how the program has achieved or is progressing toward compliance. Use passive/formal administrative voice.]\n\n"
                "### Timeline for Completion:\n"
                "[Extract or propose a realistic timeline based on the notes]\n\n"
                "### Supporting Evidence to be Attached:\n"
                "[List logical documents/artifacts that should be attached to prove compliance based on the action plan]\n\n"
                f"RAW NOTES ON CORRECTIVE ACTION:\n{raw_notes}"
            )
            
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"AI Generation Failed: {e}")
        return None

def run_gap_analysis(standard_name, evaluation_data_subset, config):
    model = get_gemini_model()
    if not model: return None
    
    nom = config["nomenclature"]
    
    combined_narratives = "\n---\n".join(evaluation_data_subset['Overall Narrative'].dropna().astype(str).tolist())
    
    prompt = f"""
    You are an expert {nom['accreditation']} Lead Surveyor auditing a {config['program_name']}.
    Review the following {nom['educator'].lower()} evaluations submitted for the standard: {standard_name}.
    
    Your goal is to identify gaps in the {nom['learner'].lower()}s' clinical exposure and recommend actionable steps for the {nom['director']}.
    
    Output Requirements:
    Return a professional, markdown-formatted report with the following sections:
    1. **Current Strengths:** A brief summary of what the program is doing well regarding this standard.
    2. **Identified Gaps:** Specific clinical areas, patient populations, or entrustment levels that are missing from these evaluations.
    3. **Actionable Recommendations:** 2-3 specific things the {nom['director']} should assign or focus on next week to close these gaps.
    
    Raw Evaluation Data:
    {combined_narratives}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error running AI Audit: {str(e)}"

def transcribe_clinical_audio(audio_bytes, mime_type="audio/wav"):
    """Passes raw audio bytes to Gemini for clinical transcription."""
    model = get_gemini_model()
    if not model: return None
    
    prompt = """
    You are an expert medical transcriptionist and clinical pharmacist. 
    Transcribe the following clinical dictation accurately. 
    Ensure all medical terminology, drug names, and dosages are spelled correctly.
    
    STRICT HIPAA RULE: You are an AI Clinical Scribe. If the preceptor accidentally dictates a patient name, date of birth, or medical record number (MRN), you must immediately redact it and replace it with [PATIENT IDENTIFIER REDACTED] before returning the text.
    
    Return ONLY the transcribed text. Do not include markdown or conversational filler.
    """
    try:
        # Gemini natively accepts multimodal byte data
        response = model.generate_content([
            prompt,
            {"mime_type": mime_type, "data": audio_bytes}
        ])
        return response.text
    except Exception as e:
        st.error(f"Audio Transcription Error: {str(e)}")
        return None

class RxBricksScribeMatcher:
    def __init__(self, knowledge_df):
        """Initializes using the live Google Sheets DataFrame"""
        self.knowledge_base = knowledge_df

    def _parse_signals(self, signal_string):
        import pandas as pd
        if pd.isna(signal_string): return []
        clean_str = str(signal_string).replace('[', '').replace(']', '').replace("'", "").replace('"', '')
        signals = clean_str.split(';') if ';' in clean_str else clean_str.split(',')
        return [s.strip().lower() for s in signals if s.strip()]

    def analyze_transcript(self, transcript_text):
        transcript_clean = transcript_text.lower()
        captured_bricks = []

        # Fail gracefully if column isn't mapped yet
        if 'Scribe_Signals' not in self.knowledge_base.columns:
            return [] 

        for index, row in self.knowledge_base.iterrows():
            signals = self._parse_signals(row['Scribe_Signals'])
            matched_phrases = []

            for signal in signals:
                # Use regex word boundaries (\b) to match whole phrases
                pattern = r'\b' + re.escape(signal) + r'\b'
                if re.search(pattern, transcript_clean):
                    matched_phrases.append(signal)

            if matched_phrases:
                captured_bricks.append({
                    "Activity": row.get('Actionable_Activity', 'Unknown'),
                    "ASHP_Objective": row.get('ASHP_Objective', 'Unknown'),
                    "Miller_Level": row.get('Miller_Level', 'Unknown'),
                    "Matched_Evidence": matched_phrases
                })
        return captured_bricks

# =========================================================
# 4. AUTHENTICATION & ROUTING FIX
# =========================================================
credentials = {"usernames": {}}
if not users_df.empty:
    for _, row in users_df.iterrows():
        uname = str(row['Username']).strip()
        raw_pw = str(row['Password']).strip()
        hpw = bcrypt.hashpw(raw_pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # FIXED: More robust role mapping
        db_role = str(row['Role']).strip().upper()
        if db_role in ["RPD", "ADMIN", "DIRECTOR"]: 
            r_internal = "admin"
        elif db_role in ["RESIDENT", "LEARNER", "STUDENT", "CANDIDATE"]: # Added CANDIDATE
            r_internal = "learner"
        else: 
            r_internal = "preceptor"
            
        u_tier = str(row['Tier']).strip().capitalize() if 'Tier' in users_df.columns else "Basic"
        
        # NEW: Safely handle the Phenotype column
        phenotype_val = "Standard"
        if 'Phenotype' in users_df.columns and pd.notna(row['Phenotype']):
            phenotype_val = str(row['Phenotype']).strip()
        
        credentials["usernames"][uname] = {
            "email": str(row['Email']), "name": str(row['Name']),
            "password": hpw, "role": r_internal, "tier": u_tier,
            "phenotype": phenotype_val # Added to dictionary
        }
authenticator = stauth.Authenticate(credentials, "rxbricks_em", "auth_key", cookie_expiry_days=30)
authenticator.login(location="main")

name = st.session_state.get("name")
authentication_status = st.session_state.get("authentication_status")
username = st.session_state.get("username")

if authentication_status is False:
    st.error("Username/password is incorrect")
    st.stop()
elif authentication_status is None:
    st.warning("Please log in to access RxBricks EM")
    st.stop()

if username not in credentials["usernames"]:
    st.error("🚨 User database sync error. Ensure your User sheet is loaded correctly.")
    st.stop()

user_role = credentials["usernames"][username]["role"]
user_tier = credentials["usernames"][username]["tier"]
user_phenotype = credentials["usernames"][username].get("phenotype", "Standard")
st.session_state['phenotype'] = user_phenotype
authenticator.logout(location="sidebar")
st.sidebar.success(f"Logged in: {name} | Tier: {user_tier}")

if user_role in ["admin", "preceptor"]:
    st.divider()

# =========================================================
# ID REPOSITORY PATTERN 
# =========================================================
def get_learner_mapping(users_dataframe, config):
    if users_dataframe.empty: return {}
    # Broadened search to match robust role logic
    learners = users_dataframe[users_dataframe['Role'].str.upper().isin(["RESIDENT", "LEARNER", "STUDENT", "CANDIDATE"])]
    id_col = config.get("learner_id_column", "Learner_ID")
    if id_col not in users_dataframe.columns:
        id_col = "Name"
    return dict(zip(learners[id_col], learners['Name']))

learner_dict = get_learner_mapping(users_df, active_config)

logged_in_id = name 
for lid, lname in learner_dict.items():
    if lname == name:
        logged_in_id = lid
        break

def get_learner_evals(df, config, learner_id):
    if df.empty: return pd.DataFrame()
    
    # 1. Try primary ID column from config
    id_col = config.get("learner_id_column", "Learner_ID")
    
    # 2. Try the learner column from config
    if id_col not in df.columns:
        id_col = config.get("learner_column", "Resident Name") 
        
    # 3. THE SAFETY NET: Check for legacy/mismatched column names
    if id_col not in df.columns:
        possible_fallbacks = ["Candidate Name", "Resident", "Resident Name", "Student Name", "Student", "Name", "Learner"]
        
        column_found = False
        for fallback in possible_fallbacks:
            if fallback in df.columns:
                id_col = fallback
                column_found = True
                break
                
        if not column_found:
            st.warning(f"⚠️ Column mapping error: Could not find '{id_col}' in the Evaluation Log sheet.")
            return pd.DataFrame() # Return empty safely instead of crashing
            
    return df[df[id_col] == learner_id].copy()

def get_recent_evals(df, config, learner_id, days=7):
    my_evals = get_learner_evals(df, config, learner_id)
    if my_evals.empty: return pd.DataFrame()
    my_evals['Timestamp'] = pd.to_datetime(my_evals['Timestamp'], errors='coerce')
    cutoff_date = datetime.now() - pd.Timedelta(days=days)
    return my_evals[my_evals['Timestamp'] >= cutoff_date]

# =========================================================
# REUSABLE COMPONENTS 
# =========================================================
def render_step_counter(learner_id, weekly_goal=5):
    st.subheader("🏃‍♂️ Clinical Step Counter")
    df = get_evaluation_log(active_sheet_name)
    
    if df.empty:
        st.info("No clinical actions logged yet. Go get some feedback!")
        return

    my_evals = get_learner_evals(df, active_config, learner_id)

    if my_evals.empty:
        st.info("You haven't logged any actions yet this week. Hunt down a preceptor!")
        return
    
    recent_evals = get_recent_evals(df, active_config, learner_id, days=7)
    current_steps = len(recent_evals)
    progress_fraction = min(current_steps / weekly_goal, 1.0)
    
    col1, col2 = st.columns([1, 3])
    with col1:
        st.metric("Actions (Last 7 Days)", f"{current_steps} / {weekly_goal}")
    with col2:
        st.write("")
        st.progress(progress_fraction)
        
    if current_steps >= weekly_goal:
        st.success("🎯 Weekly goal met! Excellent job driving your clinical autonomy.")
    else:
        st.caption(f"You need {weekly_goal - current_steps} more logged actions to hit your weekly target.")

def render_step_tracker(learner_id):
    # Standardizing use of get_evaluation_log
    live_df = get_evaluation_log(active_sheet_name)
    if live_df.empty or curriculum_df.empty:
        st.caption("👟 **Step Tracker:** Awaiting evaluation data...")
        st.progress(0.0)
        return
        
    total_topics = len(curriculum_df['Topic'].unique())
    res_evals = get_learner_evals(live_df, active_config, learner_id)
    
    if 'Activity' in res_evals.columns:
        completed_topics = res_evals['Activity'].nunique()
    elif 'Topic' in res_evals.columns:
        completed_topics = res_evals['Topic'].nunique()
    else:
        completed_topics = len(res_evals) 
        
    progress_pct = min(completed_topics / total_topics, 1.0) if total_topics > 0 else 0.0
    
    st.markdown(f"**👟 Step Tracker:** `{completed_topics} / {total_topics}` Core Topics Evaluated")
    st.progress(progress_pct)

def get_milestone_badges(learner_id):
    live_df = get_evaluation_log(active_sheet_name)
    if curriculum_df.empty or live_df.empty:
        return {}

    module_reqs = curriculum_df.groupby('Category / Module')['Topic'].nunique().to_dict()
    res_evals = get_learner_evals(live_df, active_config, learner_id)
    
    topic_col = 'Activity' if 'Activity' in res_evals.columns else ('Topic' if 'Topic' in res_evals.columns else None)
    completed_topics = res_evals[topic_col].unique().tolist() if topic_col else []

    badges = {}
    for module, total_required in module_reqs.items():
        module_topics = curriculum_df[curriculum_df['Category / Module'] == module]['Topic'].unique().tolist()
        completed_in_module = [t for t in module_topics if t in completed_topics]
        is_complete = len(completed_in_module) >= total_required
        
        badges[module] = {
            "total": total_required,
            "completed": len(completed_in_module),
            "is_complete": is_complete
        }
    return badges

def render_resident_profile(learner_id, is_preceptor_view=False):
    display_name = learner_dict.get(learner_id, learner_id)
    st.header(f"🎓 Professional Profile: {display_name}")
    
    col_img, col_info = st.columns([1, 3])
    with col_img:
        st.image("https://cdn-icons-png.flaticon.com/512/387/387561.png", width=120) 
        
    with col_info:
        st.subheader("Clinical Pharmacy Resident")
        st.write("**Program:** Emergency Medicine PGY2")
        render_step_tracker(learner_id)

    st.divider()
    st.subheader("🏆 Clinical Milestones")
    badges = get_milestone_badges(learner_id)
    
    if not badges:
        st.info("No milestone data available yet.")
    else:
        completed_modules = {k: v for k, v in badges.items() if v["is_complete"]}
        in_progress_modules = {k: v for k, v in badges.items() if not v["is_complete"]}
        
        if completed_modules:
            st.success(f"**Achieved {len(completed_modules)} Module Certifications!**")
            badge_cols = st.columns(4)
            for idx, (module, data) in enumerate(completed_modules.items()):
                with badge_cols[idx % 4]:
                    st.markdown(f"""
                    <div style="text-align: center; padding: 10px; border: 1px solid #4CAF50; border-radius: 10px; background-color: #f1f8e9; color: black; margin-bottom: 10px;">
                        <h2 style="margin: 0;">🏅</h2>
                        <strong>{module}</strong><br>
                        <small>Mastered</small>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.caption("Complete all topics in a module to earn a milestone badge!")

        if in_progress_modules:
            with st.expander("View Module Progress Details", expanded=not bool(completed_modules)):
                for module, data in in_progress_modules.items():
                    progress = data['completed'] / data['total'] if data['total'] > 0 else 0
                    st.write(f"**{module}** ({data['completed']}/{data['total']} topics)")
                    st.progress(progress)

    st.divider()
    live_df = get_evaluation_log(active_sheet_name)
    res_evals = get_learner_evals(live_df, active_config, learner_id)

    if is_preceptor_view:
        st.subheader("📋 Academic & Professional Record")
        if not res_evals.empty:
            st.dataframe(res_evals, use_container_width=True)
        else:
            st.info("No formal evaluations on record yet.")
    else:
        st.subheader("📄 Automated CV Builder")
        cv_text = f"### Core Competencies & Completed Modules\n"
        if completed_modules:
            for module in completed_modules.keys():
                cv_text += f"- **{module}:** Demonstrated independent clinical competence across all targeted therapeutic topics.\n"
        else:
            cv_text += "- *Modules currently in progress.*\n"
            
        cv_text += "\n### Advanced Clinical Actions\n"
        
        action_col = 'Activity' if 'Activity' in res_evals.columns else ('Topic' if 'Topic' in res_evals.columns else None)
        if action_col and not res_evals.empty:
            actions = res_evals[action_col].dropna().unique()
            if len(actions) > 0:
                for action in actions[:10]:
                    cv_text += f"- Successfully evaluated on: {action}\n"
                if len(actions) > 10:
                    cv_text += f"- ...and {len(actions)-10} additional clinical competencies.\n"
        else:
            cv_text += "- *Awaiting evaluated actions.*\n"
                
        st.text_area("Your CV Export:", value=cv_text, height=250)

# =========================================================
# UI BLOCKS
# =========================================================
def render_module_quiz(quiz_df, topic_name, unique_suffix=""):
    if pd.isna(topic_name) or not topic_name or quiz_df.empty: return
    
    # Strip spaces and underscores from the topic for a universal match
    safe_topic = str(topic_name).strip().lower().replace(" ", "").replace("_", "")
    
    # Strip spaces and underscores from the Form Names column
    search_column = quiz_df['Form_Name'].astype(str).str.lower().str.replace(" ", "").str.replace("_", "")
    
    # Check if the sanitized topic exists inside the sanitized file name
    mask = search_column.str.contains(safe_topic, regex=False, na=False)
    module_questions = quiz_df[mask]

    # If no match is found, silently skip rendering
    if module_questions.empty: return

    st.divider()
    st.subheader(f"📝 Knowledge Check")
    
    # Make the key globally unique to prevent duplicate form errors
    safe_state_key = safe_topic.replace(":", "")
    if unique_suffix:
        safe_state_key = f"{safe_state_key}_{unique_suffix}"
        
    if f"quiz_sub_{safe_state_key}" not in st.session_state:
        st.session_state[f"quiz_sub_{safe_state_key}"] = False

    with st.form(key=f"quiz_{safe_state_key}"):
        user_answers = {}
        for index, row in module_questions.iterrows():
            st.markdown(f"**Q{row['Question_Number']}: {row['Question_Text']}**")
            opts = [f"A) {row['Option_A']}", f"B) {row['Option_B']}", f"C) {row['Option_C']}", f"D) {row['Option_D']}"]
            user_answers[index] = st.radio("Select answer:", opts, key=f"q_{safe_state_key}_{index}", index=None)
            st.write("---")
        submit_btn = st.form_submit_button("Submit Quiz")

    if submit_btn:
        score = 0
        st.subheader("📊 Results")
        for index, row in module_questions.iterrows():
            correct_key = str(row['Correct_Answer']).strip()
            
            if correct_key in ["Option_A", "Option_B", "Option_C", "Option_D"]:
                correct_text = row[correct_key]
                correct_display = f"{correct_key.replace('Option_', '')}) {correct_text}"
            else:
                correct_display = correct_key
                
            sel = user_answers[index]
            
            if sel and (sel == correct_display or correct_key in str(sel)):
                score += 1
                st.success(f"**Q{row['Question_Number']}**: Correct! ✅")
            else:
                st.error(f"**Q{row['Question_Number']}**: Incorrect. ❌")
                st.write(f"*Correct Answer: {correct_display}*")
                
            st.info(f"**Explanation:** {row['Answer_Explanation']}")
            st.write("---")
        st.metric("Score", f"{score} / {len(module_questions)}")

def render_ce_case_logger(learner_id):
    st.subheader("🎙️ Micro-CE Voice Logger")
    st.caption("Record a quick reflection on how you applied a biologic, biosimilar, or CGT concept in practice today. The AI will automatically map it to the curriculum and award your Micro-CE credit.")

    nom = active_config.get("nomenclature", {})
    eval_set = active_config.get("eval_settings", {})
    topics = curriculum_df['Topic'].dropna().unique().tolist() if not curriculum_df.empty else ["Unknown Topic"]

    text_key = f"ce_dictation_{learner_id}"
    if text_key not in st.session_state:
        st.session_state[text_key] = ""

    # 1. AUDIO CAPTURE USING NATIVE WIDGET
    audio_tabs = st.tabs(["🎙️ Record Reflection", "📁 Upload Audio File"])
    audio_bytes = None
    audio_mime = "audio/wav"
    
    with audio_tabs[0]:
        recorded_audio = st.audio_input("Record Micro-CE Reflection", key=f"ce_rec_{learner_id}")
        if recorded_audio:
            audio_bytes = recorded_audio.read()

    with audio_tabs[1]:
        uploaded_audio = st.file_uploader("Upload an audio file (.wav, .mp3, .m4a)", type=["wav", "mp3", "m4a"], key=f"ce_upload_{learner_id}")
        if uploaded_audio:
            audio_bytes = uploaded_audio.read()
            if uploaded_audio.name.endswith(".mp3"): audio_mime = "audio/mp3"
            elif uploaded_audio.name.endswith(".m4a"): audio_mime = "audio/mp4"

    # 2. AI PROCESSING & CLASSIFICATION
    if audio_bytes:
        st.write("---")
        if st.button("✨ Process & Claim Micro-CE", type="primary", use_container_width=True, key=f"btn_transcribe_ce_{learner_id}"):
            status_placeholder = st.empty()
            with status_placeholder.container():
                st.info("🧠 Gemini is analyzing your reflection against the ABCGTBIO Standards... Please wait.")
                st.progress(50)
            
            with st.spinner("Processing..."):
                transcript = transcribe_clinical_audio(audio_bytes, mime_type=audio_mime)
                
                if transcript:
                    st.session_state[text_key] = transcript
                    
                    # Run deterministic match against the Curriculum Rubric
                    matcher = RxBricksScribeMatcher(curriculum_df) 
                    proven_bricks = matcher.analyze_transcript(transcript)
                    
                    # Generate the Self-Directed AI Classification
                    ai_result = generate_ai_evaluation(
                        raw_dictation=f"[Self-Directed CE Reflection]\n\n{transcript}", 
                        learner_name=learner_dict.get(learner_id, learner_id), 
                        config=active_config,
                        available_topics=topics,
                        proven_bricks=proven_bricks
                    )
                    
                    if ai_result:
                        st.session_state.ce_draft = ai_result
                        status_placeholder.success("✅ Micro-CE successfully mapped! Review and save below.")
                        st.rerun()
                else:
                    status_placeholder.error("❌ Transcription failed.")

    # 3. REVIEW & SAVE LOGIC
    if "ce_draft" in st.session_state and st.session_state.ce_draft:
        draft = st.session_state.ce_draft
        st.divider()
        
        st.markdown("**Your Raw Voice Journal**")
        st.text_area("Hidden Label", height=100, key=text_key, label_visibility="collapsed")
        
        st.subheader("📋 Curriculum Mapping")
        st.caption("Gemini has routed your reflection to these specific ABCGTBIO standards.")
        
        col_c, col_d = st.columns(2)
        with col_c:
            safe_rot = draft.get("InferredRotation", eval_set.get("rotations", ["Independent Study"])[0])
            if safe_rot not in eval_set.get("rotations", []): safe_rot = eval_set.get("rotations", ["Independent Study"])[0]
            final_rot = st.selectbox("Category", eval_set.get("rotations", ["Independent Study"]), index=eval_set.get("rotations", ["Independent Study"]).index(safe_rot), key=f"cerot_{learner_id}")
            
            safe_obj = draft.get("InferredObjective", topics[0] if topics else "Unknown")
            if safe_obj not in topics: topics.insert(0, safe_obj)
            final_obj = st.selectbox("Target Concept / EPA", topics, index=topics.index(safe_obj), key=f"ceobj_{learner_id}")

        with col_d:
            # Default to "Meets Expectations" or equivalent passing grade for a completed CE
            safe_grade = "Meets Expectations" if "Meets Expectations" in eval_set.get("grading_scale", []) else eval_set.get("grading_scale", ["Complete"])[-1]
            if safe_grade not in eval_set.get("grading_scale", []): safe_grade = eval_set.get("grading_scale", ["Complete"])[0]
            final_grade = st.selectbox("Self-Assessed Mastery", eval_set.get("grading_scale", ["Complete"]), index=eval_set.get("grading_scale", ["Complete"]).index(safe_grade), key=f"ceg_{learner_id}")
            
            final_interaction = st.selectbox("Interaction Type", ["Clinical Application", "Literature Review", "Peer Discussion", "Self-Study"], key=f"ceint_{learner_id}")
            
        final_comment = st.text_input("Key Takeaway", value=draft.get("Comment", ""), key=f"cec_{learner_id}")
        final_narrative = st.text_area("AI Synthesis", value=draft.get("Narrative", ""), height=120, key=f"cen_{learner_id}")
        
        if st.button("💾 Log Micro-CE to Profile", type="primary", key=f"save_ce_{learner_id}", use_container_width=True):
            with st.spinner("Locking in your CE credit..."):
                # Logs the entry using "Self-Directed" instead of a Preceptor name
                success = log_evaluation_to_sheet(
                    preceptor="Self-Directed CE", 
                    resident=learner_id,  
                    rotation=final_rot,
                    objective=final_obj,
                    criteria=final_interaction,
                    grade=final_grade,
                    comment=final_comment,
                    action_plan=draft.get("ActionPlan", ""),
                    narrative=st.session_state[text_key],
                    ai_quality_grade=draft.get("QualityGrade", "Green"),
                    pharmacademic_text=final_narrative
                )
                if success:
                    st.balloons()
                    st.success("🎉 Micro-CE Logged! Your Performance Dashboard has been updated.")
                    st.session_state.ce_draft = None

    # --- AI TRIGGER ---
    if st.button("✨ Evaluate Mission & Generate CE Lesson", type="primary", use_container_width=True):
        if len(st.session_state[text_key]) > 10:
            with st.spinner(f"Analyzing case against program standards..."):
                lesson = generate_ce_micro_lesson(st.session_state[text_key], active_mission)
                if lesson:
                    st.session_state.current_ce_lesson = lesson
                    st.session_state.current_ce_topic = active_mission['topic']

    # --- MICROLEARNING RESULTS & QUIZ ---
    if "current_ce_lesson" in st.session_state and st.session_state.current_ce_lesson:
        lesson = st.session_state.current_ce_lesson
        
        st.divider()
        if lesson.get("StandardMet", False):
            st.success(f"✅ Mission Accomplished: {lesson.get('Feedback', '')}")
        else:
            st.warning(f"⚠️ Coaching Point: {lesson.get('Feedback', '')}")
        
        st.subheader("💡 Key Learning Pearls")
        for pearl in lesson.get("LearningPearls", []):
            st.markdown(f"- {pearl}")
            
        st.subheader("📝 Complete to Earn CE Credit")
        with st.form(key="ce_quiz_form"):
            user_answers = {}
            for idx, q_data in enumerate(lesson.get("CEQuestions", [])):
                st.markdown(f"**Q{idx+1}: {q_data['Question']}**")
                user_answers[idx] = st.radio("Select answer:", q_data["Options"], key=f"ce_q_{idx}", index=None)
                st.write("---")
            
            if st.form_submit_button("Submit Answers"):
                score = 0
                for idx, q_data in enumerate(lesson.get("CEQuestions", [])):
                    if user_answers[idx] == q_data["CorrectAnswer"]:
                        score += 1
                        st.success(f"Q{idx+1}: Correct! {q_data['Explanation']}")
                    else:
                        st.error(f"Q{idx+1}: Incorrect. The answer is {q_data['CorrectAnswer']}. {q_data['Explanation']}")
                
                if score == len(lesson.get("CEQuestions", [])):
                    st.balloons()
                    st.success("🎉 CE Credit Earned! Logging to database...")
                    # Logs the CE credit to your master evaluation database seamlessly
                    log_evaluation_to_sheet(
                        preceptor="AI-CE-System",
                        resident=learner_id,
                        rotation=st.session_state.get('current_ce_topic', 'CE Module'),
                        objective="Point-of-Care Microlearning",
                        criteria="CE Credit Earned",
                        grade="Pass",
                        comment="Completed AI-generated quiz based on live clinical dictation.",
                        action_plan="",
                        narrative=st.session_state[text_key]
                    )

def render_curriculum(current_role, current_tier):
    if curriculum_df.empty:
        st.warning("Curriculum data is currently unavailable.")
        return

    st.subheader("📚 Vision Curriculum Library")
    all_cats = curriculum_df['Category / Module'].dropna().unique()
    
    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        main_cat = st.selectbox("Navigate Module", all_cats, key="curr_cat_sel")
    
    module_items = curriculum_df[curriculum_df['Category / Module'] == main_cat]
    with col_nav2:
        selected_item_name = st.selectbox("Select Resource", module_items['Topic'].unique(), key="curr_top_sel")
    
    topic_items = module_items[module_items['Topic'] == selected_item_name]
    first_item = topic_items.iloc[0]

    st.write("---")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"📖 {first_item['Topic']}")
    with col2:
        check_key = f"complete_{username}_{first_item['Topic']}"
        is_complete = st.toggle("✅ Mark as Complete", key=check_key)

    if is_complete:
        st.success(f"Awesome job! '{first_item['Topic']}' marked as complete.")

    epa_text = first_item.get('EPA', 'N/A')
    bloom_text = first_item.get('Cognitive Domain', 'N/A')
    miller_text = first_item.get('Competence Level (Miller)', 'N/A')
    
    st.caption(f"EPA: {epa_text} | Target (Bloom's): {bloom_text} | Competence (Miller's): {miller_text}")
    st.markdown(f"**Objective:** {first_item.get('ASHP Objective', 'N/A')}")

    available_types = [
        str(res).strip() if pd.notna(res) and str(res).strip() != "" else f"Resource {i+1}" 
        for i, res in enumerate(topic_items['Resource Type'].tolist())
    ]
    
    if not available_types:
        st.warning("No multimedia resources attached to this topic.")
        # Ensure the quiz still renders even if there are no videos/links
        render_module_quiz(quiz_bank_df, first_item['Topic'])
        return
        
    st.write("---")
    resource_tabs = st.tabs(available_types)
    for idx, tab in enumerate(resource_tabs):
        with tab:
            row_data = topic_items.iloc[idx]
            res_type = str(row_data['Resource Type']).strip()
            res_url = str(row_data['Resource URL (Published)']).strip()

            if pd.isna(res_url) or res_url == "" or res_url.lower() == "nan":
                st.info(f"No link provided for {res_type}.")
                continue

            is_premium = "youtube.com" in res_url.lower() or "youtu.be" in res_url.lower() or "notebooklm" in res_url.lower()
            has_access = True
            
            if is_premium and current_role == "learner" and current_tier not in ["Pro", "Premium"]:
                has_access = False
                
            if not has_access:
                st.warning("⭐️ **Premium Feature**")
                st.button("Upgrade to Pro", key=f"upgrade_{idx}_{first_item['Topic']}", type="primary")
                continue 

            if "youtube.com" in res_url.lower() or "youtu.be" in res_url.lower():
                st.video(res_url)
            elif "notebooklm" in res_url.lower():
                st.info("💡 **Interactive AI Notebook**")
                st.link_button(f"Open NotebookLM", res_url, type="primary")
            elif "docs.google.com/presentation" in res_url.lower():
                embed_url = res_url.replace("/pub?", "/embed?").replace("/pub", "/embed")
                components.html(f'<iframe src="{embed_url}" width="100%" height="700" frameborder="0"></iframe>', height=700)
            elif "docs.google.com" in res_url.lower() or "forms.gle" in res_url.lower():
                embed_url = res_url
                if "embedded=true" not in embed_url and "forms.gle" not in embed_url:
                    embed_url += "&embedded=true" if "?" in embed_url else "?embedded=true"
                components.html(f'<iframe src="{embed_url}" width="100%" height="700" frameborder="0"></iframe>', height=700)
            else:
                st.link_button(f"Open {res_type} in New Tab", res_url)
                # Render the quiz at the bottom of the module view
    render_module_quiz(quiz_bank_df, first_item['Topic'])

def render_learner_dashboard(learner_id, config):
    st.subheader("🚀 My Performance & Rewards")

    # 1. Front and center Garmin tracker
    render_step_counter(learner_id=learner_id, weekly_goal=5)
    st.divider()

    # 2. Get recent evaluations
    live_eval_df = get_evaluation_log(active_sheet_name)
    if live_eval_df.empty:
        st.info("Awaiting your first clinical evaluation...")
        return

    my_evals = get_learner_evals(live_eval_df, config, learner_id)
    if my_evals.empty:
        st.info("No evaluations on record yet. Get out there and hustle!")
        return

    # Sort to get the most recent ones
    my_evals['Timestamp'] = pd.to_datetime(my_evals['Timestamp'], errors='coerce')
    recent_evals = my_evals.sort_values(by='Timestamp', ascending=False).head(5) # Show top 5

    st.subheader("⚾ Recent Clinical Plays & Bonus Opportunities")
    st.caption("Turn your recent evaluations into extra credit by completing targeted micro-learning.")

    for idx, row in recent_evals.iterrows():
        # Safely extract the topic/objective name
        eval_col = config.get('evaluation_column', 'ASHP Objective')
        topic = str(row.get(eval_col, row.get('ASHP Objective', 'Unknown Topic'))).strip()
        grade = row.get('Grade', 'N/A')
        date_str = row['Timestamp'].strftime('%b %d, %Y') if pd.notna(row['Timestamp']) else "Recent"
        preceptor = row.get('Preceptor Name', 'Preceptor')

        # The Banana Ball "Extra Point" Expander
        with st.expander(f"🏅 {date_str} | {topic} (Grade: {grade})"):
            st.markdown(f"**Evaluator:** {preceptor}")
            st.markdown(f"**Feedback:** {row.get('Comment', 'No comment provided.')}")
            st.write("---")
            
            # The Gamification Prompt
            st.markdown("### 🍌 Earn Bonus Points")
            st.info(f"Want to lock in your knowledge on **{topic}** and boost your clinical score?")

            # Provide the quick reference material if it exists in the curriculum
            if not curriculum_df.empty:
                topic_resources = curriculum_df[curriculum_df['Topic'] == topic]
                if not topic_resources.empty:
                    res_url = topic_resources.iloc[0].get('Resource URL (Published)', None)
                    if pd.notna(res_url) and str(res_url).strip() != "":
                        st.link_button("📚 Open Quick Review Material", res_url)

            # Instantly render the quiz for this specific topic!
            # We pass the index (idx) to prevent duplicate key errors if the same topic appears twice
            render_module_quiz(quiz_bank_df, topic, unique_suffix=f"dash_{idx}")

def render_learner_voice_journal(resident_id, active_config, eval_set):
    """A dedicated Voice-to-PharmAcademic tool for Resident Self-Reflection."""
    
    # 1. CLEAN APP HEADER FOR LEARNER
    st.markdown("""
        <style>
        .main .block-container { max-width: 500px; margin: 0 auto; }
        [data-testid="stAudioInput"] { transform: scale(1.1); margin-top: 15px; margin-bottom: 15px; }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown("<h2 style='text-align: center; color: #1E1E1E;'>🎙️ Clinical Voice Journal</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #666; font-size: 15px; margin-top: -10px;'>Dictate your clinical thought process</p>", unsafe_allow_html=True)

    # ==========================================
    # NEW: LEARNER DAILY MISSION INJECTION
    # ==========================================
    prime_state_key = f"learner_prime_{resident_id}_{datetime.now().strftime('%Y%m%d')}"
    
    if prime_state_key not in st.session_state:
        with st.spinner("🤖 Booting Daily Mission Brief..."):
            # A. Get Recent Evaluations Context
            live_df = get_evaluation_log(active_sheet_name)
            my_evals = get_recent_evals(live_df, active_config, resident_id, days=14).head(3)
            evals_text = "No recent evaluations on file."
            if not my_evals.empty:
                # Safely extract the objective and grade column data
                eval_col = active_config.get('evaluation_column', 'ASHP Objective')
                evals_text = ", ".join([f"{row.get(eval_col, 'Task')} ({row.get('Grade', 'N/A')})" for _, row in my_evals.iterrows()])
            
            # B. Get Schedule Context
            today_sched = get_todays_schedule(resident_id)
            sched_text = "Standard clinical workflow."
            if not today_sched.empty and 'Subject' in today_sched.columns:
                sched_text = ", ".join(today_sched['Subject'].dropna().astype(str).tolist())
                
            learner_name = learner_dict.get(resident_id, resident_id)
            st.session_state[prime_state_key] = generate_learner_prime(learner_name, sched_text, evals_text)

    # Display the Daily Mission Briefing right above the microphone
    st.markdown(f"""
        <div style="background-color: #f3e5f5; border-left: 5px solid #9c27b0; padding: 15px; border-radius: 5px; margin-bottom: 20px; margin-top: 10px;">
            <strong style="color: #9c27b0;">🎯 Your Daily Mission</strong><br>
            <span style="color: #333; font-size: 14px;">{st.session_state[prime_state_key]}</span>
        </div>
    """, unsafe_allow_html=True)
    # ==========================================

    # 2. BACKGROUND VARIABLES (UI dropdowns removed for simplicity)
    # These hold placeholder values until the AI infers the real ones from the CSV
    selected_rotation = "Pending AI Mapping"
    selected_action = "Pending AI Mapping"
    interaction_type = "Clinical Voice Journal"

    text_key = f"self_dictation_text_{resident_id}"
    if text_key not in st.session_state:
        st.session_state[text_key] = ""

    # 3. AUDIO CAPTURE USING NATIVE WIDGET (No tabs, clean UI)
    audio_bytes = None
    audio_mime = "audio/wav"
    
    recorded_audio = st.audio_input("Record Scenario", key=f"self_rec_{resident_id}")
    if recorded_audio:
        audio_bytes = recorded_audio.read()
        
    with st.expander("📁 Upload an existing audio file instead"):
        uploaded_audio = st.file_uploader("Upload (.wav, .mp3, .m4a)", type=["wav", "mp3", "m4a"], key=f"self_upload_{resident_id}", label_visibility="collapsed")
        if uploaded_audio:
            audio_bytes = uploaded_audio.read()
            if uploaded_audio.name.endswith(".mp3"): audio_mime = "audio/mp3"
            elif uploaded_audio.name.endswith(".m4a"): audio_mime = "audio/mp4"

    # 4. AUDIO PROCESSING BLOCK
    if audio_bytes:
        st.write("---")
        col_playback, col_actions = st.columns([1, 1])
        with col_playback:
            st.audio(audio_bytes, format=audio_mime)
        with col_actions:
            st.download_button(label="📥 Download Audio File", data=audio_bytes, file_name=f"clinical_dictation_journal.{audio_mime.split('/')[-1]}", mime=audio_mime, use_container_width=True)
            if st.button("✨ Send to Gemini for Transcription", type="primary", use_container_width=True, key=f"self_transcribe_btn_{resident_id}"):
                status_placeholder = st.empty()
                with status_placeholder.container():
                    st.info("🧠 Gemini is analyzing clinical audio... Please wait.")
                    st.progress(50)
                with st.spinner("Processing..."):
                    transcript = transcribe_clinical_audio(audio_bytes, mime_type=audio_mime)
                    if transcript:
                        st.session_state[text_key] = transcript
                        status_placeholder.success("✅ Transcription complete! Review below.")
                        st.rerun()
                    else:
                        status_placeholder.error("❌ Transcription failed.")

    # 3. TEXT AREA
    st.markdown("**Review & Edit Your Scenario**")
    st.text_area("Hidden Label", height=150, key=text_key, label_visibility="collapsed")

    # 4. AI MAPPING ENGINE (Auto-pulls from CSV)
    if st.button("✨ Map My Scenario to Objectives", type="primary", use_container_width=True, key="self_map_btn"):
        if len(st.session_state[text_key]) < 5:
            st.warning("Please record your scenario first!")
        else:
            with st.spinner("AI Coach is analyzing your scenario..."):
                # Dynamically pull the CSV objectives here so Gemini knows what to map it to
                available_topics = curriculum_df['Topic'].dropna().unique().tolist() if not curriculum_df.empty else ["General Clinical Action"]
                learner_name = learner_dict.get(resident_id, resident_id)
                
                ai_result = generate_ai_evaluation(
                    raw_dictation=st.session_state[text_key], 
                    learner_name=learner_name, 
                    config=active_config,
                    available_topics=available_topics
                )
                if ai_result:
                    st.session_state.self_eval_draft = ai_result

    # 5. DISPLAY AND SAVE TO DATABASE
    if "self_eval_draft" in st.session_state and st.session_state.self_eval_draft:
        draft = st.session_state.self_eval_draft
        st.divider()
        st.success("✅ Scenario Mapped Successfully!")
        
        st.subheader("PharmAcademic Self-Evaluation Draft")
        
        # Show the user what the AI inferred
        st.info(f"**Mapped Objective:** {draft.get('InferredObjective', 'Unknown')}\n\n**Mapped Rotation:** {draft.get('InferredRotation', 'Unknown')}")
        
        final_narrative = st.text_area("AI-Generated PharmAcademic Narrative", value=draft.get("Narrative", ""), height=150, key="self_narrative")
        action_plan = st.text_area("Your Action Plan for Next Time", value=draft.get("ActionPlan", ""), height=80, key="self_action")
        
        if st.button("💾 Submit to Preceptor / Log to Database", type="primary", key="self_save_btn"):
            with st.spinner("Saving self-evaluation..."):
                success = log_evaluation_to_sheet(
                    preceptor="SELF-REFLECTION", 
                    resident=resident_id,  
                    rotation=draft.get("InferredRotation", "Self-Directed"), # Uses the AI's smart choice
                    objective=draft.get("InferredObjective", "Self-Directed"), # Uses the AI's smart choice
                    criteria=draft.get("InferredInteraction", interaction_type), 
                    grade="Self-Assessed", 
                    comment="Submitted via Voice Journal",
                    action_plan=action_plan,
                    narrative=st.session_state[text_key], 
                    ai_quality_grade="Green",
                    pharmacademic_text=final_narrative
                )
                if success:
                    st.success("🎉 Scenario safely logged! Your preceptor can now review it.")
                    st.session_state.self_eval_draft = None
                    
def render_evaluation_tool():
    if not learner_dict:
        st.warning("No learners found in the system.")
        return

    st.markdown("""
        <style>
        .main .block-container {
            max-width: 500px; 
            padding-top: 2rem;
            padding-bottom: 5rem;
            margin: 0 auto;
        }
        .stSelectbox label { display: none; }
        [data-testid="stAudioInput"] {
            transform: scale(1.1); 
            margin-top: 20px;
            margin-bottom: 20px;
        }
        </style>
    """, unsafe_allow_html=True)

    nom = active_config["nomenclature"]
    eval_set = active_config["eval_settings"]
    topics = curriculum_df['Topic'].dropna().unique().tolist() if not curriculum_df.empty else ["No Curriculum Loaded"]

    # 1. CLEAN APP HEADER
    st.markdown("<h1 style='text-align: center; color: #1E1E1E;'>RxBricks</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #666; font-size: 16px; margin-top: -15px;'>Who are you coaching today?</p>", unsafe_allow_html=True)

    # 2. RESIDENT SELECTOR
    target_res_id = st.selectbox(
        "Select Learner", 
        options=list(learner_dict.keys()), 
        format_func=lambda x: learner_dict.get(x, "Unknown"),
        key="eval_tool_res"
    )
    current_preceptor = st.session_state.get("name", f"Unknown {nom['educator']}")

    # ==========================================
    # NEW: PRECEPTOR PRIME INJECTION 
    # ==========================================
    st.markdown("<br>", unsafe_allow_html=True)
    prime_state_key = f"prime_{target_res_id}_{datetime.now().strftime('%Y%m%d')}"
    
    if prime_state_key not in st.session_state:
        with st.spinner("🤖 Booting Preceptor Prime..."):
            live_df = get_evaluation_log(active_sheet_name)
            my_evals = get_recent_evals(live_df, active_config, target_res_id, days=30)
            learner_name = learner_dict.get(target_res_id, target_res_id)
            
            st.session_state[prime_state_key] = generate_preceptor_prime(learner_name, my_evals)

    # Display the Prime Briefing right above the microphone
    st.markdown(f"""
        <div style="background-color: #e3f2fd; border-left: 5px solid #1976d2; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
            <strong style="color: #1976d2;">🤖 Preceptor Prime</strong><br>
            <span style="color: #333; font-size: 14px;">{st.session_state[prime_state_key]}</span>
        </div>
    """, unsafe_allow_html=True)
    # ==========================================

    if 'eval_draft' not in st.session_state:
        st.session_state.eval_draft = None

    text_key = f"dictation_text_{target_res_id}"
    if text_key not in st.session_state:
        st.session_state[text_key] = ""

    # 3. MASSIVE CENTERED MICROPHONE (No Tabs!)
    audio_bytes = None
    audio_mime = "audio/wav"
    
    # The native audio widget is perfectly centered and pill-shaped
    recorded_audio = st.audio_input("Record", key=f"recorder_{target_res_id}")
    if recorded_audio:
        audio_bytes = recorded_audio.read()

    # We hide the "Upload File" option in an expander so it doesn't ruin the clean UI
    with st.expander("📁 Upload an existing audio file instead"):
        uploaded_audio = st.file_uploader("Upload (.wav, .mp3, .m4a)", type=["wav", "mp3", "m4a"], key=f"upload_{target_res_id}", label_visibility="collapsed")
        if uploaded_audio:
            audio_bytes = uploaded_audio.read()
            if uploaded_audio.name.endswith(".mp3"): audio_mime = "audio/mp3"
            elif uploaded_audio.name.endswith(".m4a"): audio_mime = "audio/mp4"

    # 4. PROCESS BUTTON
    if audio_bytes:
        st.write("---")
        if st.button("✨ Process Audio", type="primary", use_container_width=True, key=f"trans_{target_res_id}"):
            status_placeholder = st.empty()
            with status_placeholder.container():
                st.info("🧠 AI is routing your clinical audio...")
                st.progress(50)
            with st.spinner("Processing..."):
                transcript = transcribe_clinical_audio(audio_bytes, mime_type=audio_mime)
                if transcript:
                    st.session_state[text_key] = transcript
                    matcher = RxBricksScribeMatcher(curriculum_df) 
                    proven_bricks = matcher.analyze_transcript(transcript)
                    ai_result = generate_ai_evaluation(
                        raw_dictation=transcript, 
                        learner_name=learner_dict.get(target_res_id, target_res_id), 
                        config=active_config,
                        available_topics=topics,
                        proven_bricks=proven_bricks
                    )
                    if ai_result:
                        st.session_state.eval_draft = ai_result
                        status_placeholder.success("✅ Complete! Review below.")
                        st.rerun()
                else:
                    status_placeholder.error("❌ Transcription failed.")

    # 5. REVIEW & SAVE LOGIC (Hidden until the AI finishes)
    if "eval_draft" in st.session_state and st.session_state.eval_draft:
        draft = st.session_state.eval_draft
        st.divider()
        
        st.markdown("**Review & Edit Your Raw Dictation**")
        st.text_area("Hidden Label", height=80, key=text_key, label_visibility="collapsed")
        
        q_grade = draft.get("QualityGrade", "Green")
        if q_grade == "Red":
            st.error(f"🔴 **AI Coach:** {draft.get('QualityFeedback')}")
        elif q_grade == "Yellow":
            st.warning(f"🟡 **AI Coach:** {draft.get('QualityFeedback')}")

        st.markdown("<p style='text-align: center; color: #666; font-size: 14px;'>📋 AI-Inferred Routing</p>", unsafe_allow_html=True)
        
        col_c, col_d = st.columns(2)
        with col_c:
            safe_rot = draft.get("InferredRotation", eval_set.get("rotations", ["Default"])[0])
            if safe_rot not in eval_set.get("rotations", []): safe_rot = eval_set.get("rotations", ["Default"])[0]
            final_rot = st.selectbox("Rotation", eval_set.get("rotations", ["Default"]), index=eval_set.get("rotations", ["Default"]).index(safe_rot), key=f"frot_{target_res_id}")
            
            safe_obj = draft.get("InferredObjective", topics[0] if topics else "Unknown")
            if safe_obj not in topics: topics.insert(0, safe_obj) 
            final_obj = st.selectbox("Objective", topics, index=topics.index(safe_obj), key=f"fobj_{target_res_id}")

        with col_d:
            safe_grade = draft.get("InferredGrade", eval_set["grading_scale"][2] if len(eval_set["grading_scale"]) > 2 else "Pass")
            if safe_grade not in eval_set["grading_scale"]: safe_grade = eval_set["grading_scale"][0]
            final_grade = st.selectbox("Grade", eval_set["grading_scale"], index=eval_set["grading_scale"].index(safe_grade), key=f"fg_{target_res_id}")
            
            interaction_opts = ["Clinical Scenario", "Topic Discussion", "Case Presentation", "Journal Club", "Project Review"]
            safe_int = draft.get("InferredInteraction", interaction_opts[0])
            if safe_int not in interaction_opts: safe_int = interaction_opts[0]
            final_interaction = st.selectbox("Interaction", interaction_opts, index=interaction_opts.index(safe_int), key=f"fint_{target_res_id}")
            
        final_comment = st.text_input("Comment", value=draft.get("Comment", ""), key=f"fc_{target_res_id}")
        final_action = st.text_area("Action Plan", value=draft.get("ActionPlan", ""), height=60, key=f"fa_{target_res_id}")
        final_narrative = st.text_area("Final Narrative", value=draft.get("Narrative", ""), height=100, key=f"fn_{target_res_id}")
        
        if st.button("💾 Confirmed: Save to Database", type="primary", key=f"save_{target_res_id}", use_container_width=True):
            with st.spinner("Saving securely..."):
                success = log_evaluation_to_sheet(
                    preceptor=current_preceptor, 
                    resident=target_res_id,  
                    rotation=final_rot,
                    objective=final_obj,
                    criteria=final_interaction,
                    grade=final_grade,
                    comment=final_comment,
                    action_plan=final_action,
                    narrative=st.session_state[text_key],
                    ai_quality_grade=q_grade,
                    pharmacademic_text=final_narrative
                )
                if success:
                    st.balloons()
                    st.success("🎉 Safely logged to Database! Ready for export.")
                    st.session_state.eval_draft = None
                    
def get_todays_schedule(target_id=None):
    if schedule_df.empty: return pd.DataFrame()
    
    start_col = 'Start Date' if 'Start Date' in schedule_df.columns else 'Date'
    if start_col not in schedule_df.columns: return pd.DataFrame()
        
    try:
        today_date = pd.to_datetime('today').normalize()
        start_dates = pd.to_datetime(schedule_df[start_col], errors='coerce').dt.normalize()
        
        # FUNDAMENTAL FIX: Handle date ranges by checking the End Date
        if 'End Date' in schedule_df.columns:
            end_dates = pd.to_datetime(schedule_df['End Date'], errors='coerce').dt.normalize()
            # If a row has a Start Date but no End Date, make the End Date the same as Start Date
            end_dates = end_dates.fillna(start_dates)
            
            # Keep rows where today is greater than/equal to Start, AND less than/equal to End
            mask_date = (start_dates <= today_date) & (end_dates >= today_date)
        else:
            # Fallback to strict match if the End Date column doesn't exist
            mask_date = (start_dates == today_date)
            
        today_sched = schedule_df[mask_date].copy()
    except Exception:
        return pd.DataFrame()
    
    if target_id and not today_sched.empty:
        id_col = active_config.get("learner_id_column", "Learner_ID")
        if id_col not in schedule_df.columns:
            id_col = active_config.get("learner_column", "Resident Name")
            
        # Expanded fallback list to catch your CSV headers
        if id_col not in schedule_df.columns:
            for fallback in ["Assigned To", "Candidate Name", "Resident", "Resident Name", "Student Name", "Student", "Name", "Learner"]:
                if fallback in schedule_df.columns:
                    id_col = fallback
                    break
                    
        if id_col in schedule_df.columns:
            # Handle "All" logic and strip whitespace to guarantee user matches
            mask_user = (
                (today_sched[id_col].astype(str).str.strip().str.lower() == str(target_id).strip().lower()) |
                (today_sched[id_col].astype(str).str.strip().str.lower() == 'all')
            )
            today_sched = today_sched[mask_user]
        else:
            return pd.DataFrame()
            
    return today_sched

def get_daily_ce_mission(learner_id):
    """Dynamically builds a mission using the specific Actionable_Activity and Scribe_Signals."""
    today_sched = get_todays_schedule(learner_id)
    
    if today_sched.empty:
        return None
        
    target_subject = today_sched.iloc[0].get('Subject', None)
    if not target_subject:
        return None
        
    # Default fallback baseline
    mission_data = {
        "topic": target_subject,
        "standard": "General Clinical Application",
        "actionable_prompt": f"Identify a relevant therapy related to {target_subject} and discuss its clinical application.",
        "target_level": "Shows How",
        "domain": "Application",
        "signals": "No specific keywords required." # <-- NEW LINE
    }
    
    if not curriculum_df.empty:
        match = curriculum_df[curriculum_df['Topic'] == target_subject]
        if not match.empty:
            row = match.iloc[0]
            
            ashp_obj = row.get('ASHP Objective', '')
            epa = row.get('EPA', '')
            miller_level = row.get('Competence Level (Miller)', '')
            bloom_domain = row.get('Cognitive Domain', '')
            action_activity = row.get('Actionable_Activity', '')
            
            # THE UPGRADE: Grab the specific scribe signals we merged via SQL
            scribe_signals = row.get('Scribe_Signals', '')
            
            core_standard = ashp_obj if pd.notna(ashp_obj) and str(ashp_obj).strip() != "" else epa
            
            if pd.notna(core_standard) and str(core_standard).strip() != "":
                mission_data["standard"] = core_standard
            if pd.notna(miller_level) and str(miller_level).strip() != "":
                mission_data["target_level"] = miller_level
            if pd.notna(bloom_domain) and str(bloom_domain).strip() != "":
                mission_data["domain"] = bloom_domain
            if pd.notna(action_activity) and str(action_activity).strip() != "":
                mission_data["actionable_prompt"] = str(action_activity).strip()
                
            # If the merge found signals, add them to the mission data
            if pd.notna(scribe_signals) and str(scribe_signals).strip() != "":
                mission_data["signals"] = str(scribe_signals).strip()
                
    return mission_data    
def render_daily_operations(learner_id, role):
    env_type = active_config.get("env_type", "clinical")
    st.markdown("## Daily Operations Command Center")

    # 1. DYNAMIC SCHEDULE
    today_sched = get_todays_schedule(learner_id)
    sched_header = "🕒 My Dynamic Study Schedule" if env_type == "academic" else "🕒 My Dynamic Schedule"
    st.markdown(f"### {sched_header}")

    if not today_sched.empty:
        # Dynamically grab available columns to prevent missing column errors
        cols_to_show = [c for c in ['Start Time', 'End Time', 'Subject', 'Status'] if c in today_sched.columns]
        if not cols_to_show: cols_to_show = today_sched.columns.tolist()
        st.dataframe(today_sched[cols_to_show], hide_index=True, use_container_width=True)
    else:
        st.info("No specific blocks scheduled for today. Check your upcoming schedule below.")

    st.markdown("---")

    # 2. DYNAMIC MODULES/TOPICS
    task_header = "📚 Today's Study Modules & Activities" if env_type == "academic" else "📋 Today's Clinical Policies & Activities"
    st.markdown(f"### {task_header}")

    # FIXED: Changed task_mapping_df to rotation_tasks_df to match global variable
    if not rotation_tasks_df.empty:
        # Safe column selection based on what actually exists in your CSV
        available_cols = rotation_tasks_df.columns.tolist()
        view_cols = []
        if "Rotation_ID" in available_cols: view_cols.append("Rotation_ID")
        if "Actionable_Activity" in available_cols: view_cols.append("Actionable_Activity")
        if "Clinical_Policy" in available_cols: view_cols.append("Clinical_Policy")
        if "Policy_Link" in available_cols: view_cols.append("Policy_Link")

        if view_cols:
            st.dataframe(
                rotation_tasks_df[view_cols],
                column_config={"Policy_Link": st.column_config.LinkColumn("Resource Link") if "Policy_Link" in view_cols else None},
                hide_index=True,
                use_container_width=True
            )
        else:
            st.dataframe(rotation_tasks_df, hide_index=True, use_container_width=True)
    else:
        st.info("No modules mapped for today.")

def render_assignments(learner_id):
    st.subheader("📝 Pending Assignments & Tasks")
    if assignments_df.empty:
        st.info("No assignments data loaded.")
        return
        
    learner_name = learner_dict.get(learner_id, learner_id)
    if 'Assigned To' in assignments_df.columns:
        assignments_df['Assigned To'] = assignments_df['Assigned To'].fillna("All")
        mask = assignments_df['Assigned To'].apply(
            lambda x: learner_name.lower() in str(x).lower() or "all" in str(x).lower()
        )
        user_assignments = assignments_df[mask].copy() 
    else:
        user_assignments = assignments_df.copy()

    if 'Start Date' in user_assignments.columns:
        user_assignments['Start Date'] = pd.to_datetime(user_assignments['Start Date'], errors='coerce')
        today = pd.to_datetime(datetime.today())
        upcoming_assign = user_assignments[user_assignments['Start Date'] >= today].sort_values(by='Start Date').head(10)
    else:
        upcoming_assign = user_assignments.head(10)

    if upcoming_assign.empty:
        st.success("🎉 You have no pending assignments right now!")
        return

    # NEW: Categorize tasks by splitting the prefix (e.g., "LECTURE: Biostats" -> "LECTURE")
    upcoming_assign['Task_Type'] = upcoming_assign['Subject'].apply(
        lambda x: str(x).split(':')[0].strip().upper() if ':' in str(x) else 'GENERAL TASK'
    )
    
    # Iterate through the groups to create clean visual categories
    for task_type, group in upcoming_assign.groupby('Task_Type'):
        st.markdown(f"#### 🔹 {task_type}")
        
        for idx, row in group.iterrows():
            # Strip the prefix from the display title
            raw_title = str(row.get('Subject', 'Unknown Assignment'))
            assign_title = raw_title.split(':', 1)[-1].strip() if ':' in raw_title else raw_title
            
            # --- ROBUST LINK EXTRACTION ---
            form_link = None # Default to None instead of a generic URL
            possible_link_cols = ['Form Link', 'Resource URL (Published)', 'URL', 'Link', 'Assignment Link', 'Resource Link']
            
            # Check multiple common column names to find the actual link
            for col in possible_link_cols:
                if col in row.index and pd.notna(row[col]):
                    val = str(row[col]).strip()
                    # Ensure the cell isn't empty or reading as 'nan'
                    if val.lower() not in ["", "nan", "none"]:
                        form_link = val
                        break

            with st.expander(f"📌 **{assign_title}**", expanded=False):
                # Conditionally render the button ONLY if a link actually exists
                if form_link:
                    st.link_button("1️⃣ Open Assignment / Resource", form_link, type="primary")
                else:
                    st.info("No external resource linked for this assignment.")
                    
                st.checkbox("2️⃣ Mark as Submitted / Complete", key=f"submit_{learner_id}_{raw_title}_{idx}")
                
# FIXED: Completed this previously hanging function
def render_assignment_tracker():
    st.subheader("📋 Global Assignment Tracker")
    if assignments_df.empty: 
        st.warning("No assignments loaded.")
        return
    
    res_options = ["All Residents"] + list(learner_dict.keys())
    selected_res_id = st.selectbox(
        "Filter by Resident:", 
        res_options, 
        format_func=lambda x: "All Residents" if x == "All Residents" else learner_dict.get(x, x)
    )
    
    # Simple logic to render the dataframe based on selection
    if selected_res_id == "All Residents":
        st.dataframe(assignments_df, use_container_width=True)
    else:
        # Check if we have an assignment column, if not just show all
        if 'Assigned To' in assignments_df.columns:
            learner_name = learner_dict.get(selected_res_id)
            filtered_df = assignments_df[assignments_df['Assigned To'].str.contains(learner_name, case=False, na=True)]
            st.dataframe(filtered_df, use_container_width=True)
        else:
            st.dataframe(assignments_df, use_container_width=True)


def render_rpd_command_center(active_config, live_eval_df, weekly_goal=5):
    nom = active_config["nomenclature"]
    
    if live_eval_df is None or live_eval_df.empty: 
        st.info("No evaluation data available yet.")
        return
    
    if not learner_dict: return
        
    macro_data = []
    
    # 1. Calculate seven_days_ago
    seven_days_ago = pd.to_datetime('today') - pd.Timedelta(days=7)

    for res_id, res_name in learner_dict.items():
        res_df = get_learner_evals(live_eval_df, active_config, res_id).copy() # Use .copy() to avoid SettingWithCopyWarning
        total_evals = len(res_df)
        
        # 2. Ensure Timestamp is datetime for comparison
        if not res_df.empty and 'Timestamp' in res_df.columns:
             res_df['Timestamp'] = pd.to_datetime(res_df['Timestamp'], errors='coerce')
             recent_evals = len(res_df[res_df['Timestamp'] >= seven_days_ago])
        else:
             recent_evals = 0
             
        status = "🌟 Excelling (Goal Met)" if recent_evals >= weekly_goal else "⚠️ Falling Behind" if recent_evals > 0 else "🚨 Critical (0 Logged)"
            
        macro_data.append({
            "Resident": res_name,
            "7-Day Volume": recent_evals,
            "Total Lifetime": total_evals,
            "Pacing Status": status
        })
        
    macro_df = pd.DataFrame(macro_data)
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Total Program Evals", len(live_eval_df))
    with col2: st.metric("Program Evals This Week", sum(macro_df['7-Day Volume']))
    with col3: st.metric("Active Residents (7 Days)", f"{len(macro_df[macro_df['7-Day Volume'] > 0])} / {len(learner_dict)}")
        
    st.dataframe(macro_df, hide_index=True)

# =========================================================
# ROUTING & DASHBOARDS
# =========================================================

if user_role == "admin":        
    nom = active_config["nomenclature"]
    st.title(f"📈 {nom['director']} Dashboard")
    
    # WE SWAPPED THE FIRST TWO TABS HERE
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["👨‍🏫 Submit Evaluation", "📊 Reports & Progress", "📅 Daily Operations", "📋 Assignment Tracker", "🎓 Academic Records", "📝 Admin & Accreditation"])
    
    # TAB 1 IS NOW THE VOICE SCRIBE
    with tab1:
        render_evaluation_tool()

    # TAB 2 IS NOW THE DASHBOARD REPORTS
    with tab2:
        st.subheader(f"🌐 {nom['director'].split(' ')[0]} Command Center: Program Overview")
        
        # 1. Fetch the data FIRST
        live_eval_df = get_evaluation_log(active_sheet_name) 
        
        # 2. Pass the data INTO the function
        render_rpd_command_center(active_config, live_eval_df, weekly_goal=5)
        st.write("---")    
        
        st.subheader(f"📊 {nom['accreditation']} Accreditation Step Tracker")
        
        if not live_eval_df.empty:
            view_mode = st.radio("Select View", ["Program Overview", f"By {nom['learner']}"], horizontal=True)
            if view_mode == f"By {nom['learner']}":
                selected_res_id = st.selectbox(
                    f"Select {nom['learner']} to Audit", 
                    options=list(learner_dict.keys()), 
                    format_func=lambda x: learner_dict.get(x, x)
                )
                working_df = get_learner_evals(live_eval_df, active_config, selected_res_id)
            else:
                working_df = live_eval_df

            st.divider()
            col1, col2 = st.columns(2)
            
            target_goals = active_config.get("target_goals", {})
            items = list(target_goals.items())
            
            eval_col = active_config.get('evaluation_column', 'ASHP Objective')
            if eval_col not in working_df.columns:
                for fallback in ["ASHP Objective", "Competency Area", "Objective", "Target", "Area"]:
                    if fallback in working_df.columns:
                        eval_col = fallback
                        break

            if items: 
                half_point = len(items) // 2
                render_progress(col1, items[:half_point], working_df, eval_col)
                render_progress(col2, items[half_point:], working_df, eval_col)
            elif selected_env_key != "NAPLEX_PREP":
                st.info("No target goals are configured in the PROGRAM_CONFIG for this environment.")
        else:
            st.info("No evaluation data found. Start logging evaluations to see progress here!")

        # --- AI GAP ANALYSIS TOOL ---
        st.divider()
        st.subheader("🤖 AI Program Gap Analysis")
        col_audit1, col_audit2 = st.columns([2, 1])
        
        with col_audit1:
            # Dynamic targets based on curriculum
            audit_targets = curriculum_df['Topic'].dropna().unique().tolist() if not curriculum_df.empty else ["No targets loaded"]
            target_audit = st.selectbox("Select Standard to Audit", audit_targets)
        with col_audit2:
            st.write("") 
            st.write("")
            run_audit = st.button("Run AI Audit", type="primary", use_container_width=True)
            
        if run_audit and not live_eval_df.empty:
            audit_code = target_audit.split(" ")[0]
            audit_df = live_eval_df[live_eval_df[active_config['evaluation_column']].astype(str).str.contains(audit_code, na=False)]
            
            if len(audit_df) == 0:
                st.warning(f"No evaluations found for {target_audit}. Start logging to run an audit.")
            else:
                with st.spinner(f"AI Surveyor analyzing {len(audit_df)} evaluations..."):
                    # Pass active_config here
                    audit_report = run_gap_analysis(target_audit, audit_df, active_config)
                    with st.expander(f"📄 Official Audit Report: {target_audit}", expanded=True):
                        st.markdown(audit_report)
    
        # --- GRANULAR TRACKING ---
        st.divider()
        st.subheader(f"Granular {nom['learner']} Assignment Tracking")
        if learner_dict and not live_eval_df.empty:
            sel_res_id = st.selectbox(f"Review {nom['learner']} Progress:", list(learner_dict.keys()), format_func=lambda x: learner_dict.get(x, x), key="admin_report_res")
            render_step_tracker(sel_res_id)
            res_data = get_learner_evals(live_eval_df, active_config, sel_res_id)
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric(f"Total Completed Evaluations", len(res_data))
            with col_b:
                csv_export = res_data.to_csv(index=False).encode('utf-8')
                st.download_button(label="📥 Export Data (CSV)", data=csv_export, file_name=f"eval_report_{datetime.today().strftime('%Y-%m-%d')}.csv", mime='text/csv', type="primary")
            
            st.dataframe(res_data, use_container_width=True, hide_index=True)
       
    with tab3:
        st.subheader("📅 Today's Active Residents")
        today_all_sched = get_todays_schedule() # Fetches everyone on the schedule today
        
        if today_all_sched.empty:
            st.info("No residents are formally scheduled for rotations today.")
        else:
            name_col = active_config.get("learner_column", "Resident Name")
            display_cols = [name_col, 'Subject']
            if 'Start Time' in today_all_sched.columns: display_cols.append('Start Time')
            if 'End Time' in today_all_sched.columns: display_cols.append('End Time')
            
            learner_col = active_config.get('learner_column', 'Resident Name')
                
            # --- NEW: Safely filter for columns that actually exist ---
            desired_cols = [learner_col, 'Subject', 'Start Time', 'Status']
            display_cols = [col for col in desired_cols if col in today_all_sched.columns]
            
            if display_cols:
                st.dataframe(today_all_sched[display_cols], hide_index=True, use_container_width=True)
            else:
                # Fallback: Just show the whole dataframe if the desired columns are missing
                st.dataframe(today_all_sched, hide_index=True, use_container_width=True)
            # ----------------------------------------------------------
            
            # Loop through today's residents and show their expected actions
            for idx, row in today_all_sched.iterrows():
                res_name = row.get(name_col, 'Unknown Learner')
                rotation_subject = row.get('Subject', 'Unknown Rotation')
                
                with st.expander(f"🩺 {res_name} | {rotation_subject}"):
                    daily_tasks = rotation_tasks_df[rotation_tasks_df['Rotation_ID'] == rotation_subject]
                    if not daily_tasks.empty:
                        st.markdown("**Mapped Clinical Actions & Policies:**")
                        st.dataframe(daily_tasks[['Actionable_Activity', 'Clinical_Policy']], hide_index=True, use_container_width=True)
                    else:
                        st.caption("No specific mapped actions found for this rotation.")
        
    with tab4: 
        render_assignment_tracker()

    with tab5:
        st.subheader("Resident Academic Records")
        if learner_dict:
            target_res_id = st.selectbox("Select Resident Record:", list(learner_dict.keys()), format_func=lambda x: learner_dict.get(x, x), key="admin_profile_res")
            render_resident_profile(target_res_id, is_preceptor_view=True)
            
    with tab6:
        st.header("📝 AI Document & Accreditation Engine")
        st.caption(f"Instantly generate formatted {nom['committee_short']} meeting minutes and formal {nom['accreditation']} progress reports from shorthand notes.")
        
        doc_tabs = st.tabs([f"👥 {nom['committee_short']} Meeting Minutes", f"🏛️ {nom['accreditation']} Progress Report"])
        
        with doc_tabs[0]:
            st.subheader(f"{nom['committee']} Scribe")
            col_date, col_time = st.columns(2)
            with col_date: rac_date = st.date_input("Meeting Date", datetime.today())
            with col_time: rac_time = st.text_input("Meeting Time", value="1400-1430")
                
            rac_context = f"Date: {rac_date.strftime('%Y-%m-%d')}, Time: {rac_time}"
            rac_notes = st.text_area("Raw Meeting Notes:", height=200, key="rac_raw_notes")
            
            if st.button(f"✨ Generate Official {nom['committee_short']} Minutes", type="primary", key="btn_rac"):
                if rac_notes:
                    with st.spinner("Synthesizing meeting minutes..."):
                        # Pass active_config here
                        generated_minutes = generate_admin_document("COMMITTEE", rac_notes, active_config, rac_context)
                        if generated_minutes: st.session_state['draft_rac'] = generated_minutes
                else: st.warning("Please provide meeting notes.")
                    
            if 'draft_rac' in st.session_state:
                st.write("---")
                final_rac = st.text_area("Review and Edit (Markdown format):", value=st.session_state['draft_rac'], height=400)
                st.download_button("📥 Download as Text File", data=final_rac, file_name=f"{nom['committee_short']}_Minutes_{rac_date.strftime('%Y-%m-%d')}.txt", mime="text/plain")

        with doc_tabs[1]:
            st.subheader(f"{nom['accreditation']} Progress Report Generator")
            
            clean_standards = ["Standard 3.1.c (Fallback Mode - CSV Not Loaded)"]
            
            if not ashp_standards_df.empty:
                std_col = active_config.get('standards_column')
                
                # SAFETY NET: Check if the configured column actually exists in the loaded sheet
                if std_col and std_col in ashp_standards_df.columns:
                    valid_standards = ashp_standards_df[std_col].dropna().tolist()
                else:
                    # Fallback: Just grab whatever is in the first column of the standards tab
                    valid_standards = ashp_standards_df.iloc[:, 0].dropna().tolist()
                
                # FIXED: Removed the aggressive filter that required the word "Standard" or a digit
                clean_standards = [s for s in valid_standards if str(s).strip() != ""]
                
                # If the fallback resulted in an empty list, provide a safe default
                if not clean_standards:
                     clean_standards = ["No valid standards found in column."]
                
            st.write(f"🏛️ **1. Select Cited Standard**")
            selected_standard = st.selectbox(f"Select from {nom['accreditation']} framework:", options=clean_standards, key="ashp_std_dropdown")
            
            st.write("🛠️ **2. Corrective Action Narrative**")
            ashp_notes = st.text_area("Briefly explain the fix:", height=100, key="ashp_raw_notes")
            
            st.write("🔗 **3. Inject Live Platform Evidence**")
            col_ev1, col_ev2 = st.columns(2)
            with col_ev1: attach_evals = st.checkbox("📊 Attach Live Evaluation Metrics")
            with col_ev2: attach_tasks = st.checkbox("📋 Attach Clinical Task/Tracking Data")

            if st.button(f"✨ Draft Data-Backed {nom['accreditation']} Response", type="primary", key="btn_ashp"):
                if selected_standard and ashp_notes:
                    with st.spinner("Compiling platform data..."):
                        platform_evidence = "\n--- LIVE PROGRAM DATA ---\n"
                        
                        if attach_evals:
                            live_eval_df = get_evaluation_log(active_sheet_name)
                            if not live_eval_df.empty:
                                total_evals = len(live_eval_df)
                                res_count = live_eval_df[active_config['learner_column']].nunique() if active_config['learner_column'] in live_eval_df.columns else 0
                                platform_evidence += f"- EVALUATIONS: Logged {total_evals} evaluations across {res_count} active {nom['learner'].lower()}s.\n"
                        
                        if attach_tasks and not assignments_df.empty:
                            platform_evidence += f"- TASKS: Managing {len(assignments_df)} active clinical assignments.\n"
                        
                        combined_notes = f"NARRATIVE CONTEXT:\n{ashp_notes}\n{platform_evidence}"
                        # Pass active_config here
                        generated_response = generate_admin_document("ACCREDITATION", combined_notes, active_config, context=selected_standard)
                        
                        if generated_response: st.session_state['draft_ashp'] = generated_response
                else: st.warning("Please provide a brief narrative.")
                    
            if 'draft_ashp' in st.session_state:
                st.write("---")
                final_ashp = st.text_area("Review and Edit:", value=st.session_state['draft_ashp'], height=400)
                st.download_button("📥 Download Response", data=final_ashp, file_name=f"{nom['accreditation']}_Response_Draft.txt", mime="text/plain")
                
elif user_role == "preceptor":
    st.title("👨‍🏫 Preceptor Dashboard")
    
    # --- RESTORED: Today's Schedule Overview ---
    today_date_str = datetime.today().strftime('%Y-%m-%d')
    st.subheader(f"📅 Today: {today_date_str}")
    today_all_sched = get_todays_schedule()
    
    if not today_all_sched.empty:
        name_col = active_config.get("learner_column", "Resident Name")
        display_cols = [name_col, 'Subject']
        if 'Start Time' in today_all_sched.columns: display_cols.append('Start Time')
        if 'End Time' in today_all_sched.columns: display_cols.append('End Time')
        st.dataframe(today_all_sched[display_cols], hide_index=True, use_container_width=True)
    else:
        st.info("No residents scheduled for clinical rotations today.")
    st.divider()
    # -------------------------------------------

    tab1, tab2, tab3, tab4 = st.tabs(["👨‍🏫 Evaluate Resident", "📈 Resident Status", "📚 Curriculum Library", "🎓 Academic Records"])
   
    with tab1:
        render_evaluation_tool()
        
    with tab2:
        st.subheader("Resident Progress Status")
        if learner_dict:
            stat_res_id = st.selectbox("Check Status for:", list(learner_dict.keys()), format_func=lambda x: learner_dict.get(x, x), key="prec_stat_res")
            render_step_tracker(stat_res_id)
            
            # --- RESTORED: Recent Evaluations Table ---
            st.write("---")
            st.subheader("📈 Recent Evaluations (Last 10)")
            live_eval_df = get_evaluation_log(active_sheet_name)
            if not live_eval_df.empty:
                res_evals = get_learner_evals(live_eval_df, active_config, stat_res_id)
                if not res_evals.empty:
                    res_evals['Timestamp'] = pd.to_datetime(res_evals['Timestamp'], errors='coerce')
                    recent_10 = res_evals.sort_values(by='Timestamp', ascending=False).head(10)
                    recent_10['Timestamp'] = recent_10['Timestamp'].dt.strftime('%Y-%m-%d %H:%M')
                    display_cols = ['Timestamp', 'Preceptor Name', 'Rotation', 'ASHP Objective', 'Grade']
                    valid_cols = [col for col in display_cols if col in recent_10.columns]
                    st.dataframe(recent_10[valid_cols], use_container_width=True, hide_index=True)
                else:
                    st.info("No recent evaluations found for this resident.")
            # -------------------------------------------
            
    with tab3:
        render_curriculum(user_role, user_tier)

    with tab4:
        st.subheader("Resident Academic Records")
        if learner_dict:
            target_res_id = st.selectbox("Select Resident Record:", list(learner_dict.keys()), format_func=lambda x: learner_dict.get(x, x), key="prec_profile_res")
            render_resident_profile(target_res_id, is_preceptor_view=True)

elif user_role == "learner":
    st.title(f"Welcome, {learner_dict.get(logged_in_id, logged_in_id)}!")
    
    st.markdown(f"**Cognitive Phenotype:** `{st.session_state.get('phenotype', 'Standard')}`")
    
    render_step_tracker(logged_in_id)
    st.write("---")
    
    # NEW TAB ORDER: Voice Capture is now Front and Center!
    if selected_env_key == "ABCGTBIO":
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎙️ Earn CE Credit", "🚀 Performance Dashboard", "🎯 Today's Plan", "📚 Curriculum Library", "🎓 Profile & CV"])
        with tab1:
            render_ce_case_logger(logged_in_id)
        with tab2:
            render_learner_dashboard(logged_in_id, active_config)
    else:
        # Standard display for EM and APPE learners
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎙️ Clinical Voice Journal", "🚀 Performance Dashboard", "🎯 Today's Plan", "📚 Curriculum Library", "🎓 Profile & CV"])
        with tab1:
            render_learner_voice_journal(logged_in_id, active_config, active_config.get("eval_settings", {}))
        with tab2:
            render_learner_dashboard(logged_in_id, active_config)
        
    with tab3:
        render_daily_operations(logged_in_id, user_role)
        render_assignments(logged_in_id)
        
        if not schedule_df.empty: 
            sched_df = schedule_df.copy()
            
            learner_col = active_config.get("learner_id_column", "Learner_ID")
            if learner_col not in sched_df.columns:
                learner_col = active_config.get("learner_column", "Resident Name")
            if learner_col not in sched_df.columns:
                for fallback in ["Candidate Name", "Resident", "Resident Name", "Student Name", "Student", "Name", "Learner"]:
                    if fallback in sched_df.columns:
                        learner_col = fallback
                        break
            
            if learner_col in sched_df.columns and 'Start Date' in sched_df.columns:
                st.divider()
                with st.expander("🛠️ Schedule Adjustments"):
                    st.info("💡 **Fell behind?** Use this tool to mark today's tasks as missed and automatically cascade your remaining study schedule.")
                    if st.button("🚨 Mark Today Missed & Recalculate", use_container_width=True):
                        with st.spinner("Cascading schedule..."):
                            today_date = pd.to_datetime('today').normalize()
                            today_mask = (sched_df[learner_col] == logged_in_id) & (pd.to_datetime(sched_df['Start Date'], errors='coerce').dt.normalize() == today_date)
                            sched_df.loc[today_mask, 'Status'] = 'Missed'
                            
                            exam_date = ""
                            if not users_df.empty and 'Exam_Date' in users_df.columns: 
                                user_row = users_df[users_df['Username'] == st.session_state["username"]]
                                if not user_row.empty:
                                    exam_date = user_row.iloc[0]['Exam_Date']

                            new_sched, msg = recalculate_cascade(sched_df, learner_col, logged_in_id, exam_date)
                            
                            if "successfully" in msg:
                                save_schedule_to_sheet(active_sheet_name, new_sched)
                                st.success(msg)
                                st.rerun()
                            else:
                                st.warning(msg)
            
    with tab4:
        render_curriculum(user_role, user_tier)
        
    with tab5:     
        render_resident_profile(logged_in_id, is_preceptor_view=False)
        
        # --- FEATURE FLAG CHECK ---
        if active_config.get("show_upcoming_schedule", True):
            
            if not schedule_df.empty:
                id_col = active_config.get("learner_id_column", "Learner_ID")
                
                if id_col not in schedule_df.columns:
                    id_col = active_config.get("learner_column", "Resident Name")
                    
                if id_col not in schedule_df.columns:
                    possible_fallbacks = ["Candidate Name", "Resident", "Resident Name", "Student Name", "Student", "Name", "Learner"]
                    for fallback in possible_fallbacks:
                        if fallback in schedule_df.columns:
                            id_col = fallback
                            break
                            
            # --- DYNAMIC UPCOMING SCHEDULE ---
            env_type = active_config.get("env_type", "clinical")
            sched_header = "📅 Upcoming Study Schedule" if env_type == "academic" else "📅 Upcoming Shifts"
            st.divider()
            st.subheader(sched_header)

            if not schedule_df.empty:
                id_col = active_config.get("learner_id_column", "Learner_ID")
                if id_col not in schedule_df.columns:
                    id_col = active_config.get("learner_column", "Resident Name")

                if id_col not in schedule_df.columns:
                    possible_fallbacks = ["Candidate Name", "Resident", "Resident Name", "Student Name", "Student", "Name", "Learner"]
                    for fallback in possible_fallbacks:
                        if fallback in schedule_df.columns:
                            id_col = fallback
                            break

                if id_col in schedule_df.columns:
                    my_sched_all = schedule_df[schedule_df[id_col].astype(str).str.strip() == str(logged_in_id).strip()].copy()
                    date_col = 'Start Date' if 'Start Date' in schedule_df.columns else 'Date'

                    if not my_sched_all.empty and date_col in my_sched_all.columns:
                        try:
                            my_sched_all[date_col] = pd.to_datetime(my_sched_all[date_col], errors='coerce')
                            my_sched_all = my_sched_all.dropna(subset=[date_col])

                            today_date = pd.to_datetime('today').normalize()
                            future_sched = my_sched_all[my_sched_all[date_col] >= today_date].sort_values(by=date_col)

                            if not future_sched.empty:
                                future_sched[date_col] = future_sched[date_col].dt.strftime('%Y-%m-%d')
                                display_cols = ['Subject', date_col]
                                if 'Start Time' in future_sched.columns: display_cols.append('Start Time')
                                st.table(future_sched[display_cols])
                            else:
                                st.info("No upcoming sessions scheduled. Enjoy the downtime!")
                        except Exception as e:
                            st.warning(f"Schedule dates could not be parsed. Error: {e}")
                    else:
                        st.info("No upcoming schedule data found for your user.")
                else:
                    st.warning("⚠️ Schedule Error: Could not find a matching student name column.")
            else:
                st.warning("Schedule data unavailable.")
