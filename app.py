import zlib
import json
import bcrypt
import pandas as pd
import streamlit as st
import gspread
import streamlit_authenticator as stauth
import streamlit.components.v1 as components
import google.generativeai as genai
from datetime import datetime
from google.oauth2.service_account import Credentials

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
        # NEW: Terminology mapping
        "nomenclature": {
            "learner": "Resident",
            "educator": "Preceptor",
            "director": "Residency Program Director",
            "committee": "Residency Advisory Committee (RAC)",
            "committee_short": "RAC",
            "eval_system": "PharmAcademic",
            "accreditation": "ASHP"
        },
        # NEW: Program-specific settings
        "eval_settings": {
            "grading_scale": ["ACHR", "ACH", "SP", "NI"],
            "entrustment_scale": ["1 - Knows", "2 - Knows How", "3 - Shows How", "4 - Does"],
            "rotations": ["CORE - 1 - EM", "CORE - 2 - EM", "CORE - 3 - ICU", "ELEC - Tox"] 
            # Note: Rotations ideally should be loaded dynamically from schedule_df if possible
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
        "nomenclature": {
            "learner": "Student",
            "educator": "Preceptor",
            "director": "Course Coordinator",
            "committee": "Curriculum Committee",
            "committee_short": "CC",
            "eval_system": "CoreELMS", # Or whichever system they use
            "accreditation": "ACPE"
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
        sheet = client.open(active_sheet_name).worksheet("3_Evaluation_Log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        row_data = [
            timestamp, preceptor, resident, rotation, objective,
            criteria, grade, comment, action_plan, narrative,
            ai_quality_grade, pharmacademic_text
        ]
        sheet.append_row(row_data)
        get_evaluation_log.clear() # Clear cache so new data shows immediately
        return True
    except Exception as e:
        st.error(f"Error writing to Google Sheets: {e}")
        return False

@st.cache_data(ttl=60)
def get_evaluation_log(sheet_name):
    client = get_gspread_client()
    if not client: return pd.DataFrame()
    
    try:
        sheet = client.open(sheet_name).worksheet("3_Evaluation_Log")
        df = pd.DataFrame(sheet.get_all_records())
        
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
        spreadsheet = client.open(sheet_name)
        
        curr = pd.DataFrame(spreadsheet.worksheet("1_Curriculum").get_all_records())
        resp = pd.DataFrame(spreadsheet.worksheet("Form Responses 1").get_all_records()) 
        sched = pd.DataFrame(spreadsheet.worksheet("4_Schedule").get_all_records())
        user_db = pd.DataFrame(spreadsheet.worksheet("3_Users").get_all_records())
        assign_df = pd.DataFrame(spreadsheet.worksheet("5_Assignments").get_all_records())
        rotation_tasks_df = pd.DataFrame(spreadsheet.worksheet("7_Rotation_Task_Mapping").get_all_records())
        ashp_df = pd.DataFrame(spreadsheet.worksheet(standards_tab_name).get_all_records())
        
        for df in [curr, resp, sched, user_db, assign_df, rotation_tasks_df, ashp_df]:
            df.replace("", pd.NA, inplace=True)
            df.dropna(how='all', inplace=True)
            
        if not sched.empty:
            if 'Start Date' in sched.columns:
                sched['Start Date'] = pd.to_datetime(sched['Start Date'], errors='coerce')
            if 'End Date' in sched.columns:
                sched['End Date'] = pd.to_datetime(sched['End Date'], errors='coerce')
        
        return curr, resp, sched, user_db, assign_df, rotation_tasks_df, ashp_df
        
    except Exception as e:
        st.error(f"⚠️ Database Connection Error. Details: {e}")
        return tuple(pd.DataFrame() for _ in range(7))

# Load data globally for the session
curriculum_df, eval_df, schedule_df, users_df, assignments_df, rotation_tasks_df, ashp_standards_df = load_all_data(active_sheet_name, active_config["standards_tab"])

# ==========================================\
# 2. AI ENGINES
# ==========================================\
def generate_ai_evaluation(raw_dictation, learner_name, rotation, topic, zone, config):
    model = get_gemini_model()
    if not model: return None
    
    nom = config["nomenclature"]
    eval_sys = nom["eval_system"]
    
    prompt = f"""
    You are an expert {nom['director']}.
    First, evaluate the quality of the raw {nom['educator'].lower()} dictation. Then, format it into a highly professional clinical evaluation.
    
    Context:
    * {nom['learner']}: {learner_name}
    * Rotation: {rotation}
    * Topic/Action: {topic}
    * Target Zone: {zone}
    
    Raw {nom['educator']} Dictation:
    {raw_dictation}
    
    Output Requirements:
    Return ONLY a strict JSON object with exactly these 6 keys:
    1. "QualityGrade": String ("Green", "Yellow", or "Red"). Red means the dictation was lazy or lacked clinical context.
    2. "QualityFeedback": String (1 short sentence of direct coaching to the {nom['educator'].lower()} explaining *why* their dictation scored that grade).
    3. "Grade": Must be one of: {', '.join(config['eval_settings']['grading_scale'])}.
    4. "Comment": A 1-2 sentence professional assessment.
    5. "ActionPlan": 1-2 sentences detailing specific next steps.
    6. "Narrative": A comprehensive synthesis paragraph ready for {eval_sys}.
    """
        
    try:
        response = model.generate_content(prompt, generation_config=genai.GenerationConfig(response_mime_type="application/json"))
        return json.loads(response.text)
    except Exception as e:
        st.error(f"AI Formatting Error: {str(e)}")
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
        elif db_role in ["RESIDENT", "LEARNER", "STUDENT"]: 
            r_internal = "learner"
        else: 
            r_internal = "preceptor"
            
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

if username not in credentials["usernames"]:
    st.error("🚨 User database sync error. Ensure your User sheet is loaded correctly.")
    st.stop()

user_role = credentials["usernames"][username]["role"]
user_tier = credentials["usernames"][username]["tier"]
authenticator.logout(location="sidebar")
st.sidebar.success(f"Logged in: {name} | Tier: {user_tier}")

# FIXED: Removed the leaked variable check 'role' here.
if user_role in ["admin", "preceptor"]:
    st.divider()

# =========================================================
# ID REPOSITORY PATTERN 
# =========================================================
def get_learner_mapping(users_dataframe, config):
    if users_dataframe.empty: return {}
    # Broadened search to match robust role logic
    learners = users_dataframe[users_dataframe['Role'].str.upper().isin(["RESIDENT", "LEARNER", "STUDENT"])]
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
    id_col = config.get("learner_id_column", "Learner_ID")
    if id_col not in df.columns:
        id_col = config.get("learner_column", "Resident Name") 
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

def render_evaluation_tool():
    if not learner_dict:
        st.warning("No learners found in the system.")
        return

    nom = active_config["nomenclature"]
    eval_set = active_config["eval_settings"]

    target_res_id = st.selectbox(
        f"Select {nom['learner']} to Evaluate", 
        options=list(learner_dict.keys()), 
        format_func=lambda x: learner_dict.get(x, "Unknown"),
        key="eval_tool_res"
    )
    current_preceptor = st.session_state.get("name", f"Unknown {nom['educator']}")
    
    render_step_tracker(target_res_id)
    st.write("---")

    if 'eval_draft' not in st.session_state:
        st.session_state.eval_draft = None

    # Dynamically pull topics from curriculum if available, else use a fallback
    topics = curriculum_df['Topic'].dropna().unique().tolist() if not curriculum_df.empty else ["No Curriculum Loaded"]

    col_a, col_b = st.columns(2)
    with col_a:
        selected_rotation = st.selectbox("Rotation", eval_set.get("rotations", ["Default"]), key=f"rot_{target_res_id}")
        selected_action = st.selectbox("Clinical Action / Topic", topics, key=f"act_{target_res_id}")
    with col_b:
        zone_action = st.selectbox("Target Entrustment", eval_set.get("entrustment_scale", ["1", "2", "3", "4"]), key=f"zone_{target_res_id}")
        
    raw_dictation_1 = st.text_area(f"{nom['educator']} Dictation / Rough Notes (Be honest!)", height=100, key=f"dict_{target_res_id}")
    
    if st.button("✨ Assess Quality & Draft Evaluation", type="primary", use_container_width=True, key=f"draft_btn_{target_res_id}"):
        if len(raw_dictation_1) < 5:
            st.warning("Please dictate a few words first!")
        else:
            with st.spinner("AI Coach is analyzing and drafting..."):
                ai_result = generate_ai_evaluation(raw_dictation_1, learner_dict.get(target_res_id, target_res_id), selected_rotation, selected_action, zone_action, active_config)
                if ai_result:
                    st.session_state.eval_draft = ai_result

    if st.session_state.eval_draft:
        draft = st.session_state.eval_draft
        st.divider()
        
        q_grade = draft.get("QualityGrade", "Green")
        if q_grade == "Red":
            st.error(f"🔴 **AI {nom['educator']} Coach (Deficient Entry):** {draft.get('QualityFeedback')}")
        elif q_grade == "Yellow":
            st.warning(f"🟡 **AI {nom['educator']} Coach (Borderline Entry):** {draft.get('QualityFeedback')}")
        else:
            st.success(f"✅ **AI {nom['educator']} Coach (Robust Entry):** {draft.get('QualityFeedback')}")

        st.subheader(f"📋 {nom['eval_system']} Draft")
        col_c, col_d = st.columns([1, 3])
        with col_c:
            safe_grade = draft.get("Grade", eval_set["grading_scale"][2] if len(eval_set["grading_scale"]) > 2 else "Pass")
            if safe_grade not in eval_set["grading_scale"]: safe_grade = eval_set["grading_scale"][0]
            final_grade = st.selectbox("Grade", eval_set["grading_scale"], index=eval_set["grading_scale"].index(safe_grade), key=f"fg_{target_res_id}")
        with col_d:
            final_comment = st.text_input("Comment", value=draft.get("Comment", ""), key=f"fc_{target_res_id}")
            
        final_action = st.text_area("Action Plan", value=draft.get("ActionPlan", ""), height=80, key=f"fa_{target_res_id}")
        final_narrative = st.text_area("Overall Narrative (Editable)", value=draft.get("Narrative", ""), height=150, key=f"fn_{target_res_id}")
        
        if st.button("💾 Save to Master Database", type="primary", key=f"save_{target_res_id}"):
            with st.spinner("Writing securely to Google Sheets..."):
                success = log_evaluation_to_sheet(
                    preceptor=current_preceptor, 
                    resident=target_res_id,  
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
                    st.success(f"🎉 Safely logged to Database! Ready for {nom['eval_system']} export.")
                    st.session_state.eval_draft = None
                    
def get_todays_schedule(target_id=None):
    if schedule_df.empty: return pd.DataFrame()
    today_str = datetime.today().strftime("%Y-%m-%d")
    
    date_col = 'Start Date' if 'Start Date' in schedule_df.columns else 'Date'
    today_sched = schedule_df[schedule_df[date_col] == today_str]
    
    if target_id:
        id_col = active_config.get("learner_id_column", "Learner_ID")
        if id_col not in schedule_df.columns:
            id_col = active_config.get("learner_column", "Resident Name")
        today_sched = today_sched[today_sched[id_col] == target_id]
    return today_sched

def render_daily_operations(learner_id, current_role):
    st.subheader("🎯 Today's Clinical Policies & Activities")
    today_sched = get_todays_schedule(learner_id)
    
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
        st.info("💡 **Today's Focus:** Review your daily operational tasks below.")
        show_all_tasks = st.toggle("View all available rotation tasks", value=False)
        today_str = datetime.today().strftime('%Y-%m-%d')
        seed_string = f"{learner_id}_{rotation_subject}_{today_str}"
        daily_seed = zlib.crc32(seed_string.encode())
        
        if not show_all_tasks and len(daily_tasks) > 5:
            display_tasks = daily_tasks.sample(n=5, random_state=daily_seed)
        else:
            display_tasks = daily_tasks
        
        for idx, row in display_tasks.iterrows():
            action_text = row.get('Actionable_Activity', 'General Clinical Action')
            policy_name = row.get('Clinical_Policy', 'Standard Clinical Guidelines')
            policy_link = row.get('Policy_Link', '')
            sub_obj = str(row.get('ASHP_Sub_Objective', ''))
            
            obj_code = sub_obj.replace('"', '').strip().split(' ')[0] if sub_obj and sub_obj != "nan" else "ROTATION_EXPECTATION"
            display_policy = policy_name if pd.notna(policy_name) and policy_name != "nan" else "Standard Departmental Policy"
            
            st.markdown(f"#### 🎯 {action_text}")
            with st.expander(f"📘 Policy & Application Details: {display_policy}", expanded=False):
                st.markdown(f"**Objective `{obj_code}`**")
                if pd.notna(policy_link) and str(policy_link).strip() != "" and str(policy_link) != "nan":
                    st.link_button(f"🔗 Review Policy", str(policy_link), type="primary")
                    
                if st.button(f"Mark Complete", key=f"complete_btn_{learner_id}_{rotation_subject}_{idx}"):
                    pass
            st.divider()

def render_assignments(learner_id):
    st.subheader("📝 Pending Assignments & Tasks")
    if assignments_df.empty:
        st.info("No assignments data loaded.")
        return
        
    learner_name = learner_dict.get(learner_id, learner_id)
    if 'Assigned To' in assignments_df.columns:
        assignments_df['Assigned To'] = assignments_df['Assigned To'].fillna("All PGY2")
        mask = assignments_df['Assigned To'].apply(
            lambda x: learner_name.lower() in str(x).lower() or "all" in str(x).lower()
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
        form_link = row.get('Form Link', "https://docs.google.com/forms")

        with st.expander(f"📌 **{assign_title}**", expanded=(idx==0)):
            st.link_button("1️⃣ Open Assignment Form", form_link, type="primary")
            st.checkbox("2️⃣ Mark as Submitted", key=f"submit_{learner_id}_{assign_title}_{idx}")

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
    for res_id, res_name in learner_dict.items():
        res_df = get_learner_evals(live_eval_df, active_config, res_id)
        total_evals = len(res_df)
        recent_evals = len(res_df[res_df['Timestamp'] >= seven_days_ago])
        
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
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Reports & Progress", "👨‍🏫 Submit Evaluation", "📅 Daily Operations", "📋 Assignment Tracker", "🎓 Academic Records", "📝 Admin & Accreditation"])
    
    with tab1:
        st.subheader(f"🌐 {nom['director'].split(' ')[0]} Command Center: Program Overview")
        
        # 1. Fetch the data FIRST
        live_eval_df = get_evaluation_log(active_sheet_name) 
        
        # 2. Pass the data INTO the function
        render_rpd_command_center(active_config, live_eval_df, weekly_goal=5)
        st.write("---")    
        
        st.subheader(f"📊 {nom['accreditation']} Accreditation Step Tracker")
        
        # 3. We already fetched live_eval_df above, so we can just use it immediately
        if not live_eval_df.empty:
            target_goals = {
                "R1.1.1 (Therapeutic Regimens)": 10,
                "R1.1.8 (Patient Outcomes)": 10,
                "R5.1.1 (Medical Emergencies)": 5,
                "E7.1.1 (Pre-hospital Teamwork)": 3
            }
            
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
            items = list(target_goals.items())
            half_point = len(items) // 2
    
            def render_progress(column, items_to_render):
                with column:
                    for goal_name, required_count in items_to_render:
                        objective_code = goal_name.split(" ")[0] 
                        current_count = len(working_df[working_df[active_config['evaluation_column']].astype(str).str.contains(objective_code, na=False)])
                        progress_pct = min(current_count / required_count, 1.0)
                        
                        st.write(f"**{goal_name}**")
                        st.progress(progress_pct)
                        if current_count >= required_count:
                            st.caption(f"✅ Target Met: {current_count} / {required_count} logged")
                        else:
                            st.caption(f"⏳ Pending: {current_count} / {required_count} logged")
                        st.write("")
    
            render_progress(col1, items[:half_point])
            render_progress(col2, items[half_point:])
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
                
    with tab2:
        render_evaluation_tool()
       
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
            
            # Display high-level schedule
            st.dataframe(today_all_sched[display_cols], hide_index=True, use_container_width=True)
            
            st.divider()
            st.subheader("📋 Expected Daily Operations by Resident")
            
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
                valid_standards = ashp_standards_df[active_config['standards_column']].dropna().tolist()
                clean_standards = [s for s in valid_standards if str(s).strip() != "" and ("Standard" in str(s) or str(s)[0].isdigit())]
                
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

    render_step_tracker(logged_in_id)
    st.write("---")
    
    tab1, tab2, tab3, tab4 = st.tabs(["🎯 Today's Plan", "📚 Curriculum Library", "📅 Schedule & Progress", "🎓 Profile & CV"])
    
    with tab1:
        render_daily_operations(logged_in_id, user_role)
        render_assignments(logged_in_id)
        
        # --- RESTORED: Recommended Study Context ---
        st.divider()
        st.subheader("📖 Today's Recommended Study")
        today_sched = get_todays_schedule(logged_in_id)
        if not today_sched.empty and not curriculum_df.empty:
            current_rotation = today_sched.iloc[0]['Subject']
            # Heuristic to match rotation to curriculum module
            matched_modules = curriculum_df[curriculum_df['Category / Module'].str.contains(str(current_rotation).split()[-1], case=False, na=False)]
            if not matched_modules.empty:
                rec_topic = matched_modules.iloc[0]
                st.info(f"Based on your **{current_rotation}** rotation, we recommend reviewing:")
                st.markdown(f"**Module:** {rec_topic['Category / Module']}  \n**Topic:** {rec_topic['Topic']}")
                if pd.notna(rec_topic.get('Resource URL (Published)')):
                    st.link_button("Open Study Material", str(rec_topic['Resource URL (Published)']))
            else:
                st.info("Head over to the Curriculum Library to select a study module for today.")
        else:
            st.info("No active clinical rotations today. Browse the Curriculum Library for independent study.")
        # ------------------------------------------
            
    with tab2:
        render_curriculum(user_role, user_tier)
        
    with tab3:
        st.subheader("📅 Upcoming Shifts")
        
        # --- RESTORED: Upcoming Shifts Table ---
        if not schedule_df.empty:
            id_col = active_config.get("learner_id_column", "Learner_ID")
            if id_col not in schedule_df.columns:
                id_col = active_config.get("learner_column", "Resident Name")
                
            my_sched_all = schedule_df[schedule_df[id_col] == logged_in_id].copy()
            date_col = 'Start Date' if 'Start Date' in schedule_df.columns else 'Date'
            
            if not my_sched_all.empty and date_col in my_sched_all.columns:
                my_sched_all[date_col] = pd.to_datetime(my_sched_all[date_col], errors='coerce')
                today_date = pd.to_datetime(datetime.today().strftime("%Y-%m-%d"))
                
                future_sched = my_sched_all[my_sched_all[date_col] >= today_date].sort_values(by=date_col).head(5)
                
                if not future_sched.empty:
                    future_sched[date_col] = future_sched[date_col].dt.strftime('%Y-%m-%d')
                    display_cols = ['Subject', date_col]
                    if 'Start Time' in future_sched.columns: display_cols.append('Start Time')
                    st.table(future_sched[display_cols])
                else:
                    st.info("No upcoming shifts scheduled. Enjoy the downtime!")
            else:
                st.warning("Schedule dates could not be parsed.")
        else:
            st.warning("Schedule data unavailable.")
        # ---------------------------------------
        
        st.divider()
        render_step_counter(learner_id=logged_in_id, weekly_goal=5)
        st.divider()
        
        st.subheader("📈 My 10 Most Recent Evaluations")
        live_eval_df = get_evaluation_log(active_sheet_name) 
        if not live_eval_df.empty:
            my_evals = get_learner_evals(live_eval_df, active_config, logged_in_id)
            if not my_evals.empty:
                my_evals['Timestamp'] = pd.to_datetime(my_evals['Timestamp'], errors='coerce')
                recent_10 = my_evals.sort_values(by='Timestamp', ascending=False).head(10)
                recent_10['Timestamp'] = recent_10['Timestamp'].dt.strftime('%Y-%m-%d %H:%M')
                st.metric("Total Lifetime Evaluations Logged", len(my_evals))
                st.dataframe(recent_10, use_container_width=True, hide_index=True)
            else:
                st.info("No evaluations on record.")

    with tab4:
        render_resident_profile(logged_in_id, is_preceptor_view=False)
