import requests
import datetime
import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
import bcrypt
import streamlit.components.v1 as components

# 1. SETTINGS & CONFIG
st.set_page_config(page_title="RxBricks: EM Trust Verification", layout="wide", page_icon="🧱")

# Google Sheets Links
sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=0&single=true&output=csv"
responses_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=1012642150&single=true&output=csv"
users_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=1844700463&single=true&output=csv"
schedule_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=1966612732&single=true&output=csv"

@st.cache_data(ttl=60)
def load_all_data():
    def clean(u): return u.strip() if isinstance(u, str) else u
    try:
        curr = pd.read_csv(clean(sheet_url))
        resp = pd.read_csv(clean(responses_url))
        sched = pd.read_csv(clean(schedule_url))
        user_db = pd.read_csv(clean(users_url))
        return curr, resp, sched, user_db
    except Exception as e:
        st.error(f"⚠️ Link Verification Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

curriculum_df, eval_df, schedule_df, users_df = load_all_data()

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

    st.sidebar.title("Vision 2026 Curriculum")
    all_cats = curriculum_df['Category / Module'].dropna().unique()
    sidebar_cat = st.sidebar.selectbox("Navigate Module", all_cats)
    
    module_items = curriculum_df[curriculum_df['Category / Module'] == sidebar_cat]
    selected_item_name = st.sidebar.selectbox("Select Resource", module_items['Topic'].unique())
    
    topic_items = module_items[module_items['Topic'] == selected_item_name]
    first_item = topic_items.iloc[0]

    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"📖 {first_item['Topic']}")
    with col2:
        check_key = f"complete_{username}_{first_item['Topic']}"
        is_complete = st.toggle("✅ Mark as Complete", key=check_key)

    if is_complete:
        st.success(f"Awesome job! '{first_item['Topic']}' marked as complete.")

    # --- NEW: Added Miller's Competence Level to the caption ---
    epa_text = first_item.get('EPA', 'N/A')
    bloom_text = first_item.get('Cognitive Domain', 'N/A')
    miller_text = first_item.get('Competence Level (Miller)', 'N/A')
    
    st.caption(f"EPA: {epa_text} | Target (Bloom's): {bloom_text} | Competence (Miller's): {miller_text}")
    st.markdown(f"**Objective:** {first_item.get('ASHP Objective', 'N/A')}")

    # NEW FIX: Convert everything to strings and handle blanks
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
    if curriculum_df.empty:
        st.warning("Curriculum data is unavailable.")
        return

    res_names = users_df[users_df['Role'].str.upper() == 'RESIDENT']['Name'].tolist()
    if not res_names:
        st.warning("No residents found in the system.")
        return

    target_res = st.selectbox("Select Resident to Evaluate", res_names, key="eval_tool_res")
    
    render_step_tracker(target_res)
    st.write("---")
    
    st.subheader("Evaluation Details")
    cats = curriculum_df['Category / Module'].dropna().unique()
    sel_cat = st.selectbox("Module", cats, key="eval_tool_cat")
    
    topics = curriculum_df[curriculum_df['Category / Module'] == sel_cat]['Topic'].dropna().unique()
    if len(topics) == 0:
        st.warning("No topics found for this module.")
        return

    sel_topic = st.selectbox("Activity", topics, key="eval_tool_topic")
    
    topic_data = curriculum_df[curriculum_df['Topic'] == sel_topic]
    if topic_data.empty:
        st.warning("Data missing for this activity.")
        return

    activity_row = topic_data.iloc[0]
    
    # Safely get variables using .get() to prevent KeyErrors
    raw_obj = activity_row.get('ASHP Objective', 'Patient Care Objective')
    raw_sub_obj = activity_row.get('ASHP Sub-Objective', 'Perform clinical duties')
    raw_miller = activity_row.get('Competence Level (Miller)', 'N/A')
    
    # --- NEW: Display Miller's level for the Preceptor ---
    st.info(f"**Target Competence (Miller's):** {raw_miller}\n\n**ASHP Objective:** {raw_obj}\n\n**Sub-Objective:** {raw_sub_obj}")
    
    zone = st.radio("Entrustment Zone:", [
        "Zone 1: Direct Supervision", 
        "Zone 2: Proactive Supervision", 
        "Zone 3: Reactive Supervision", 
        "Zone 4: Independent"
    ], key="eval_tool_zone")
    
    # Clean text for narrative
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

    # --- NEW: Injected Miller's Level into the formal paragraph ---
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
    
    if st.button("🚀 Submit to Master Database", type="primary", key="eval_tool_submit"):
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
# NEW: DAILY ACTIVITIES & CLINICAL POLICIES MODULE
# =========================================================
def get_todays_schedule(target_name=None):
    """Filters the schedule_df for today's date."""
    if schedule_df.empty: return pd.DataFrame()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    # Assuming 'Date' or 'Start Date' is the column name in schedule_df
    date_col = 'Start Date' if 'Start Date' in schedule_df.columns else 'Date'
    
    # Filter for today
    today_sched = schedule_df[schedule_df[date_col] == today_str]
    
    if target_name:
        today_sched = today_sched[today_sched['Resident Name'] == target_name]
    return today_sched

