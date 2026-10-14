import streamlit as st
import requests
import sqlite3
import hashlib
from datetime import datetime

# =========================================================
# CONFIGURATION
# =========================================================
BACKEND_URL = "http://localhost:8000"
HISTORY_DB = "incident_history.db"

st.set_page_config(page_title="ResQ-AI Command Center", page_icon="🚨", layout="wide", initial_sidebar_state="expanded")

# =========================================================
# INCIDENT HISTORY DATABASE (keeps existing rows; does not touch Qdrant)
# =========================================================
def init_history_db():
    with sqlite3.connect(HISTORY_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS incident_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL,
                incident TEXT NOT NULL,
                response TEXT NOT NULL,
                event_key TEXT UNIQUE,
                priority TEXT NOT NULL DEFAULT 'MEDIUM'
            )
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(incident_history)").fetchall()}
        if "priority" not in columns:
            conn.execute("ALTER TABLE incident_history ADD COLUMN priority TEXT NOT NULL DEFAULT 'MEDIUM'")


def classify_priority(incident, response=""):
    text = f"{incident or ''} {response or ''}".lower()
    critical_terms = ("critical", "life-threatening", "life threatening", "trapped", "people inside", "building fire", "major fire", "icu", "unconscious", "severe bleeding", "explosion", "multiple casualties")
    high_terms = ("high priority", "urgent", "rapidly spreading", "severe flooding", "blocked road", "injured", "medical emergency", "power failure")
    low_terms = ("minor", "no injuries", "contained", "low priority", "resolved")
    if any(term in text for term in critical_terms):
        return "CRITICAL"
    if any(term in text for term in high_terms):
        return "HIGH"
    if any(term in text for term in low_terms):
        return "LOW"
    return "MEDIUM"


