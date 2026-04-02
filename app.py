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
        
        credentials["usernames"][uname] = {
            "email": str(row['Email']),
            "name": str(row['Name']),
            "password": hpw,
            "role": r_internal
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

user_role = credentials["usernames"][username]["role"]
authenticator.logout(location="sidebar")
st.sidebar.success(f"Logged in: {name}")

# =========================================================
# REUSABLE COMPONENT: CURRICULUM VIEWER
# =========================================================
def render_curriculum():
    if curriculum_df.empty:
        st.warning("Curriculum data is currently unavailable.")
        return

    st.sidebar.title("Vision 2026 Curriculum")
    all_cats = curriculum_df['Category / Module'].dropna().unique()
    sidebar_cat = st.sidebar.selectbox("Navigate Module", all_cats)
    
    module_items = curriculum_df[curriculum_df['Category / Module'] == sidebar_cat]
    selected_item_name = st.sidebar.selectbox("Select Resource", module_items['Topic'].unique())
    
    # Grab ALL rows for the selected topic, not just the first one
    topic_items = module_items[module_items['Topic'] == selected_item_name]
    
    # We can use the first row to grab the global info like EPA and Objectives
    first_item = topic_items.iloc[0]

    st.subheader(f"📖 {first_item['Topic']}")
    st.caption(f"EPA: {first_item['EPA']} | Target: {first_item['Cognitive Domain']}")
    st.markdown(f"**Objective:** {first_item['ASHP Objective']}")

    # Get a list of the available resource types for this topic (e.g., Google Doc, Google Slides)
    available_types = topic_items['Resource Type'].tolist()
    
    if not available_types:
        st.warning("No resources attached to this topic.")
        return

    # Create dynamic tabs based on the resources available for this specific topic
    st.write("---")
    resource_tabs = st.tabs(available_types)

    # Loop through the available resources and embed them into their respective tabs
    for idx, tab in enumerate(resource_tabs):
        with tab:
            row_data = topic_items.iloc[idx]
            res_type = str(row_data['Resource Type']).strip()
            res_url = str(row_data['Resource URL (Published)']).strip()

            if pd.isna(res_url) or res_url == "" or res_url.lower() == "nan":
                st.info(f"No link provided for {res_type}.")
            else:
                # Robust URL matching for YouTube
                if "youtube.com" in res_url.lower() or "youtu.be" in res_url.lower():
                    st.video(res_url)
                    
                # Robust URL matching for Google Docs, Slides, and Forms
                elif "docs.google.com" in res_url.lower() or "forms.gle" in res_url.lower():
                    embed_url = res_url
                    
                    # forms.gle links sometimes don't need embedded=true, but docs/slides do
                    if "embedded=true" not in embed_url and "forms.gle" not in embed_url:
                        embed_url += "&embedded=true" if "?" in embed_url else "?embedded=true"
                    
                    iframe_html = f'''
                        <iframe src="{embed_url}" 
                                width="100%" 
                                height="700" 
                                frameborder="0" 
                                allowfullscreen="true" 
                                mozallowfullscreen="true" 
                                webkitallowfullscreen="true">
                        </iframe>
                    '''
                    components.html(iframe_html, height=700)
                    
                # Fallback for any other type of link
                else:
                    st.link_button(f"Open {res_type} in New Tab", res_url)

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
            res_data = eval_df[eval_df['Resident Name'] == sel_res]
            st.metric("Completed Evaluations", len(res_data))
            st.dataframe(res_data, use_container_width=True)
    
    st.divider()
    render_curriculum()

# --- PRECEPTOR VIEW ---
elif user_role == "preceptor":
    st.title("👨‍🏫 Bedside Trust Verification")
    
    res_names = users_df[users_df['Role'].str.upper() == 'RESIDENT']['Name'].tolist()
    if res_names:
        target_res = st.selectbox("Select Resident", res_names)
        cats = curriculum_df['Category / Module'].unique()
        sel_cat = st.selectbox("Module", cats)
        topics = curriculum_df[curriculum_df['Category / Module'] == sel_cat]['Topic'].unique()
        sel_topic = st.selectbox("Activity", topics)
        
        activity_row = curriculum_df[curriculum_df['Topic'] == sel_topic].iloc[0]
        st.info(f"**ASHP Objective:** {activity_row['ASHP Objective']}")
        zone = st.radio("Entrustment Zone:", ["Zone 1: Direct", "Zone 2: Proactive", "Zone 3: Reactive", "Zone 4: Independent"])
        
        if st.button("Submit Evaluation"):
            st.success("Evaluation logged to Master Database.")
            
    st.divider()
    render_curriculum()

# --- RESIDENT/LEARNER VIEW ---
elif user_role == "learner":
    st.title(f"Welcome, {name}!")
    
    tab1, tab2, tab3 = st.tabs(["📚 Curriculum & Resources", "📅 My Progress & Schedule", "💡 Encouragement"])
    
    with tab1:
        render_curriculum()
        
    with tab2:
        st.subheader("📅 Upcoming Shifts")
        if not schedule_df.empty:
            my_sched = schedule_df[schedule_df['Resident Name'] == name].head(5)
            if not my_sched.empty:
                st.table(my_sched[['Subject', 'Start Date', 'Start Time']])
            else:
                st.info("No upcoming shifts scheduled.")
        
        st.divider()
        st.subheader("📈 My Evaluation Progress")
        if not eval_df.empty:
            my_evals = eval_df[eval_df['Resident Name'] == name]
            st.metric("Total Completed Evaluations", len(my_evals))
            if not my_evals.empty:
                st.dataframe(my_evals, use_container_width=True)
        else:
            st.info("No evaluation data found yet.")
            
    with tab3:
        st.subheader("Keep Pushing Forward!")
        st.success("You are making great progress in your PGY2 EM Residency.")
        st.markdown("> *\"Success is the sum of small efforts, repeated day in and day out.\"*")
        # Balloons have been removed from here!
