import streamlit as st
import gspread
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google.oauth2.service_account import Credentials
import numpy as np
from datetime import datetime, date
import time 
import os
from tmscraper import get_player_data
def setup_scraperapi():
    """Set up ScraperAPI key from Streamlit secrets"""
    st.write("DEBUG: Checking for ScraperAPI key...")
    
    try:
        # Check if st.secrets exists
        st.write(f"DEBUG: st.secrets exists: {hasattr(st, 'secrets')}")
        
        if hasattr(st, 'secrets'):
            # Check what keys are available in secrets
            try:
                secret_keys = list(st.secrets.keys())
                st.write(f"DEBUG: Available secret keys: {secret_keys}")
            except Exception as e:
                st.write(f"DEBUG: Error getting secret keys: {e}")
            
            # Check specifically for SCRAPERAPI_KEY
            if 'SCRAPERAPI_KEY' in st.secrets:
                key = st.secrets['SCRAPERAPI_KEY']
                masked_key = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else f"{key[:4]}..."
                st.write(f"DEBUG: Found SCRAPERAPI_KEY: {masked_key}")
                os.environ['SCRAPERAPI_KEY'] = key
                return True
            else:
                st.write("DEBUG: SCRAPERAPI_KEY not found in secrets")
        else:
            st.write("DEBUG: st.secrets not available")
            
    except Exception as e:
        st.write(f"DEBUG: Exception in setup_scraperapi: {e}")
    
    # Check if already in environment
    env_key = os.getenv('SCRAPERAPI_KEY')
    if env_key:
        masked_key = f"{env_key[:8]}...{env_key[-4:]}" if len(env_key) > 12 else f"{env_key[:4]}..."
        st.write(f"DEBUG: Found SCRAPERAPI_KEY in environment: {masked_key}")
        return True
    else:
        st.write("DEBUG: SCRAPERAPI_KEY not in environment")
        
    return False

 
# Page configuration
st.set_page_config(
    page_title="FCM Scouting System",
    page_icon="⚽",
    layout="wide"
)

# Authentication setup
@st.cache_resource
def init_connection():
    """Initialize connection to Google Sheets"""
    try:
        credentials = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/script.external_request"  # Add this scope
            ]
        )
        return gspread.authorize(credentials) 
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {e}")
        st.info("Please add your Google Service Account credentials to Streamlit secrets")
        return None
# Data loading functions
@st.cache_data(ttl=30)  # Cache for 30 seconds for near real-time updates
def load_scouting_data(sheet_url):
    """Load all scouting data from single Google Sheet"""
    try:
        conn = init_connection()
        if not conn:
            return pd.DataFrame()
        
        sheet = conn.open_by_url(sheet_url)
        worksheet = sheet.sheet1  # Use first worksheet
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Clean up data types
        numeric_cols = ['Age', 'CR', 'PR'] + [col for col in df.columns if col in ALL_ATTRIBUTES]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    except Exception as e:
        st.error(f"Error loading scouting data: {e}")
        return pd.DataFrame()
def add_player_to_sheet(sheet_url, player_data):
    """Add new player to Google Sheet"""
    try:
        conn = init_connection()
        sheet = conn.open_by_url(sheet_url)
        worksheet = sheet.sheet1
        
        # Get headers to match column order
        headers = worksheet.row_values(1)
        if not headers:
            # If no headers, create them
            headers = get_all_column_headers()
            worksheet.update('1:1', [headers])

        # Generate unique Entry_ID
        import uuid
        entry_id = str(uuid.uuid4())[:8]  # Short unique ID
        player_data["Entry_ID"] = entry_id
        
        # Create row data matching headers
        row_data = []
        for header in headers:
            if header == "Comment":
                row_data.append("")  # Always empty for new players
            else:
                row_data.append(player_data.get(header, ""))
        
        worksheet.append_row(row_data)
        #worksheet.append_row(row_data)
        st.success(f"Player {player_data.get('Player', 'Unknown')} added successfully! (Entry ID: {entry_id})")
        st.cache_data.clear()
        
    except Exception as e:
        st.error(f"Error adding player: {e}")
def add_comment_to_cell(sheet_url, row_index, col_index, comment_text):
    """Add a proper Google Sheets note to a specific cell"""
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        
        credentials = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        
        service = build('sheets', 'v4', credentials=credentials)
        
        # Get spreadsheet ID
        conn = init_connection()
        sheet = conn.open_by_url(sheet_url)
        spreadsheet_id = sheet.id
        
        # Get worksheet ID properly using the API
        spreadsheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        worksheet_id = spreadsheet_metadata['sheets'][0]['properties']['sheetId']
        
        # Convert pandas/numpy types to native Python int
        row_start = int(row_index)
        row_end = int(row_index) + 1
        col_start = int(col_index)
        col_end = int(col_index) + 1
        
        # Create the batch update request for adding a note AND cell value
        requests = [{
            "updateCells": {
                "range": {
                    "sheetId": int(worksheet_id),
                    "startRowIndex": row_start,
                    "endRowIndex": row_end,
                    "startColumnIndex": col_start,
                    "endColumnIndex": col_end
                },
                "rows": [{
                    "values": [{
                        "userEnteredValue": {"stringValue": "Done"},  # Add "Done" in the cell
                        "note": str(comment_text)  # Add comment as note
                    }]
                }],
                "fields": "userEnteredValue,note"
            }
        }]
        
        # Execute the batch update
        body = {"requests": requests}
        response = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()
        
        return True
        
    except Exception as e:
        st.error(f"Note API failed: {str(e)}")
        return False
    

def update_assessment_in_sheet(sheet_url, row_index, assessment_data):
    """Update existing row with assessment data and add comment as cell note"""
    try:
        conn = init_connection()
        sheet = conn.open_by_url(sheet_url)
        worksheet = sheet.sheet1
        headers = worksheet.row_values(1)
        
        comment_text = assessment_data.get("Comment", "")
        
        # Update all fields except Comment
        for col_name, value in assessment_data.items():
            if col_name != "Comment" and col_name in headers:
                col_index = headers.index(col_name) + 1
                if hasattr(value, 'item'):
                    value = value.item()
                elif pd.isna(value):
                    value = ""
                worksheet.update_cell(row_index + 2, col_index, value)
        
        # Add comment as note to Comment column
        if comment_text and "Comment" in headers:
            comment_col_index = headers.index("Comment")
            success = add_comment_to_cell(sheet_url, row_index + 1, comment_col_index, comment_text)
            if not success:
                st.warning("Assessment saved but comment note failed to add")
        
        st.cache_data.clear()
        return True
        
    except Exception as e:
        st.error(f"Error updating assessment: {e}")
        return False

