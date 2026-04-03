import requests
import datetime
import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
import urllib.parse
import bcrypt
import streamlit.components.v1 as components

# 1. SETTINGS & CONFIG
st.set_page_config(page_title="RxBricks: EM Trust Verification", layout="wide", page_icon="🧱")

# 🚨 RE-PASTE YOUR LINKS HERE
sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=0&single=true&output=csv"
responses_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=676004133&single=true&output=csv"
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
        st.info("Check that your Google Sheet 'Publish to Web' settings are set to 'CSV' for each individual tab.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

def generate_gcal_link(title, date_str, start_time="08:00:00", end_time="17:00:00", details=""):
    try:
        start_dt = pd.to_datetime(f"{date_str} {start_time}")
        end_dt = pd.to_datetime(f"{date_str} {end_time}")
        start_f = start_dt.strftime('%Y%m%dT%H%M%S')
        end_f = end_dt.strftime('%Y%m%dT%H%M%S')
        params = {"action": "TEMPLATE", "text": title, "dates": f"{start_f}/{end_f}", "details": details}
        return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(params)
    except:
        return "https://calendar.google.com"

# 3. DATA INITIALIZATION
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

        # Safely grab the user's tier, default to Basic if the column doesn't exist yet
        u_tier = str(row['Tier']).strip().capitalize() if 'Tier' in users_df.columns else "Basic"
        
        credentials["usernames"][uname] = {
            "email": str(row['Email']),
            "name": str(row['Name']),
            "password": hpw,
            "role": r_internal,
            "tier": u_tier # Store the tier in the active session
        }

authenticator = stauth.Authenticate(credentials, "rxbricks_em", "auth_key", cookie_expiry_days=30)

# 5. LOGIN INTERFACE
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

# Grab both role and tier for the logged-in user
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

    # --- NEW: INTERACTIVE CHECKLIST PROTOTYPE ---
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"📖 {first_item['Topic']}")
    with col2:
        # Using session state to track completion temporarily
        check_key = f"complete_{username}_{first_item['Topic']}"
        is_complete = st.toggle("✅ Mark as Complete", key=check_key)

    if is_complete:
        st.success(f"Awesome job! '{first_item['Topic']}' marked as complete.")

    st.caption(f"EPA: {first_item['EPA']} | Target: {first_item['Cognitive Domain']}")
    st.markdown(f"**Objective:** {first_item['ASHP Objective']}")

    available_types = topic_items['Resource Type'].tolist()
    
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

            # --- PAYWALL LOGIC ---
            is_premium = "youtube.com" in res_url.lower() or "youtu.be" in res_url.lower() or "notebooklm" in res_url.lower()
            has_access = True
            
            # If it's a premium resource, check if the user is a learner on the Basic tier
            if is_premium and current_role == "learner" and current_tier not in ["Pro", "Premium"]:
                has_access = False
                
            if not has_access:
                st.warning("⭐️ **Premium Feature**")
                st.write("Video lectures, audio podcasts, and AI NotebookLM integrations are reserved for Pro subscribers.")
                # You can add a link to a Stripe checkout or Google Form here later
                st.button("Upgrade to Pro", key=f"upgrade_{idx}_{first_item['Topic']}", type="primary")
                continue # Skips the rest of the code for this tab, effectively hiding the resource

            # --- RESOURCE RENDERING LOGIC ---
            
            # 1. YOUTUBE HANDLER 
            if "youtube.com" in res_url.lower() or "youtu.be" in res_url.lower():
                st.video(res_url)
                
            # 2. NOTEBOOKLM HANDLER (Cannot be embedded securely, must open in new tab)
            elif "notebooklm" in res_url.lower():
                st.info("💡 **Interactive AI Notebook**\n\nGoogle NotebookLM requires a secure browser session. Click below to open your AI study guide.")
                st.link_button(f"Open NotebookLM", res_url, type="primary")

            # 3. GOOGLE SLIDES HANDLER 
            elif "docs.google.com/presentation" in res_url.lower():
                embed_url = res_url.replace("/pub?", "/embed?").replace("/pub", "/embed")
                iframe_html = f'''
                    <iframe src="{embed_url}" width="100%" height="700" frameborder="0" allowfullscreen="true" mozallowfullscreen="true" webkitallowfullscreen="true"></iframe>
                '''
                components.html(iframe_html, height=700)

            # 4. GOOGLE DOCS & FORMS HANDLER
            elif "docs.google.com" in res_url.lower() or "forms.gle" in res_url.lower():
                embed_url = res_url
                if "embedded=true" not in embed_url and "forms.gle" not in embed_url:
                    embed_url += "&embedded=true" if "?" in embed_url else "?embedded=true"
                
                iframe_html = f'''
                    <iframe src="{embed_url}" width="100%" height="700" frameborder="0" allowfullscreen="true" mozallowfullscreen="true" webkitallowfullscreen="true"></iframe>
                '''
                components.html(iframe_html, height=700)
                
            # 5. FALLBACK HANDLER
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
    
    # Check which column the Google Form feeds into (usually 'Activity' or 'Topic')
    if 'Activity' in res_evals.columns:
        completed_topics = res_evals['Activity'].nunique()
    elif 'Topic' in res_evals.columns:
        completed_topics = res_evals['Topic'].nunique()
    else:
        completed_topics = len(res_evals) # Fallback
        
    progress_pct = min(completed_topics / total_topics, 1.0) if total_topics > 0 else 0.0
    
    st.markdown(f"**👟 Step Tracker:** `{completed_topics} / {total_topics}` Core Topics Evaluated")
    st.progress(progress_pct)

