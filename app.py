import streamlit as st
import datetime as dt
from collections import defaultdict
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

import toml
import base64

# Serve the icon directly if accessed with ?icon=1
params = st.query_params
if "icon" in params:
    with open("apple-touch-icon.png", "rb") as f:
        img_bytes = f.read()
    b64 = base64.b64encode(img_bytes).decode()
    st.markdown(
        f"<img src='data:image/png;base64,{b64}' width='512'>",
        unsafe_allow_html=True
    )
    st.stop()
# -------------------
# CONFIGURATION
# -------------------
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
TICKET_TYPES = {
    "standard_return": {"name": "Standard Return", "price": 49.50, "validity_days": 1, "max_trips": 1},
    "weekly": {"name": "Weekly Ticket", "price": 145.40, "validity_days": 7, "max_trips": float('inf')},
    "monthly": {"name": "Monthly Ticket", "price": 558.40, "validity_days": 30, "max_trips": float('inf')},
    "flex": {"name": "Flex Ticket (8 Trips)", "price": 346.50, "validity_days": 28, "max_trips": 8}
}

# -------------------
# CALENDAR LOGIC
# -------------------
@st.cache_data
def get_london_travel_days(_service, calendar_id='primary', search_text="James in London"):
    now = dt.datetime.now(dt.timezone.utc)
    time_min = now.isoformat()
    time_max = (now + dt.timedelta(days=60)).isoformat()

    events_result = _service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    travel_days = []

    for event in events:
        if event.get('summary', '').lower() == search_text.lower() and 'date' in event['start']:
            travel_days.append(event['start']['date'])

    return sorted(set(travel_days))

def recommend_next_ticket_limited(travel_dates, ticket_types):
    if not travel_dates:
        return None, {}

    travel_dates = sorted([dt.datetime.strptime(d, "%Y-%m-%d").date() for d in travel_dates])
    first_trip = travel_dates[0]

    results = {}
    for ticket in ticket_types.values():
        validity_end = first_trip + dt.timedelta(days=ticket["validity_days"])
        covered_trips = [d for d in travel_dates if first_trip <= d < validity_end]
        if ticket["max_trips"] != float('inf'):
            covered_trips = covered_trips[:int(ticket["max_trips"])]

        trips = len(covered_trips)
        cost_per_trip = ticket["price"] / trips if trips > 0 else float('inf')

        results[ticket["name"]] = {
            "start_date": str(first_trip),
            "valid_until": str(validity_end - dt.timedelta(days=1)),
            "trips_covered": trips,
            "cost_per_trip": round(cost_per_trip, 2),
            "total_cost": ticket["price"]
        }

    best_ticket = min(results.items(), key=lambda x: x[1]["cost_per_trip"])
    return best_ticket, results

# -------------------
# STREAMLIT UI
# -------------------
st.set_page_config(page_title="Train Ticket Optimiser", page_icon="favicon.png", layout="centered")
st.markdown("<h1 style='text-align: center;'>🚆 Train Ticket Optimiser</h1>", unsafe_allow_html=True)
st.markdown("##### Smart, simple savings on travel — based on your Google Calendar 📅")
st.divider()

# -------------------
# AUTH FLOW (Automatic)
# -------------------
params = st.query_params

if "credentials" not in st.session_state:
    st.subheader("🔐 Google Login Required")

    # Load redirect_uri manually from secrets.toml
    with open("secrets.toml", "r") as f:
        secrets = toml.load(f)
    redirect_uri = secrets["redirect_uri"]

    if "auth_url" not in st.session_state:
        flow = Flow.from_client_secrets_file(
            'client_secret_web.json',
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        st.session_state["auth_url"] = auth_url
        st.session_state["flow_state"] = state

    # If Google redirected back with ?code= and ?state=
    if "code" in params and "state" in params:
        try:
            flow = Flow.from_client_secrets_file(
                'client_secret_web.json',
                scopes=SCOPES,
                redirect_uri=redirect_uri,
                state=st.session_state["flow_state"]
            )
            flow.fetch_token(code=params["code"])
            creds = flow.credentials
            st.session_state["credentials"] = creds
            st.success("✅ Logged in successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Authentication failed: {e}")
    else:
        st.markdown(f"[Click here to sign in with Google]({st.session_state['auth_url']})")

else:
    creds = st.session_state["credentials"]
    service = build('calendar', 'v3', credentials=creds)
    travel_days = get_london_travel_days(service)

    if travel_days:
        best, options = recommend_next_ticket_limited(travel_days, TICKET_TYPES)

        st.subheader("📍 Upcoming London Trips")
        st.success(f"Found **{len(travel_days)}** upcoming 'James in London' days.")

        def format_pretty_date(date_str):
            date_obj = dt.datetime.strptime(date_str, "%Y-%m-%d")
            day = date_obj.day
            suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            return date_obj.strftime("%a ") + f"{day}{suffix} " + date_obj.strftime("%B")

        def group_dates_by_week(date_list):
            grouped = defaultdict(list)
            for date_str in date_list:
                date_obj = dt.datetime.strptime(date_str, "%Y-%m-%d")
                year_week = date_obj.isocalendar()[:2]
                grouped[year_week].append(date_str)
            return grouped

        grouped_weeks = group_dates_by_week(travel_days)
        for (year, week_num), dates in sorted(grouped_weeks.items()):
            pretty = [format_pretty_date(d) for d in sorted(dates)]
            with st.container():
                st.markdown(f"**Week {week_num} ({year})**")
                st.write(" | ".join(pretty))

        st.divider()
        st.subheader("💡 Recommended Ticket")
        with st.container(border=True):
            st.markdown(f"""
            <h3 style="color: #0066ff;">{best[0]}</h3>
            <ul>
                <li><strong>Valid:</strong> {best[1]['start_date']} to {best[1]['valid_until']}</li>
                <li><strong>Trips covered:</strong> {best[1]['trips_covered']}</li>
                <li><strong>Total cost:</strong> £{best[1]['total_cost']}</li>
                <li><strong>Cost per trip:</strong> £{best[1]['cost_per_trip']}</li>
            </ul>
            """, unsafe_allow_html=True)

        st.divider()
        st.subheader("🔍 Other Ticket Options")
        for name, info in options.items():
            col1, col2, col3 = st.columns(3)
            col1.markdown(f"**{name}**")
            col2.markdown(f"£{info['total_cost']} / {info['trips_covered']} trips")
            col3.markdown(f"£{info['cost_per_trip']} per trip")
    else:
        st.info("No upcoming 'James in London' trips found.")