def add_new_assessment_row(sheet_url, player_name, original_data, assessment_data):
    """Add new row for additional assessment of same player with comment as note"""
    try:
        conn = init_connection()
        sheet = conn.open_by_url(sheet_url)
        worksheet = sheet.sheet1
        headers = worksheet.row_values(1)
        
        comment_text = assessment_data.get("Comment", "")
        
        # Combine original player data with new assessment (without comment in cell data)
        combined_data = {**original_data}
        for key, value in assessment_data.items():
            if key != "Comment":
                if hasattr(value, 'item'):
                    combined_data[key] = value.item()
                elif pd.isna(value):
                    combined_data[key] = ""
                else:
                    combined_data[key] = str(value) if value is not None else ""
        
        # Create row data matching headers
        row_data = []
        for header in headers:
            if header == "Comment":
                row_data.append("")  # Empty cell for comment column
            else:
                value = combined_data.get(header, "")
                if hasattr(value, 'item'):
                    row_data.append(value.item())
                elif pd.isna(value):
                    row_data.append("")
                else:
                    row_data.append(str(value) if value is not None else "")
        
        worksheet.append_row(row_data)
        
        # Add comment as note if provided
        if comment_text and "Comment" in headers:
            new_row_index = len(worksheet.get_all_values())
            comment_col_index = headers.index("Comment")
            add_comment_to_cell(sheet_url, new_row_index - 1, comment_col_index, comment_text)
        
        st.cache_data.clear()
        return True
        
    except Exception as e:
        st.error(f"Error adding new assessment: {e}")
        return False

# Position-specific attributes

POSITION_ATTRIBUTES = {
        1: ["Shot Stopping", "Reflexes", "Command Area", "Short Distribution", "Long Distribution"],
        2: ['1v1 Defending', 'Defensive Awareness', 'Acceleration', 'Speed', 'Strength', 'Aerial Ability', 'Athleticism', 'Stamina',
            'Passing Vision', '1v1 Dribbling', 'Ball Carrying', 'Run Making', 'Crossing', 'Chance Creation'],
        3: ['1v1 Defending', 'Defensive Awareness', 'Acceleration', 'Speed', 'Strength', 'Aerial Ability', 'Athleticism', 'Stamina',
            'Passing Vision', '1v1 Dribbling', 'Ball Carrying', 'Run Making', 'Crossing', 'Chance Creation'],
        4: ['1v1 Defending', 'Defensive Awareness', 'Acceleration', 'Speed', 'Strength', 'Aerial Ability', 'Athleticism', 
            'Technical Level', 'Passing Vision', 'Ball Carrying'],
        6: ['1v1 Defending', 'Defensive Awareness', 'Acceleration', 'Speed', 'Strength', 'Aerial Ability', 'Athleticism', 'Covering Ground', 'Stamina',
            'Technical Level','Passing Vision', 'Ball Carrying', '1v1 Dribbling', 'Long Range Shooting'],
        8: ['1v1 Defending', 'Defensive Awareness', 'Acceleration', 'Speed', 'Strength', 'Aerial Ability', 'Athleticism', 'Covering Ground', 'Stamina',
            'Technical Level','Passing Vision','Ball Carrying', '1v1 Dribbling', 'Chance Creation', 'Run Making', 
            'Finishing', 'Long Range Shooting'],
        10: ['1v1 Defending', 'Defensive Awareness', 'Pressing Intensity', 'Acceleration', 'Speed', 'Strength', 'Aerial Ability', 'Stamina', 'Athleticism',
            'Technical Level', 'Passing Vision', '1v1 Dribbling', 'Crossing', 'Chance Creation', 'Run Making', 'Finishing', 'Long Range Shooting'],
        7: ['1v1 Defending', 'Defensive Awareness', 'Pressing Intensity', 'Acceleration', 'Speed', 'Strength', 'Aerial Ability', 'Stamina', 'Athleticism',
            'Technical Level', 'Passing Vision', '1v1 Dribbling', 'Crossing', 'Chance Creation', 'Run Making', 'Finishing', 'Long Range Shooting'],
        11: ['1v1 Defending', 'Defensive Awareness', 'Pressing Intensity', 'Acceleration', 'Speed', 'Strength', 'Aerial Ability', 'Stamina', 'Athleticism',
            'Technical Level', 'Passing Vision', '1v1 Dribbling', 'Crossing', 'Chance Creation', 'Run Making', 'Finishing', 'Long Range Shooting'],
        9:  ['1v1 Defending', 'Defensive Awareness', 'Pressing Intensity', 'Acceleration', 'Speed', 'Strength', 'Aerial Ability', 'Stamina', 'Athleticism',
            'Technical Level', 'Hold Up Play',  '1v1 Dribbling',  'Chance Creation', 'Passing Vision','Run Making', 'Finishing', 'Shot Location Quality', 'Long Range Shooting'],
    }



# All possible attributes (for column headers)
# All possible attributes (for column headers) - fix the generation
ALL_ATTRIBUTES = []
for attrs in POSITION_ATTRIBUTES.values():
    ALL_ATTRIBUTES.extend(attrs)
ALL_ATTRIBUTES = list(set(ALL_ATTRIBUTES))  # Remove duplicates


def get_all_column_headers():
    """Get all possible column headers for the sheet"""
    base_cols = [
        "Entry_ID", "Player", "Club", "League", "Age", "DOB", "Position", "Height", 
        "Category", "Date_Sent", "Priority", "Scout", "Date_Watched","Advance", "Comment", 
        "CR", "PR"
    ]
    # Convert attribute names to match what's used in the form
    attribute_cols = []
    for attrs in POSITION_ATTRIBUTES.values():
        attribute_cols.extend(attrs)
    attribute_cols = list(set(attribute_cols))  # Remove duplicates
    
    return base_cols + sorted(attribute_cols)


# Main app 
def main():
    st.title("FCM Scouting System")
    sheet_url = "https://docs.google.com/spreadsheets/d/17PXkZUNFAgFYnW2m0NshoN23GP681tYXNB1S1kM109Q/edit?gid=0#gid=0"
    st.session_state["sheet_url"] = sheet_url
    

    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")
        # sheet_url = st.text_input(
        #     "Google Sheet URL",
        #     value=st.session_state.get("sheet_url", ""),
        #     help="Paste your Google Sheet URL here"
        # )
        
        # if sheet_url:
        #     st.session_state["sheet_url"] = sheet_url
        
        # Scout login
        st.markdown("---")
        st.subheader("Scout Login")
        scout_name = st.text_input("Scout Name", value=st.session_state.get("scout_name", ""))
        if scout_name:
            st.session_state["scout_name"] = scout_name
            st.success(f"Logged in as: {scout_name}")
        
        st.markdown("---")
        #st.markdown("### Sheet Structure")
        
    
    if not sheet_url:
        st.warning("Please enter your Google Sheet URL in the sidebar to get started.")
        return
    
    # Load data
    scouting_df = load_scouting_data(sheet_url)
    
    # Main tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Database", "➕ Add Player", "👤 Player View", "🔍 Scout Panel", "🏆 Power Rankings"])
    
    with tab1:
        database_tab(sheet_url, scouting_df)
    
    with tab2:
        add_player_tab(sheet_url, scouting_df)

    with tab3:
        player_view_tab(scouting_df)
    
    with tab4:
        scout_panel_tab(sheet_url, scouting_df)
    
    with tab5:
        power_rankings_tab(scouting_df)

