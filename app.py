import requests
import datetime
import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
import urllib.parse

def generate_gcal_link(title, date_str, start_time="08:00:00", end_time="17:00:00", details=""):
    """Converts a shift into a clickable Google Calendar link"""
    # Format dates for Google Calendar (YYYYMMDDTHHMMSSZ)
    try:
        # Basic parsing assuming YYYY-MM-DD and HH:MM:SS AM/PM
        start_dt = pd.to_datetime(f"{date_str} {start_time}")
        end_dt = pd.to_datetime(f"{date_str} {end_time}")
        
        start_formatted = start_dt.strftime('%Y%m%dT%H%M%S')
        end_formatted = end_dt.strftime('%Y%m%dT%H%M%S')
        
        base_url = "https://calendar.google.com/calendar/render?action=TEMPLATE"
        params = {
            "text": title,
            "dates": f"{start_formatted}/{end_formatted}",
            "details": details
        }
        return base_url + "&" + urllib.parse.urlencode(params)
    except:
        return "https://calendar.google.com"

st.set_page_config(page_title="PGY2 EM: Trust Verification", layout="wide")

# ---------------------------------------------------------
# 1. CONNECT TO GOOGLE SHEETS (Keep your existing data loaders here)
# ---------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQVGthqSsiAk6txg7baS6n2stL4cLIP9kBOLEHx9W86W8KOjxUccExJugw8dB9-HxRh13M5CRanNCBZ/pub?gid=1033342405&single=true&output=csv"
responses_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQVGthqSsiAk6txg7baS6n2stL4cLIP9kBOLEHx9W86W8KOjxUccExJugw8dB9-HxRh13M5CRanNCBZ/pub?gid=589997778&single=true&output=csv"
schedule_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQVGthqSsiAk6txg7baS6n2stL4cLIP9kBOLEHx9W86W8KOjxUccExJugw8dB9-HxRh13M5CRanNCBZ/pub?gid=751471446&single=true&output=csv"