def render_daily_operations(resident_name):
    """Generates the daily checklist based on rotation assignment."""
    st.subheader("🎯 Today's Clinical Policies & Activities")
    
    today_sched = get_todays_schedule(resident_name)
    
    if today_sched.empty:
        st.info("You have no specific clinical rotations scheduled for today. Use this time for project work or curriculum review.")
        return

    rotation_subject = today_sched.iloc[0]['Subject']
    st.markdown(f"**Assigned Rotation:** `{rotation_subject}`")
    
    # Mock routing based on rotation name (You can expand this mapping)
    if "EM" in str(rotation_subject).upper() or "CLINICAL" in str(rotation_subject).upper():
        st.write("---")
        st.markdown("### 🧫 Discharge Culture Follow-Up Protocol")
        st.caption("Reference: CTMFH-PGY2-EM - CLINICAL POLICY - 10")
        
        # Pulling specific tasks from the provided Clinical Policy 10
        c1 = st.checkbox("1. Identify Discharged Patients with Pending Cultures (Review EMR)")
        c2 = st.checkbox("2. Review Culture Results & Susceptibility Testing")
        c3 = st.checkbox("3. Assess Appropriateness of Initial Empiric Therapy")
        c4 = st.checkbox("4. Identify Potential Discrepancies & Need for Therapy Adjustment")
        c5 = st.checkbox("5. Collaborate with Prescribing Provider (Communicate findings)")
        c6 = st.checkbox("6. Document Follow-Up Activities in Epic Medical Record")
        
        progress = sum([c1, c2, c3, c4, c5, c6]) / 6.0
        st.progress(progress, text=f"Culture Follow-Up Completion: {int(progress*100)}%")
        
        st.write("---")
        st.markdown("### 📚 Core ASHP Goals for Today")
        # Pulling specific core knowledge activities from the Master Evaluation sheet
        st.info("**R1.1.4:** Analyze and assess information on which to base safe and effective medication therapy.\n\n*Activity Focus:* Select the best medication for all emergent clinical scenarios. Differentiate hemodynamic responses.")
        st.checkbox("Log cognitive application in Pharmacademic for today's shift")

# =========================================================
# DASHBOARDS
# =========================================================

# --- ADMIN VIEW (RPD) ---
if user_role == "admin":
    st.title("📈 Program Director Dashboard")
    tab1, tab2, tab3 = st.tabs(["📊 Reports & Progress", "👨‍🏫 Submit Evaluation", "📅 Daily Operations Oversight"])
    
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
        
    with tab3: # NEW RPD OVERSIGHT TAB
        st.subheader("Today's Active Residents")
        today_all_sched = get_todays_schedule()
        if not today_all_sched.empty:
            st.dataframe(today_all_sched[['Resident Name', 'Subject', 'Start Time']], use_container_width=True)
            st.write("### Operational Metric Tracking")
            st.info("Metrics for clinical policy completions (e.g., Discharge Culture Follow-ups) will populate here as residents check off their daily steps.")
        else:
            st.warning("No scheduled activities found for today.")

# --- PRECEPTOR VIEW ---
elif user_role == "preceptor":
    st.title("👨‍🏫 Preceptor Dashboard")
    
    # NEW PRECEPTOR WIDGET: Daily Visual Schedule
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
    # render_step_tracker(name) # Your existing tracker
    st.write("---")
    
    tab1, tab2, tab3 = st.tabs(["🎯 Today's Plan", "📚 Curriculum", "📅 My Progress"])
    
    with tab1: # NEW RESIDENT TAB FOR DAILY OPERATIONS
        render_daily_operations(name)
        
    with tab2:
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
            
    with tab3:
        st.subheader("Keep Pushing Forward!")
        st.success("You are making great progress in your PGY2 EM Residency.")
        st.markdown("> *\"Success is the sum of small efforts, repeated day in and day out.\"*")