def database_tab(sheet_url, scouting_df):
    """Database tab with live updates and data entry"""
    
    
    

    st.subheader("Scouting Database")
    
    if not scouting_df.empty:
        # Add search and filter
        
        
        # Show only basic player info columns
        display_cols = ["Player", "Club", "League", "Age", "DOB","Position", "Scout", "Advance", "CR", "PR", "Available?"]
        available_cols = [col for col in display_cols if col in scouting_df.columns]
        
        ##Filters
        
        col1, col2, col3, col4, col5, col6 = st.columns(6)

        with col1: search_term = st.text_input("Search players...")
        with col2: filtered_position = st.pills("Positions", list(POSITION_ATTRIBUTES.keys()), selection_mode = 'multi', default = list(POSITION_ATTRIBUTES.keys()))
        with col3: 
            if len(scouting_df) == 1: filtered_age = st.slider("Age", min(scouting_df['Age']-1), max(scouting_df['Age']), (min(scouting_df['Age']), max(scouting_df['Age'])))
            else: filtered_age = st.slider("Age", min(scouting_df['Age']), max(scouting_df['Age']), (min(scouting_df['Age']), max(scouting_df['Age'])))
        with col4: 
            advance_options = ["Yes", "No"]
            unique_vals = [x for x in scouting_df["Advance"].dropna().unique() if x not in ["Yes", "No"]]
            advance_options.extend(unique_vals)
            filtered_advance = st.pills("Advanced?", advance_options, selection_mode='multi', default = advance_options)
            #filtered_advance = st.pills("Advanced?", ["Yes", "Maybe", "No", "Not Yet"], selection_mode = 'multi')
        with col5: 
            available_options = ["Yes", "No"]
            unique_vals = [x for x in scouting_df["Available?"].dropna().unique() if x not in ["Yes", "No"]]
            available_options.extend(unique_vals)
            filtered_available = st.pills("Available?", available_options, selection_mode='multi', default = available_options)
            #filtered_available = st.pills("Available?", ['Yes','No']+scouting_df["Available?"].unique(), selection_mode='multi')
        with col6: filtered_scout = st.pills("Filter Scout", scouting_df["Scout"].unique(), selection_mode = 'multi', default = scouting_df["Scout"].unique())
        
        filtered_df = scouting_df.copy(deep=True)

        if search_term:
            mask = scouting_df.astype(str).apply(lambda x: x.str.contains(search_term, case=False, na=False)).any(axis=1)
            filtered_df = scouting_df[mask][available_cols]
        
        filtered_df = filtered_df[(filtered_df['Position'].isin(filtered_position)) & (filtered_df['Age'] >= filtered_age[0]) &  (filtered_df['Age'] <= filtered_age[1]) & (filtered_df['Advance'].isin(filtered_advance)) & (filtered_df['Available?'].isin(filtered_available)) & (filtered_df['Scout'].isin(filtered_scout))]

        
        filtered_df = filtered_df[available_cols]
        
        #st.dataframe(filtered_df, use_container_width=True, hide_index=True)
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
        
        

        st.subheader("Overall")
        # Display stats
        col_a, col_b, col_c, col_d = st.columns(4)
        
        
        with col_a:
            #unique_players = scouting_df["Player"].nunique() if "Player" in scouting_df.columns else 0
            st.metric("Players Added", len(scouting_df))
        with col_b:
            #high_priority = len(scouting_df[scouting_df.get("Priority", "") == "High"])
            st.metric("Watched", len(scouting_df[scouting_df['Advance'].isin(['Yes', 'No', 'Maybe'])]))
        with col_c:
            st.metric("Approved", len(scouting_df[(scouting_df['Advance'] == 'Yes')]))
        with col_d:
            st.metric("Available", len(scouting_df[(scouting_df['Available?'] == 'Yes')]))
        #     total_assessments = len(scouting_df)
        #     st.metric("Total Assessments", total_assessments)

        # Display Positional Stats
        st.subheader("Centre Backs")
        scouting_df_subsection = scouting_df[scouting_df['Position'] == 4]
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a: st.metric("Players Added", len(scouting_df_subsection))
        with col_b: st.metric("Watched", len(scouting_df_subsection[scouting_df_subsection['Advance'].isin(['Yes', 'No', 'Maybe'])]))
        with col_c: st.metric("Approved", len(scouting_df_subsection[(scouting_df_subsection['Advance'] == 'Yes')]))
        with col_d: st.metric("Available", len(scouting_df_subsection[(scouting_df_subsection['Available?'] == 'Yes')]))

        st.subheader("Left Backs")
        scouting_df_subsection = scouting_df[scouting_df['Position'] == 2]
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a: st.metric("Players Added", len(scouting_df_subsection))
        with col_b: st.metric("Watched", len(scouting_df_subsection[scouting_df_subsection['Advance'].isin(['Yes', 'No', 'Maybe'])]))
        with col_c: st.metric("Approved", len(scouting_df_subsection[(scouting_df_subsection['Advance'] == 'Yes')]))
        with col_d: st.metric("Available", len(scouting_df_subsection[(scouting_df_subsection['Available?'] == 'Yes')]))

        st.subheader("Right Backs")
        scouting_df_subsection = scouting_df[scouting_df['Position'] == 3]
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a: st.metric("Players Added", len(scouting_df_subsection))
        with col_b: st.metric("Watched", len(scouting_df_subsection[scouting_df_subsection['Advance'].isin(['Yes', 'No', 'Maybe'])]))
        with col_c: st.metric("Approved", len(scouting_df_subsection[(scouting_df_subsection['Advance'] == 'Yes')]))
        with col_d: st.metric("Available", len(scouting_df_subsection[(scouting_df_subsection['Available?'] == 'Yes')]))

        st.subheader("Defensive Midfielders")
        scouting_df_subsection = scouting_df[scouting_df['Position'] == 6]
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a: st.metric("Players Added", len(scouting_df_subsection))
        with col_b: st.metric("Watched", len(scouting_df_subsection[scouting_df_subsection['Advance'].isin(['Yes', 'No', 'Maybe'])]))
        with col_c: st.metric("Approved", len(scouting_df_subsection[(scouting_df_subsection['Advance'] == 'Yes')]))
        with col_d: st.metric("Available", len(scouting_df_subsection[(scouting_df_subsection['Available?'] == 'Yes')]))

        st.subheader("Central Midfielders")
        scouting_df_subsection = scouting_df[scouting_df['Position'] == 8]
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a: st.metric("Players Added", len(scouting_df_subsection))
        with col_b: st.metric("Watched", len(scouting_df_subsection[scouting_df_subsection['Advance'].isin(['Yes', 'No', 'Maybe'])]))
        with col_c: st.metric("Approved", len(scouting_df_subsection[(scouting_df_subsection['Advance'] == 'Yes')]))
        with col_d: st.metric("Available", len(scouting_df_subsection[(scouting_df_subsection['Available?'] == 'Yes')]))

        st.subheader("Attacking Midfielders")
        scouting_df_subsection = scouting_df[scouting_df['Position'] == 10]
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a: st.metric("Players Added", len(scouting_df_subsection))
        with col_b: st.metric("Watched", len(scouting_df_subsection[scouting_df_subsection['Advance'].isin(['Yes', 'No', 'Maybe'])]))
        with col_c: st.metric("Approved", len(scouting_df_subsection[(scouting_df_subsection['Advance'] == 'Yes')]))
        with col_d: st.metric("Available", len(scouting_df_subsection[(scouting_df_subsection['Available?'] == 'Yes')]))

        st.subheader("Left Wingers")
        scouting_df_subsection = scouting_df[scouting_df['Position'] == 11]
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a: st.metric("Players Added", len(scouting_df_subsection))
        with col_b: st.metric("Watched", len(scouting_df_subsection[scouting_df_subsection['Advance'].isin(['Yes', 'No', 'Maybe'])]))
        with col_c: st.metric("Approved", len(scouting_df_subsection[(scouting_df_subsection['Advance'] == 'Yes')]))
        with col_d: st.metric("Available", len(scouting_df_subsection[(scouting_df_subsection['Available?'] == 'Yes')]))

        st.subheader("Right Wingers")
        scouting_df_subsection = scouting_df[scouting_df['Position'] == 7]
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a: st.metric("Players Added", len(scouting_df_subsection))
        with col_b: st.metric("Watched", len(scouting_df_subsection[scouting_df_subsection['Advance'].isin(['Yes', 'No', 'Maybe'])]))
        with col_c: st.metric("Approved", len(scouting_df_subsection[(scouting_df_subsection['Advance'] == 'Yes')]))
        with col_d: st.metric("Available", len(scouting_df_subsection[(scouting_df_subsection['Available?'] == 'Yes')]))

        st.subheader("Strikers")
        scouting_df_subsection = scouting_df[scouting_df['Position'] == 9]
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a: st.metric("Players Added", len(scouting_df_subsection))
        with col_b: st.metric("Watched", len(scouting_df_subsection[scouting_df_subsection['Advance'].isin(['Yes', 'No', 'Maybe'])]))
        with col_c: st.metric("Approved", len(scouting_df_subsection[(scouting_df_subsection['Advance'] == 'Yes')]))
        with col_d: st.metric("Available", len(scouting_df_subsection[(scouting_df_subsection['Available?'] == 'Yes')]))


        #     total_assessments = len(scouting_df)
        #     st.metric("Total Assessments", total_assessments)
    else:
        st.info("No scouting data found. Add some players below!")