# =========================================================
# DASHBOARDS
# =========================================================

# --- ADMIN VIEW ---
if user_role == "admin":
    st.title("📈 Program Director Dashboard")
    if eval_df.empty:
        st.info("No evaluation data found.")
    else:
        res_list = eval_df['Resident Name'].dropna().unique().tolist()
        if res_list:
            sel_res = st.selectbox("Review Resident Progress:", res_list)
            
            # --- INJECT STEP TRACKER ---
            render_step_tracker(sel_res)
            st.write("---")
            
            res_data = eval_df[eval_df['Resident Name'] == sel_res]
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Completed Evaluations", len(res_data))
            with col2:
                # Convert dataframe to CSV for download
                csv_export = res_data.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Export Resident Data (CSV)",
                    data=csv_export,
                    file_name=f"{sel_res}_eval_report.csv",
                    mime='text/csv',
                    type="primary"
                )
                
            st.dataframe(res_data, use_container_width=True)
    
    st.divider()
    render_curriculum(user_role, user_tier)

# --- PRECEPTOR VIEW ---
elif user_role == "preceptor":
    st.title("👨‍🏫 Bedside Trust Verification")
    
    res_names = users_df[users_df['Role'].str.upper() == 'RESIDENT']['Name'].tolist()
    if res_names:
        target_res = st.selectbox("Select Resident", res_names)
        
        # --- INJECT STEP TRACKER ---
        render_step_tracker(target_res)
        st.write("---")
        
        cats = curriculum_df['Category / Module'].unique()
        sel_cat = st.selectbox("Module", cats)
        topics = curriculum_df[curriculum_df['Category / Module'] == sel_cat]['Topic'].unique()
        sel_topic = st.selectbox("Activity", topics)
        
        activity_row = curriculum_df[curriculum_df['Topic'] == sel_topic].iloc[0]
        st.info(f"**ASHP Objective:** {activity_row['ASHP Objective']}\n\n**Sub-Objective:** {activity_row['ASHP Sub-Objective']}")
        
        zone = st.radio("Entrustment Zone:", [
            "Zone 1: Direct Supervision (Preceptor present for all steps)", 
            "Zone 2: Proactive Supervision (Preceptor available, reviews all plans)", 
            "Zone 3: Reactive Supervision (Preceptor available on demand)", 
            "Zone 4: Independent (Resident practices independently)"
        ])
        
        # --- AUTOGENERATE PHARMACADEMIC NARRATIVE LOGIC ---
        obj_text = str(activity_row['ASHP Objective']).lower()
        sub_obj_text = str(activity_row['ASHP Sub-Objective']).replace('"', '').strip()
        action_verb = str(activity_row.get('Action Verb', 'evaluate')).lower()
        cog_domain = str(activity_row.get('Cognitive Domain', 'application')).lower()
        
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
            f"Operating within the cognitive domain of {cog_domain}, the resident demonstrated the ability to {action_verb} "
            f"as it relates to the broader program goal to {obj_text}.\n\n"
            f"Targeted Next Steps: {next_steps}"
        )

        st.divider()
        st.subheader("📝 Pharmacademic Narrative")
        st.markdown("This narrative was **auto-generated** based on the selected entrustment zone and ASHP curriculum taxonomy. You may edit the text below before copying.")
        
        final_narrative = st.text_area("Final Evaluation Text (Editable):", value=auto_narrative, height=250)
        
        if st.button("Log Evaluation internally", type="primary"):
            st.success(f"Evaluation for {target_res} logged internally.")
            st.write("**📋 Ready for Pharmacademic:** Click the copy icon in the top right corner of the box below to transpose.")
            st.code(final_narrative, language="markdown")
            
    st.divider()
    render_curriculum(user_role, user_tier)

# --- RESIDENT/LEARNER VIEW ---
elif user_role == "learner":
    st.title(f"Welcome, {name}!")
    
    # --- INJECT STEP TRACKER (Always visible above tabs) ---
    render_step_tracker(name)
    st.write("---")
    
    tab1, tab2, tab3 = st.tabs(["📚 Curriculum & Resources", "📅 My Progress & Schedule", "💡 Encouragement"])
    
    with tab1:
        render_curriculum(user_role, user_tier)
        
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
            # Filter to only this resident
            my_evals = eval_df[eval_df['Resident Name'] == name]
            
            if not my_evals.empty:
                # Attempt to sort by Date if your Google Form column is named 'Date'
                if 'Date' in my_evals.columns:
                    # Convert to datetime for accurate sorting, then sort newest to oldest
                    my_evals['Date'] = pd.to_datetime(my_evals['Date'], errors='coerce')
                    recent_10 = my_evals.sort_values(by='Date', ascending=False).head(10)
                else:
                    # Fallback just in case the Date column is missing: grab the last 10 rows added
                    recent_10 = my_evals.tail(10)
                
                # Show the total count, but only display the dataframe of the recent 10
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