def save_incident_history(source, incident, response, event_key=None):
    if not incident or not incident.strip() or not response or not response.strip():
        return
    priority = classify_priority(incident, response)
    if event_key is None:
        event_key = hashlib.sha256(f"{source}|{incident}|{response}|{datetime.now().isoformat()}".encode("utf-8")).hexdigest()
    with sqlite3.connect(HISTORY_DB) as conn:
        conn.execute("""
            INSERT OR IGNORE INTO incident_history
                (created_at, source, incident, response, event_key, priority)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), source, incident.strip(), response.strip(), event_key, priority))


def get_incident_history():
    with sqlite3.connect(HISTORY_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, created_at, source, incident, response, priority FROM incident_history ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


init_history_db()

# =========================================================
# SESSION STATE
# =========================================================
def init_state(key, default):
    if key not in st.session_state:
        st.session_state[key] = default

init_state("analysis", "")
init_state("allocations", [])
init_state("voice_status", "waiting")
init_state("voice_transcript", "")
init_state("voice_response", "")
init_state("last_voice_transcript", "")
init_state("voice_error", "")
init_state("current_page", "Overview")

INITIAL_RESOURCES = {"Ambulance": 2, "Rescue Boat": 1, "Fire Truck": 1, "Generator": 1, "Medical Team": 2, "Rescue Team": 2}


def get_available_resources():
    used = {}
    for item in st.session_state.allocations:
        resource = item["resource"]
        used[resource] = used.get(resource, 0) + 1
    return {resource: max(0, qty - used.get(resource, 0)) for resource, qty in INITIAL_RESOURCES.items()}


def allocate_resource(resource, incident):
    incident = incident.strip()
    if not incident:
        return False, "Enter an incident or location."
    if get_available_resources()[resource] <= 0:
        return False, f"No {resource} units remain available."
    st.session_state.allocations.append({"resource": resource, "incident": incident})
    return True, f"{resource} assigned to {incident}."


def fetch_omi_result():
    try:
        response = requests.get(f"{BACKEND_URL}/latest-result", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.session_state.voice_error = "Cannot connect to backend. Make sure Uvicorn is running on port 8000."
    except requests.exceptions.Timeout:
        st.session_state.voice_error = "Backend request timed out."
    except Exception as error:
        st.session_state.voice_error = f"Could not get Omi result: {error}"
    return None


def process_omi_result(data):
    if not data:
        return
    status = data.get("status", "waiting")
    transcript = data.get("transcript", "")
    ai_response = data.get("response", "")
    if transcript:
        st.session_state.voice_transcript = transcript
    if status == "completed" and ai_response:
        st.session_state.voice_status = "completed"
        st.session_state.voice_response = ai_response
        st.session_state.analysis = ai_response
        if transcript:
            event_key = hashlib.sha256(f"Omi|{transcript.strip()}|{ai_response.strip()}".encode("utf-8")).hexdigest()
            save_incident_history("Omi Voice", transcript, ai_response, event_key=event_key)
            st.session_state.last_voice_transcript = transcript
    elif status in ("processing", "pending", "waiting"):
        st.session_state.voice_status = "processing" if status != "waiting" else "waiting"
    elif status == "error":
        st.session_state.voice_status = "error"
        st.session_state.voice_error = data.get("error", "Omi processing failed.")

# =========================================================
# STYLING
# =========================================================
st.markdown("""
<style>
.stApp { background: #f4f7fb; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px; }
[data-testid="stSidebar"] { background: #102c46; }
[data-testid="stSidebar"] * { color: #edf5fb; }
.resq-brand { background: linear-gradient(135deg,#102c46,#17496b); border-radius: 18px; padding: 24px 28px; margin-bottom: 18px; color: white; }
.resq-brand h1 { margin: 0; font-size: 32px; color: white; }
.resq-brand p { margin: 5px 0 0; color: #c6d9e8; }
.section-title { color: #17324d; font-size: 22px; font-weight: 750; margin: 18px 0 12px; }
.metric-card { background: white; border: 1px solid #e1e8ef; border-radius: 14px; padding: 18px; min-height: 100px; }
.metric-label { color: #718398; font-size: 11px; font-weight: 700; letter-spacing: .6px; }
.metric-value { color: #17324d; font-size: 28px; font-weight: 800; margin-top: 6px; }
.panel { background: white; border: 1px solid #e1e8ef; border-radius: 14px; padding: 18px 20px; }
.stButton > button { border-radius: 9px; min-height: 42px; font-weight: 650; }
.footer { text-align: center; color: #8191a2; font-size: 11px; margin-top: 36px; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# SIDEBAR NAVIGATION
# =========================================================
with st.sidebar:
    st.markdown("<div style='text-align:center;padding:10px 0 18px'><div style='font-size:34px'>🚨</div><div style='font-size:25px;font-weight:800'>ResQ-AI</div><div style='font-size:10px;letter-spacing:1px;color:#b8cddd'>COMMAND CENTER</div></div>", unsafe_allow_html=True)
    st.divider()
    pages = ["Overview", "Incidents", "Voice Assistant", "Resource Allocation", "Hyderabad Map"]
    icons = {"Overview":"🏠", "Incidents":"🚨", "Voice Assistant":"🎤", "Resource Allocation":"🚑", "Hyderabad Map":"🗺️"}
    selected = st.radio("NAVIGATION", pages, index=pages.index(st.session_state.current_page) if st.session_state.current_page in pages else 0, format_func=lambda p: f"{icons[p]}  {p}", label_visibility="visible")
    st.session_state.current_page = selected
    st.divider()
    st.caption("EMERGENCY COMMAND CENTER")

page = st.session_state.current_page
history = get_incident_history()
available = get_available_resources()
total_resources = sum(INITIAL_RESOURCES.values())
available_count = sum(available.values())
allocated_count = total_resources - available_count

st.markdown(f"<div class='resq-brand'><h1>{icons.get(page, '🚨')} {page}</h1><p>ResQ-AI · Intelligent Emergency Response Coordination System</p></div>", unsafe_allow_html=True)

# =========================================================
# OVERVIEW PAGE
# =========================================================
if page == "Overview":
    st.markdown("<div class='section-title'>System Overview</div>", unsafe_allow_html=True)
    critical_count = sum(1 for x in history if x.get("priority") == "CRITICAL")
    metric_cols = st.columns(4)
    metrics = [("SYSTEM STATUS", "ONLINE"), ("SAVED INCIDENTS", str(len(history))), ("CRITICAL REPORTS", str(critical_count)), ("AVAILABLE UNITS", str(available_count))]
    for col, (label, value) in zip(metric_cols, metrics):
        with col:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>{label}</div><div class='metric-value'>{value}</div></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Incident Priority Summary</div>", unsafe_allow_html=True)
    priority_styles = [("CRITICAL", "#b3261e", "#fce8e6"), ("HIGH", "#995c00", "#fff0d9"), ("MEDIUM", "#245a9a", "#e8f1fb"), ("LOW", "#176b3a", "#e2f3e8")]
    cols = st.columns(4)
    for col, (label, color, bg) in zip(cols, priority_styles):
        count = sum(1 for x in history if x.get("priority", "MEDIUM") == label)
        with col:
            st.markdown(f"<div style='background:{bg};border:1px solid {color}33;border-radius:12px;padding:16px'><div style='font-size:11px;font-weight:800;color:{color}'>{label}</div><div style='font-size:28px;font-weight:800;color:{color}'>{count}</div><div style='font-size:11px;color:#596b7a'>Saved incidents</div></div>", unsafe_allow_html=True)
    st.caption("Priority labels are text-based estimates, not validated emergency triage.")
    st.markdown("<div class='section-title'>Recent Incidents</div>", unsafe_allow_html=True)
    if history:
        for item in history[:5]:
            with st.expander(f"{item.get('priority','MEDIUM')} · {item['created_at']} · {item['incident'][:85]}"):
                st.write("Source:", item["source"])
                st.write(item["incident"])
                st.markdown("**AI response**")
                st.markdown(item["response"])
    else:
        st.info("No saved incidents yet. Open Incidents to submit a test report.")
    st.markdown("<div class='section-title'>Resource Availability</div>", unsafe_allow_html=True)
    cols = st.columns(3)
    for i, (name, qty) in enumerate(INITIAL_RESOURCES.items()):
        with cols[i % 3]:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>{name.upper()}</div><div class='metric-value'>{available[name]} <span style='font-size:14px;color:#8191a2'>/ {qty}</span></div></div>", unsafe_allow_html=True)

# =========================================================
# INCIDENT ANALYSIS PAGE
# =========================================================
elif page == "Incidents":
    st.markdown("<div class='section-title'>Submit an emergency report</div>", unsafe_allow_html=True)
    default_report = """Hyderabad emergency scenario\nArea A: Heavy rainfall has caused flooding. 30 people are trapped; two elderly people need assistance and one road is blocked.\nArea B: A residential building has caught fire. 15 people are inside, including three children.\nArea C: A hospital has lost electrical power and the ICU needs backup power.\nAvailable resources: 2 ambulances, 1 rescue boat, 1 fire truck, 1 generator, 2 medical teams, 2 rescue teams.\nAnalyze the incidents, prioritize them, identify resource requirements, and propose a response plan."""
    with st.form("incident_form"):
        report = st.text_area("Emergency report", value=default_report, height=250)
        submitted = st.form_submit_button("🚨 Analyze Emergency", type="primary", use_container_width=True)
    if submitted:
        if not report.strip():
            st.warning("Please enter an emergency report.")
        else:
            with st.spinner("ResQ-AI is analyzing the situation..."):
                try:
                    response = requests.post(f"{BACKEND_URL}/analyze", json={"report": report}, timeout=120)
                    response.raise_for_status()
                    data = response.json()
                    answer = data.get("response", "No AI response received.")
                    st.session_state.analysis = answer
                    if answer != "No AI response received.":
                        save_incident_history("Manual", report, answer)
                        st.success("Analysis complete and incident saved to history.")
                    st.rerun()
                except requests.exceptions.ConnectionError:
                    st.error("Cannot connect to backend. Ensure Uvicorn is running on port 8000.")
                except requests.exceptions.Timeout:
                    st.error("The AI request timed out. Please try again.")
                except Exception as error:
                    st.error(f"Analysis failed: {error}")
    if st.session_state.analysis:
        st.markdown("<div class='section-title'>AI Response Plan</div>", unsafe_allow_html=True)
        st.markdown(st.session_state.analysis)

# =========================================================
# HYDERABAD MAP PAGE
# =========================================================
elif page == "Hyderabad Map":
    st.markdown("Map locations are approximate and illustrative. Live emergency feeds, GPS, and vehicle positions are not connected.")
    try:
        import pandas as pd
        map_locations = pd.DataFrame([
            {"Incident":"Charminar area — Building fire","Priority":"CRITICAL","lat":17.3616,"lon":78.4747,"Suggested resource":"Fire Truck + Rescue Team"},
            {"Incident":"Hussain Sagar — Flooding","Priority":"HIGH","lat":17.4239,"lon":78.4738,"Suggested resource":"Rescue Boat + Rescue Team"},
            {"Incident":"Osmania General Hospital — Backup power","Priority":"HIGH","lat":17.3810,"lon":78.4804,"Suggested resource":"Generator + Medical Team"},
            {"Incident":"Secunderabad — Medical assistance","Priority":"MEDIUM","lat":17.4399,"lon":78.4983,"Suggested resource":"Ambulance + Medical Team"},
            {"Incident":"HITEC City — Minor water leak","Priority":"LOW","lat":17.4435,"lon":78.3772,"Suggested resource":"Inspection team"},
        ])
        st.map(map_locations, latitude="lat", longitude="lon", size=150, use_container_width=True)
        st.dataframe(map_locations[["Incident", "Priority", "Suggested resource"]], use_container_width=True, hide_index=True)
        selected_location = st.selectbox("Inspect a location", map_locations["Incident"].tolist())
        details = map_locations[map_locations["Incident"] == selected_location].iloc[0]
        st.info(f"Priority: {details['Priority']} · Suggested resource: {details['Suggested resource']}")
    except Exception as error:
        st.warning(f"The map could not be displayed: {error}")

# =========================================================
# RESOURCE ALLOCATION PAGE
# =========================================================
elif page == "Resource Allocation":
    st.markdown("<div class='section-title'>Available Resources</div>", unsafe_allow_html=True)
    cols = st.columns(3)
    for i, (resource, total) in enumerate(INITIAL_RESOURCES.items()):
        with cols[i % 3]:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>{resource.upper()}</div><div class='metric-value'>{available[resource]} <span style='font-size:14px;color:#8191a2'>/ {total} available</span></div></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Assign a resource</div>", unsafe_allow_html=True)
    with st.form("allocation_form"):
        resource_choice = st.selectbox("Resource", list(INITIAL_RESOURCES.keys()))
        incident_name = st.text_input("Incident / location", placeholder="Example: Area B - Building Fire")
        assign = st.form_submit_button("Assign resource", type="primary", use_container_width=True)
    if assign:
        success, message = allocate_resource(resource_choice, incident_name)
        if success:
            st.success(message)
            st.rerun()
        else:
            st.error(message)
    st.markdown("<div class='section-title'>Current Assignments</div>", unsafe_allow_html=True)
    if st.session_state.allocations:
        for index, item in enumerate(st.session_state.allocations):
            col1, col2, col3 = st.columns([2, 5, 1])
            col1.write(f"🚑 **{item['resource']}**")
            col2.write(item["incident"])
            if col3.button("Release", key=f"release_{index}"):
                st.session_state.allocations.pop(index)
                st.rerun()
    else:
        st.info("No resources are currently assigned.")
    st.caption("Assignments are kept in the current session and reset when that session is cleared.")

# =========================================================
# OMI VOICE PAGE
# =========================================================
elif page == "Voice Assistant":
    st.markdown("<div class='section-title'>Omi Voice Integration</div>", unsafe_allow_html=True)
    st.write("Speak through your configured Omi device. This page checks the existing backend for the latest voice result.")
    @st.fragment(run_every="2s")
    def omi_voice_monitor():
        data = fetch_omi_result()
        if data:
            process_omi_result(data)
        status = st.session_state.voice_status
        if status == "completed":
            st.success("Voice emergency processed successfully.")
        elif status == "processing":
            st.info("Omi voice input is being processed…")
        elif status == "error":
            st.error(st.session_state.voice_error or "Omi processing failed.")
        else:
            st.info("Waiting for Omi voice input…")
        if st.button("🔄 Check Omi result now"):
            result = fetch_omi_result()
            if result:
                process_omi_result(result)
            st.rerun()
    omi_voice_monitor()
    if st.session_state.voice_transcript:
        st.markdown("**Voice transcript**")
        st.markdown(f"> {st.session_state.voice_transcript}")
    if st.session_state.voice_response:
        st.markdown("**AI response from voice input**")
        st.markdown(st.session_state.voice_response)

st.markdown("<div class='footer'>ResQ-AI provides AI-assisted emergency decision support. Final operational decisions must be made by qualified personnel.</div>", unsafe_allow_html=True)
