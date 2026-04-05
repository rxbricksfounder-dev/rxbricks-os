import requests
import datetime
import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
import bcrypt
import streamlit.components.v1 as components

# =========================================================
# UI TRANSLATION DICTIONARY (ASHP to Clinical Role)
# =========================================================
ASHP_TO_CLINICAL_ROLE = {
    # BEDSIDE EMERGENCY RESPONSE
    "R1.1.6": {
        "role_name": "Bedside Emergency Response",
        "ui_header": "### 🚨 Acute Medical Response & Direct Care",
        "description": "Ensure implementation of therapeutic regimens."
    },
    "R5.1.1": {
        "role_name": "Medical Emergency Management & Leadership",
        "ui_header": "### 🚨 Acute Medical Response & Direct Care",
        "description": "Demonstrate the essential role of the EM pharmacist in emergencies."
    },

    # MULTIDISCIPLINARY INTERACTION & DRUG INFO
    "R1.1.1": {
        "role_name": "Multidisciplinary Interaction & Drug Info",
        "ui_header": "### 🗣️ Multidisciplinary Interaction & Drug Info",
        "description": "Interact effectively with health care teams."
    },
    "R1.1.2": {
        "role_name": "Multidisciplinary Interaction & Drug Info",
        "ui_header": "### 🗣️ Multidisciplinary Interaction & Drug Info",
        "description": "Interact effectively with patients, family, and caregivers."
    },
    "R1.1.7": {
        "role_name": "Multidisciplinary Interaction & Drug Info",
        "ui_header": "### 🗣️ Multidisciplinary Interaction & Drug Info",
        "description": "Communicate and document direct patient care activities."
    },

    # PATIENT WORK-UPS & PRECEPTOR DISCUSSION
    "R1.1.3": {
        "role_name": "Patient Work-ups & Preceptor Discussion",
        "ui_header": "### 🧠 Patient Work-ups & Preceptor Discussion",
        "description": "Collect and analyze information to base safe therapy."
    },
    "R1.1.4": {
        "role_name": "Patient Work-ups & Preceptor Discussion",
        "ui_header": "### 🧠 Patient Work-ups & Preceptor Discussion",
        "description": "Analyze and assess information for safe medication therapy."
    },
    "R1.1.5": {
        "role_name": "Patient Work-ups & Preceptor Discussion",
        "ui_header": "### 🧠 Patient Work-ups & Preceptor Discussion",
        "description": "Design safe and effective patient-centered therapeutic regimens."
    },
    "R1.1.8": {
        "role_name": "Patient Work-ups & Preceptor Discussion",
        "ui_header": "### 🧠 Patient Work-ups & Preceptor Discussion",
        "description": "Demonstrate responsibility for patient outcomes."
    },
    "R1.2.1": {
        "role_name": "Patient Work-ups & Preceptor Discussion",
        "ui_header": "### 🔄 Transitions of Care",
        "description": "Manage transitions of care effectively."
    },

    # MEDICATION PREPARATION & DELIVERY
    "R1.3.1": {
        "role_name": "Medication Preparation & Delivery",
        "ui_header": "### 💊 Medication Preparation & Delivery",
        "description": "Facilitate delivery of medications following best practices."
    },
    "R1.3.2": {
        "role_name": "Medication Preparation & Delivery",
        "ui_header": "### 💊 Medication Preparation & Delivery",
        "description": "Manage aspects of the medication-use process related to formulary."
    },
    "R1.3.3": {
        "role_name": "Medication Preparation & Delivery",
        "ui_header": "### 💊 Medication Preparation & Delivery",
        "description": "Facilitate aspects of the medication-use process."
    },

    # DEPARTMENTAL RESPONSIBILITIES & QUALITY IMPROVEMENT
    "R2.1.1": {
        "role_name": "Systems Educator & Innovator",
        "ui_header": "### 📋 Departmental Responsibilities & Projects",
        "description": "Prepare or revise a drug class review, monograph, or guideline."
    },
    "R2.1.2": {
        "role_name": "Systems Educator & Innovator",
        "ui_header": "### 📋 Departmental Responsibilities & Projects",
        "description": "Identify opportunities for improvement of the medication-use system."
    },
    "R2.2.1": {
        "role_name": "Systems Educator & Innovator",
        "ui_header": "### 📋 Departmental Responsibilities & Projects",
        "description": "Identify and demonstrate understanding of specific project topic."
    },
    
    # Catch-all
    "ROTATION_EXPECTATION": {
        "role_name": "Departmental Responsibilities",
        "ui_header": "### 📋 General Rotation Expectations",
        "description": "General rotation expectations, meetings, and standard duties."
    }
}

