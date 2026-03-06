import streamlit as st
import pandas as pd
import math
import time
import base64
from datetime import datetime, timezone
from supabase import create_client, Client
from streamlit_js_eval import get_geolocation
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim


# ----------------------------
# PAGE CONFIG
# ----------------------------
st.set_page_config(page_title="Suly Transit System", layout="wide")


# ----------------------------
# BACKGROUND IMAGE
# ----------------------------
def set_background(image_file: str) -> None:
    with open(image_file, "rb") as img:
        encoded = base64.b64encode(img.read()).decode()

    page_bg = f"""
    <style>
    .stApp {{
        background-image: linear-gradient(
            rgba(10, 15, 30, 0.40),
            rgba(10, 15, 30, 0.55)
        ), url("data:image/jpg;base64,{encoded}");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}

    [data-testid="stHeader"] {{
        background: rgba(0, 0, 0, 0);
    }}

    [data-testid="stSidebar"] {{
        background: rgba(15, 20, 40, 0.65);
    }}

    .block-container {{
        background-color: rgba(0, 0, 0, 0.10);
        padding: 2rem;
        border-radius: 18px;
    }}

    .glass-card {{
        background: rgba(10, 20, 35, 0.50);
        border: 1px solid rgba(255,255,255,0.08);
        backdrop-filter: blur(8px);
        padding: 1rem 1.2rem;
        border-radius: 16px;
        margin-bottom: 1rem;
    }}
    </style>
    """
    st.markdown(page_bg, unsafe_allow_html=True)


set_background("assets/suli_bg.jpg")


# ----------------------------
# SUPABASE CONNECTION
# ----------------------------
URL = st.secrets["URL"]
KEY = st.secrets["KEY"]
supabase: Client = create_client(URL, KEY)


# ----------------------------
# GEOCODER
# ----------------------------
@st.cache_resource
def get_geocoder():
    return Nominatim(user_agent="suly_transit_system")


geocoder = get_geocoder()


# ----------------------------
# STATIC ROUTES
# Replace with real route data later
# ----------------------------
LINES = {
    "L1": {
        "name": "Line 1",
        "color": "blue",
        "stops": [
            {"stop_name": "Bakhtiary", "lat": 35.5610, "lon": 45.4300},
            {"stop_name": "Salim Street", "lat": 35.5640, "lon": 45.4350},
            {"stop_name": "Sarchnar", "lat": 35.5680, "lon": 45.4400},
            {"stop_name": "City Center", "lat": 35.5615, "lon": 45.4440},
        ],
        "path": [
            [35.5610, 45.4300],
            [35.5621, 45.4325],
            [35.5640, 45.4350],
            [35.5661, 45.4374],
            [35.5680, 45.4400],
            [35.5650, 45.4420],
            [35.5615, 45.4440],
        ],
    },
    "L2": {
        "name": "Line 2",
        "color": "green",
        "stops": [
            {"stop_name": "Tasluja", "lat": 35.5330, "lon": 45.3940},
            {"stop_name": "Azadi Park", "lat": 35.5480, "lon": 45.4200},
            {"stop_name": "Saray", "lat": 35.5570, "lon": 45.4330},
            {"stop_name": "City Center", "lat": 35.5615, "lon": 45.4440},
        ],
        "path": [
            [35.5330, 45.3940],
            [35.5390, 45.4040],
            [35.5480, 45.4200],
            [35.5530, 45.4270],
            [35.5570, 45.4330],
            [35.5615, 45.4440],
        ],
    },
}


# ----------------------------
# HELPERS
# ----------------------------
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def flatten_stops() -> pd.DataFrame:
    rows = []
    for line_id, line_data in LINES.items():
        for idx, stop in enumerate(line_data["stops"]):
            rows.append(
                {
                    "line_id": line_id,
                    "line_name": line_data["name"],
                    "stop_name": stop["stop_name"],
                    "lat": stop["lat"],
                    "lon": stop["lon"],
                    "stop_order": idx,
                }
            )
    return pd.DataFrame(rows)


def geocode_address(address: str):
    if not address.strip():
        return None
    try:
        q = f"{address}, Sulaymaniyah, Iraq"
        result = geocoder.geocode(q, timeout=10)
        if result:
            return {
                "label": result.address,
                "lat": result.latitude,
                "lon": result.longitude,
            }
    except Exception:
        return None
    return None


