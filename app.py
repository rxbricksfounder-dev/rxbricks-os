import requests
import datetime
import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth

st.set_page_config(page_title="PGY2 EM: Trust Verification", layout="wide")

# ---------------------------------------------------------
# 1. CONNECT TO GOOGLE SHEETS (Keep your existing data loaders here)
# ---------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQVGthqSsiAk6txg7baS6n2stL4cLIP9kBOLEHx9W86W8KOjxUccExJugw8dB9-HxRh13M5CRanNCBZ/pub?gid=1033342405&single=true&output=csv"
responses_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQVGthqSsiAk6txg7baS6n2stL4cLIP9kBOLEHx9W86W8KOjxUccExJugw8dB9-HxRh13M5CRanNCBZ/pub?gid=589997778&single=true&output=csv"

@st.cache_data(ttl=60)
def load_data():
    try:
        curr_df = pd.read_csv(sheet_url)
        if 'Status' in curr_df.columns:
            curr_df = curr_df[curr_df['Status'] == 'Active']
        eval_df = pd.read_csv(responses_url)
        return curr_df, eval_df
    except Exception as e:
        st.error(f"Connection Failed. System Error: {e}")
        return pd.DataFrame(), pd.DataFrame() 

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
# 2. THE USER DATABASE & AUTHENTICATOR
# ---------------------------------------------------------
credentials = {
    "usernames": {
        "jsmith": {"email": "jsmith@test.com", "name": "Dr. Smith", "password": "abc", "role": "learner"},
        "preceptor1": {"email": "p1@test.com", "name": "Dr. Preceptor", "password": "def", "role": "preceptor"},
        "rpd": {"email": "rpd@test.com", "name": "Program Director", "password": "ghi", "role": "admin"}
    }
}

# The new authenticator has "auto_hash=True" by default!
# It will securely scramble the "abc", "def", "ghi" passwords automatically.
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
    
    # =========================================================
    # ROOM A: THE LEARNER PERSPECTIVE (EVERYONE SEES THIS)
    # =========================================================
    st.title("My Clinical Journey")
    
    # 🚨 PASTE ALL OF YOUR ROOM A CODE HERE 🚨
    # (Start from "if 'Resident Roster' in curriculum_df.columns:" 
    # and paste all the way down through the 4 Miller's Pyramid Tabs)
    # DO NOT paste "if app_mode == 'Learner Mode':"
    
    # --- 1. IDENTIFY THE LEARNER ---
    if 'Resident Roster' in curriculum_df.columns:
        active_residents = curriculum_df['Resident Roster'].dropna().unique().tolist()
        active_residents.insert(0, "Select your name...") 
    else:
        active_residents = ["⚠️ Add 'Resident Roster' column"]

    learner_name = st.selectbox("Who is viewing this?", active_residents)
    
    # --- 2. CALCULATE PROGRESS ---
    if learner_name != "Select your name...":
        # Total active activities in the curriculum
        total_activities = len(curriculum_df['Activity'].unique())
        
        # Total unique activities this resident has been evaluated on
        if not eval_df.empty and 'Resident Name' in eval_df.columns:
            learner_evals = eval_df[eval_df['Resident Name'] == learner_name]
            completed_activities = learner_evals['Activity'].nunique()
        else:
            completed_activities = 0
            
        # Calculate Percentage (Prevent dividing by zero)
        progress_pct = completed_activities / total_activities if total_activities > 0 else 0
        
        # --- 3. THE STEP TRACKER UI ---
        st.markdown(f"### 🏃‍♂️ Curriculum Progress: {completed_activities} / {total_activities} Tasks")
        
        # Streamlit's native progress bar requires a float between 0.0 and 1.0
        st.progress(progress_pct)
        
        # --- 4. DYNAMIC ENCOURAGEMENT ---
        if progress_pct == 0:
            st.info("🌱 Your journey begins today! Dive into the Level 1 materials below to get started.")
        elif progress_pct < 0.25:
            st.success("🔥 Great start! You are building a rock-solid foundation. Keep knocking out those didactic modules.")
        elif progress_pct < 0.75:
            st.success("🚀 Incredible momentum! You are deep in the trenches now. Keep pushing for those bedside evaluations.")
        elif progress_pct < 1.0:
            st.success("🏆 You are in the home stretch! Focus on polishing those Zone 4 independent skills.")
        else:
            st.balloons() # Triggers a cool balloon animation in Streamlit!
            st.success("🌟 CURRICULUM COMPLETE! You are ready for independent practice.")
            
        st.divider()

    # --- 5. THE RESOURCE LIBRARY ---
    st.markdown("### 📚 Clinical Preparation")
    st.write("Access your foundational knowledge and protocols below.")
    
    st.sidebar.title("Vision 2026 Curriculum")
    st.sidebar.markdown("**Protection of Execution**")

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
        if not module_data.empty: display_objectives(module_data, "4")


    # =========================================================
    # ROOM B: THE PRECEPTOR PERSPECTIVE
    # =========================================================
    if user_role in ["preceptor", "admin"]:
        st.divider()
        st.title("👨‍🏫 Preceptor Evaluation Tools")
        
        # 🚨 PASTE ALL OF YOUR ROOM B CODE HERE 🚨
        # (Start from "if 'Resident Roster' in curriculum_df.columns:" where it builds the dropdown,
        # down through the Bloom's slider, Entrustment zone, and Submit Button)
        # DO NOT paste "elif app_mode == 'Preceptor Mode':" or the old PIN Padlock code!
  
    if 'Resident Roster' in curriculum_df.columns:
        active_residents = curriculum_df['Resident Roster'].dropna().unique().tolist()
        active_residents.insert(0, "Select Learner...") 
    else:
        active_residents = ["⚠️ Add 'Resident Roster' column to Sheet"]

    resident_name = st.selectbox("Select Resident", active_residents)
    
    # 🚨 THIS IS THE LINE THAT WAS MISSING! 🚨
    selected_activity = st.selectbox("Select Activity to Evaluate", curriculum_df['Activity'].unique())
    
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

    # =========================================================
    # ROOM C: THE RPD DASHBOARD
    # =========================================================
    if user_role == "admin":
        st.divider()
        st.title("📈 Live Resident Status Board")
        
        # 🚨 PASTE ALL OF YOUR ROOM C CODE HERE 🚨
        # (Start from reading the Form Responses CSV down to the Bar Chart and dataframe)
        # DO NOT paste "elif app_mode == 'RPD Dashboard':" or the old PIN Padlock code!

    responses_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQVGthqSsiAk6txg7baS6n2stL4cLIP9kBOLEHx9W86W8KOjxUccExJugw8dB9-HxRh13M5CRanNCBZ/pub?gid=589997778&single=true&output=csv"
    
    try:
        # Load the data and skip the timestamp column for cleaner viewing
        eval_df = pd.read_csv(responses_url)
        
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

    except Exception as e:
        st.error(f"Could not load the evaluation database. Check the CSV link. Error: {e}")
