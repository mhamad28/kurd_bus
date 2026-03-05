import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from supabase import create_client, Client
from streamlit_js_eval import get_geolocation
import time

# --- 1. CLOUD CONNECTION ---
URL = st.secrets["URL"]
KEY = st.secrets["KEY"]
supabase: Client = create_client(URL, KEY)

st.set_page_config(page_title="Suly Bus Digital Twin", layout="wide")

# --- 2. LOAD ROUTE DATA ---
@st.cache_data
def load_route():
    return pd.read_csv('l v l.csv')
df_route = load_route()

# --- 3. INTERFACE NAVIGATION ---
st.sidebar.title("Suly Transit System")
role = st.sidebar.radio("Select Portal:", ["🚶 Pedestrian View", "👨‍✈️ Driver Broadcast"])

# --- 4. DRIVER PORTAL ---
if role == "👨‍✈️ Driver Broadcast":
    st.header("Driver Tracking Mode")

    if 'tracking_active' not in st.session_state:
        st.session_state.tracking_active = False

    if not st.session_state.tracking_active:
        with st.form("driver_info"):
            st.session_state.driver_name = st.text_input("Driver Name")
            st.session_state.plate = st.text_input("Bus Plate Number")
            submit = st.form_submit_button("Start Shift")
            if submit:
                st.session_state.tracking_active = True
                st.rerun()
    else:
        st.success(f"🚀 Tracking Active for {st.session_state.plate}")
        if st.button("Stop Shift"):
            st.session_state.tracking_active = False
            st.rerun()
        
        status = st.empty()
        while st.session_state.tracking_active:
            loc = get_geolocation()
            if loc:
                lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
                
                # A. Update Map
                supabase.table("live_bus_data").upsert({
                    "plate_number": st.session_state.plate, 
                    "driver_name": st.session_state.driver_name, 
                    "lat": lat, "lon": lon
                }, on_conflict="plate_number").execute()
                
                # B. Save History
                supabase.table("bus_location_history").insert({
                    "plate_number": st.session_state.plate, 
                    "lat": lat, "lon": lon
                }).execute()
                
                with status.container():
                    st.info(f"📡 Last Ping: {time.strftime('%H:%M:%S')}")
                    st.write(f"Logged: {lat}, {lon}")
            
            time.sleep(15)
            st.rerun()

# --- 5. PEDESTRIAN VIEW ---
else:
    st.header("Real-Time Bus Tracker")
    res = supabase.table("live_bus_data").select("*").execute()
    m = folium.Map(location=[35.5852, 45.4390], zoom_start=14)
    folium.PolyLine(df_route[['Y', 'X']].values, color="blue", weight=5).add_to(m)
    if res.data:
        for bus in res.data:
            folium.Marker([bus['lat'], bus['lon']], popup=bus['plate_number']).add_to(m)
    st_folium(m, width=1200, height=600)
    time.sleep(20)
    st.rerun()
