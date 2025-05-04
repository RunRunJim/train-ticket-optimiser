import streamlit as st
import datetime as dt
import pickle
import os
from collections import defaultdict
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# -------------------
# CONFIGURATION
# -------------------
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
TICKET_TYPES = {
    "standard_return": {
        "name": "Standard Return",
        "price": 49.50,
        "validity_days": 1,
        "max_trips": 1
    },
    "weekly": {
        "name": "Weekly Ticket",
        "price": 145.40,
        "validity_days": 7,
        "max_trips": float('inf')
    },
    "monthly": {
        "name": "Monthly Ticket",
        "price": 558.40,
        "validity_days": 30,
        "max_trips": float('inf')
    },
    "flex": {
        "name": "Flex Ticket (8 Trips)",
        "price": 346.50,
        "validity_days": 28,
        "max_trips": 8
    }
}

# -------------------
# GOOGLE AUTH & CALENDAR
# -------------------
def get_calendar_service():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(
            port=8080,
            open_browser=False,
            authorization_prompt_message="Please visit this URL to authorize:\n{url}",
            success_message="Authentication complete. You can close this window.",
            redirect_uri_trusted=True,
        )
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('calendar', 'v3', credentials=creds)


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

# -------------------
# RECOMMENDATION LOGIC
# -------------------
def recommend_next_ticket_limited(travel_dates, ticket_types):
    if not travel_dates:
        return None, {}

    # Convert date strings to datetime.date objects
    travel_dates = sorted([dt.datetime.strptime(d, "%Y-%m-%d").date() for d in travel_dates])
    first_trip = travel_dates[0]

    results = {}

    for ticket_key, ticket in ticket_types.items():
        validity_end = first_trip + dt.timedelta(days=ticket["validity_days"])

        # Only include trips that fall within the ticket's validity window
        covered_trips = [d for d in travel_dates if first_trip <= d < validity_end]

        # Respect max trips if defined
        if ticket["max_trips"] != float('inf'):
            covered_trips = covered_trips[:int(ticket["max_trips"])]

        num_trips = len(covered_trips)
        cost_per_trip = ticket["price"] / num_trips if num_trips > 0 else float('inf')

        results[ticket["name"]] = {
            "start_date": str(first_trip),
            "valid_until": str(validity_end - dt.timedelta(days=1)),
            "trips_covered": num_trips,
            "cost_per_trip": round(cost_per_trip, 2),
            "total_cost": ticket["price"]
        }

    best_ticket = min(results.items(), key=lambda x: x[1]["cost_per_trip"])

    return best_ticket, results


# -------------------
# STREAMLIT UI
# -------------------
st.set_page_config(page_title="Train Ticket Optimiser", layout="centered")

st.markdown("<h1 style='text-align: center;'>🚆 Train Ticket Optimiser</h1>", unsafe_allow_html=True)
st.markdown("##### Smart, simple savings on travel — based on your Google Calendar 📅")

st.divider()

# ✅ Make sure the logic runs before using travel_days, best, or options
try:
    service = get_calendar_service()
    travel_days = get_london_travel_days(service)

    if travel_days:
        best, options = recommend_next_ticket_limited(travel_days, TICKET_TYPES)

        st.subheader("📍 Upcoming London Trips")
        st.success(f"Found **{len(travel_days)}** upcoming 'James in London' days.")


        def format_pretty_date(date_str):
            date_obj = dt.datetime.strptime(date_str, "%Y-%m-%d")
            day = date_obj.day
            suffix_str = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            return date_obj.strftime("%a ") + f"{day}{suffix_str} " + date_obj.strftime("%B")


        def group_dates_by_week(date_list):
            grouped = defaultdict(list)
            for date_str in date_list:
                date_obj = dt.datetime.strptime(date_str, "%Y-%m-%d")
                year_week = date_obj.isocalendar()[:2]  # (year, week_number)
                grouped[year_week].append(date_str)
            return grouped


        # Format & group travel days
        grouped_weeks = group_dates_by_week(travel_days)

        # Display each week in a row
        for (year, week_num), dates in sorted(grouped_weeks.items()):
            pretty_dates = [format_pretty_date(d) for d in sorted(dates)]
            with st.container():
                st.markdown(f"**Week {week_num} ({year})**")
                st.write(" | ".join(pretty_dates))

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
            with col1:
                st.markdown(f"**{name}**")
            with col2:
                st.markdown(f"£{info['total_cost']} / {info['trips_covered']} trips")
            with col3:
                st.markdown(f"£{info['cost_per_trip']} per trip")
    else:
        st.info("No upcoming 'James in London' trips found.")

except Exception as e:
    st.error(f"An error occurred: {e}")


