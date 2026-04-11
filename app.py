import zlib
import json
import requests
import datetime
import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
import bcrypt
import streamlit.components.v1 as components
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import google.generativeai as genai # NEW: Google AI import

# ==========================================\
# 0. MULTI-TENANT PROGRAM CONFIGURATION
# ==========================================\
PROGRAM_CONFIG = {
    "PGY2_EM": {
        "program_name": "PGY2 Emergency Medicine",
        "sheet_name": "01_MASTER_SHEET_EM",
        "standards_tab": "ASHP_Standards",
        "evaluation_column": "ASHP Objective"    # <--- ADD THIS
    },
    "APPE_CLINICAL": {
        "program_name": "University of Arizona APPE",
        "sheet_name": "02_MASTER_SHEET_APPE",
        "standards_tab": "APPE_Standards",
        "evaluation_column": "AACP EPA Evaluated"  # <--- ADD THIS (Match your tab header!)
    }
}

# ==========================================\
# 1. THE BACKEND WRITE-BACK FUNCTION (UPDATED)
# ==========================================\
def log_evaluation_to_sheet(preceptor, resident, rotation, objective, criteria, grade, comment, action_plan, narrative, ai_quality_grade="", pharmacademic_text=""):
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        # Assumes your secrets.toml has the raw json string under [raw_google_json]
        creds = Credentials.from_service_account_info(json.loads(st.secrets["raw_google_json"]), scopes=scopes)
        client = gspread.authorize(creds)
      
        sheet = client.open(active_sheet_name).worksheet("3_Evaluation_Log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Now writing 12 columns to match your CSV structure
        row_data = [
            timestamp, preceptor, resident, rotation, objective,
            criteria, grade, comment, action_plan, narrative,
            ai_quality_grade, pharmacademic_text
        ]
        
        sheet.append_row(row_data)
        return True
    except Exception as e:
        st.error(f"Error writing to Google Sheets: {e}")
        return False

# ==========================================\
# 2. THE AI EVALUATION SCRIBE & QUALITY GATE
# ==========================================\
def generate_ai_evaluation(raw_dictation, resident_name, rotation, topic, zone):
    """Evaluates preceptor input AND auto-fills the evaluation form fields using AI."""
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
    You are an expert Pharmacy Residency Program Director.
    First, evaluate the quality of the raw preceptor dictation. Then, format it into a highly professional clinical evaluation.
    
    Context:
    * Resident: {resident_name}
    * Rotation: {rotation}
    * Topic/Action: {topic}
    * Target Zone: {zone}
    
    Raw Preceptor Dictation:
    {raw_dictation}
    
    Output Requirements:
    Return ONLY a strict JSON object with exactly these 6 keys:
    1. "QualityGrade": String ("Green", "Yellow", or "Red"). Red means the dictation was lazy or lacked clinical context.
    2. "QualityFeedback": String (1 short sentence of direct coaching to the preceptor explaining *why* their dictation scored that grade).
    3. "Grade": Must be one of: "ACHR", "ACH", "SP", or "NI".
    4. "Comment": A 1-2 sentence professional assessment.
    5. "ActionPlan": 1-2 sentences detailing specific next steps.
    6. "Narrative": A comprehensive synthesis paragraph ready for PharmAcademic.
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
# ==========================================
# 2B. THE AI SCRIBE ENGINE (ADMIN & ASHP)
# ==========================================
def generate_admin_document(doc_type, raw_notes, context=""):
    """Processes raw notes into formal administrative reports."""
    try:
        if "GEMINI_API_KEY" not in st.secrets:
            st.error("🚨 Missing GEMINI_API_KEY in Streamlit secrets.")
            return None
            
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        if doc_type == "RAC":
            prompt = (
                "You are an expert clinical pharmacy Residency Program Director.\n"
                "Take these rough meeting notes and format them strictly into the following RAC Meeting Minutes template.\n"
                "Use Markdown tables for the structured data. Ensure a professional, objective tone.\n\n"
                f"Meeting Date/Time Context: {context}\n\n"
                "TEMPLATE STRUCTURE TO FOLLOW:\n"
                "# CTMFH-PGY2-EM - Residency Advisory Committee Meeting Minutes\n"
                "**Chair:** Craig Cocchio\n"
                "**Location:** Microsoft Teams\n\n"
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
        elif doc_type == "ASHP":
            prompt = (
                "You are an expert clinical pharmacy Residency Program Director responding to an ASHP accreditation survey.\n"
                "Take the cited standard and the raw notes regarding the program's corrective action, and format it into a formal ASHP Progress Report response.\n\n"
                f"Cited ASHP Standard/Area: {context}\n\n"
                "Format the output strictly as follows, using highly professional, accreditation-standard language:\n\n"
                "### ASHP Standard / Principle Cited:\n"
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

# ==========================================\
# 3. AI GAP ANALYSIS ENGINE (RPD AUDIT)
# ==========================================\
def run_gap_analysis(standard_name, evaluation_data_subset):
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    # We combine all the narratives for this standard into one giant text block for the AI to read
    combined_narratives = "\n---\n".join(evaluation_data_subset['Overall Narrative'].dropna().astype(str).tolist())
    
    prompt = f"""
    You are an expert ASHP Lead Surveyor auditing a Pharmacy Residency Program.
    Review the following preceptor evaluations submitted for the standard: {standard_name}.
    
    Your goal is to identify gaps in the residents' clinical exposure and recommend actionable steps for the Program Director.
    
    Output Requirements:
    Return a professional, markdown-formatted report with the following sections:
    1. **Current Strengths:** A brief summary of what the program is doing well regarding this standard.
    2. **Identified Gaps:** Specific clinical areas, patient populations, or entrustment levels that are missing from these evaluations.
    3. **Actionable Recommendations:** 2-3 specific things the RPD should assign or focus on next week to close these gaps.
    
    Raw Evaluation Data:
    {combined_narratives}
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error running AI Audit: {str(e)}"

# ==========================================
# 3. THE BACKEND READ FUNCTION (STEP COUNTER)
# ==========================================
@st.cache_data(ttl=60)
def get_evaluation_log():
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(json.loads(st.secrets["raw_google_json"]), scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open(active_sheet_name).worksheet("3_Evaluation_Log")
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Failed to load evaluation log: {e}")
        return pd.DataFrame()

# ==========================================
# 4. THE STEP COUNTER DASHBOARD COMPONENT
# ==========================================
def render_step_counter(resident_name, weekly_goal=5):
    st.subheader("🏃‍♂️ Clinical Step Counter")
    
    df = get_evaluation_log()
    
    if df.empty:
        st.info("No clinical actions logged yet. Go get some feedback!")
        return

    my_evals = df[df['Resident Name'] == resident_name].copy()
    
    if my_evals.empty:
        st.info("You haven't logged any actions yet this week. Hunt down a preceptor!")
        return

    my_evals['Timestamp'] = pd.to_datetime(my_evals['Timestamp'], errors='coerce')
    seven_days_ago = datetime.now() - pd.Timedelta(days=7)
    recent_evals = my_evals[my_evals['Timestamp'] >= seven_days_ago]
    
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
        
# =========================================================
# UI TRANSLATION DICTIONARY (ASHP to Clinical Role)
# =========================================================
ASHP_TO_CLINICAL_ROLE = {
    "R1.1.6": {"role_name": "Bedside Emergency Response", "ui_header": "### 🚨 Acute Medical Response & Direct Care", "description": "Ensure implementation of therapeutic regimens."},
    "R5.1.1": {"role_name": "Medical Emergency Management & Leadership", "ui_header": "### 🚨 Acute Medical Response & Direct Care", "description": "Demonstrate the essential role of the EM pharmacist in emergencies."},
    "R1.1.1": {"role_name": "Multidisciplinary Interaction & Drug Info", "ui_header": "### 🗣️ Multidisciplinary Interaction & Drug Info", "description": "Interact effectively with health care teams."},
    "R1.1.2": {"role_name": "Multidisciplinary Interaction & Drug Info", "ui_header": "### 🗣️ Multidisciplinary Interaction & Drug Info", "description": "Interact effectively with patients, family, and caregivers."},
    "R1.1.7": {"role_name": "Multidisciplinary Interaction & Drug Info", "ui_header": "### 🗣️ Multidisciplinary Interaction & Drug Info", "description": "Communicate and document direct patient care activities."},
    "R1.1.3": {"role_name": "Patient Work-ups & Preceptor Discussion", "ui_header": "### 🧠 Patient Work-ups & Preceptor Discussion", "description": "Collect and analyze information to base safe therapy."},
    "R1.1.4": {"role_name": "Patient Work-ups & Preceptor Discussion", "ui_header": "### 🧠 Patient Work-ups & Preceptor Discussion", "description": "Analyze and assess information for safe medication therapy."},
    "R1.1.5": {"role_name": "Patient Work-ups & Preceptor Discussion", "ui_header": "### 🧠 Patient Work-ups & Preceptor Discussion", "description": "Design safe and effective patient-centered therapeutic regimens."},
    "R1.1.8": {"role_name": "Patient Work-ups & Preceptor Discussion", "ui_header": "### 🧠 Patient Work-ups & Preceptor Discussion", "description": "Demonstrate responsibility for patient outcomes."},
    "R1.2.1": {"role_name": "Patient Work-ups & Preceptor Discussion", "ui_header": "### 🔄 Transitions of Care", "description": "Manage transitions of care effectively."},
    "R1.3.1": {"role_name": "Medication Preparation & Delivery", "ui_header": "### 💊 Medication Preparation & Delivery", "description": "Facilitate delivery of medications following best practices."},
    "R1.3.2": {"role_name": "Medication Preparation & Delivery", "ui_header": "### 💊 Medication Preparation & Delivery", "description": "Manage aspects of the medication-use process related to formulary."},
    "R1.3.3": {"role_name": "Medication Preparation & Delivery", "ui_header": "### 💊 Medication Preparation & Delivery", "description": "Facilitate aspects of the medication-use process."},
    "R2.1.1": {"role_name": "Systems Educator & Innovator", "ui_header": "### 📋 Departmental Responsibilities & Projects", "description": "Prepare or revise a drug class review, monograph, or guideline."},
    "R2.1.2": {"role_name": "Systems Educator & Innovator", "ui_header": "### 📋 Departmental Responsibilities & Projects", "description": "Identify opportunities for improvement of the medication-use system."},
    "R2.2.1": {"role_name": "Systems Educator & Innovator", "ui_header": "### 📋 Departmental Responsibilities & Projects", "description": "Identify and demonstrate understanding of specific project topic."},
    "ROTATION_EXPECTATION": {"role_name": "Departmental Responsibilities", "ui_header": "### 📋 General Rotation Expectations", "description": "General rotation expectations, meetings, and standard duties."}
}

# 1. SETTINGS & CONFIG
st.set_page_config(page_title="RxBricks: EM Trust Verification", layout="wide", page_icon="🧱")

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
# CORE DATA INGESTION (DYNAMIC API READ)
# ==========================================\
@st.cache_data(ttl=60)
def load_all_data(sheet_name, standards_tab_name):
    try:
        # Authenticate using existing secrets
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(json.loads(st.secrets["raw_google_json"]), scopes=scopes)
        client = gspread.authorize(creds)
        
        spreadsheet = client.open(sheet_name)
        
        curr = pd.DataFrame(spreadsheet.worksheet("1_Curriculum").get_all_records())
        resp = pd.DataFrame(spreadsheet.worksheet("Form Responses 1").get_all_records())
        sched = pd.DataFrame(spreadsheet.worksheet("4_Schedule").get_all_records())
        user_db = pd.DataFrame(spreadsheet.worksheet("3_Users").get_all_records())
        assign_df = pd.DataFrame(spreadsheet.worksheet("5_Assignments").get_all_records())
        rotation_tasks_df = pd.DataFrame(spreadsheet.worksheet("7_Rotation_Task_Mapping").get_all_records())
        ashp_df = pd.DataFrame(spreadsheet.worksheet(standards_tab_name).get_all_records()) 
        
        return curr, resp, sched, user_db, assign_df, rotation_tasks_df, ashp_df
        
    except Exception as e:
        st.error(f"⚠️ Database Connection Error. Ensure '{sheet_name}' is shared with your Google Service Account email. Details: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

curriculum_df, eval_df, schedule_df, users_df, assignments_df, rotation_tasks_df, ashp_standards_df = load_all_data(active_sheet_name, active_config["standards_tab"])

# 4. AUTHENTICATION SETUP
credentials = {"usernames": {}}
if not users_df.empty:
    for _, row in users_df.iterrows():
        uname = str(row['Username']).strip()
        raw_pw = str(row['Password']).strip()
        hpw = bcrypt.hashpw(raw_pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        role = str(row['Role']).strip().upper()
        if role == "RPD": r_internal = "admin"
        elif role == "RESIDENT": r_internal = "learner"
        else: r_internal = "preceptor"
        u_tier = str(row['Tier']).strip().capitalize() if 'Tier' in users_df.columns else "Basic"
        
        credentials["usernames"][uname] = {
            "email": str(row['Email']), "name": str(row['Name']),
            "password": hpw, "role": r_internal, "tier": u_tier
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

# --- NEW SAFETY CHECK ---
if username not in credentials["usernames"]:
    st.error("🚨 User database sync error. The app couldn't find your profile. This usually means one of your Google Sheet links (like the new ASHP one) is broken or not published as a CSV, causing the database to load empty.")
    st.stop()

user_role = credentials["usernames"][username]["role"]
user_tier = credentials["usernames"][username]["tier"]
authenticator.logout(location="sidebar")
st.sidebar.success(f"Logged in: {name} | Tier: {user_tier}")

if role in ["RPD", "Preceptor"]:
    st.divider()

# =========================================================
# REUSABLE COMPONENT: CURRICULUM VIEWER
# =========================================================
def render_curriculum(current_role, current_tier):
    if curriculum_df.empty:
        st.warning("Curriculum data is currently unavailable.")
        return

    st.subheader("📚 Vision 2026 Curriculum Library")
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
        st.warning("No resources attached to this topic.")
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
                st.write("Video lectures, audio podcasts, and AI NotebookLM integrations are reserved for Pro subscribers.")
                st.button("Upgrade to Pro", key=f"upgrade_{idx}_{first_item['Topic']}", type="primary")
                continue 

            if "youtube.com" in res_url.lower() or "youtu.be" in res_url.lower():
                st.video(res_url)
            elif "notebooklm" in res_url.lower():
                st.info("💡 **Interactive AI Notebook**\n\nGoogle NotebookLM requires a secure browser session. Click below to open your AI study guide.")
                st.link_button(f"Open NotebookLM", res_url, type="primary")
            elif "docs.google.com/presentation" in res_url.lower():
                embed_url = res_url.replace("/pub?", "/embed?").replace("/pub", "/embed")
                components.html(f'<iframe src="{embed_url}" width="100%" height="700" frameborder="0" allowfullscreen="true" mozallowfullscreen="true" webkitallowfullscreen="true"></iframe>', height=700)
            elif "docs.google.com" in res_url.lower() or "forms.gle" in res_url.lower():
                embed_url = res_url
                if "embedded=true" not in embed_url and "forms.gle" not in embed_url:
                    embed_url += "&embedded=true" if "?" in embed_url else "?embedded=true"
                components.html(f'<iframe src="{embed_url}" width="100%" height="700" frameborder="0" allowfullscreen="true" mozallowfullscreen="true" webkitallowfullscreen="true"></iframe>', height=700)
            else:
                st.link_button(f"Open {res_type} in New Tab", res_url)

# =========================================================
# REUSABLE COMPONENT: STEP TRACKER
# =========================================================
def render_step_tracker(resident_name):
    if eval_df.empty or curriculum_df.empty:
        st.caption("👟 **Step Tracker:** Awaiting evaluation data...")
        st.progress(0.0)
        return
        
    total_topics = len(curriculum_df['Topic'].unique())
    res_evals = eval_df[eval_df['Resident Name'] == resident_name]
    
    if 'Activity' in res_evals.columns:
        completed_topics = res_evals['Activity'].nunique()
    elif 'Topic' in res_evals.columns:
        completed_topics = res_evals['Topic'].nunique()
    else:
        completed_topics = len(res_evals) 
        
    progress_pct = min(completed_topics / total_topics, 1.0) if total_topics > 0 else 0.0
    
    st.markdown(f"**👟 Step Tracker:** `{completed_topics} / {total_topics}` Core Topics Evaluated")
    st.progress(progress_pct)


# =========================================================
# REUSABLE COMPONENT: MILESTONES & PROFILE
# =========================================================
def get_milestone_badges(resident_name):
    if curriculum_df.empty or eval_df.empty:
        return {}

    module_reqs = curriculum_df.groupby('Category / Module')['Topic'].nunique().to_dict()
    res_evals = eval_df[eval_df['Resident Name'] == resident_name]
    
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

def render_resident_profile(resident_name, is_preceptor_view=False):
    st.header(f"🎓 Professional Profile: {resident_name}")
    
    col_img, col_info = st.columns([1, 3])
    with col_img:
        st.image("https://cdn-icons-png.flaticon.com/512/387/387561.png", width=120) 
        
    with col_info:
        st.subheader("Clinical Pharmacy Resident")
        st.write("**Program:** Emergency Medicine PGY2")
        render_step_tracker(resident_name)

    st.divider()

    st.subheader("🏆 Clinical Milestones")
    badges = get_milestone_badges(resident_name)
    
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

    if is_preceptor_view:
        st.subheader("📋 Academic & Professional Record")
        st.caption("Official log of clinical competencies for residency accreditation review.")
        res_evals = eval_df[eval_df['Resident Name'] == resident_name]
        if not res_evals.empty:
            st.dataframe(res_evals, use_container_width=True)
        else:
            st.info("No formal evaluations on record yet.")
    else:
        st.subheader("📄 Automated CV Builder")
        st.caption("Copy this formatted text to update your curriculum vitae with your latest clinical achievements.")
        
        cv_text = f"### Core Competencies & Completed Modules\n"
        if completed_modules:
            for module in completed_modules.keys():
                cv_text += f"- **{module}:** Demonstrated independent clinical competence across all targeted therapeutic topics.\n"
        else:
            cv_text += "- *Modules currently in progress.*\n"
            
        cv_text += "\n### Advanced Clinical Actions\n"
        res_evals = eval_df[eval_df['Resident Name'] == resident_name]
        
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
# REUSABLE COMPONENT: EVALUATION TOOL (INTEGRATED)
# =========================================================
def render_evaluation_tool():
    res_names = users_df[users_df['Role'].str.upper() == 'RESIDENT']['Name'].tolist()
    if not res_names:
        st.warning("No residents found in the system.")
        return

    target_res = st.selectbox("Select Resident to Evaluate", res_names, key="eval_tool_res")
    current_preceptor = st.session_state.get("name", "Unknown Preceptor")
    
    render_step_tracker(target_res)
    st.write("---")

    # Initialize the session state for the draft
    if 'eval_draft' not in st.session_state:
        st.session_state.eval_draft = None

    # The clean, unified evaluation UI
    col_a, col_b = st.columns(2)
    with col_a:
        selected_rotation = st.selectbox("Rotation", ["CORE - 1 - EM", "CORE - 2 - EM", "CORE - 3 - ICU", "ELEC - Tox"], key=f"rot_{target_res}")
        selected_action = st.selectbox("Clinical Action", ["R1.1.1 (Therapeutic Regimens)", "R1.1.8 (Patient Outcomes)", "R5.1.1 (Medical Emergencies)"], key=f"act_{target_res}")
    with col_b:
        zone_action = st.selectbox("Target Entrustment", ["1 - Knows", "2 - Knows How", "3 - Shows How", "4 - Does"], key=f"zone_{target_res}")
        
    raw_dictation_1 = st.text_area("Preceptor Dictation / Rough Notes (Be honest!)", height=100, key=f"dict_{target_res}")
    
    if st.button("✨ Assess Quality & Draft Evaluation", type="primary", use_container_width=True, key=f"draft_btn_{target_res}"):
        if len(raw_dictation_1) < 5:
            st.warning("Please dictate a few words first!")
        else:
            with st.spinner("AI Coach is analyzing and drafting..."):
                ai_result = generate_ai_evaluation(raw_dictation_1, target_res, selected_rotation, selected_action, zone_action)
                if ai_result:
                    st.session_state.eval_draft = ai_result

    # --- SHOW THE RESULTS (THE WOW FACTOR) ---
    if st.session_state.eval_draft:
        draft = st.session_state.eval_draft
        st.divider()
        
        # The Pitch: The AI Scolding
        q_grade = draft.get("QualityGrade", "Green")
        if q_grade == "Red":
            st.error(f"🔴 **AI Preceptor Coach (Deficient Entry):** {draft.get('QualityFeedback')}")
            st.info("✨ *I have automatically expanded your entry to meet ASHP accreditation standards below. Please review and save.*")
        elif q_grade == "Yellow":
            st.warning(f"🟡 **AI Preceptor Coach (Borderline Entry):** {draft.get('QualityFeedback')}")
        else:
            st.success(f"✅ **AI Preceptor Coach (Robust Entry):** {draft.get('QualityFeedback')}")

        st.subheader("📋 PharmAcademic Draft")
        col_c, col_d = st.columns([1, 3])
        with col_c:
            # Fallback handling just in case the AI returns an unexpected grade string
            safe_grade = draft.get("Grade", "SP")
            if safe_grade not in ["ACHR", "ACH", "SP", "NI"]: safe_grade = "SP"
            
            final_grade = st.selectbox("Grade", ["ACHR", "ACH", "SP", "NI"], 
                                       index=["ACHR", "ACH", "SP", "NI"].index(safe_grade), 
                                       key=f"fg_{target_res}")
        with col_d:
            final_comment = st.text_input("Comment", value=draft.get("Comment", ""), key=f"fc_{target_res}")
            
        final_action = st.text_area("Action Plan", value=draft.get("ActionPlan", ""), height=80, key=f"fa_{target_res}")
        final_narrative = st.text_area("Overall Narrative (Editable)", value=draft.get("Narrative", ""), height=150, key=f"fn_{target_res}")
        
        if st.button("💾 Save to Master Database", type="primary", key=f"save_{target_res}"):
            with st.spinner("Writing securely to Google Sheets..."):
                success = log_evaluation_to_sheet(
                    preceptor=current_preceptor, 
                    resident=target_res,
                    rotation=selected_rotation,
                    objective=selected_action,
                    criteria="Clinical Scenario",
                    grade=final_grade,
                    comment=final_comment,
                    action_plan=final_action,
                    narrative=raw_dictation_1, 
                    ai_quality_grade=q_grade,
                    pharmacademic_text=final_narrative
                )
                if success:
                    st.success("🎉 Safely logged to Database! Ready for PharmAcademic export.")
                    st.balloons()
                    st.session_state.eval_draft = None
                        
# =========================================================
# DAILY ACTIVITIES & CLINICAL POLICIES MODULE
# =========================================================
def get_todays_schedule(target_name=None):
    if schedule_df.empty: return pd.DataFrame()
    today_str = datetime.today().strftime("%Y-%m-%d")
    
    date_col = 'Start Date' if 'Start Date' in schedule_df.columns else 'Date'
    today_sched = schedule_df[schedule_df[date_col] == today_str]
    
    if target_name:
        today_sched = today_sched[today_sched['Resident Name'] == target_name]
    return today_sched

def render_daily_operations(resident_name, current_role):
    st.subheader("🎯 Today's Clinical Policies & Activities")
    
    today_sched = get_todays_schedule(resident_name)
    
    if today_sched.empty:
        st.info("No specific clinical rotations scheduled today. Focus on curriculum modules or project work.")
        return

    rotation_subject = today_sched.iloc[0]['Subject']
    st.markdown(f"**Assigned Rotation:** `{rotation_subject}`")
    
    daily_tasks = rotation_tasks_df[rotation_tasks_df['Rotation_ID'] == rotation_subject].copy()
    
    if daily_tasks.empty:
        st.warning(f"No task mappings found for {rotation_subject}.")
        return

    if current_role == "learner":
        st.info("💡 **Today's Focus:** Review your daily operational tasks below. Click 'Policy & Application Details' to see how each task connects to your core residency objectives.")
        
        show_all_tasks = st.toggle("View all available rotation tasks", value=False)
        
        today_str = datetime.today().strftime('%Y-%m-%d')
        seed_string = f"{resident_name}_{rotation_subject}_{today_str}"
        daily_seed = zlib.crc32(seed_string.encode())
        
        if not show_all_tasks and len(daily_tasks) > 5:
            display_tasks = daily_tasks.sample(n=5, random_state=daily_seed)
            st.caption("🔄 *Showing 5 selected focus tasks for today to optimize learning. Toggle above to see the complete list.*")
        else:
            display_tasks = daily_tasks
            if len(daily_tasks) > 5:
                st.caption("⚠️ *Viewing full rotation task list.*")
        
        for idx, row in display_tasks.iterrows():
            action_text = row.get('Actionable_Activity', 'General Clinical Action')
            policy_name = row.get('Clinical_Policy', 'Standard Clinical Guidelines')
            policy_link = row.get('Policy_Link', '')
            sub_obj = str(row.get('ASHP_Sub_Objective', ''))
            action_verb = row.get('Action_Verb', 'execute')
            
            obj_code = sub_obj.replace('"', '').strip().split(' ')[0] if sub_obj and sub_obj != "nan" else "ROTATION_EXPECTATION"
            mapping_data = ASHP_TO_CLINICAL_ROLE.get(obj_code, {
                "role_name": "General Clinical Task",
                "description": "General clinical expectation."
            })

            display_policy = policy_name if pd.notna(policy_name) and policy_name != "nan" else "Standard Departmental Policy"
            
            st.markdown(f"#### 🎯 {action_text}")
            
            with st.expander(f"📘 Policy & Application Details: {display_policy}", expanded=False):
                st.markdown(f"**Objective `{obj_code}`:** {mapping_data['description']}")
                st.markdown(f"**Application:** To target the *{action_verb.lower()}* level of competence today, utilize this policy to guide your approach.")
                
                col1, col2 = st.columns([1, 2])
                with col1:
                    if pd.notna(policy_link) and str(policy_link).strip() != "" and str(policy_link) != "nan":
                        st.link_button(f"🔗 Review Policy", str(policy_link), type="primary", use_container_width=True)
                    else:
                        st.caption("No specific external link provided.")
                with col2:
                    st.checkbox(f"I understand how this policy applies.", key=f"ack_{resident_name}_{rotation_subject}_{idx}")
                
                if st.button(f"Mark '{display_policy}' Complete", key=f"complete_btn_{resident_name}_{rotation_subject}_{idx}"):
                    is_successful = log_task_completion(resident_name, display_policy, rotation_subject) 
                    if is_successful:
                        st.success(f"Successfully logged completion for {display_policy}!")
            
            st.divider()

    else:
        grouped_tasks = {}
        action_group = daily_tasks.groupby('Actionable_Activity')
        
        for action_text, group in action_group:
            sub_objs = group['ASHP_Sub_Objective'].dropna().astype(str).tolist()
            primary_sub_obj = sub_objs[0] if sub_objs else ""
            objective_code = primary_sub_obj.replace('"', '').strip().split(' ')[0] if primary_sub_obj else "ROTATION_EXPECTATION"
                
            mapping_data = ASHP_TO_CLINICAL_ROLE.get(objective_code, {
                "role_name": "General Clinical Task",
                "ui_header": "### 📋 General Clinical Tasks",
                "description": "General clinical expectation."
            })
            
            header = mapping_data['ui_header']
            if header not in grouped_tasks:
                grouped_tasks[header] = []
                
            target_level = str(group['Action_Verb'].iloc[0]) if 'Action_Verb' in group.columns else 'General Target'
            obj_codes_display = ", ".join([str(x).replace('"', '').strip().split(' ')[0] for x in sub_objs if pd.notna(x)])
            
            grouped_tasks[header].append({
                "activity": action_text,
                "codes": obj_codes_display,
                "target": target_level,
                "idx": group.index[0] 
            })

        for header, tasks in grouped_tasks.items():
            st.write("---")
            task_count = len(tasks)
            role_title = header.replace('### ', '')
            
            with st.expander(f"{role_title} ({task_count} unique tasks)", expanded=True):
                with st.container(height=400, border=False):
                    for task in tasks:
                        checkbox_key = f"{resident_name}_{rotation_subject}_{task['idx']}"
                        st.checkbox(
                            f"**[{task['codes']}]** {task['activity']} *(Target: {task['target']})*", 
                            key=checkbox_key
                        )


def render_assignments(resident_name):
    st.subheader("📝 Pending Assignments & Tasks")
    
    if assignments_df.empty:
        st.info("No assignments data loaded.")
        return
        
    if 'Assigned To' in assignments_df.columns:
        assignments_df['Assigned To'] = assignments_df['Assigned To'].fillna("All PGY2")
        mask = assignments_df['Assigned To'].apply(
            lambda x: resident_name.lower() in str(x).lower() or "all" in str(x).lower()
        )
        user_assignments = assignments_df[mask].copy() 
    else:
        user_assignments = assignments_df.copy()

    if 'Start Date' in user_assignments.columns:
        user_assignments['Start Date'] = pd.to_datetime(user_assignments['Start Date'], errors='coerce')
        today = pd.to_datetime(datetime.today())
        upcoming_assign = user_assignments[user_assignments['Start Date'] >= today].sort_values(by='Start Date').head(5)
    else:
        upcoming_assign = user_assignments.head(5)

    if upcoming_assign.empty:
        st.success("🎉 You have no pending assignments right now!")
        return

    for idx, row in upcoming_assign.iterrows():
        assign_title = row.get('Subject', 'Unknown Assignment')
        due_date = row['Start Date'].strftime('%B %d, %Y') if pd.notna(row.get('Start Date')) else "Ongoing"
        
        form_link = row.get('Form Link')
        if pd.isna(form_link) or str(form_link).strip() == "": 
            form_link = "https://docs.google.com/forms/d/e/1FAIpQLScB7n7l8VaKUGHJo60TCngFhnMF_YiBV-S-pY7xQO1p5bAkQg/viewform?usp=sharing&ouid=103419041044944178788"

        with st.expander(f"📌 **{assign_title}** — Due: {due_date}", expanded=(idx==0)):
            st.markdown(f"**Instructions:** Complete the required documentation for `{assign_title}`.")
            
            col1, col2 = st.columns([1, 1])
            with col1:
                st.link_button("1️⃣ Open Assignment Form", form_link, type="primary", use_container_width=True)
            with col2:
                submit_key = f"submit_{resident_name}_{assign_title}_{idx}"
                if st.checkbox("2️⃣ Mark as Submitted", key=submit_key):
                    st.success("Marked as complete! Your RPD can now review your submission.")

def render_assignment_tracker():
    st.subheader("📋 Global Assignment Tracker")
    
    if assignments_df.empty:
        st.info("No assignment data available to track.")
        return

    residents = users_df[users_df['Role'].str.upper() == 'RESIDENT']['Name'].tolist()
    if not residents:
        st.warning("No residents found in the system.")
        return

    tracker_data = []
    
    if 'Assigned To' not in assignments_df.columns:
        assignments_df['Assigned To'] = "All PGY2"
    else:
        assignments_df['Assigned To'] = assignments_df['Assigned To'].fillna("All PGY2")

    for res in residents:
        mask = assignments_df['Assigned To'].apply(
            lambda x: res.lower() in str(x).lower() or "all" in str(x).lower()
        )
        res_assignments = assignments_df[mask]
        
        for _, row in res_assignments.iterrows():
            assign_title = row.get('Subject', 'Unknown Assignment')
            start_date = row.get('Start Date', 'Ongoing')
            
            status = "⏳ Pending"
            if not eval_df.empty:
                res_col = 'Resident Name' if 'Resident Name' in eval_df.columns else None
                topic_col = 'Activity' if 'Activity' in eval_df.columns else ('Topic' if 'Topic' in eval_df.columns else None)
                
                if res_col and topic_col:
                    match = eval_df[(eval_df[res_col] == res) & (eval_df[topic_col] == assign_title)]
                    if not match.empty:
                        status = "✅ Submitted"

            tracker_data.append({
                "Resident Name": res,
                "Assignment Subject": assign_title,
                "Due Date": start_date,
                "Status": status
            })

    tracker_df = pd.DataFrame(tracker_data)

    if tracker_df.empty:
        st.info("No assignments currently mapped to residents.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Assigned Tasks", len(tracker_df))
    with col2:
        completed = len(tracker_df[tracker_df['Status'] == '✅ Submitted'])
        st.metric("Total Completed", completed)
    with col3:
        completion_rate = (completed / len(tracker_df)) * 100 if len(tracker_df) > 0 else 0
        st.metric("Program Completion Rate", f"{completion_rate:.1f}%")

    selected_res = st.selectbox("Filter by Resident:", ["All Residents"] + residents)
    
    display_df = tracker_df if selected_res == "All Residents" else tracker_df[tracker_df["Resident Name"] == selected_res]
    
    st.dataframe(display_df, use_container_width=True)

    st.write("---")
    st.subheader("📥 Export for Pharmacademic")
    st.caption("Generate a CSV report of these assignments to upload into Pharmacademic's document tracking system.")
    
    csv_data = display_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label=f"Download Report ({selected_res})",
        data=csv_data,
        file_name=f"Pharmacademic_Assignment_Report_{selected_res.replace(' ', '_')}_{datetime.today().strftime('%Y-%m-%d')}.csv",
        mime="text/csv",
        type="primary"
    )

def log_task_completion(resident_name, task_name, rotation):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

        if "raw_google_json" in st.secrets:
            creds_dict = json.loads(st.secrets["raw_google_json"])
        else:
            st.error("🚨 Secret Missing: Streamlit cannot find 'raw_google_json' in your settings.")
            return False 

        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        
        try:
            sheet = client.open("01_MASTER_SHEET_EM").worksheet("Task_Tracking")
        except gspread.exceptions.SpreadsheetNotFound:
            st.error("🚨 Access Denied: The Google Sheet was not found. Please make sure you shared it!")
            return False 
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row_to_insert = [timestamp, resident_name, rotation, task_name, "Completed"]
        sheet.append_row(row_to_insert)
        
        return True 
        
    except Exception as e:
        st.error(f"🚨 System Error: {e}")
        return False 

# =========================================================
# REUSABLE COMPONENT: RPD COMMAND CENTER DASHBOARD
# =========================================================
def render_rpd_command_center(weekly_goal=5):
    st.subheader("🌐 RPD Command Center: Program Overview")
    st.caption("Live aggregate view of clinical evaluation pacing across all residents.")
    
    live_eval_df = get_evaluation_log()
    
    if live_eval_df.empty:
        st.info("No evaluation data available yet to build macro view.")
        return
        
    # Ensure Timestamp is datetime
    live_eval_df['Timestamp'] = pd.to_datetime(live_eval_df['Timestamp'], errors='coerce')
    seven_days_ago = datetime.now() - pd.Timedelta(days=7)
    
    # Get all residents from the user database so we see zeros for those avoiding preceptors
    res_names = users_df[users_df['Role'].str.upper() == 'RESIDENT']['Name'].tolist()
    
    if not res_names:
        st.warning("No residents found in the system to track.")
        return
        
    macro_data = []
    for res in res_names:
        res_df = live_eval_df[live_eval_df['Resident Name'] == res]
        total_evals = len(res_df)
        recent_evals = len(res_df[res_df['Timestamp'] >= seven_days_ago])
        
        # Determine Pacing Status
        if recent_evals >= weekly_goal:
            status = "🌟 Excelling (Goal Met)"
        elif recent_evals > 0:
            status = "⚠️ Falling Behind"
        else:
            status = "🚨 Critical (0 Logged)"
            
        macro_data.append({
            "Resident": res,
            "7-Day Volume": recent_evals,
            "Total Lifetime": total_evals,
            "Pacing Status": status
        })
        
    macro_df = pd.DataFrame(macro_data)
    
    # 1. Top-Level Metric Cards
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Program Evals", len(live_eval_df))
    with col2:
        st.metric("Program Evals This Week", sum(macro_df['7-Day Volume']))
    with col3:
        active_count = len(macro_df[macro_df['7-Day Volume'] > 0])
        st.metric("Active Residents (7 Days)", f"{active_count} / {len(res_names)}")
        
    st.write("---")
    
    # 2. Visual Progress Table
    st.dataframe(
        macro_df,
        column_config={
            "7-Day Volume": st.column_config.ProgressColumn(
                "7-Day Volume (Target: 5)",
                help="Number of evaluations logged in the last 7 days.",
                format="%f",
                min_value=0,
                max_value=weekly_goal,
            ),
            "Pacing Status": st.column_config.TextColumn(
                "Pacing Status",
                help="Status based on meeting the weekly evaluation target."
            )
        },
        use_container_width=True,
        hide_index=True
    )
# =========================================================
# DASHBOARDS
# =========================================================

# --- ADMIN VIEW (RPD) ---
if user_role == "admin":        
    st.title("📈 Program Director Dashboard")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Reports & Progress", "👨‍🏫 Submit Evaluation", "📅 Daily Operations", "📋 Assignment Tracker", "🎓 Academic Records", "📝 Admin & Accreditation"])
    
    with tab1:
        # INJECT THE NEW MACRO COMMAND CENTER HERE
        render_rpd_command_center(weekly_goal=5)
        
        st.write("---")    
        # ==========================================
        # 1. ASHP ACCREDITATION STEP TRACKER
        # ==========================================
        st.subheader("📊 ASHP Accreditation Step Tracker")
    
        try:
            eval_df = get_evaluation_log() 
        except Exception as e:
            st.error("Could not load Evaluation Log.")
            eval_df = pd.DataFrame()
    
        if not eval_df.empty:
            target_goals = {
                "R1.1.1 (Therapeutic Regimens)": 10,
                "R1.1.8 (Patient Outcomes)": 10,
                "R5.1.1 (Medical Emergencies)": 5,
                "E7.1.1 (Pre-hospital Teamwork)": 3
            }
    
            view_mode = st.radio("Select View", ["Program Overview", "By Resident"], horizontal=True)
            
            if view_mode == "By Resident":
                selected_res = st.selectbox("Select Resident to Audit", ["Gabby Alvarez", "Brayden Key", "Samantha Richardson"])
                working_df = eval_df[eval_df['Resident Name'] == selected_res]
            else:
                working_df = eval_df
    
            st.divider()
    
            col1, col2 = st.columns(2)
            items = list(target_goals.items())
            half_point = len(items) // 2
    
            def render_progress(column, items_to_render):
                with column:
                    for goal_name, required_count in items_to_render:
                        objective_code = goal_name.split(" ")[0] 
                        current_count = len(working_df[working_df[active_config["evaluation_column"]].str.contains(objective_code, na=False)])
                        progress_pct = min(current_count / required_count, 1.0)
                        
                        st.write(f"**{goal_name}**")
                        st.progress(progress_pct)
                        
                        if current_count >= required_count:
                            st.caption(f"✅ Target Met: {current_count} / {required_count} logged")
                        else:
                            st.caption(f"⏳ Pending: {current_count} / {required_count} logged ({required_count - current_count} remaining)")
                        st.write("")
    
            render_progress(col1, items[:half_point])
            render_progress(col2, items[half_point:])
    
        else:
            st.info("No evaluation data found. Start logging evaluations to see progress here!")
    
        st.divider() # A clean line to separate the tracker from the granular tracking

        # ==========================================
        # AI GAP ANALYSIS TOOL (Under the Step Tracker)
        # ==========================================
        st.divider()
        st.subheader("🤖 AI Program Gap Analysis")
        st.write("Run an automated ASHP audit on a specific standard to identify missing clinical experiences.")
        
        col_audit1, col_audit2 = st.columns([2, 1])
        
        with col_audit1:
            # Dropdown options match the shorthand names from your Step Tracker
            target_audit = st.selectbox("Select Standard to Audit", [
                "R1.1.1 (Therapeutic Regimens)",
                "R1.1.8 (Patient Outcomes)",
                "R5.1.1 (Medical Emergencies)",
                "E7.1.1 (Pre-hospital Teamwork)"
            ])
            
        with col_audit2:
            st.write("") # Spacing to align button with dropdown
            st.write("")
            run_audit = st.button("Run AI Audit", type="primary", use_container_width=True)
            
        if run_audit:
            # 1. Extract the objective code (e.g., "R1.1.1")
            audit_code = target_audit.split(" ")[0]
            
            # 2. Filter the dataframe to ONLY include evaluations for this standard
            audit_df = eval_df[eval_df['ASHP Objective'].str.contains(audit_code, na=False)]
            
            if len(audit_df) == 0:
                st.warning(f"No evaluations found for {target_audit}. Start logging to run an audit.")
            else:
                with st.spinner(f"AI Surveyor analyzing {len(audit_df)} evaluations..."):
                    # 3. Call the AI function
                    audit_report = run_gap_analysis(target_audit, audit_df)
                    
                    # 4. Display the results in a nice expander box
                    with st.expander(f"📄 Official Audit Report: {target_audit}", expanded=True):
                        st.markdown(audit_report)
    
        # ==========================================
        # 2. GRANULAR RESIDENT ASSIGNMENT TRACKING (Your existing code)
        # ==========================================
        st.subheader("Granular Resident Assignment Tracking")
        if eval_df.empty:
            st.info("No legacy evaluation data found.")
        else:
            # Note: We pull from live_eval_df here to make sure the export matches the live database
            live_eval_df = get_evaluation_log()
            res_list = live_eval_df['Resident Name'].dropna().unique().tolist()
            if res_list:
                sel_res = st.selectbox("Review Resident Progress:", res_list, key="admin_report_res")
                render_step_tracker(sel_res)
                st.write("---")
                
                res_data = live_eval_df[live_eval_df['Resident Name'] == sel_res]
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(f"Total Completed Evaluations ({sel_res})", len(res_data))
                with col2:
                    csv_export = res_data.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Export Resident Data (CSV)",
                        data=csv_export,
                        file_name=f"{sel_res}_eval_report_{datetime.today().strftime('%Y-%m-%d')}.csv",
                        mime='text/csv',
                        type="primary"
                    )
                
                st.dataframe(res_data, use_container_width=True, hide_index=True)
                
    with tab2:
        render_evaluation_tool()
       
    with tab3: 
        st.subheader("Today's Active Residents")
        today_all_sched = get_todays_schedule()
        if not today_all_sched.empty:
            st.dataframe(today_all_sched[['Resident Name', 'Subject', 'Start Time']], use_container_width=True)
            st.write("### Operational Metric Tracking")
            st.info("Metrics for clinical policy completions (e.g., Discharge Culture Follow-ups) will populate here as residents check off their daily steps.")
        else:
            st.warning("No scheduled activities found for today.")
    
    with tab4: 
        render_assignment_tracker()

    with tab5:
        st.subheader("Resident Academic Records")
        res_names = users_df[users_df['Role'].str.upper() == 'RESIDENT']['Name'].tolist()
        if res_names:
            target_res = st.selectbox("Select Resident Record:", res_names, key="admin_profile_res")
            render_resident_profile(target_res, is_preceptor_view=True)
        else:
            st.warning("No residents found in the system.")
    with tab6:
            st.header("📝 AI Document & Accreditation Engine")
            st.caption("Instantly generate formatted RAC meeting minutes and formal ASHP progress reports from shorthand notes.")
            
            doc_tabs = st.tabs(["👥 RAC Meeting Minutes", "🏛️ ASHP Progress Report"])
            
            # --- RAC MEETING MINUTES GENERATOR ---
            with doc_tabs[0]:
                st.subheader("Residency Advisory Committee (RAC) Scribe")
                st.info("Paste your rough notes from the Teams meeting. The AI will map it to the official CTMFH-PGY2-EM template.")
                
                col_date, col_time = st.columns(2)
                with col_date:
                    rac_date = st.date_input("Meeting Date", datetime.today())
                with col_time:
                    rac_time = st.text_input("Meeting Time", value="1400-1430")
                    
                rac_context = f"Date: {rac_date.strftime('%Y-%m-%d')}, Time: {rac_time}"
                
                rac_notes = st.text_area("Raw Meeting Notes (Attendees, topics, decisions, who is doing what):", height=200, key="rac_raw_notes")
                
                if st.button("✨ Generate Official RAC Minutes", type="primary", key="btn_rac"):
                    if rac_notes:
                        with st.spinner("Synthesizing meeting minutes..."):
                            generated_minutes = generate_admin_document("RAC", rac_notes, rac_context)
                            if generated_minutes:
                                st.session_state['draft_rac'] = generated_minutes
                    else:
                        st.warning("Please provide meeting notes.")
                        
                if 'draft_rac' in st.session_state:
                    st.write("---")
                    st.subheader("Drafted Minutes")
                    final_rac = st.text_area("Review and Edit (Markdown format):", value=st.session_state['draft_rac'], height=400)
                    
                    st.download_button(
                        label="📥 Download as Text File",
                        data=final_rac,
                        file_name=f"RAC_Minutes_{rac_date.strftime('%Y-%m-%d')}.txt",
                        mime="text/plain"
                    )

            # --- ASHP ACCREDITATION ENGINE (FRAMEWORK-LOCKED) ---
            with doc_tabs[1]:
                st.subheader("ASHP Progress Report Generator")
                st.info("Generate formal responses to ASHP citations based strictly on the official Accreditation Standards framework.")
                
                # 1. Parse the ASHP Framework CSV
                if not ashp_standards_df.empty:
                    # Assuming the standards are in a column named 'ASHP Standards' (based on your CSV structure)
                    # We filter out empty rows or headers
                    valid_standards = ashp_standards_df['ASHP Standards'].dropna().tolist()
                    clean_standards = [
                        str(s).strip() for s in valid_standards 
                        if str(s).strip() != "" and ("Standard" in str(s) or str(s).strip()[0].isdigit())
                    ]
                else:
                    clean_standards = ["Standard 3.1.c (Fallback Mode - CSV Not Loaded)"]
    
                # 2. Framework Selection Dropdown
                st.write("🏛️ **1. Select Cited Standard**")
                selected_standard = st.selectbox(
                    "Search and select the exact standard from the ASHP framework:", 
                    options=clean_standards,
                    key="ashp_std_dropdown"
                )
                
                st.write("🛠️ **2. Corrective Action Narrative**")
                ashp_notes = st.text_area("Briefly explain the process, tool, or policy you implemented to fix this:", height=100, key="ashp_raw_notes")
                
                st.write("🔗 **3. Inject Live Platform Evidence**")
                st.caption("Select the live data you want Gemini to pull directly from the RxBricks platform to prove compliance.")
                
                col_ev1, col_ev2 = st.columns(2)
                with col_ev1:
                    attach_evals = st.checkbox("📊 Attach Live Evaluation Metrics")
                with col_ev2:
                    attach_tasks = st.checkbox("📋 Attach Clinical Task/Policy Tracking")
    
                if st.button("✨ Draft Data-Backed ASHP Response", type="primary", key="btn_ashp"):
                    if selected_standard and ashp_notes:
                        with st.spinner("Compiling platform data and mapping to ASHP framework..."):
                            
                            # --- DATA AGGREGATION ENGINE ---
                            platform_evidence = "\n--- LIVE PROGRAM DATA ---\n"
                            
                            if attach_evals:
                                live_eval_df = get_evaluation_log()
                                if not live_eval_df.empty:
                                    total_evals = len(live_eval_df)
                                    res_count = live_eval_df['Resident Name'].nunique()
                                    recent_7_days = len(live_eval_df[pd.to_datetime(live_eval_df['Timestamp'], errors='coerce') >= (datetime.now() - pd.Timedelta(days=7))])
                                    platform_evidence += f"- EVALUATIONS: The program has successfully logged {total_evals} formal clinical evaluations across {res_count} active residents. {recent_7_days} evaluations were completed in the last 7 days alone, demonstrating continuous active preceptor engagement.\n"
                            
                            if attach_tasks:
                                if not assignments_df.empty:
                                    platform_evidence += f"- TASKS/ASSIGNMENTS: The program utilizes an automated tracking system. Currently managing {len(assignments_df)} active clinical assignments/policies integrated directly into daily operations.\n"
                            
                            # Combine user notes, platform data, AND the exact framework text
                            combined_notes = f"NARRATIVE CONTEXT:\n{ashp_notes}\n{platform_evidence}"
                            
                            # Pass the exact standard text as the context
                            generated_response = generate_admin_document("ASHP", combined_notes, context=selected_standard)
                            
                            if generated_response:
                                st.session_state['draft_ashp'] = generated_response
                    else:
                        st.warning("Please provide a brief narrative of your action plan.")
                        
                if 'draft_ashp' in st.session_state:
                    st.write("---")
                    st.subheader("Official Progress Report Response")
                    final_ashp = st.text_area("Review and Edit:", value=st.session_state['draft_ashp'], height=400)
                    
                    st.download_button(
                        label="📥 Download Response",
                        data=final_ashp,
                        file_name=f"ASHP_Response_Draft.txt",
                        mime="text/plain"
                    )        
# --- PRECEPTOR VIEW ---
elif user_role == "preceptor":
    st.title("👨‍🏫 Preceptor Dashboard")
    
    st.info(f"📅 **Today's Date:** {datetime.today().strftime('%B %d, %Y')}")
    today_sched = get_todays_schedule()
    if not today_sched.empty:
        st.markdown("### 👥 Resident Schedule Today")
        st.table(today_sched[['Resident Name', 'Subject', 'Start Time']])
    else:
        st.caption("No residents are scheduled for clinical shifts today.")
    st.write("---")

    tab1, tab2, tab3, tab4 = st.tabs(["👨‍🏫 Evaluate Resident", "📈 Resident Status", "📚 Curriculum Library", "🎓 Academic Records"])
   
    with tab1:
            render_evaluation_tool()
        
    with tab2:
        st.subheader("Resident Progress Status")
        res_names = users_df[users_df['Role'].str.upper() == 'RESIDENT']['Name'].tolist()
        if res_names:
            stat_res = st.selectbox("Check Status for:", res_names, key="prec_stat_res")
            render_step_tracker(stat_res)
            
            st.write("**Recent Evaluations (Last 10):**")
            if not eval_df.empty:
                res_evals = eval_df[eval_df['Resident Name'] == stat_res]
                if not res_evals.empty:
                    if 'Date' in res_evals.columns:
                        res_evals['Date'] = pd.to_datetime(res_evals['Date'], errors='coerce')
                        recent_10 = res_evals.sort_values(by='Date', ascending=False).head(10)
                    else:
                        recent_10 = res_evals.tail(10)
                    st.dataframe(recent_10, use_container_width=True)
                else:
                    st.info("No evaluations logged for this resident yet.")
            else:
                st.info("No evaluation data found in the system.")
                
    with tab3:
        render_curriculum(user_role, user_tier)

    with tab4:
        st.subheader("Resident Academic Records")
        res_names = users_df[users_df['Role'].str.upper() == 'RESIDENT']['Name'].tolist()
        if res_names:
            target_res = st.selectbox("Select Resident Record:", res_names, key="prec_profile_res")
            render_resident_profile(target_res, is_preceptor_view=True)
        else:
            st.warning("No residents found in the system.")

# --- RESIDENT/LEARNER VIEW ---
elif user_role == "learner":
    st.title(f"Welcome, {name}!")

    render_step_tracker(name)
    st.write("---")
    
    tab1, tab2, tab3, tab4 = st.tabs(["🎯 Today's Plan", "📚 Curriculum Library", "📅 Schedule & Progress", "🎓 Profile & CV"])
    
    with tab1:
        render_daily_operations(name, user_role)
        
        st.write("---")
        render_assignments(name)
        st.subheader("📖 Today's Recommended Study")
        today_sched = get_todays_schedule(name)
        
        if not today_sched.empty and not curriculum_df.empty:
            rot_sub = str(today_sched.iloc[0]['Subject']).upper()
            possible_cats = curriculum_df['Category / Module'].dropna().unique()
            
            matches = [c for c in possible_cats if str(c).upper() in rot_sub or rot_sub in str(c).upper()]
            
            if matches:
                st.success(f"**Curriculum Match!** Based on your shift ({rot_sub}), we recommend reviewing topics in the **{matches[0]}** module today.")
            else:
                st.info(f"You are scheduled for **{rot_sub}**. Check the Curriculum Library for related self-directed study.")
        
        st.caption("👉 Navigate to the **📚 Curriculum Library** tab to access your study guides, videos, and NotebookLM links.")
        
    with tab2:
        render_curriculum(user_role, user_tier)
        
    with tab3:
        st.subheader("📅 Upcoming Shifts")
        if not schedule_df.empty:
            temp_sched = schedule_df.copy()
            temp_sched['Start Date'] = pd.to_datetime(temp_sched['Start Date'], errors='coerce')
            today_date = pd.to_datetime(datetime.today().date())
            future_sched = temp_sched[(temp_sched['Resident Name'] == name) & (temp_sched['Start Date'] >= today_date)]
            my_sched = future_sched.sort_values('Start Date').head(5)
            
            if not my_sched.empty:
                my_sched['Start Date'] = my_sched['Start Date'].dt.strftime('%Y-%m-%d')
                st.table(my_sched[['Subject', 'Start Date', 'Start Time']])
            else:
                st.info("No upcoming shifts scheduled. Enjoy the downtime!")
        
        st.divider()
        render_step_counter(resident_name=name, weekly_goal=5)
        st.divider()
        
        st.subheader("📈 My 10 Most Recent Evaluations")
        live_eval_df = get_evaluation_log() 
        
        if not live_eval_df.empty:
            my_evals = live_eval_df[live_eval_df['Resident Name'] == name].copy()
            if not my_evals.empty:
                my_evals['Timestamp'] = pd.to_datetime(my_evals['Timestamp'], errors='coerce')
                recent_10 = my_evals.sort_values(by='Timestamp', ascending=False).head(10)
                recent_10['Timestamp'] = recent_10['Timestamp'].dt.strftime('%Y-%m-%d %H:%M')
                st.metric("Total Lifetime Evaluations Logged", len(my_evals))
                st.dataframe(recent_10, use_container_width=True, hide_index=True)
            else:
                st.info("No evaluations logged yet. Hunt down a preceptor!")
        else:
            st.info("Evaluation database is currently empty.")
    with tab4:
        render_resident_profile(name, is_preceptor_view=False)