def add_player_tab(sheet_url, scouting_df):
    st.subheader("Add TM Link")

    # st.write("=== SCRAPERAPI DEBUG ===")
    # scraperapi_available = setup_scraperapi()
    # st.write(f"DEBUG: ScraperAPI available: {scraperapi_available}")
    # st.write("=== END DEBUG ===")

    # scraperapi_available = setup_scraperapi()
    # if scraperapi_available:
    #     st.success("Enhanced scraping enabled")
    # else:
    #     st.warning("Using basic scraping (may fail on Streamlit Cloud)")
    
    with st.form("tm_player_form"):
        # Single player
        tm_link = st.text_input("Enter TM Link (use .com format on basic player page NOT .uk,.de,etc)")
        col1, col2, col3,col4= st.columns(4)
        with col1: 
            #scout_assigned = st.text_input("Select Scout*")
            scout_assigned = st.multiselect("Select Scout", ['Maxi', 'Adam', 'Pablo', 'Nithin', 'Enzo', 'Vasileios', 'Julián'])
        with col2: 
            priority_assigned = st.selectbox("Priority", ["High", "Medium", "Low"])
        with col3: 
            category_assigned = st.selectbox("Category", ["First Team", "Emerging"])
        with col4:
            source_assigned = st.selectbox("Source", ["Data", "Agent", "EyeBall", "Scouting"])

        tm_submitted = st.form_submit_button("Add Player from TM")
        
        if tm_submitted and tm_link and scout_assigned and priority_assigned and category_assigned:
            
            scraperapi_key = os.getenv('SCRAPERAPI_KEY')
            #if scraperapi_key:
                #api_url = f"https://api.scraperapi.com/?api_key={scraperapi_key[:8]}...&url={tm_link}"
                #st.write(f"**DEBUG: Using ScraperAPI URL:** {api_url}")
            #else:
                #st.write(f"**DEBUG: Using direct URL:** {tm_link}")

            try:
                #st.write("DEBUG: Calling get_player_data...")
                player = get_player_data(tm_link)
                #st.write(f"DEBUG: Scraper returned: {type(player)}")
                #st.write(f"DEBUG: Player data: {player}")
                
                if player:
                    for i in range(len(scout_assigned)):
                        st.success("DEBUG: Player data successfully retrieved")
                        player_data = {
                            "Player": player['Player Name'],
                            "Club": player['Club'],
                            "League": player['League Level'],
                            "Age": player['Age'],
                            "DOB": player['Date of Birth'],
                            "Position": player['Position'],
                            "Height": player['Height'],
                            "Source": source_assigned,
                            "Category": category_assigned,  # Remove the comma and tuple
                            "Date_Sent": datetime.now().strftime("%Y-%m-%d"),
                            "Priority": priority_assigned,
                            "Scout": scout_assigned[i],
                            "Agent": player['Player Agent'],
                            "Market Value": player['Market Value'],
                            "Contract Expires": player['Contract Expires'],
                        }
                        add_player_to_sheet(sheet_url, player_data)
                    st.rerun()
                else:
                    st.error("Could not extract player data from TM link")
                    #st.error(f"DEBUG: Exception in TM scraping: {type(e).__name__}: {e}")
                    #import traceback
                    #st.code(traceback.format_exc())
            except Exception as e:
                st.error(f"Error processing TM link: {e}")
                #st.error(f"DEBUG: Exception in TM scraping: {type(e).__name__}: {e}")
                #import traceback
                #st.code(traceback.format_exc())

        elif tm_submitted:
            st.error("Please fill out all required fields")

    st.write("")
    st.write("")
    st.subheader("Or Add Player Manually")
    with st.form("add_player_form"):
        player_name = st.text_input("Player Name*")
        club = st.text_input("Club*")
        league = st.text_input("League*")
        age = st.number_input("Age", min_value=16, max_value=40, value=20)
        #dob = st.date_input("Date of Birth", value=date(2004, 1, 1))
        dob = st.text_input("Date of Birth (MM/YY)", placeholder="")
        position = st.selectbox("Position*", list(POSITION_ATTRIBUTES.keys()))
        height = st.text_input("Height (cm)", placeholder="")
        source = st.selectbox("Source", ["Data", "Agent", "EyeBall", "Scouting"])
        category = st.selectbox("Category", ["First Team", "Emerging"])
        priority = st.selectbox("Priority", ["High", "Medium", "Low"])
        scout = st.multiselect("Select Scout", ['Maxi', 'Adam', 'Pablo', 'Nithin', 'Enzo', 'Vasileios', 'Julián'])
        agent = st.text_input("Agent")
        market_value = st.text_input("Market Value")
        contract_expires = st.text_input("Contract Expires")
        
        submitted = st.form_submit_button("Add Player")
        
        if submitted and player_name and club and league:
            for i in range(len(scout)):
                player_data = {
                    "Player": player_name,
                    "Club": club,
                    "League": league,
                    "Age": age,
                    "DOB": dob,
                    "Position": position,
                    "Height": height,
                    "Category": category,
                    "Source": source,
                    "Date_Sent": datetime.now().strftime("%Y-%m-%d"),
                    "Priority": priority,
                    "Scout": scout[i],
                    "Agent": agent,
                    "Market Value": market_value,
                    "Contract Expires": contract_expires
                }
                add_player_to_sheet(sheet_url, player_data)
            st.rerun()

