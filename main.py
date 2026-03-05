import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from supabase import create_client, Client
from streamlit_js_eval import get_geolocation
import time

# --- 1. CLOUD CONNECTION ---
# These pull from the "Secrets" you added to Streamlit Cloud
URL = st.secrets["URL"]
KEY = st.secrets["KEY"]
supabase: Client = create_client(URL, KEY)

st.set_page_config(page_title="Suly Bus Digital Twin", layout="wide")

# --- 2. LOAD ROUTE DATA ---
@st.cache_data
def load_route():
    # Ensure 'l v l.csv' is in your GitHub folder
    return pd.read_csv('l v l.csv')

df_route = load_route()

# --- 3. INTERFACE NAVIGATION ---
st.sidebar.title("Suly Transit System")
role = st.sidebar.radio("Select Portal:", ["🚶 Pedestrian View", "👨‍✈️ Driver Broadcast"])

# --- 4. DRIVER PORTAL (Data Ingestion) ---
if start:
            st.info(f"Tracking Active for {plate}. Keep screen ON.")
            
            # Create a fixed area on the screen so it doesn't jump around
            dashboard = st.empty() 
            
            while True:
                loc = get_geolocation()
                
                if loc:
                    lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
                    
                    # Log to both tables
                    supabase.table("live_bus_data").upsert({"plate_number": plate, "lat": lat, "lon": lon, "driver_name": name}, on_conflict="plate_number").execute()
                    supabase.table("bus_location_history").insert({"plate_number": plate, "lat": lat, "lon": lon}).execute()
                    
                    # Update ONLY the dashboard area
                    with dashboard.container():
                        st.success("📡 Signal Strong - Broadcasting...")
                        st.metric("Current Latitude", f"{lat:.5f}")
                        st.metric("Current Longitude", f"{lon:.5f}")
                        st.write(f"Last update: {time.strftime('%H:%M:%S')}")
                else:
                    with dashboard.container():
                        st.warning("⏳ Waiting for GPS signal... Check if Location is enabled on your phone.")

                time.sleep(10) # 10 seconds is the "sweet spot" for Suly traffic data
                st.rerun()

# --- 5. PEDESTRIAN PORTAL (Real-Time Map) ---
else:
    st.header("Real-Time Bus Tracker")
    
    # Fetch live buses from Supabase
    response = supabase.table("live_bus_data").select("*").execute()
    live_buses = response.data

    # Center map on Sulaymaniyah
    m = folium.Map(location=[35.5852, 45.4390], zoom_start=14)
    
    # Draw the static 319-point Raparin Baridaka route line
    folium.PolyLine(df_route[['Y', 'X']].values, color="blue", weight=5, opacity=0.7).add_to(m)

    # Plot markers for all active buses
    if live_buses:
        for bus in live_buses:
            folium.Marker(
                [bus['lat'], bus['lon']],
                popup=f"Bus: {bus['plate_number']} (Driver: {bus['driver_name']})",
                icon=folium.Icon(color='red', icon='bus', prefix='fa')
            ).add_to(m)
            st.success(f"✅ Bus {bus['plate_number']} is currently on route.")
    else:
        st.warning("No buses are currently broadcasting.")

    st_folium(m, width=1200, height=600)

# Auto-refresh Pedestrian view every 20 seconds
if role == "🚶 Pedestrian View":
    time.sleep(20)
    st.rerun()

