import streamlit as st
from supabase import create_client
import hashlib
from datetime import date, timedelta
import pandas as pd
import io

# ---------------- SUPABASE CONNECTION ----------------
import streamlit as st
from supabase import create_client

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- UTILITIES ----------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_week_start(d):
    return d - timedelta(days=d.weekday())

def is_friday(d):
    return d.weekday() == 4

def get_week_status(email, week_start):
    res = supabase.table("weekly_submissions") \
        .select("status") \
        .eq("user_email", email) \
        .eq("week_start", str(week_start)) \
        .execute()
    return res.data[0]["status"] if res.data else "Draft"

# ---------------- SESSION ----------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ---------------- LOGIN ----------------
def login(email, password):
    hashed = hash_password(password)
    res = supabase.table("users") \
        .select("*") \
        .eq("email", email) \
        .eq("password", hashed) \
        .execute()
    return res.data[0] if res.data else None

# ---------------- UI ----------------
st.title("📘 Firm Timesheet System (Cloud)")

if not st.session_state.logged_in:

    st.subheader("Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        user = login(email, password)
        if user:
            st.session_state.logged_in = True
            st.session_state.user_email = user["email"]
            st.session_state.user_name = user["name"]
            st.session_state.user_role = user["role"]
            st.rerun()
        else:
            st.error("Invalid credentials")

else:

    st.sidebar.title("Navigation")
    role = st.session_state.user_role

    if role == "employee":
        page = st.sidebar.radio(
            "Go To",
            ["Dashboard", "Daily Entry", "Weekly Summary"]
        )
    else:
        page = st.sidebar.radio(
            "Go To",
            ["Dashboard", "Manage Clients", "Approvals", "Reports"]
        )

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    st.success(f"Welcome {st.session_state.user_name}")

    # ================= EMPLOYEE =================
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
            week_status = get_week_status(st.session_state.user_email, week_start)

            st.info(f"Week Status: {week_status}")

            clients = supabase.table("clients").select("client_name").execute().data
            client_list = [c["client_name"] for c in clients]

            client = st.selectbox("Client", client_list)
            project = st.text_input("Project")
            description = st.text_area("Description")
            hours = st.number_input("Hours", 0.0, 9.0, step=0.5)

            if week_status not in ["Submitted", "Approved"]:
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

            if week_status == "Draft" and is_friday(date.today()):
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
                total = df["hours"].sum()
                utilization = (total / 45) * 100
                st.metric("Total Hours", total)
                st.metric("Utilization %", f"{utilization:.2f}%")

    # ================= ADMIN =================
    else:

        if page == "Dashboard":

            users = supabase.table("users").select("id").eq("role", "employee").execute().data
            submissions = supabase.table("weekly_submissions") \
                .select("id") \
                .eq("status", "Submitted") \
                .execute().data

            col1, col2 = st.columns(2)
            col1.metric("Total Employees", len(users))
            col2.metric("Pending Approvals", len(submissions))

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

                sid = st.number_input("Submission ID", min_value=1)

                col1, col2 = st.columns(2)

                if col1.button("Approve"):
                    supabase.table("weekly_submissions") \
                        .update({"status": "Approved"}) \
                        .eq("id", sid).execute()
                    st.success("Approved")
                    st.rerun()

                if col2.button("Reject"):
                    supabase.table("weekly_submissions") \
                        .update({"status": "Rejected"}) \
                        .eq("id", sid).execute()
                    st.warning("Rejected")
                    st.rerun()

        elif page == "Reports":

            res = supabase.table("timesheets").select("*").execute()
            if res.data:
                df = pd.DataFrame(res.data)
                st.dataframe(df)
                st.metric("Total Hours", df["hours"].sum())

                sunday_df = df[pd.to_datetime(df["work_date"]).dt.weekday == 6]

                st.subheader("Sunday Work")
                if not sunday_df.empty:
                    st.dataframe(sunday_df)
                else:
                    st.info("No Sunday entries.")

                buffer = io.BytesIO()
                df.to_excel(buffer, index=False)
                st.download_button(
                    "Download Excel",
                    buffer.getvalue(),
                    file_name="Timesheet_Report.xlsx"
                )