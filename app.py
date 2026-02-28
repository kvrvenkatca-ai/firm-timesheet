import streamlit as st
from supabase import create_client
from datetime import date, timedelta
import pandas as pd
import io

# ---------------- SUPABASE CONNECTION ----------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- UTILITIES ----------------
def get_week_start(d):
    return d - timedelta(days=d.weekday())

def is_friday(d):
    return d.weekday() == 4

# ---------------- SESSION ----------------
if "session" not in st.session_state:
    st.session_state.session = None

if "user_role" not in st.session_state:
    st.session_state.user_role = None

if "user_name" not in st.session_state:
    st.session_state.user_name = None

if "user_email" not in st.session_state:
    st.session_state.user_email = None

# ---------------- LOGIN FUNCTION ----------------
def login_user(email, password):
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return response
    except Exception:
        return None

# ---------------- UI ----------------
st.title("📘 Firm Timesheet System (Cloud)")

# ---------------- LOGIN PAGE ----------------
if not st.session_state.session:

    st.subheader("Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        result = login_user(email, password)

        if result and result.user:
            st.session_state.session = result.session
            st.session_state.user_email = result.user.email
            st.session_state.user_id = result.user.id

            profile = supabase.table("profiles") \
                .select("*") \
                .eq("id", result.user.id) \
                .single() \
                .execute()

            if profile.data:
                st.session_state.user_role = profile.data["role"]
                st.session_state.user_name = profile.data["name"]
                st.rerun()
            else:
                st.error("Profile not found. Contact admin.")
        else:
            st.error("Invalid credentials")

# ---------------- MAIN APP ----------------
else:

    st.sidebar.title("Navigation")
    role = st.session_state.user_role

    if role == "employee":
        page = st.sidebar.radio("Go To", ["Dashboard", "Daily Entry", "Weekly Summary"])
    else:
        page = st.sidebar.radio("Go To", ["Dashboard", "Manage Clients", "Approvals", "Reports"])

    if st.sidebar.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.session = None
        st.session_state.user_role = None
        st.session_state.user_name = None
        st.session_state.user_email = None
        st.rerun()

    st.success(f"Welcome {st.session_state.user_name}")

    # ---------------- EMPLOYEE ----------------
    if role == "employee":

        if page == "Dashboard":
            today = date.today()
            week_start = get_week_start(today)
            week_end = week_start + timedelta(days=6)

            res = supabase.table("timesheets") \
                .select("hours") \
                .eq("user_email", st.session_state.user_email) \
                .gte("work_date", str(week_start)) \
                .lte("work_date", str(week_end)) \
                .execute()

            total = sum(r["hours"] for r in res.data)
            utilization = (total / 45) * 100

            col1, col2 = st.columns(2)
            col1.metric("This Week Hours", total)
            col2.metric("Utilization %", f"{utilization:.2f}%")

        elif page == "Daily Entry":

            work_date = st.date_input("Work Date", date.today(), max_value=date.today())
            week_start = get_week_start(work_date)

            clients = supabase.table("clients").select("client_name").execute().data
            client_list = [c["client_name"] for c in clients]

            client = st.selectbox("Client", client_list)
            project = st.text_input("Project")
            description = st.text_area("Description")
            hours = st.number_input("Hours", 0.0, 9.0, step=0.5)

            if st.button("Save Entry"):
                supabase.table("timesheets").insert({
                    "user_email": st.session_state.user_email,
                    "work_date": str(work_date),
                    "client": client,
                    "project": project,
                    "description": description,
                    "hours": hours
                }).execute()
                st.success("Saved")
                st.rerun()

            if is_friday(date.today()):
                if st.button("Submit Week"):
                    supabase.table("weekly_submissions").insert({
                        "user_email": st.session_state.user_email,
                        "week_start": str(week_start),
                        "status": "Submitted"
                    }).execute()
                    st.success("Week submitted")
                    st.rerun()

        elif page == "Weekly Summary":

            week_date = st.date_input("Select Week", date.today())
            week_start = get_week_start(week_date)
            week_end = week_start + timedelta(days=6)

            res = supabase.table("timesheets") \
                .select("*") \
                .eq("user_email", st.session_state.user_email) \
                .gte("work_date", str(week_start)) \
                .lte("work_date", str(week_end)) \
                .execute()

            if res.data:
                df = pd.DataFrame(res.data)
                st.dataframe(df)
                st.metric("Total Hours", df["hours"].sum())

    # ---------------- ADMIN ----------------
    else:

        if page == "Dashboard":

            employees = supabase.table("profiles") \
                .select("*") \
                .eq("role", "employee") \
                .execute()

            submissions = supabase.table("weekly_submissions") \
                .select("*") \
                .eq("status", "Submitted") \
                .execute()

            col1, col2 = st.columns(2)
            col1.metric("Total Employees", len(employees.data))
            col2.metric("Pending Approvals", len(submissions.data))

        elif page == "Manage Clients":

            new_client = st.text_input("Add Client")
            if st.button("Add Client"):
                supabase.table("clients").insert({
                    "client_name": new_client
                }).execute()
                st.success("Client added")

        elif page == "Approvals":

            res = supabase.table("weekly_submissions").select("*").execute()

            if res.data:
                df = pd.DataFrame(res.data)
                st.dataframe(df)

        elif page == "Reports":

            res = supabase.table("timesheets").select("*").execute()

            if res.data:
                df = pd.DataFrame(res.data)
                st.dataframe(df)

                buffer = io.BytesIO()
                df.to_excel(buffer, index=False)
                st.download_button(
                    "Download Excel",
                    buffer.getvalue(),
                    file_name="Timesheet_Report.xlsx"
                )