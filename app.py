import streamlit as st
import pandas as pd

st.set_page_config(page_title="PGY2 EM: Trust Verification", layout="wide")

# ---------------------------------------------------------
# 1. Connect to the Live Google Sheet
# ---------------------------------------------------------
# IMPORTANT: Replace this placeholder with your actual Sheet ID!
SHEET_ID = "1zpbz0IQoNfDZkmE-kdh98vXHdD2zHEK0E3euCo016eQ"
GID = "0" # This targets the first tab in your spreadsheet

# This special URL tells Google to hand the data to Python as a clean CSV
sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

# ttl=600 tells the app to check the Google Sheet for new updates every 10 minutes
@st.cache_data(ttl=600) 
def load_curriculum():
    try:
        # Read the live web link into a pandas DataFrame
        df = pd.read_csv(sheet_url)
        return df
    except Exception as e:
        st.error("Could not connect to the Google Sheet. Please check the sharing permissions and Sheet ID.")
        return pd.DataFrame() 

# Load the data into the app
curriculum_df = load_curriculum()

# ---------------------------------------------------------
# 2. Dynamic Sidebar (Vision 2026 Curriculum)
# ---------------------------------------------------------
st.sidebar.title("Vision 2026 Curriculum")
st.sidebar.markdown("**Protection of Execution**")

if not curriculum_df.empty:
    # Build dropdowns based on what is actually in the spreadsheet
    available_epas = curriculum_df['EPA'].dropna().unique()
    selected_epa = st.sidebar.selectbox("Select EPA", available_epas)
    
    # Filter modules that belong to the selected EPA
    epa_filtered_df = curriculum_df[curriculum_df['EPA'] == selected_epa]
    available_modules = epa_filtered_df['Module'].dropna().unique()
    selected_module = st.sidebar.selectbox("Active Module", available_modules)
    
    # Final filter: isolate only the rows (objectives) for the chosen module
    module_data = epa_filtered_df[epa_filtered_df['Module'] == selected_module]
else:
    selected_epa, selected_module = "Loading...", "Loading..."
    module_data = pd.DataFrame()

st.title(f"{selected_epa} | {selected_module}")
st.markdown("---")

# ---------------------------------------------------------
# 3. Miller's Pyramid Sorting Logic
# ---------------------------------------------------------
level1, level2, level3, level4 = st.tabs([
    "📚 Level 1: Knows", 
    "🗣️ Level 2: Knows How", 
    "🎯 Level 3: Shows How (Sim)", 
    "🏥 Level 4: Does (Live)"
])

# Helper function to display objectives cleanly
def display_objectives(df, target_level):
    if 'Competence Level (Miller)' in df.columns:
        # Convert to string just in case pandas read the numbers as integers
        df['Competence Level (Miller)'] = df['Competence Level (Miller)'].astype(str)
        level_items = df[df['Competence Level (Miller)'].str.contains(target_level, na=False)]
        
        if not level_items.empty:
            for index, row in level_items.iterrows():
                activity = row.get('Activity', 'Objective text missing')
                st.info(f"**Task:** {activity}")
                
                # If you eventually add Google Drive web links to your spreadsheet, 
                # you can display them as clickable buttons here!
                if 'Web Link' in row and pd.notna(row['Web Link']):
                    st.link_button("📄 Open Resource", row['Web Link'])
        else:
            st.write(f"No Level {target_level} objectives found for this module.")
    else:
        st.warning("Please ensure your Google Sheet has a column named 'Competence Level (Miller)'")

# ---------------------------------------------------------
# 4. Render the 4 Stages
# ---------------------------------------------------------
with level1:
    st.header("Level 1: Knows (Cognitive Audit)")
    st.write("Assessment: Written Exams, Topic Discussions. Goal: 'Tell me what you would do.'")
    if not module_data.empty:
        display_objectives(module_data, "1")

with level2:
    st.header("Level 2: Knows How (Competence)")
    st.write("Assessment: Case Presentations. Goal: 'Explain your strategy.'")
    if not module_data.empty:
        display_objectives(module_data, "2")

with level3:
    st.header("Level 3: Shows How (The Simulation Gateway)")
    st.warning("⚠️ CRITICAL CHECKPOINT: The resident must pass this mock scenario before they are allowed to manage a live patient alone.")
    if not module_data.empty:
        display_objectives(module_data, "3")
        
    if st.button("Issue Verification Badge"):
        st.success("Badge Issued! Resident is authorized for clinical response.")

with level4:
    st.header("Level 4: Does (Trust Verification)")
    st.write("Assessment: Direct Observation during a live clinical event.")
    if not module_data.empty:
        display_objectives(module_data, "4")
        
    st.subheader("Entrustment Scale (Risk Matrix)")
    resident_name = st.text_input("Resident Name:")
    entrustment_level = st.radio(
        "Select supervision level required during this event:",
        [
            "Zone 1: Not Entrustable (Intervention Required)",
            "Zone 2: Prescribed Supervision (Reactive Prompting)",
            "Zone 3: Entrustable (Independent)"
        ]
    )
    if st.button("Submit Clinical Evaluation"):
        # In a future update, we can have this button write the score directly back to a Google Sheet!
        st.toast(f"Evaluation saved for {resident_name}. Current status: {entrustment_level.split(':')[0]}")