# 1. SETTINGS & CONFIG
st.set_page_config(page_title="RxBricks: EM Trust Verification", layout="wide", page_icon="🧱")

# Google Sheets Links
sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=0&single=true&output=csv"
responses_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=1012642150&single=true&output=csv"
users_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=1844700463&single=true&output=csv"
schedule_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=1966612732&single=true&output=csv"
assignments_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=1293289954&single=true&output=csv"
tasks_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=230208050&single=true&output=csv"

@st.cache_data(ttl=60)
def load_all_data():
    def clean(u): return u.strip() if isinstance(u, str) else u
    try:
        curr = pd.read_csv(clean(sheet_url))
        resp = pd.read_csv(clean(responses_url))
        sched = pd.read_csv(clean(schedule_url))
        user_db = pd.read_csv(clean(users_url))
        assign_df = pd.read_csv(clean(assignments_url))
        rotation_tasks_df = pd.read_csv(clean(tasks_url))
        
        return curr, resp, sched, user_db, assign_df, rotation_tasks_df
    except Exception as e:
        st.error(f"⚠️ Link Verification Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

curriculum_df, eval_df, schedule_df, users_df, assignments_df, rotation_tasks_df = load_all_data()

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

user_role = credentials["usernames"][username]["role"]
user_tier = credentials["usernames"][username]["tier"]
authenticator.logout(location="sidebar")
st.sidebar.success(f"Logged in: {name} | Tier: {user_tier}")

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
# REUSABLE COMPONENT: EVALUATION TOOL
# =========================================================
def render_evaluation_tool():
    if curriculum_df.empty and rotation_tasks_df.empty:
        st.warning("Curriculum and Task data are unavailable.")
        return

    res_names = users_df[users_df['Role'].str.upper() == 'RESIDENT']['Name'].tolist()
    if not res_names:
        st.warning("No residents found in the system.")
        return

    target_res = st.selectbox("Select Resident to Evaluate", res_names, key="eval_tool_res")
    
    render_step_tracker(target_res)
    st.write("---")
    
    eval_tabs = st.tabs(["⚡ Log Clinical Action", "📚 Evaluate Curriculum Topic"])
    
    # ---------------------------------------------------------
    # TAB 1: ACTION-ORIENTED EVALUATION (Cascading Dropdowns)
    # ---------------------------------------------------------
    with eval_tabs[0]:
        st.subheader("Action-Oriented Evaluation")
        if rotation_tasks_df.empty:
            st.info("No clinical task mappings available.")
        else:
            clean_tasks = rotation_tasks_df.dropna(subset=['Actionable_Activity'])
            
            # 1. Filter by Rotation First to reduce cognitive load
            all_rotations = sorted(clean_tasks['Rotation_ID'].dropna().unique().tolist())
            selected_rotation = st.selectbox("1. Select Rotation / Learning Experience", options=all_rotations, key="eval_rotation_sel")
            
            if selected_rotation:
                # Filter the tasks to only show those belonging to the selected rotation
                filtered_tasks = clean_tasks[clean_tasks['Rotation_ID'] == selected_rotation]
                
                action_mapping = filtered_tasks.groupby('Actionable_Activity')['ASHP_Sub_Objective'].apply(
                    lambda x: [str(item) for item in x if pd.notna(item)]
                ).to_dict()
                
                # 2. Select the specific clinical action from the narrowed-down list
                selected_action = st.selectbox("2. Select Prediction Event / Clinical Action", options=list(action_mapping.keys()), key="eval_action_sel")
                
                if selected_action:
                    available_objs = action_mapping.get(selected_action, [])
                    applicable_objectives = st.multiselect(
                        "Associated ASHP Objectives Satisfied", 
                        options=available_objs,
                        default=available_objs,
                        key="eval_action_multi"
                    )
                    
                    zone_action = st.radio("Entrustment Zone:", [
                        "Zone 1: Direct Supervision", 
                        "Zone 2: Proactive Supervision", 
                        "Zone 3: Reactive Supervision", 
                        "Zone 4: Independent"
                    ], key="eval_tool_zone_action")
                    
                    st.write("---")
                    st.subheader("📝 Pharmacademic Narrative")
                    
                    if "Zone 1" in zone_action:
                        zone_narrative = "required direct and continuous supervision"
                        next_steps = "Future encounters should focus on moving toward proactive supervision."
                    elif "Zone 2" in zone_action:
                        zone_narrative = "required proactive supervision and routine preceptor review prior to acting"
                        next_steps = "Future encounters should encourage the resident to execute plans with reactive preceptor availability."
                    elif "Zone 3" in zone_action:
                        zone_narrative = "performed with reactive supervision, appropriately seeking guidance when clinically necessary"
                        next_steps = "The resident is progressing excellently; next steps involve pushing for full independence."
                    else:
                        zone_narrative = "performed completely independently, serving as a reliable and competent practitioner"
                        next_steps = "The resident has achieved mastery in this area and should continue independent practice."
                    
                    objs_str = "; ".join(applicable_objectives) if applicable_objectives else "general clinical expectations"
                    
                    auto_action_narrative = (
                        f"Resident {target_res} was evaluated on the clinical action: '{selected_action}' during the '{selected_rotation}' rotation.\n\n"
                        f"During this encounter, the resident {zone_narrative}.\n\n"
                        f"This clinical action successfully demonstrated competence toward the following ASHP objectives:\n{objs_str}\n\n"
                        f"Targeted Next Steps: {next_steps}"
                    )
                    
                    final_action_narrative = st.text_area("Review and edit your evaluation text. (Copy this for Pharmacademic):", value=auto_action_narrative, height=200, key="eval_action_narrative")
                    
                    if st.button("🚀 Log Clinical Action", type="primary", key="eval_action_submit"):
                        current_date = datetime.date.today().strftime("%Y-%m-%d")
                        post_url = "https://docs.google.com/forms/d/e/1FAIpQLSe8arpBwEQi2pzFEb7qKC9oag8SN11HEU-_gGN0vQkEWqvlYA/formResponse"
                        
                        logged_objs = " | ".join(applicable_objectives)
                        
                        form_data = {
                            "entry.1175930505": target_res,                            
                            "entry.137559973": current_date,                           
                            "entry.597824849": selected_action,                              
                            "entry.575285059": logged_objs,         
                            "entry.930508246": selected_rotation, # Submitting the Rotation instead of a generic string       
                            "entry.411526759": zone_action                                    
                        }
                        
                        try:
                            response = requests.post(post_url, data=form_data)
                            if response.status_code == 200:
                                st.success(f"✅ Success! Clinical action for {target_res} securely logged to the Master Database.")
                                st.balloons()
                            else:
                                st.error(f"⚠️ Submission failed with status code: {response.status_code}.")
                        except Exception as e:
                            st.error(f"Error connecting to database: {e}")

    # ---------------------------------------------------------
    # TAB 2: CURRICULUM TOPIC EVALUATION
    # ---------------------------------------------------------
    with eval_tabs[1]:
        st.subheader("Curriculum Topic Evaluation")
        cats = curriculum_df['Category / Module'].dropna().unique()
        sel_cat = st.selectbox("Module", cats, key="eval_tool_cat")
        
        topics = curriculum_df[curriculum_df['Category / Module'] == sel_cat]['Topic'].dropna().unique()
        if len(topics) == 0:
            st.warning("No topics found for this module.")
        else:
            sel_topic = st.selectbox("Activity", topics, key="eval_tool_topic")
            
            topic_data = curriculum_df[curriculum_df['Topic'] == sel_topic]
            if topic_data.empty:
                st.warning("Data missing for this activity.")
            else:
                activity_row = topic_data.iloc[0]
                
                raw_obj = activity_row.get('ASHP Objective', 'Patient Care Objective')
                raw_sub_obj = activity_row.get('ASHP Sub-Objective', 'Perform clinical duties')
                raw_miller = activity_row.get('Competence Level (Miller)', 'N/A')
                
                st.info(f"**Target Competence (Miller's):** {raw_miller}\n\n**ASHP Objective:** {raw_obj}\n\n**Sub-Objective:** {raw_sub_obj}")
                
                zone = st.radio("Entrustment Zone:", [
                    "Zone 1: Direct Supervision", 
                    "Zone 2: Proactive Supervision", 
                    "Zone 3: Reactive Supervision", 
                    "Zone 4: Independent"
                ], key="eval_tool_zone")
                
                obj_text = str(raw_obj).lower()
                sub_obj_text = str(raw_sub_obj).replace('"', '').strip()
                action_verb = str(activity_row.get('Action Verb', 'evaluate')).lower()
                cog_domain = str(activity_row.get('Cognitive Domain', 'application')).lower()
                miller_level = str(raw_miller).lower()
                
                if "Zone 1" in zone:
                    zone_narrative = "required direct and continuous supervision"
                    next_steps = "Future encounters should focus on moving toward proactive supervision by having the resident formulate and propose plans prior to execution."
                elif "Zone 2" in zone:
                    zone_narrative = "required proactive supervision and routine preceptor review prior to acting"
                    next_steps = "Future encounters should encourage the resident to execute plans with reactive preceptor availability, building clinical confidence."
                elif "Zone 3" in zone:
                    zone_narrative = "performed with reactive supervision, appropriately seeking guidance when clinically necessary"
                    next_steps = "The resident is progressing excellently; next steps involve pushing for full independence on routine cases within this topic."
                else:
                    zone_narrative = "performed completely independently, serving as a reliable and competent practitioner"
                    next_steps = "The resident has achieved mastery in this area and should continue independent practice and peer mentoring."

                auto_narrative = (
                    f"Resident {target_res} was evaluated on the clinical topic of {sel_topic}. "
                    f"During this encounter, the resident {zone_narrative} in order to {sub_obj_text}.\n\n"
                    f"Operating within the cognitive domain of {cog_domain} and targeting the '{miller_level}' level of clinical competence, the resident demonstrated the ability to {action_verb} "
                    f"as it relates to the broader program goal to {obj_text}.\n\n"
                    f"Targeted Next Steps: {next_steps}"
                )

                st.write("---")
                st.subheader("📝 Pharmacademic Narrative")
                final_narrative = st.text_area("Review and edit your evaluation text. (Copy this for Pharmacademic):", value=auto_narrative, height=200, key="eval_tool_narrative")
                
                if st.button("🚀 Submit Topic to Master Database", type="primary", key="eval_tool_submit"):
                    current_date = datetime.date.today().strftime("%Y-%m-%d")
                    post_url = "https://docs.google.com/forms/d/e/1FAIpQLSe8arpBwEQi2pzFEb7qKC9oag8SN11HEU-_gGN0vQkEWqvlYA/formResponse"
                    
                    form_data = {
                        "entry.1175930505": target_res,                            
                        "entry.137559973": current_date,                           
                        "entry.597824849": sel_topic,                              
                        "entry.575285059": raw_obj,         
                        "entry.930508246": activity_row.get('Cognitive Domain', 'N/A'),       
                        "entry.411526759": zone                                    
                    }
                    
                    try:
                        response = requests.post(post_url, data=form_data)
                        if response.status_code == 200:
                            st.success(f"✅ Success! Evaluation for {target_res} securely logged to the Master Database.")
                            st.balloons()
                        else:
                            st.error(f"⚠️ Submission failed with status code: {response.status_code}.")
                    except Exception as e:
                        st.error(f"Error connecting to database: {e}")
                        
# =========================================================
# DAILY ACTIVITIES & CLINICAL POLICIES MODULE
# =========================================================
def get_todays_schedule(target_name=None):
    if schedule_df.empty: return pd.DataFrame()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    date_col = 'Start Date' if 'Start Date' in schedule_df.columns else 'Date'
    today_sched = schedule_df[schedule_df[date_col] == today_str]
    
    if target_name:
        today_sched = today_sched[today_sched['Resident Name'] == target_name]
    return today_sched

def render_daily_operations(resident_name):
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
        
    # --- DYNAMIC DICTIONARY MAPPING (Grouped by Action to Prevent Duplicate Checkboxes) ---
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
        
        # Combine the objective codes for display so the resident sees all satisfied targets
        obj_codes_display = ", ".join([str(x).replace('"', '').strip().split(' ')[0] for x in sub_objs if pd.notna(x)])
        
        grouped_tasks[header].append({
            "activity": action_text,
            "codes": obj_codes_display,
            "target": target_level,
            "idx": group.index[0] 
        })

    # --- UI RENDERING ---
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
        today = pd.to_datetime(datetime.date.today())
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
        file_name=f"Pharmacademic_Assignment_Report_{selected_res.replace(' ', '_')}_{datetime.date.today()}.csv",
        mime="text/csv",
        type="primary"
    )

