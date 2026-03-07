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

# ---------------- LOGIN FUNCTION ----------------
def login_user(email, password):

    try:
        result = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if result.user:

            profile = supabase.table("profiles")\
                .select("*")\
                .eq("id", result.user.id)\
                .single()\
                .execute()

            if not profile.data["active"]:
                return "inactive"

        return result

    except Exception:
        return None

# ---------------- UI ----------------
st.title("📘 Firm Timesheet System (Cloud)")

# ---------------- PASSWORD RESET HANDLER ----------------
query_params = st.query_params

if "type" in query_params and query_params["type"] == "recovery":

    st.subheader("Set New Password")

    new_password = st.text_input("New Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")

    if st.button("Update Password"):

        if new_password != confirm_password:
            st.error("Passwords do not match")
        else:
            try:
                supabase.auth.update_user({
                    "password": new_password
                })
                st.success("Password updated successfully. Please login.")
                st.stop()
            except Exception:
                st.error("Password update failed")

# ---------------- AUTH ----------------
if not st.session_state.session:

    tab1, tab2, tab3 = st.tabs(["Login","Register","Reset Password"])

    # LOGIN
    with tab1:

        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        if st.button("Login"):

            result = login_user(email,password)

            if result == "inactive":
                st.error("Account deactivated. Contact admin.")
                st.stop()

            if result and result.user:

                st.session_state.session = result.session
                st.session_state.user_email = result.user.email
                st.session_state.user_id = result.user.id

                profile = supabase.table("profiles")\
                    .select("*")\
                    .eq("id",result.user.id)\
                    .single()\
                    .execute()

                st.session_state.user_role = profile.data["role"]
                st.session_state.user_name = profile.data["name"]

                st.rerun()

            else:
                st.error("Invalid credentials")

    # REGISTER
    with tab2:

        name = st.text_input("Full Name")
        email = st.text_input("Email", key="reg_email")
        password = st.text_input("Password", type="password", key="reg_pwd")

        if st.button("Create Account"):

            res = supabase.auth.sign_up({
                "email": email,
                "password": password
            })

            if res.user:

                supabase.table("profiles").insert({
                    "id": res.user.id,
                    "email": email,
                    "name": name,
                    "role": "employee",
                    "active": True
                }).execute()

                st.success("Account created. Verify email.")

    # PASSWORD RESET
    with tab3:

        email = st.text_input("Enter email")

        if st.button("Send Reset Link"):
            supabase.auth.reset_password_email(email)
            st.success("Password reset email sent")

# ---------------- MAIN APP ----------------
else:

    st.sidebar.title("Navigation")

    role = st.session_state.user_role

    if role == "employee":
        page = st.sidebar.radio("Go To",
        ["Dashboard","Daily Entry","Weekly Summary"])

    else:
        page = st.sidebar.radio("Go To",
        ["Dashboard","Manage Clients","Approvals","Reports","Employee Management"])

    if st.sidebar.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.session=None
        st.rerun()

    st.success(f"Welcome {st.session_state.user_name}")

# ---------------- EMPLOYEE ----------------
    if role == "employee":

        if page == "Dashboard":

            today=date.today()
            ws=get_week_start(today)
            we=ws+timedelta(days=6)

            res=supabase.table("timesheets")\
                .select("hours")\
                .eq("user_id",st.session_state.user_id)\
                .gte("work_date",str(ws))\
                .lte("work_date",str(we))\
                .execute()

            total=sum(r["hours"] for r in res.data)

            util=(total/45)*100

            c1,c2=st.columns(2)

            c1.metric("Week Hours",total)
            c2.metric("Utilization",f"{util:.1f}%")

        if page=="Daily Entry":

            d=st.date_input("Work Date",date.today())

            clients=supabase.table("clients").select("client_name").execute().data
            client=[c["client_name"] for c in clients]

            client_sel=st.selectbox("Client",client)
            project=st.text_input("Project")
            desc=st.text_area("Description")
            hrs=st.number_input("Hours",0.0,9.0,step=0.5)

            if st.button("Save"):

                supabase.table("timesheets").insert({
                    "user_id":st.session_state.user_id,
                    "work_date":str(d),
                    "client":client_sel,
                    "project":project,
                    "description":desc,
                    "hours":hrs
                }).execute()

                st.success("Saved")

        if page=="Weekly Summary":

            res=supabase.table("timesheets")\
                .select("*")\
                .eq("user_id",st.session_state.user_id)\
                .execute()

            if res.data:
                df=pd.DataFrame(res.data)
                st.dataframe(df)

# ---------------- ADMIN ----------------
    if role=="admin":

        if page=="Dashboard":

            emps=supabase.table("profiles")\
                .select("*")\
                .eq("role","employee")\
                .execute()

            st.metric("Total Employees",len(emps.data))

        if page=="Manage Clients":

            nc=st.text_input("New Client")

            if st.button("Add Client"):

                supabase.table("clients").insert({
                    "client_name":nc
                }).execute()

                st.success("Client added")

        if page=="Reports":

            res=supabase.table("timesheets").select("*").execute()

            if res.data:
                df=pd.DataFrame(res.data)
                st.dataframe(df)

        # ---------------- EMPLOYEE MANAGEMENT ----------------
        if page=="Employee Management":

            st.subheader("Employees")

            res=supabase.table("profiles")\
                .select("*")\
                .eq("role","employee")\
                .execute()

            if res.data:

                df=pd.DataFrame(res.data)
                st.dataframe(df)

                emp=st.selectbox("Select Employee",
                df["email"])

                reason=st.text_area("Removal Reason")

                eff_date=st.date_input("Effective Date")

                if st.button("Deactivate Employee"):

                    supabase.table("profiles")\
                        .update({
                        "active":False,
                        "removal_reason":reason,
                        "removal_date":str(eff_date)
                        })\
                        .eq("email",emp)\
                        .execute()

                    st.success("Employee deactivated")