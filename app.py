import streamlit as st
from supabase import create_client
from datetime import date, timedelta
import pandas as pd
import io

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="Firm Timesheet System",
    page_icon="📘",
    layout="wide"
)

# ---------------- PURPLE UI STYLE ----------------
st.markdown("""
<style>

.stApp {
    background-color: #f6f2ff;
}

h1, h2, h3 {
    color: #5b21b6;
}

.stButton>button {
    background-color:#7c3aed;
    color:white;
    border-radius:8px;
}

.stButton>button:hover {
    background-color:#6d28d9;
}

.stTextInput>div>div>input {
    border-radius:8px;
}

.stSelectbox>div>div {
    border-radius:8px;
}

.stMetric {
    background-color:white;
    padding:15px;
    border-radius:10px;
}

</style>
""", unsafe_allow_html=True)

# ---------------- SUPABASE CONNECTION ----------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- UTILITIES ----------------
def get_week_start(d):
    return d - timedelta(days=d.weekday())

def is_friday(d):
    return d.weekday() == 4

# ---------------- SESSION INIT ----------------
if "session" not in st.session_state:
    st.session_state.session = None

if "user_role" not in st.session_state:
    st.session_state.user_role = None

if "user_name" not in st.session_state:
    st.session_state.user_name = None

if "user_email" not in st.session_state:
    st.session_state.user_email = None

if "user_id" not in st.session_state:
    st.session_state.user_id = None

# ---------------- PASSWORD RESET HANDLER ----------------
query_params = st.query_params

if "type" in query_params and query_params["type"][0] == "recovery":

    st.title("🔑 Reset Password")

    new_password = st.text_input("New Password", type="password")

    if st.button("Update Password"):

        try:

            supabase.auth.update_user({
                "password": new_password
            })

            st.success("Password updated. Please login.")
            st.stop()

        except Exception:
            st.error("Password reset failed")

# ---------------- AUTH FUNCTIONS ----------------
def login_user(email, password):

    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        return response

    except Exception:
        return None


def signup_user(name, email, password):

    try:

        response = supabase.auth.sign_up({
            "email": email,
            "password": password
        })

        if response.user:

            supabase.table("profiles").insert({
                "id": response.user.id,
                "email": email,
                "name": name,
                "role": "employee"
            }).execute()

        return True

    except Exception:
        return False


def send_reset(email):

    try:

        supabase.auth.reset_password_for_email(
            email,
            {
                "redirect_to": st.secrets["APP_URL"]
            }
        )

        return True

    except Exception:
        return False

# ---------------- TITLE ----------------
st.title("📘 Firm Timesheet System")

# ---------------- LOGIN / SIGNUP UI ----------------
if not st.session_state.session:

    tab1, tab2, tab3 = st.tabs(["Login", "Create Account", "Forgot Password"])

    # ---------------- LOGIN ----------------
    with tab1:

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
                    st.error("Profile missing. Contact admin.")

            else:
                st.error("Invalid login")

    # ---------------- SIGNUP ----------------
    with tab2:

        name = st.text_input("Name")
        email = st.text_input("Email ", key="signup_email")
        password = st.text_input("Password ", type="password")

        if st.button("Create Account"):

            ok = signup_user(name, email, password)

            if ok:
                st.success("Account created. Please login.")
            else:
                st.error("Signup failed")

    # ---------------- FORGOT PASSWORD ----------------
    with tab3:

        email = st.text_input("Enter your email")

        if st.button("Send Reset Link"):

            ok = send_reset(email)

            if ok:
                st.success("Password reset link sent.")
            else:
                st.error("Failed to send reset email")

# ---------------- MAIN APP ----------------
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

        supabase.auth.sign_out()

        st.session_state.session = None
        st.session_state.user_role = None
        st.session_state.user_name = None
        st.session_state.user_email = None
        st.session_state.user_id = None

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
                .eq("user_id", st.session_state.user_id) \
                .gte("work_date", str(week_start)) \
                .lte("work_date", str(week_end)) \
                .execute()

            total = sum(r["hours"] for r in res.data)

            utilization = (total / 45) * 100

            c1, c2 = st.columns(2)

            c1.metric("Week Hours", total)
            c2.metric("Utilization", f"{utilization:.2f}%")

        if page == "Daily Entry":

            work_date = st.date_input("Work Date", date.today())

            clients = supabase.table("clients").select("client_name").execute().data

            client_list = [c["client_name"] for c in clients]

            client = st.selectbox("Client", client_list)

            project = st.text_input("Project")

            description = st.text_area("Description")

            hours = st.number_input("Hours", 0.0, 9.0, step=0.5)

            if st.button("Save Entry"):

                supabase.table("timesheets").insert({
                    "user_id": st.session_state.user_id,
                    "work_date": str(work_date),
                    "client": client,
                    "project": project,
                    "description": description,
                    "hours": hours
                }).execute()

                st.success("Saved")

                st.rerun()

        if page == "Weekly Summary":

            res = supabase.table("timesheets") \
                .select("*") \
                .eq("user_id", st.session_state.user_id) \
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

            c1, c2 = st.columns(2)

            c1.metric("Employees", len(employees.data))

        if page == "Manage Clients":

            new_client = st.text_input("Add Client")

            if st.button("Add Client"):

                supabase.table("clients").insert({
                    "client_name": new_client
                }).execute()

                st.success("Client Added")

        if page == "Reports":

            res = supabase.table("timesheets").select("*").execute()

            if res.data:

                df = pd.DataFrame(res.data)

                st.dataframe(df)

                buffer = io.BytesIO()

                df.to_excel(buffer, index=False)

                st.download_button(
                    "Download Excel",
                    buffer.getvalue(),
                    file_name="timesheet.xlsx"
                )