# =========================================================
# DASHBOARDS
# =========================================================

# --- ADMIN VIEW (RPD) ---
if user_role == "admin":
    st.title("📈 Program Director Dashboard")
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Reports & Progress", "👨‍🏫 Submit Evaluation", "📅 Daily Operations", "📋 Assignment Tracker"])
    
    with tab1:
        st.subheader("Resident Assignment Tracking")
        if eval_df.empty:
            st.info("No evaluation data found.")
        else:
            res_list = eval_df['Resident Name'].dropna().unique().tolist()
            if res_list:
                sel_res = st.selectbox("Review Resident Progress:", res_list, key="admin_report_res")
                render_step_tracker(sel_res)
                st.write("---")
                
                res_data = eval_df[eval_df['Resident Name'] == sel_res]
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Completed Evaluations", len(res_data))
                with col2:
                    csv_export = res_data.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Export Resident Data (CSV)",
                        data=csv_export,
                        file_name=f"{sel_res}_eval_report.csv",
                        mime='text/csv',
                        type="primary"
                    )
                
                st.dataframe(res_data, use_container_width=True)
                
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
        
# --- PRECEPTOR VIEW ---
elif user_role == "preceptor":
    st.title("👨‍🏫 Preceptor Dashboard")
    
    st.info(f"📅 **Today's Date:** {datetime.date.today().strftime('%B %d, %Y')}")
    today_sched = get_todays_schedule()
    if not today_sched.empty:
        st.markdown("### 👥 Resident Schedule Today")
        st.table(today_sched[['Resident Name', 'Subject', 'Start Time']])
    else:
        st.caption("No residents are scheduled for clinical shifts today.")
    st.write("---")

    tab1, tab2, tab3 = st.tabs(["👨‍🏫 Evaluate Resident", "📈 Resident Status", "📚 Curriculum Library"])
   
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