def player_view_tab(scouting_df):
    """Individual player view with comments and radar chart"""
    
    if scouting_df.empty:
        st.info("No players available. Add some players in the Database tab.")
        return
    
    # Create player options with name (club) format - show all unique player-club combinations
    unique_combinations = scouting_df.groupby(['Player', 'Club']).size().reset_index(name='count')
    player_options = []
    player_mapping = {}
    
    for _, row in unique_combinations.iterrows():
        display_name = f"{row['Player']} ({row['Club']})"
        player_options.append(display_name)
        player_mapping[display_name] = (row['Player'], row['Club'])
    
    # Player selection
    selected_display = st.selectbox("Select a player:", player_options)
    
    if not selected_display:
        return
    
    selected_player, selected_club = player_mapping[selected_display]
    
    # Get all data for this player-club combination
    player_data = scouting_df[
        (scouting_df["Player"] == selected_player) & 
        (scouting_df["Club"] == selected_club)
    ]
    
    if player_data.empty:
        st.error("No data found for selected player.")
        return
    
    # Get basic player info (from first/most recent entry)
    latest_entry = player_data.iloc[-1]
    
    col1, col2 = st.columns([0.7, 1])
    
    with col1:
        st.subheader(f"{selected_player} Bio")
        
        # Display player details
        info_col1, info_col2 = st.columns(2)
        with info_col1:
            st.write(f"**Club:** {latest_entry.get('Club', 'N/A')}")
            st.write(f"**League:** {latest_entry.get('League', 'N/A')}")
            st.write(f"**Age:** {latest_entry.get('Age', 'N/A')} ({latest_entry.get('DOB', 'N/A')})")
            st.write(f"**Position:** {latest_entry.get('Position', 'N/A')}")
            st.write(f"**Height:** {latest_entry.get('Height', 'N/A')} cm")
            st.write(f"**Source:** {latest_entry.get('Source', 'N/A')}")
            #st.write(f"**Scout:** {latest_entry.get('Scout', 'N/A')}")
            st.write(f"**Agent:** {latest_entry.get('Agent', 'N/A')}")
            st.write(f"**Market Value:** €{latest_entry.get('Market Value', 'N/A')}m")
            st.write(f"**Contract Expires:** {latest_entry.get('Contract Expires', 'N/A')}")
        
        st.subheader("Assessment History")
        
        # Show ALL assessments for this player across ALL entries - EXPANDABLE
        all_player_assessments = scouting_df[scouting_df["Player"] == selected_player]
        assessed_entries = all_player_assessments[
            (all_player_assessments["Comment"].notna() & (all_player_assessments["Comment"] != "")) |
            (all_player_assessments["Date_Watched"].notna() & (all_player_assessments["Date_Watched"] != ""))
        ]
        
        if not assessed_entries.empty:
            for idx, assessment in assessed_entries.iterrows():
                date_watched = assessment.get('Date_Watched', 'N/A')
                advance_status = assessment.get('Advance', 'N/A')
                scout_name = assessment.get('Scout', 'N/A')
                club_name = assessment.get('Club', 'N/A')
                
                # Get the actual comment from the Google Sheets note
                comment_col_index = scouting_df.columns.get_loc("Comment") if "Comment" in scouting_df.columns else -1
                if comment_col_index >= 0:
                    original_row_index = idx + 1
                    actual_comment = get_cell_note(st.session_state["sheet_url"], original_row_index, comment_col_index)
                else:
                    actual_comment = "No comment available"
                
                # Display in expandable format with club info
                with st.expander(f"{scout_name} - {club_name} - {advance_status} - {date_watched}"):
                    st.write(f"**Club:** {club_name}")
                    st.write(f"**Advance?** {advance_status}")
                    st.write(f"**Current Rating:** {assessment.get('CR', 'N/A')}")
                    st.write(f"**Potential Rating:** {assessment.get('PR', 'N/A')}")
                    st.write(f"**Comment:** {actual_comment if actual_comment else 'No detailed comment'}")
                    
                    # Show position-specific attributes if available
                    position = assessment.get('Position', '')
                    if position in POSITION_ATTRIBUTES:
                        attr_values = []
                        for attr in POSITION_ATTRIBUTES[position]:
                            attr_value = assessment.get(attr, '')
                            if pd.notna(attr_value) and attr_value != '':
                                attr_display = attr.replace('_', ' ').title()
                                attr_values.append(f"{attr_display}: {attr_value}")
                        
                        if attr_values:
                            st.write(f"**Attributes:** {', '.join(attr_values)}")
        else:
            st.info("No assessments available for this player.")
    
    with col2:
        st.subheader("Performance Radar")
        
        # Get ALL assessments with ratings for this player (across all entries)
        all_player_data = scouting_df[scouting_df["Player"] == selected_player]
        rated_assessments = all_player_data.dropna(subset=["CR"])
        
        if not rated_assessments.empty and latest_entry.get('Position') in POSITION_ATTRIBUTES:
            # Create assessment options
            assessment_options = []
            for idx, assessment in rated_assessments.iterrows():
                scout = assessment.get('Scout', 'Unknown Scout')
                crr = assessment.get('CR', 'NA')
                prr = assessment.get('PR', 'NA')
                date = assessment.get('Date_Watched', 'Unknown Date')
                option_name = f"{scout} - {date} - CR: {crr} - PR: {prr} "
                assessment_options.append((assessment, option_name, idx))
            
            # Initialize session state for checkboxes if not exists
            if 'selected_radar_assessments' not in st.session_state:
                st.session_state.selected_radar_assessments = [0] if len(assessment_options) > 0 else []
            
            # Get selected assessments based on session state
            selected_assessments = []
            colors = ['#00ff00', '#ff0000']  # Green, Red
            
            for i, checkbox_idx in enumerate(st.session_state.selected_radar_assessments[:2]):  # Max 2
                if checkbox_idx < len(assessment_options):
                    selected_assessments.append(assessment_options[checkbox_idx])
            
            if selected_assessments:
                # Get position from first assessment
                position = selected_assessments[0][0]['Position']
                attributes = POSITION_ATTRIBUTES[position]
                
                # Create radar chart
                fig = go.Figure()
                
                for i, (assessment, name, idx) in enumerate(selected_assessments):
                    # Extract ratings for this assessment
                    ratings = []
                    display_attributes = []
                    
                    for attr in attributes:
                        if attr in assessment and pd.notna(assessment[attr]):
                            ratings.append(float(assessment[attr]))
                        else:
                            ratings.append(0.0)  # Default rating
                        display_attributes.append(attr.replace('_', ' ').title())
                    
                    if ratings and len(ratings) > 2:
                        # Close the polygon
                        closed_ratings = ratings + [ratings[0]]
                        closed_attributes = display_attributes + [display_attributes[0]]
                        
                        # Get color for this trace
                        color = colors[i % len(colors)]
                        
                        # Add trace for this assessment
                        fig.add_trace(go.Scatterpolar(
                            r=closed_ratings,
                            theta=closed_attributes,
                            fill='toself',
                            name=name,
                            line=dict(color=color, width=3),
                            fillcolor=f'rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.2)',
                            marker=dict(size=8, color=color),
                            showlegend=False
                        ))
                
                # Update layout
                fig.update_layout(
                    polar=dict(
                        bgcolor='rgba(0,0,0,0)',
                        radialaxis=dict(
                            visible=True,
                            range=[0, 4.0],
                            showticklabels=False,
                            gridcolor='white',
                            gridwidth=1,
                            tick0=0,
                            dtick=1
                        ),
                        angularaxis=dict(
                            tickfont=dict(size=14, color='white'),
                            gridcolor='white',
                            gridwidth=1,
                            linecolor='white',
                            linewidth=2,
                            direction='clockwise',
                            rotation=90
                        )
                    ),
                    showlegend=False,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='white', size=14),
                    height=600,
                    margin=dict(l=80, r=80, t=80, b=80)
                )
                
                # Add assessment info annotations in top corners
                if len(selected_assessments) >= 1:
                    first_assessment = selected_assessments[0][0]
                    scout1 = first_assessment.get('Scout', 'Unknown Scout')
                    date1 = first_assessment.get('Date_Watched', 'Unknown Date')
                    cr1 = first_assessment.get('CR', 'N/A')
                    pr1 = first_assessment.get('PR', 'N/A')
                    
                    fig.add_annotation(
                        x=0.02, y=1.18,
                        text=f"{scout1}",
                        showarrow=False,
                        font=dict(size=16, color='#00ff00', family='Arial Black'),
                        xref="paper", yref="paper",
                        xanchor='left'
                    )
                    fig.add_annotation(
                        x=0.02, y=1.13,
                        text=f"{date1} | CR: {cr1} | PR: {pr1}",
                        showarrow=False,
                        font=dict(size=12, color='#00ff00'),
                        xref="paper", yref="paper",
                        xanchor='left'
                    )
                
                if len(selected_assessments) >= 2:
                    second_assessment = selected_assessments[1][0]
                    scout2 = second_assessment.get('Scout', 'Unknown Scout')
                    date2 = second_assessment.get('Date_Watched', 'Unknown Date')
                    cr2 = second_assessment.get('CR', 'N/A')
                    pr2 = second_assessment.get('PR', 'N/A')
                    
                    fig.add_annotation(
                        x=0.98, y=1.18,
                        text=f"{scout2}",
                        showarrow=False,
                        font=dict(size=16, color='#ff0000', family='Arial Black'),
                        xref="paper", yref="paper",
                        xanchor='right'
                    )
                    fig.add_annotation(
                        x=0.98, y=1.13,
                        text=f"{date2} | CR: {cr2} | PR: {pr2}",
                        showarrow=False,
                        font=dict(size=12, color='#ff0000'),
                        xref="paper", yref="paper",
                        xanchor='right'
                    )
                
                #st.plotly_chart(fig, use_container_width=True)
                st.plotly_chart(fig, use_container_width=True)
            
            # Checkboxes below the radar
            st.write("**Select assessments to display (max 2):**")
            
            new_selections = []
            for i, (assessment, name, idx) in enumerate(assessment_options):
                is_checked = i in st.session_state.selected_radar_assessments
                
                if st.checkbox(name, value=is_checked, key=f"radar_checkbox_{i}"):
                    new_selections.append(i)
            
            # Update session state, limiting to 2 selections
            if len(new_selections) <= 2:
                st.session_state.selected_radar_assessments = new_selections
            elif len(new_selections) > 2:
                # Keep only the first 2 selections
                st.session_state.selected_radar_assessments = new_selections[:2]
                st.warning("Maximum 2 assessments can be selected for comparison.")
        
        else:
            st.info("No assessment data available for radar chart.")
        