def nearest_stop(lat: float, lon: float):
    stops_df = flatten_stops().copy()
    stops_df["distance_km"] = stops_df.apply(
        lambda row: haversine_km(lat, lon, row["lat"], row["lon"]),
        axis=1,
    )
    return stops_df.sort_values("distance_km").iloc[0].to_dict()


def find_direct_line_by_stops(origin_stop_name: str, destination_stop_name: str):
    for line_id, line_data in LINES.items():
        stop_names = [s["stop_name"] for s in line_data["stops"]]
        if origin_stop_name in stop_names and destination_stop_name in stop_names:
            if stop_names.index(origin_stop_name) < stop_names.index(destination_stop_name):
                return line_id
    return None


def get_stop_coords(line_id: str, stop_name: str):
    for stop in LINES[line_id]["stops"]:
        if stop["stop_name"] == stop_name:
            return stop["lat"], stop["lon"]
    return None, None


def estimate_eta_minutes(bus_lat, bus_lon, stop_lat, stop_lon, speed_kmh=18):
    distance_km = haversine_km(bus_lat, bus_lon, stop_lat, stop_lon)
    speed_kmh = max(speed_kmh, 12)
    return (distance_km / speed_kmh) * 60


def estimate_route_ride_minutes(line_id, origin_stop, destination_stop, avg_speed_kmh=20):
    stops = LINES[line_id]["stops"]
    origin_index = next(i for i, s in enumerate(stops) if s["stop_name"] == origin_stop)
    destination_index = next(i for i, s in enumerate(stops) if s["stop_name"] == destination_stop)

    total_km = 0.0
    for i in range(origin_index, destination_index):
        s1 = stops[i]
        s2 = stops[i + 1]
        total_km += haversine_km(s1["lat"], s1["lon"], s2["lat"], s2["lon"])

    return (total_km / avg_speed_kmh) * 60


def get_live_buses() -> pd.DataFrame:
    result = supabase.table("live_bus_data").select("*").execute()
    if result.data:
        return pd.DataFrame(result.data)
    return pd.DataFrame(columns=["plate_number", "driver_name", "line_id", "lat", "lon", "last_ping"])


def save_driver_ping(driver_name, plate_number, line_id, lat, lon):
    now_iso = datetime.now(timezone.utc).isoformat()

    live_data = {
        "plate_number": plate_number,
        "driver_name": driver_name,
        "line_id": line_id,
        "lat": lat,
        "lon": lon,
        "last_ping": now_iso,
    }

    history_data = {
        "plate_number": plate_number,
        "line_id": line_id,
        "lat": lat,
        "lon": lon,
        "recorded_at": now_iso,
    }

    supabase.table("live_bus_data").upsert(live_data, on_conflict="plate_number").execute()
    supabase.table("bus_location_history").insert(history_data).execute()