@st.cache_data(ttl=60)
def load_data():
    try:
        curr_df = pd.read_csv(sheet_url)
        if 'Status' in curr_df.columns:
            curr_df = curr_df[curr_df['Status'] == 'Active']
        eval_df = pd.read_csv(responses_url)
        sched_df = pd.read_csv(schedule_url) 
        return curr_df, eval_df, sched_df
    except Exception as e:
        st.error(f"Data Load Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame() 

curriculum_df, eval_df = load_data()

# Helper function for Learner Mode formatting
def display_objectives(df, target_level):
    if 'Competence Level (Miller)' in df.columns:
        df['Competence Level (Miller)'] = df['Competence Level (Miller)'].astype(str)
        level_items = df[df['Competence Level (Miller)'].str.contains(target_level, na=False)]
        if not level_items.empty:
            for index, row in level_items.iterrows():
                activity = row.get('Activity', 'Objective text missing')
                st.info(f"**Task:** {activity}")
                if 'Web Link' in row and pd.notna(row['Web Link']):
                    st.link_button("📄 Open Resource", row['Web Link'])
        else:
            st.write(f"No Level {target_level} objectives found for this module.")

# ---------------------------------------------------------
# 2. THE USER DATABASE (Powered by Google Sheets)
# ---------------------------------------------------------
import bcrypt # Add this at the top of Section 2

# 🚨 PASTE YOUR 'USER DIRECTORY' CSV LINK HERE:
users_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQVGthqSsiAk6txg7baS6n2stL4cLIP9kBOLEHx9W86W8KOjxUccExJugw8dB9-HxRh13M5CRanNCBZ/pub?gid=389769523&single=true&output=csv"

@st.cache_data(ttl=60)
def load_users():
    try:
        return pd.read_csv(users_url)
    except:
        return pd.DataFrame()

users_df = load_users()

credentials = {"usernames": {}}

if not users_df.empty:
    for index, row in users_df.iterrows():
        username = str(row['Username']).strip()
        raw_password = str(row['Password']).strip()
        
        # 1. THE SECURITY FIX: Hash the password on-the-fly
        # This converts "hansolo" into a secure bcrypt hash before the app reads it
        hashed_password = bcrypt.hashpw(raw_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # 2. THE VOCABULARY FIX: Translate the Google Sheet roles to the App's internal roles
        sheet_role = str(row['Role']).strip().lower()
        
        if sheet_role == "rpd":
            internal_role = "admin"
        elif sheet_role == "resident":
            internal_role = "learner"
        else:
            internal_role = "preceptor"
        
        # Build the secure user profile
        credentials["usernames"][username] = {
            "email": str(row['Email']).strip(),
            "name": str(row['Name']).strip(),
            "password": hashed_password,
            "role": internal_role
        }

# Initialize the authenticator with the newly hashed dictionary
authenticator = stauth.Authenticate(
    credentials, 
    "residency_dashboard", 
    "abcdef", 
    cookie_expiry_days=30
)
# ---------------------------------------------------------
# 3. THE SECURE ROUTING SYSTEM
# ---------------------------------------------------------
try:
    authenticator.login()
except Exception as e:
    st.error(e)

# We check Streamlit's internal memory (session_state) to see if they logged in
if st.session_state.get("authentication_status") is False:
    st.error("❌ Username/password is incorrect")
    
elif st.session_state.get("authentication_status") is None:
    st.warning("🔒 Please enter your username and password")
    
elif st.session_state.get("authentication_status") is True:
    
    # --- IF LOGGED IN SUCCESSFULLY ---
    name = st.session_state["name"]
    username = st.session_state["username"]
    user_role = credentials["usernames"][username]["role"]
    
    authenticator.logout("Logout", "sidebar")
    st.sidebar.success(f"Welcome, *{name}*")
    
    # Grab the Resident Roster so all rooms can use it
    if 'Resident Roster' in curriculum_df.columns:
        active_residents = curriculum_df['Resident Roster'].dropna().unique().tolist()
        active_residents.insert(0, "Select Learner...") 
    else:
        active_residents = ["⚠️ Add 'Resident Roster' column"]

    # =========================================================
    # ROOM C: THE RPD DASHBOARD (ADMIN ONLY) 
    # **MOVED TO TOP**
    # =========================================================
    if user_role == "admin":
        st.title("📈 Live Resident Status Board")
        st.write("Program-wide analytics and progression tracking.")
        
        if eval_df.empty:
            st.info("No evaluations logged yet. Once preceptors submit data, charts will appear here.")
            st.stop()
            
        # 3. SELECT A RESIDENT TO REVIEW
        # Assuming your form question was exactly "Resident Name"
        resident_list = eval_df['Resident Name'].dropna().unique().tolist()
        selected_resident = st.selectbox("Select Resident to Review:", resident_list)
        
        # Filter the data for just this resident
        resident_data = eval_df[eval_df['Resident Name'] == selected_resident]
        
        # 4. SUMMARY METRICS
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Evaluations", len(resident_data))
        with col2:
            # Get the most recent zone achieved
            latest_zone = resident_data.iloc[-1]['Zone'] if 'Zone' in resident_data.columns else "N/A"
            st.metric("Latest Entrustment Zone", latest_zone)
            
        st.divider()
        
        # 5. VISUALIZE ENTRUSTMENT PROGRESSION
        if 'Zone' in resident_data.columns:
            st.markdown("### Entrustment Zone Distribution")
            st.caption("How much supervision has this resident required across all logged activities?")
            
            # Count how many times they hit each zone and plot it
            zone_counts = resident_data['Zone'].value_counts().reset_index()
            zone_counts.columns = ['Zone', 'Count']
            st.bar_chart(data=zone_counts, x='Zone', y='Count')
            
        # 6. RAW DATA LOG
        st.markdown("### Recent Evaluation Log")
        # Display the raw data cleanly, hiding any blank columns
        st.dataframe(resident_data.dropna(axis=1, how='all'), use_container_width=True)

  # --- 5. SUBMIT & NARRATIVE GENERATOR ---
    if st.button("Submit Evaluation & Log Data", use_container_width=True):
        
        today = datetime.date.today().strftime("%B %d, %Y")
        form_url = "https://docs.google.com/forms/d/e/1FAIpQLSfhRstSlY7fxJMfXoPtgeCQTeyTdKcWEoGH8nU9jYs9Fhoz_g/formResponse"
        
        form_data = {
            "entry.1175930505": resident_name,                              
            "entry.597824849": selected_activity,                           
            "entry.575285059": activity_data.get('ASHP Objective', 'N/A'),  
            "entry.930508246": observed_bloom,                              
            "entry.411526759": zone                                         
        }
        
        # Make sure 'try' and 'except' have the exact same number of spaces!
        try:
            response = requests.post(form_url, data=form_data)
            if response.status_code == 200:
                st.success(f"✅ Evaluation seamlessly logged to the RPD Database for {resident_name}!")
            else:
                st.error(f"⚠️ The data didn't save! Google rejected the Entry IDs. (Error {response.status_code})")
        except Exception as e:
            st.error(f"Warning: Could not connect to Google Forms. ({e})")
        
        narrative = (
            f"CLINICAL EVALUATION SUMMARY ({today}):\n"
            f"Learner: {resident_name}\n"
            f"Activity: {selected_activity}\n"
            f"ASHP Objective: {activity_data.get('ASHP Objective', 'N/A')}\n\n"
            f"During this clinical activity, the resident was evaluated on their ability to perform tasks related to {activity_data.get('ASHP Objective', 'the assigned objective')}. "
            f"The resident successfully demonstrated a cognitive complexity at the '{observed_bloom}' level (Target: {activity_data.get('Cognitive Domain', 'N/A')}). "
            f"Clinically, the resident required '{zone}' supervision from the preceptor to complete the necessary patient care tasks safely and effectively. "
            f"This activity aligns with the program's progression toward independent clinical practice."
        )

    # =========================================================
    # ROOM B: THE PRECEPTOR PERSPECTIVE (PRECEPTOR & ADMIN)
    # **MOVED TO TOP**
    # =========================================================
    if user_role in ["preceptor", "admin"]:
        st.title("👨‍🏫 Preceptor Evaluation Tools")
        st.write("Perform real-time bedside Trust Verification.")
        
        resident_name = st.selectbox("Select Resident", active_residents)
        
        # --- NEW: CASCADING ACTIVITY FILTER ---
        st.markdown("##### Locate Activity")
        col1, col2 = st.columns(2)
        with col1:
            # Optional EPA Filter
            filter_epa = st.selectbox("Filter by EPA (Optional)", ["All EPAs"] + list(curriculum_df['EPA'].dropna().unique()))
        
        filtered_curr = curriculum_df
        if filter_epa != "All EPAs":
            filtered_curr = filtered_curr[filtered_curr['EPA'] == filter_epa]
            with col2:
                # Optional Module Filter
                filter_module = st.selectbox("Filter by Module", ["All Modules"] + list(filtered_curr['Module'].dropna().unique()))
                if filter_module != "All Modules":
                    filtered_curr = filtered_curr[filtered_curr['Module'] == filter_module]

        # The final dropdown (Reminder: Users can type directly into this box to search!)
        selected_activity = st.selectbox("🔍 Search or Select Activity to Evaluate", filtered_curr['Activity'].unique())
        
        # 🚨 PASTE THE REST OF YOUR ROOM B EVALUATION CODE HERE 🚨
        # (Start from `filtered_data = curriculum_df...` down to the Submit button)

        # --- 3. LOAD RUBRIC DATA ---
        filtered_data = curriculum_df[curriculum_df['Activity'] == selected_activity]
        
        if filtered_data.empty:
            st.warning("⚠️ No data found for this activity. Please select another or check the Google Sheet.")
            st.stop() 
        
        activity_data = filtered_data.iloc[0]
        
        st.markdown("### 🎯 Target Rubric")
        try:
            st.info(f"**ASHP Objective:** {activity_data['ASHP Objective']}\n\n**Target Cognitive Domain:** {activity_data['Cognitive Domain']} ({activity_data['Action Verb']})")
        except KeyError:
            st.warning("⚠️ Waiting for 'ASHP Objective' and 'Cognitive Domain' columns to be added to the Google Sheet.")
    
        st.divider()
    
        # --- 4. DUAL-AXIS EVALUATION ---
        st.markdown("### 🧠 1. Observed Cognitive Level")
        blooms_options = ["Remembering", "Understanding", "Applying", "Analyzing", "Evaluating", "Creating"]
        default_bloom = activity_data.get('Cognitive Domain', "Applying")
        default_index = blooms_options.index(default_bloom) if default_bloom in blooms_options else 2
        
        observed_bloom = st.select_slider("Bloom's Taxonomy:", options=blooms_options, value=blooms_options[default_index])
    
        st.markdown("### 📊 2. Entrustment Level")
        zone = st.radio("Miller's Pyramid / Trust Zones:", 
                        ["Zone 1: Requires Direct Observation", 
                         "Zone 2: Requires Proactive Supervision", 
                         "Zone 3: Requires Reactive Supervision", 
                         "Zone 4: Ready for Independent Practice"])
    
        st.divider()
       
    # --- 5. SUBMIT & NARRATIVE GENERATOR ---
        
        today = datetime.date.today().strftime("%B %d, %Y")
        form_url = "https://docs.google.com/forms/d/e/1FAIpQLSfhRstSlY7fxJMfXoPtgeCQTeyTdKcWEoGH8nU9jYs9Fhoz_g/formResponse"
            
        form_data = {
            "entry.1175930505": resident_name,                              
            "entry.597824849": selected_activity,                           
            "entry.575285059": activity_data.get('ASHP Objective', 'N/A'),  
            "entry.930508246": observed_bloom,                              
            "entry.411526759": zone                                         
            }
            
        try:
            response = requests.post(form_url, data=form_data)
            if response.status_code == 200:
                st.success(f"✅ Evaluation seamlessly logged to the RPD Database for {resident_name}!")
            else:
                st.error(f"⚠️ The data didn't save! Google rejected the Entry IDs. (Error {response.status_code})")
        except Exception as e:
            st.error(f"Warning: Could not connect to Google Forms. ({e})")
            
        narrative = (
            f"CLINICAL EVALUATION SUMMARY ({today}):\n"
            f"Learner: {resident_name}\n"
            f"Activity: {selected_activity}\n"
            f"ASHP Objective: {activity_data.get('ASHP Objective', 'N/A')}\n\n"
            f"During this clinical activity, the resident was evaluated on their ability to perform tasks related to {activity_data.get('ASHP Objective', 'the assigned objective')}. "
            f"The resident successfully demonstrated a cognitive complexity at the '{observed_bloom}' level (Target: {activity_data.get('Cognitive Domain', 'N/A')}). "
            f"Clinically, the resident required '{zone}' supervision from the preceptor to complete the necessary patient care tasks safely and effectively. "
            f"This activity aligns with the program's progression toward independent clinical practice."
        )
            
        st.markdown("### 📋 Pharmacademic Export")
        st.caption("Click the copy icon in the top right corner of the box below to paste directly into Pharmacademic.")
        st.code(narrative, language="text")
        
        st.divider()


    # =========================================================
    # ROOM A1: THE PROGRESS TRACKER (LEARNERS ONLY)
    # =========================================================
    if user_role == "learner":
        st.title("My Clinical Journey")
        
        learner_name = name 
        total_activities = len(curriculum_df['Activity'].unique())
        
        if not eval_df.empty and 'Resident Name' in eval_df.columns:
            learner_evals = eval_df[eval_df['Resident Name'] == learner_name]
            completed_activities = learner_evals['Activity'].nunique()
        else:
            completed_activities = 0
            
        progress_pct = completed_activities / total_activities if total_activities > 0 else 0
        
        st.markdown(f"### 🏃‍♂️ Curriculum Progress: {completed_activities} / {total_activities} Tasks")
        st.progress(progress_pct)
        
        if progress_pct == 0:
            st.info("🌱 Your journey begins today! Dive into the Level 1 materials below to get started.")
        elif progress_pct < 0.25:
            st.success("🔥 Great start! You are building a rock-solid foundation. Keep knocking out those didactic modules.")
        elif progress_pct < 0.75:
            st.success("🚀 Incredible momentum! You are deep in the trenches now. Keep pushing for those bedside evaluations.")
        elif progress_pct < 1.0:
            st.success("🏆 You are in the home stretch! Focus on polishing those Zone 4 independent skills.")
        else:
            st.balloons() 
            st.success("🌟 CURRICULUM COMPLETE! You are ready for independent practice.")
            
        # --- NEW: LIVE RESIDENT STATUS LOG ---
        st.markdown("### 📊 My Recent Evaluations")
        if not eval_df.empty and 'Resident Name' in eval_df.columns:
            if completed_activities > 0:
                # Clean up the table to show just the essentials, grabbing the 5 most recent
                my_recent_evals = learner_evals[['Date', 'Activity', 'Zone', "Bloom's Level"]].tail(5)
                st.dataframe(my_recent_evals, use_container_width=True, hide_index=True)
            else:
                st.info("No evaluations logged yet. Complete tasks with your preceptor to see them here!")

       # --- LIVE SCHEDULE & GOOGLE CALENDAR SYNC ---
        st.markdown("### 📅 My Upcoming Schedule")
        
        if not schedule_df.empty:
            try:
                # 1. Filter for the logged-in user
                # We use .str.contains to be flexible with names
                my_schedule = schedule_df[schedule_df['Resident Name'].str.contains(learner_name, na=False, case=False)]
                
                # 2. Convert Date and Sort
                my_schedule['Start Date'] = pd.to_datetime(my_schedule['Start Date'])
                
                # Only show today and future dates
                today_dt = pd.to_datetime(datetime.date.today())
                upcoming = my_schedule[my_schedule['Start Date'] >= today_dt].sort_values(by='Start Date').head(5)
                
                if upcoming.empty:
                    st.info("No upcoming shifts found in the system for your name.")
                else:
                    for index, row in upcoming.iterrows():
                        shift_title = row['Subject']
                        shift_date = row['Start Date'].strftime('%B %d, %Y')
                        start_t = row.get('Start Time', '08:00:00 AM')
                        
                        with st.expander(f"🗓️ {shift_date} | **{shift_title}**"):
                            st.write(f"**Time:** {start_t} - {row.get('End Time', 'N/A')}")
                            
                            # Generate Google Calendar Link
                            gcal_link = generate_gcal_link(
                                title=f"EM Shift: {shift_title}", 
                                date_str=row['Start Date'].strftime('%Y-%m-%d'),
                                start_time=start_t,
                                end_time=row.get('End Time', '05:00:00 PM')
                            )
                            st.link_button("➕ Add to Google Calendar", gcal_link)
                            
            except Exception as e:
                # This will tell us EXACTLY why it's failing
                st.warning(f"Schedule Sync Error: Missing or mismatched column. (Details: {e})")
        else:
            st.error("Schedule database is empty or link is broken.")

    # =========================================================
    # ROOM A2: THE RESOURCE LIBRARY (EVERYONE SEES THIS)
    # **MOVED TO BOTTOM**
    # =========================================================
    st.markdown("### 📚 Clinical Preparation")
    st.write("Access your foundational knowledge and protocols below.")
    
    st.sidebar.title("Vision 2026 Curriculum")
    st.sidebar.markdown("**Protection of Execution**")
    
    # 🚨 PASTE YOUR ROOM A2 CURRICULUM TABS CODE HERE 🚨
    # (Start from `if not curriculum_df.empty:` down through the `with level4:` tab)

    if not curriculum_df.empty:
        available_epas = curriculum_df['EPA'].dropna().unique()
        selected_epa = st.sidebar.selectbox("Select EPA", available_epas)
        
        epa_filtered_df = curriculum_df[curriculum_df['EPA'] == selected_epa]
        available_modules = epa_filtered_df['Module'].dropna().unique()
        selected_module = st.sidebar.selectbox("Active Module", available_modules)
        
        module_data = epa_filtered_df[epa_filtered_df['Module'] == selected_module]
    else:
        selected_epa, selected_module = "Loading...", "Loading..."
        module_data = pd.DataFrame()

    st.markdown(f"### {selected_epa} | {selected_module}")
    st.markdown("---")

    level1, level2, level3, level4 = st.tabs([
        "📚 Level 1: Knows", 
        "🗣️ Level 2: Knows How", 
        "🎯 Level 3: Shows How (Sim)", 
        "🏥 Level 4: Does (Live)"
    ])

    with level1:
        st.header("Level 1: Knows (Cognitive Audit)")
        if not module_data.empty: display_objectives(module_data, "1")

    with level2:
        st.header("Level 2: Knows How (Competence)")
        if not module_data.empty: display_objectives(module_data, "2")

    with level3:
        st.header("Level 3: Shows How (The Simulation Gateway)")
        if not module_data.empty: display_objectives(module_data, "3")

    with level4:
        st.header("Level 4: Does (Trust Verification)")
        st.write("Assessment: Direct Observation during a live clinical event.")
        if not module_data.empty: display_objectives(module_data, "4")
        # DELETE EVERYTHING BELOW THIS POINT! 
        # (No more resident name inputs, entrustment scales, or submit buttons here. 
        # The Preceptor Tool at the top handles all of that now!)