def get_cell_note(sheet_url, row_index, col_index):
    """Get the note content from a specific cell"""
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        
        credentials = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        
        service = build('sheets', 'v4', credentials=credentials)
        
        # Get spreadsheet ID
        conn = init_connection()
        sheet = conn.open_by_url(sheet_url)
        spreadsheet_id = sheet.id
        
        # Get worksheet ID
        spreadsheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        worksheet_id = spreadsheet_metadata['sheets'][0]['properties']['sheetId']
        
        # Get cell data including notes
        result = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            ranges=[f"Sheet1!{chr(65 + col_index)}{row_index + 1}"],
            includeGridData=True
        ).execute()
        
        # Extract note if it exists
        sheets = result.get('sheets', [])
        if sheets and 'data' in sheets[0]:
            grid_data = sheets[0]['data'][0]
            if 'rowData' in grid_data and grid_data['rowData']:
                row_data = grid_data['rowData'][0]
                if 'values' in row_data and row_data['values']:
                    cell_data = row_data['values'][0]
                    return cell_data.get('note', '')
        
        return ''
        
    except Exception as e:
        return ''
    

def scout_panel_tab(sheet_url, scouting_df):
    """Scout-specific panel for managing assigned players"""
    
    scout_name = st.session_state.get("scout_name", "")
    
    if not scout_name:
        st.warning("Please enter your scout name in the sidebar to access the scout panel.")
        return
    
    if scouting_df.empty:
        st.info("No scouting data available.")
        return
    
    # Filter for this scout's players
    scout_players = scouting_df[scouting_df.get("Scout", "") == scout_name]
    
    if scout_players.empty:
        st.info(f"No players assigned to scout: {scout_name}")
        return
    
    st.subheader(f"Scout Panel - {scout_name}")
    
    # Toggle between watched/unwatched
    view_mode = st.radio(
        "View Mode:",
        ["Unwatched Players", "Watched Players", "All Assigned Players"],
        horizontal=True
    )
    
    if view_mode == "Unwatched Players":
        # Check both Comment and Date_Watched for unwatched players
        display_players = scout_players[
            (scout_players["Comment"].isna() | (scout_players["Comment"] == "")) &
            (scout_players["Date_Watched"].isna() | (scout_players["Date_Watched"] == ""))
        ]
    elif view_mode == "Watched Players":
        # Player is watched if they have either Comment or Date_Watched
        display_players = scout_players[
            (scout_players["Comment"].notna() & (scout_players["Comment"] != "")) |
            (scout_players["Date_Watched"].notna() & (scout_players["Date_Watched"] != ""))
        ]
    else:
        display_players = scout_players
    
    if display_players.empty:
        st.info(f"No {view_mode.lower()} found.")
        return
    
    # Display players
    st.write(f"**{len(display_players)} players**")
    
    # Group by unique player name for display
    unique_players_in_view = display_players["Player"].unique()
    
    for player_name in unique_players_in_view:
        player_entries = display_players[display_players["Player"] == player_name]
        has_assessments = not (
            player_entries.dropna(subset=["Comment"]).empty and 
            player_entries.dropna(subset=["Date_Watched"]).empty
        )
        latest_entry = player_entries.iloc[-1]
        
        with st.expander(f"{player_name} - {latest_entry['Club']} ({latest_entry['Position']})"):
            
            # Show player basic info
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Player:** {latest_entry['Player']}")
                st.write(f"**Club:** {latest_entry['Club']}")
                st.write(f"**League:** {latest_entry['League']}")
                st.write(f"**Age:** {latest_entry['Age']} ({latest_entry['DOB']})")
                st.write(f"**Position:** {latest_entry['Position']}")
                st.write(f"**Height:** {latest_entry['Height']}cm")
            # with col2:
            #     change_position = st.button('Change Position?')
            #     if change_position: 
                #st.write(f"**Position:** {latest_entry['Position']}")
                #st.write(f"**Priority:** {latest_entry['Priority']}")
                #st.write(f"**Assessments:** {len(player_entries)}")
            
            # # Show existing assessments if any
            # assessed_entries = player_entries[
            #     (player_entries["Comment"].notna() & (player_entries["Comment"] != "")) |
            #     (player_entries["Date_Watched"].notna() & (player_entries["Date_Watched"] != ""))
                
            # ]

            # if not assessed_entries.empty:
            #     st.write("**Previous Assessments:**")
            #     for _, entry in assessed_entries.iterrows():
            #         date_watched = entry.get('Date_Watched', 'N/A')
            #         comment = entry.get('Comment', 'Assessment recorded - check sheet for details')
            #         st.write(f"• [{date_watched}] {comment} (CR: {entry.get('CR', 'N/A')}, PR: {entry.get('PR', 'N/A')})")
            
            # Assessment form
            st.write("---")
            st.write("**Add/Update Assessment:**")

            assessment_key = f"assessment_{player_name}_{latest_entry.name}"

            # Get existing values for editing (if any)
            if has_assessments:
                # Get the latest assessment data
                current_entry_id = latest_entry.get("Entry_ID")
                latest_assessed = scouting_df[
                    (scouting_df["Player"] == player_name) & 
                    (scouting_df["Entry_ID"] == current_entry_id) & 
                    ((scouting_df["Comment"].notna() & (scouting_df["Comment"] != "")) |
                    (scouting_df["Date_Watched"].notna() & (scouting_df["Date_Watched"] != "")))
                ]
                
                if not latest_assessed.empty:
                    existing_data = latest_assessed.iloc[-1]
                    default_advance = existing_data.get("Advance", "")
                    default_cr = float(existing_data.get("CR", 0.0)) if pd.notna(existing_data.get("CR")) else 0.0
                    default_pr = float(existing_data.get("PR", 0.0)) if pd.notna(existing_data.get("PR")) else 0.0
                    
                    # Get the actual comment from the Google Sheets note
                    comment_col_index = scouting_df.columns.get_loc("Comment") if "Comment" in scouting_df.columns else -1
                    if comment_col_index >= 0:
                        # Find the row index in the original sheet (add 1 for header)
                        original_row_index = latest_assessed.index[-1] + 1
                        default_comment = get_cell_note(sheet_url, original_row_index, comment_col_index)
                    else:
                        default_comment = ""
                    
                    existing_data = latest_assessed.iloc[-1]  # Keep this for attributes
                else:
                    default_advance, default_cr, default_pr, default_comment = "", 0.0, 0.0, ""
                    existing_data = None
            else:
                default_advance, default_cr, default_pr, default_comment = "", 0.0, 0.0, ""
                existing_data = None

            current_position = latest_entry.get('Position', '')
            all_positions = list(POSITION_ATTRIBUTES.keys())

            selected_position = st.pills(
                "Position",
                all_positions,
                default=current_position if current_position in all_positions else all_positions[0],
                key=f"position_{assessment_key}"
            )

            # Get the selected position (pills returns a list)
            position_for_attributes = selected_position if selected_position else current_position


            with st.form(f"assessment_form_{player_name}_{latest_entry.name}"):
                col_a, col_b = st.columns(2)
                
                with col_a:
                    # advance_decision = st.selectbox(
                    #     "Advance?", 
                    #     ["", "Yes", "No", "Maybe"],
                    #     index=["", "Yes", "No", "Maybe"].index(default_advance) if default_advance in ["", "Yes", "No", "Maybe"] else 0,
                    #     key=f"advance_{assessment_key}"
                    # )
                    advance_decision = st.pills(
                        "Advance?", 
                        ["Yes", "No", "Maybe"],
                        default=default_advance if default_advance in ["Yes", "No", "Maybe"] else "Yes",
                        key=f"advance_{assessment_key}"
                    )
                    current_rating = st.slider(
                        "Current Rating", 
                        min_value=0.0, max_value=4.0, value=float(default_cr),step=0.5,
                        key=f"cr_{assessment_key}"
                    )
                    potential_rating = st.slider(
                        "Potential Rating", 
                        min_value=0.0, max_value=4.0, value=float(default_pr), step=0.5,
                        key=f"pr_{assessment_key}"
                    )
                    
                
                with col_b:
                    comment = st.text_area(
                        "Assessment Comment",
                        value=default_comment,
                        key=f"comment_{assessment_key}",
                        height=150,
                        placeholder="Enter your detailed assessment here..."
                    )
                
                # Position-specific attributes with existing values
                position = latest_entry.get('Position', '')
                attribute_ratings = {}
                
                if position_for_attributes in POSITION_ATTRIBUTES:
                    st.write(f"**#{position_for_attributes} Attributes **")
                    attributes = POSITION_ATTRIBUTES[position_for_attributes]
    
                    
                    for row_start in range(0, len(attributes), 5):
                        attr_cols = st.columns(5)
                        row_attributes = attributes[row_start:row_start + 5]
                        
                        for i, attr in enumerate(row_attributes):
                            with attr_cols[i]:
                                attr_display = attr.replace('_', ' ').title()
                                
                                # Get existing attribute value if available
                                if existing_data is not None and existing_data.get('Position') == position_for_attributes:
                                    existing_attr_value = existing_data.get(attr, 2.0)  # Default to 2.0 for 0-4 range
                                    default_attr = float(existing_attr_value) if pd.notna(existing_attr_value) else 2.0
                                else:
                                    default_attr = 2.0
                                
                                attribute_ratings[attr] = st.slider(
                                    attr_display,
                                    0.0, 4.0, default_attr,
                                    step=0.5,
                                    key=f"{attr}_{assessment_key}_{position_for_attributes}"
                                )
                # Single submit button
                submitted = st.form_submit_button("Submit Assessment", type="primary")
                
                # Handle form submission
                # Handle form submission
                if submitted:
                    if not comment.strip():
                        st.error("Please add a comment before submitting the assessment")
                    else:
                        # Convert all values to native Python types
                        assessment_data = {
                            "Advance": advance_decision,
                            "Comment": comment,
                            "Date_Watched": datetime.now().strftime("%Y-%m-%d"),
                            "Position": position_for_attributes, 
                            "CR": int(current_rating),
                            "PR": int(potential_rating)
                        }
                        
                        # Add attribute ratings as integers
                        for attr, rating in attribute_ratings.items():
                            assessment_data[attr] = float(rating)
                        
                        success = False
                        
                        # Find the specific row for this scout and player combination
                        scout_player_entries = scouting_df[
                            (scouting_df["Player"] == player_name) & 
                            (scouting_df["Scout"] == scout_name) &
                            (scouting_df["Entry_ID"] == latest_entry.get("Entry_ID"))  # Same entry
                        ]
                        
                        if not scout_player_entries.empty:
                            # Update the existing row for this scout-player combination
                            existing_row_index = scout_player_entries.index[-1]  # Get the most recent one
                            success = update_assessment_in_sheet(sheet_url, existing_row_index, assessment_data)
                        else:
                            # This scout hasn't assessed this player yet, create new row
                            original_data = {
                                "Entry_ID": latest_entry.get("Entry_ID", ""),
                                "Player": latest_entry["Player"],
                                "Club": latest_entry["Club"],
                                "League": latest_entry["League"],
                                "Age": latest_entry["Age"],
                                "DOB": latest_entry["DOB"],
                                "Position": latest_entry["Position"],
                                "Height": latest_entry["Height"],
                                "Category": latest_entry["Category"],
                                "Date_Sent": latest_entry.get("Date_Sent", datetime.now().strftime("%Y-%m-%d")),
                                "Priority": latest_entry["Priority"],
                                "Scout": scout_name
                            }
                            success = add_new_assessment_row(sheet_url, player_name, original_data, assessment_data)
                        
                        if success:
                            st.success("Assessment submitted successfully!")
                            time.sleep(1)
                            st.rerun()

