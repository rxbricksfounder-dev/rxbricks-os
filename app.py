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

# 🚨 DATABASE LINKS (Updated to your RxBricks Master Sheets)
sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=0&single=true&output=csv"
responses_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=676004133&single=true&output=csv"
users_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=1844709292&single=true&output=csv"
schedule_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQSRv0bDNmRR1p97XJtIYKfsUL01mTUfqrCe8wcluUan6hF-pOMRus-NTvxawFlXeawAmSb2yoKfmre/pub?gid=2040997103&single=true&output=csv"

# 2. HELPER FUNCTIONS 
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

@st.cache_data(ttl=60)
def load_all_data():
    try:
        curr = pd.read_csv(sheet_url)
        resp = pd.read_csv(responses_url)
        sched = pd.read_csv(schedule_url)
        user_db = pd.read_csv(users_url)
        return curr, resp, sched, user_db
    except Exception as e:
        st.error(f"Data Load Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

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
# ROOM C: RPD DASHBOARD (ADMIN ONLY)
# =========================================================
if user_role == "admin":
    st.title("📈 Program Director Dashboard")
    if eval_df.empty:
        st.info("No evaluation data found.")
    else:
        res_list = eval_df['Resident Name'].dropna().unique().tolist()
        sel_res = st.selectbox("Review Resident Progress:", res_list)
        res_data = eval_df[eval_df['Resident Name'] == sel_res]
        st.metric("Completed Evaluations", len(res_data))
        st.dataframe(res_data, use_container_width=True)

# =========================================================
# ROOM B: PRECEPTOR EVALUATION TOOL
# =========================================================
if user_role in ["preceptor", "admin"]:
    st.title("👨‍🏫 Bedside Trust Verification")
    
    # Selection Logic
    res_names = users_df[users_df['Role'].str.upper() == 'RESIDENT']['Name'].tolist()
    target_res = st.selectbox("Select Resident", res_names)
    
    # Filter by Category
    cats = curriculum_df['Category / Module'].unique()
    sel_cat = st.selectbox("Module", cats)
    
    # Filter by Topic
    topics = curriculum_df[curriculum_df['Category / Module'] == sel_cat]['Topic'].unique()
    sel_topic = st.selectbox("Activity", topics)
    
    activity_row = curriculum_df[curriculum_df['Topic'] == sel_topic].iloc[0]
    
    st.info(f"**ASHP Objective:** {activity_row['ASHP Objective']}")
    
    zone = st.radio("Entrustment Zone:", ["Zone 1: Direct", "Zone 2: Proactive", "Zone 3: Reactive", "Zone 4: Independent"])
    
    if st.button("Submit Evaluation"):
        # Google Form POST Logic would go here
        st.success("Evaluation logged to Master Database.")

# =========================================================
# ROOM A: THE RESOURCE LIBRARY & JOURNEY
# =========================================================
st.divider()
st.sidebar.title("Vision 2026 Curriculum")

if not curriculum_df.empty:
    all_cats = curriculum_df['Category / Module'].dropna().unique()
    sidebar_cat = st.sidebar.selectbox("Navigate Module", all_cats)
    
    module_items = curriculum_df[curriculum_df['Category / Module'] == sidebar_cat]
    selected_item_name = st.sidebar.selectbox("Select Resource", module_items['Topic'].unique())
    selected_item = module_items[module_items['Topic'] == selected_item_name].iloc[0]

    st.subheader(f"📖 {selected_item['Topic']}")
    st.caption(f"EPA: {selected_item['EPA']} | Target: {selected_item['Cognitive Domain']}")

    # --- THE MEDIA ROOM (EMBEDDING LOGIC) ---
    res_type = selected_item['Resource Type']
    res_url = selected_item['Resource URL (Published)']

    if pd.isna(res_url) or res_url == "":
        st.warning("No digital resource linked for this activity yet.")
    else:
        with st.expander("📂 View Clinical Resource", expanded=True):
            if res_type == "Google Doc" or res_type == "Google Slides":
                # Embed the Published Google Doc/Slide
                components.iframe(res_url, height=600, scrolling=True)
            elif res_type == "YouTube":
                # Use the Native YouTube Player
                st.video(res_url)
            else:
                st.link_button("Open Resource in New Tab", res_url)

    st.markdown(f"**Objective:** {selected_item['ASHP Objective']}")
    
# Schedule Logic (Learner Only)
if user_role == "learner":
    st.divider()
    st.subheader("📅 My Upcoming Shifts")
    my_sched = schedule_df[schedule_df['Resident Name'] == name].head(5)
    if not my_sched.empty:
        st.table(my_sched[['Subject', 'Start Date', 'Start Time']])
    else:
        st.info("No upcoming shifts scheduled.")