def build_passenger_map(
    selected_line_id=None,
    live_buses_df=None,
    origin_point=None,
    destination_point=None,
):
    m = folium.Map(
        location=[35.56, 45.43],
        zoom_start=12,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    # Draw all line paths
    for line_id, line_data in LINES.items():
        color = line_data.get("color", "blue")
        weight = 6 if line_id == selected_line_id else 4
        opacity = 0.95 if line_id == selected_line_id else 0.55

        folium.PolyLine(
            locations=line_data["path"],
            color=color,
            weight=weight,
            opacity=opacity,
            tooltip=f"{line_id} - {line_data['name']}",
        ).add_to(m)

        # Draw stops
        for stop in line_data["stops"]:
            folium.CircleMarker(
                location=[stop["lat"], stop["lon"]],
                radius=5,
                color="white",
                weight=1,
                fill=True,
                fill_opacity=0.9,
                popup=f"{stop['stop_name']} ({line_id})",
            ).add_to(m)

    # Draw live buses
    if live_buses_df is not None and not live_buses_df.empty:
        for _, row in live_buses_df.iterrows():
            folium.Marker(
                location=[row["lat"], row["lon"]],
                popup=f"Bus: {row['plate_number']}",
                tooltip=f"Bus {row['plate_number']}",
                icon=folium.Icon(color="orange", icon="bus", prefix="fa"),
            ).add_to(m)

    # Draw origin
    if origin_point is not None:
        folium.Marker(
            location=[origin_point["lat"], origin_point["lon"]],
            popup=f"Origin: {origin_point.get('label', 'Selected point')}",
            tooltip="Origin",
            icon=folium.Icon(color="green", icon="play"),
        ).add_to(m)

    # Draw destination
    if destination_point is not None:
        folium.Marker(
            location=[destination_point["lat"], destination_point["lon"]],
            popup=f"Destination: {destination_point.get('label', 'Selected point')}",
            tooltip="Destination",
            icon=folium.Icon(color="red", icon="flag"),
        ).add_to(m)

    return m


# ----------------------------
# SESSION STATE
# ----------------------------
defaults = {
    "portal": None,
    "is_tracking": False,
    "driver_name": "",
    "plate_number": "",
    "line_id": "",
    "origin_point": None,
    "destination_point": None,
    "pick_mode": None,   # "origin" or "destination"
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ----------------------------
# HOME PAGE
# ----------------------------
st.title("Suly Transit System")

if st.session_state.portal is None:
    st.subheader("Choose your portal")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 👨‍✈️ Driver")
        st.write("Start shift and broadcast live bus location.")
        if st.button("Open Driver Portal", use_container_width=True):
            st.session_state.portal = "driver"
            st.rerun()

    with col2:
        st.markdown("### 🚶 Passenger")
        st.write("Find the best line, see buses, and estimate arrival.")
        if st.button("Open Passenger Portal", use_container_width=True):
            st.session_state.portal = "passenger"
            st.rerun()

else:
    back_col, _ = st.columns([1, 6])
    with back_col:
        if st.button("⬅ Back"):
            st.session_state.portal = None
            st.rerun()

    # ----------------------------
    # DRIVER PORTAL
    # ----------------------------
    if st.session_state.portal == "driver":
        st.header("Driver Tracking Portal")

        if not st.session_state.is_tracking:
            with st.form("driver_form"):
                driver_name = st.text_input("Driver Name")
                plate_number = st.text_input("Bus Plate Number")
                line_id = st.selectbox(
                    "Choose Bus Line",
                    list(LINES.keys()),
                    format_func=lambda x: f"{x} - {LINES[x]['name']}"
                )

                submitted = st.form_submit_button("Start Tracking")
                if submitted:
                    if not driver_name or not plate_number:
                        st.warning("Please fill in driver name and bus plate number.")
                    else:
                        st.session_state.driver_name = driver_name
                        st.session_state.plate_number = plate_number
                        st.session_state.line_id = line_id
                        st.session_state.is_tracking = True
                        st.rerun()

        else:
            st.success(
                f"Tracking active | Driver: {st.session_state.driver_name} | "
                f"Bus: {st.session_state.plate_number} | Line: {st.session_state.line_id}"
            )

            if st.button("Stop Tracking"):
                st.session_state.is_tracking = False
                st.rerun()

            loc = get_geolocation()
            if loc and "coords" in loc:
                lat = loc["coords"]["latitude"]
                lon = loc["coords"]["longitude"]

                save_driver_ping(
                    st.session_state.driver_name,
                    st.session_state.plate_number,
                    st.session_state.line_id,
                    lat,
                    lon
                )

                st.info(f"📡 Last Ping: {time.strftime('%H:%M:%S')}")
                st.write(f"Latitude: {lat}")
                st.write(f"Longitude: {lon}")

                driver_map_df = pd.DataFrame([{"lat": lat, "lon": lon}])
                st.map(driver_map_df)

            else:
                st.warning("Waiting for location permission or GPS data...")

            time.sleep(15)
            st.rerun()

    # ----------------------------
    # PASSENGER PORTAL
    # ----------------------------
    elif st.session_state.portal == "passenger":
        st.header("Passenger Portal")

        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.subheader("Trip Planner")

        input_mode = st.radio(
            "Choose input mode",
            ["Type address", "Choose from map"],
            horizontal=True,
        )

        col1, col2, col3 = st.columns([2, 2, 1])

        with col1:
            if input_mode == "Type address":
                origin_text = st.text_input(
                    "Origin",
                    placeholder="Example: Azadi Park",
                    key="origin_text_input",
                )
                if st.button("Set origin from address"):
                    point = geocode_address(origin_text)
                    if point:
                        st.session_state.origin_point = point
                        st.success("Origin set from typed address.")
                    else:
                        st.error("Could not find that origin address.")
            else:
                st.write("Pick origin by clicking on the map.")
                if st.button("Pick Origin From Map"):
                    st.session_state.pick_mode = "origin"

        with col2:
            if input_mode == "Type address":
                destination_text = st.text_input(
                    "Destination",
                    placeholder="Example: City Center",
                    key="destination_text_input",
                )
                if st.button("Set destination from address"):
                    point = geocode_address(destination_text)
                    if point:
                        st.session_state.destination_point = point
                        st.success("Destination set from typed address.")
                    else:
                        st.error("Could not find that destination address.")
            else:
                st.write("Pick destination by clicking on the map.")
                if st.button("Pick Destination From Map"):
                    st.session_state.pick_mode = "destination"

        with col3:
            st.write(" ")
            st.write(" ")
            if st.button("Use My Location"):
                loc = get_geolocation()
                if loc and "coords" in loc:
                    st.session_state.origin_point = {
                        "label": "My current location",
                        "lat": loc["coords"]["latitude"],
                        "lon": loc["coords"]["longitude"],
                    }
                    st.success("Current location set as origin.")
                else:
                    st.warning("Could not get your current location.")

        st.markdown("</div>", unsafe_allow_html=True)

        # Live buses for map
        live_df = get_live_buses()

        # Build and render map
        selected_line_id = None
        passenger_map = build_passenger_map(
            selected_line_id=selected_line_id,
            live_buses_df=live_df if not live_df.empty else None,
            origin_point=st.session_state.origin_point,
            destination_point=st.session_state.destination_point,
        )

        map_data = st_folium(passenger_map, width=None, height=600)

        # Handle map click
        clicked = map_data.get("last_clicked") if map_data else None
        if clicked and st.session_state.pick_mode in ("origin", "destination"):
            clicked_point = {
                "label": f"Map selected point ({clicked['lat']:.5f}, {clicked['lng']:.5f})",
                "lat": clicked["lat"],
                "lon": clicked["lng"],
            }

            if st.session_state.pick_mode == "origin":
                st.session_state.origin_point = clicked_point
                st.success("Origin selected from map.")
            elif st.session_state.pick_mode == "destination":
                st.session_state.destination_point = clicked_point
                st.success("Destination selected from map.")

            st.session_state.pick_mode = None
            st.rerun()

        # Routing result
        if st.session_state.origin_point and st.session_state.destination_point:
            origin_stop = nearest_stop(
                st.session_state.origin_point["lat"],
                st.session_state.origin_point["lon"],
            )
            destination_stop = nearest_stop(
                st.session_state.destination_point["lat"],
                st.session_state.destination_point["lon"],
            )

            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.subheader("Trip Result")

            st.write(
                f"Nearest boarding stop: **{origin_stop['stop_name']}** "
                f"({origin_stop['distance_km']:.2f} km away)"
            )
            st.write(
                f"Nearest destination stop: **{destination_stop['stop_name']}** "
                f"({destination_stop['distance_km']:.2f} km away)"
            )

            if origin_stop["stop_name"] == destination_stop["stop_name"]:
                st.warning("Origin and destination snapped to the same stop.")
            else:
                line_id = find_direct_line_by_stops(
                    origin_stop["stop_name"],
                    destination_stop["stop_name"],
                )

                if not line_id:
                    st.warning("No direct line found yet. Later we can add transfer logic.")
                else:
                    st.success(f"Recommended line: {line_id} - {LINES[line_id]['name']}")

                    board_lat, board_lon = get_stop_coords(line_id, origin_stop["stop_name"])
                    ride_minutes = estimate_route_ride_minutes(
                        line_id,
                        origin_stop["stop_name"],
                        destination_stop["stop_name"],
                    )

                    line_buses = (
                        live_df[live_df["line_id"] == line_id].copy()
                        if not live_df.empty
                        else pd.DataFrame()
                    )

                    if not line_buses.empty:
                        line_buses["eta_minutes"] = line_buses.apply(
                            lambda row: estimate_eta_minutes(
                                row["lat"], row["lon"], board_lat, board_lon, speed_kmh=18
                            ),
                            axis=1,
                        )

                        best_bus = line_buses.sort_values("eta_minutes").iloc[0]
                        st.info(
                            f"Next bus: {best_bus['plate_number']} | "
                            f"ETA to boarding stop: {best_bus['eta_minutes']:.1f} min"
                        )
                    else:
                        st.info("No live buses currently broadcasting on this line.")

                    st.write(f"Estimated in-bus ride time: {ride_minutes:.1f} min")

            st.markdown("</div>", unsafe_allow_html=True)