# --- RESIDENT/LEARNER VIEW ---
elif user_role == "learner":
    st.title(f"Welcome, {name}!")

    render_step_tracker(name)
    st.write("---")
    
    tab1, tab2, tab3 = st.tabs(["🎯 Today's Plan", "📚 Curriculum Library", "📅 Schedule & Progress"])
    
    with tab1:
        render_daily_operations(name)
        
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
            my_sched = schedule_df[schedule_df['Resident Name'] == name].head(5)
            if not my_sched.empty:
                st.table(my_sched[['Subject', 'Start Date', 'Start Time']])
            else:
                st.info("No upcoming shifts scheduled.")
        
        st.divider()
        st.subheader("📈 My 10 Most Recent Evaluations")
        
        if not eval_df.empty:
            my_evals = eval_df[eval_df['Resident Name'] == name]
            
            if not my_evals.empty:
                if 'Date' in my_evals.columns:
                    my_evals['Date'] = pd.to_datetime(my_evals['Date'], errors='coerce')
                    recent_10 = my_evals.sort_values(by='Date', ascending=False).head(10)
                else:
                    recent_10 = my_evals.tail(10)
                
                st.metric("Total Lifetime Evaluations Logged", len(my_evals))
                st.dataframe(recent_10, use_container_width=True)
            else:
                st.info("No evaluation data found yet.")
        else:
            st.info("No evaluation data found yet.")