def power_rankings_tab(scouting_df):
    """Power rankings by position and profile"""
    
    if scouting_df.empty:
        st.info("No scouting data available for power rankings.")
        return
    
    # Filter out entries without ratings
    rated_data = scouting_df.dropna(subset=["CR"])
    
    if rated_data.empty:
        st.info("No assessed players available for rankings.")
        return
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.subheader("Filters")
        
        # Position filter
        positions = list(POSITION_ATTRIBUTES.keys())
        selected_position = st.selectbox("Select Position:", positions)
        
        # Profile filter (based on age/category)
        profile_options = ["All", "Youth (Under 21)", "Senior (21+)", "Development"]
        selected_profile = st.selectbox("Select Profile:", profile_options)
        
        # Rating type
        rating_type = st.selectbox("Rank by:", ["Current Rating (CR)", "Potential Rating (PR)"])
        
        min_assessments = st.number_input("Minimum Assessments:", min_value=1, value=1)
    
    with col2:
        st.subheader(f"Top {selected_position}s - {selected_profile}")
        
        # Filter by position
        position_data = rated_data[rated_data["Position"] == selected_position]
        
        if position_data.empty:
            st.warning(f"No assessed players found for position: {selected_position}")
            return
        
        # Apply profile filter
        if selected_profile == "Youth (Under 21)":
            position_data = position_data[position_data["Age"] < 21]
        elif selected_profile == "Senior (21+)":
            position_data = position_data[position_data["Age"] >= 21]
        elif selected_profile == "Development":
            position_data = position_data[position_data["Category"] == "Development"]
        
        if position_data.empty:
            st.warning("No players found matching the selected criteria.")
            return
        
        # Calculate player statistics
        rating_col = "CR" if "Current" in rating_type else "PR"
        
        # Group by player and calculate stats
        player_stats = []
        
        for player in position_data["Player"].unique():
            player_data = position_data[position_data["Player"] == player]
            
            if len(player_data) >= min_assessments:
                latest_entry = player_data.iloc[-1]
                avg_rating = player_data[rating_col].mean()
                
                if not pd.isna(avg_rating):
                    player_stats.append({
                        "Player": player,
                        "Club": latest_entry["Club"],
                        "Age": latest_entry["Age"],
                        "Rating": round(avg_rating, 1),
                        "Assessments": len(player_data),
                        "Scout": latest_entry["Scout"],
                        "Latest Comment": latest_entry.get("Comment", "No comment")[:50] + ("..." if len(str(latest_entry.get("Comment", ""))) > 50 else "")
                    })
        
        if not player_stats:
            st.warning("No players meet the minimum assessment criteria.")
            return
        
        # Create rankings dataframe
        rankings_df = pd.DataFrame(player_stats)
        rankings_df = rankings_df.sort_values("Rating", ascending=False).reset_index(drop=True)
        rankings_df.insert(0, "Rank", range(1, len(rankings_df) + 1))
        
        # Display rankings
        #st.dataframe(rankings_df, use_container_width=True)
        st.dataframe(rankings_df, stretch='width')
        
        # Show top 3 with more details
        if len(rankings_df) >= 3:
            st.subheader("Top 3 Spotlight")
            
            col_a, col_b, col_c = st.columns(3)
            
            for i, col in enumerate([col_a, col_b, col_c]):
                if i < len(rankings_df):
                    player_data = rankings_df.iloc[i]
                    with col:
                        st.metric(
                            label=f"#{i+1} {player_data['Player']}", 
                            value=f"{player_data['Rating']}/10",
                            delta=f"{player_data['Club']} • Age {player_data['Age']}"
                        )
                        st.caption(f"Scout: {player_data['Scout']}")

if __name__ == "__main__":
    main()