import streamlit as st
import pandas as pd
import gspread
import datetime
import io
import time
import json
import os
import hashlib
import plotly.graph_objects as go
import plotly.express as px
import streamlit.components.v1 as components
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe
from datetime import timedelta

# تهيئة الصفحة الرسمية للتطبيق
st.set_page_config(page_title="Activity Tracker Multi-User", layout="wide", page_icon="🟢")

STATE_FILE = ".stopwatch_state.json"

def load_stopwatch_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f: return json.load(f)
        except: pass
    return {"running": False, "start_time": None, "elapsed": 0, "mode": "free", "duration_mins": 25}

def save_stopwatch_state(running, start_time, elapsed, mode="free", duration_mins=25):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"running": running, "start_time": start_time, "elapsed": elapsed, "mode": mode, "duration_mins": duration_mins}, f)
    except: pass

saved_state = load_stopwatch_state()

# حل مشكلة الـ Widget instantiated: استخدام الـ Session State بشكل مستقل
if "duration_val" not in st.session_state:
    st.session_state.duration_val = 1.0

if "sw_running" not in st.session_state:
    st.session_state.sw_running = saved_state["running"]
    st.session_state.sw_start = saved_state["start_time"]
    st.session_state.sw_elapsed = saved_state["elapsed"]
    st.session_state.sw_mode = saved_state["mode"]
    st.session_state.sw_pomo_mins = saved_state["duration_mins"]

def set_duration(amount):
    st.session_state.duration_val = float(amount)

def make_hashes(password): 
    return hashlib.sha256(str.encode(password)).hexdigest()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_spreadsheet():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet_name = st.secrets["google"]["sheet_name"]
    return client.open(sheet_name)

spreadsheet = get_spreadsheet()
sheet_main = spreadsheet.sheet1

# التحقق من ورقة المستخدمين
try:
    sheet_users = spreadsheet.worksheet("Users")
except gspread.exceptions.WorksheetNotFound:
    sheet_users = spreadsheet.add_worksheet(title="Users", rows="100", cols="5")
    sheet_users.append_row(["Username", "Password", "Role"])
    sheet_users.append_row(["admin", make_hashes("admin123"), "Admin"])

# الهيكل الثابت للأعمدة المطلوبة
COLUMNS = ['ID', 'المستخدم', 'التاريخ', 'السنة', 'الشهر', 'الأسبوع', 'اليوم', 'الساعة', 'النشاط', 'المدة_بالدقائق', 'الملاحظات']

@st.cache_data(ttl=15)
def load_users_db():
    try:
        records = sheet_users.get_all_records()
        return pd.DataFrame(records)
    except:
        return pd.DataFrame(columns=["Username", "Password", "Role"])

@st.cache_data(ttl=15)
def load_data():
    try:
        records = sheet_main.get_all_records()
        if len(records) == 0: 
            return pd.DataFrame(columns=COLUMNS)
        
        df = pd.DataFrame(records)
        # تنظيف والتأكد من وجود جميع الأعمدة الأساسية لمنع أخطاء الـ KeyError
        for col in COLUMNS:
            if col not in df.columns: 
                df[col] = ""
        return df[COLUMNS]
    except Exception as e:
        return pd.DataFrame(columns=COLUMNS)

def save_data(df):
    try:
        clean_df = df[COLUMNS].copy()
        
        # حل خطأ تجاوز حدود الورقة وجدول البيانات الذكي
        try:
            sheet_main.clear()
        except:
            pass
            
        # توسيع الشبكة برمجياً لتجنب خطأ Exceeds grid limits
        req_rows = max(len(clean_df) + 50, 100)
        req_cols = len(COLUMNS) + 5
        if sheet_main.row_count < req_rows or sheet_main.col_count < req_cols:
            sheet_main.resize(rows=req_rows, cols=req_cols)
            
        set_with_dataframe(sheet_main, clean_df, include_index=False, include_column_header=True, resize=True)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"خطأ أثناء الحفظ في قاعدة البيانات: {e}")

# ==========================================
# 🔐 نظام إدارة الجلسات وتأكيد الهوية
# ==========================================
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "username" not in st.session_state: st.session_state.username = ""
if "user_role" not in st.session_state: st.session_state.user_role = "User"

LEXICON = {
    "AR": {
        "nav_title": "🧭 قائمة التنقل", "page_log": "📥 تسجيل نشاط جديد", "page_dash": "📊 لوحة التحكم والإحصاءات", "page_admin": "👑 إدارة المستخدمين (المدير)",
        "goals_setup": "🎯 إدارة الأهداف الذكية", "g_daily": "الهدف اليومي (ساعات):", "g_weekly": "الهدف الأسبوعي (ساعات):", "g_monthly": "الهدف الشهري (ساعات):",
        "duration_lbl": "مدة النشاط (بالساعات)", "presets_lbl": "⏱️ أزرار تعيين الوقت السريعة:", "m30": "30 د", "h1": "1 س", "h15": "1.5 س", "h2": "2 س",
        "del_dialog_title": "⚠️ تأكيد عملية الحذف", "del_all_warn": "🚨 هل أنت متأكد تماماً؟ لا يمكن التراجع عن هذا الإجراء!", "del_all_btn": "❌ نعم، امسح السجل بالكامل",
        "del_sel_warn": "هل أنت متأكد أنك تريد حذف الأنشطة المحددة؟ العدد:", "del_sel_btn": "🗑️ تأكيد الحذف النهائي", "log_header": "🟢 تسجيل ومتابعة الأنشطة",
        "focus_hub": "⏱️ نظام التركيز المطور (ساعة الإيقاف)", "focus_sys": "اختر نظام التركيز:", "f_sw": "⏱️ عداد حر تصاعدي", "f_pomo": "🎯 مؤقت بومودورو (Pomodoro)",
        "pomo_sel": "اختر مدة جلسة التركيز (بالدقائق):", "sw_active": "العداد يعمل حالياً بنظام:", "sw_start_btn": "▶️ ابدأ التركيز الآن", "sw_stop_btn": "⏸️ إنهاء الجلسة وتعبئة الوقت",
        "sw_running_lbl": "⏳ العداد المستمر يعمل", "sw_remaining_lbl": "🎯 متبقي على النهاية", "pomo_done": "🎉 انتهت جلسة البومودورو بنجاح!",
        "sw_updated_toast": "📥 تم تحديث حقل المدة بـ {} ساعة!", "sw_ready": "⏱️ الوقت المسجل الجاهز", "sw_reset": "🔄 تصفير وإعادة تعيين", "form_sub": "📥 نموذج البيانات والملء الذكي",
        "form_auto": "التسجيل التلقائي بالوقت والتاريخ الحالي فوراً ⚡", "act_cat": "النشاط", "act_custom_opt": "➕ إضافة نشاط مخصص...", "act_custom_lbl": "اكتب اسم النشاط الجديد هنا:",
        "notes_lbl": "✍️ ملاحظات وتعليقات على النشاط (اختياري):", "notes_ph": "مثال: تمرين، برمجة التطبيق", "notes_ph_manual": "مثال: مراجعة كاملة للملفات القديمة",
        "cal_lbl": "اختر التاريخ من التقويم 📅", "clock_lbl": "اضبط وقت النشاط ⌚", "submit_btn": "➕ تسجيل النشاط وحفظه تلقائياً", "success_toast": "✅ تم تسجيل نشاط ({}) بنجاح!",
        "history_sub": "📋 سجل التحكم بالبيانات وحذف الأسطر", "col_del": "حذف؟", "col_user": "المستخدم", "col_ts": "التاريخ", "col_cat": "النشاط", "col_hours": "المدة (ساعات)", "col_notes": "الملاحظات", "col_wd": "اليوم", "col_time": "الساعة",
        "del_selected_trigger": "🗑️ حذف الأنشطة المحددة", "dl_excel": "📥 تحميل سجل تمارينك كملف Excel", "wipe_all_trigger": "🚨 مسح السجل بالكامل والبدء من جديد",
        "dash_header": "📊 لوحة التحكم والأداء العام", "filter_sub": "🔍 فلترة التحليلات حسب النطاق الزمني", "filter_lbl": "اختر الفترة الزمنية لتحديث كافة التحليلات والرسومات:",
        "f_all": "🔄 السجل بالكامل (كل البيانات)", "f_today": "📅 اليوم", "f_week": "📆 هذا الأسبوع", "f_month": "🗓️ هذا الشهر", "f_90": "🚀 آخر 90 يوماً", "f_custom": "✏️ نطاق مخصص...",
        "date_from": "من تاريخ:", "date_to": "إلى تاريخ:",
        "metric_curr_streak": "🔥 السلسلة الحالية", "metric_max_streak": "🏆 أطول سلسلة (Streak)", "metric_scoped_hrs": "⏱ إجمالي الساعات", "metric_entries": "📋 عدد الأنشطة", "metric_today_vol": "🎯 ساعات اليوم", "metric_dominant": "⭐ الأكثر تفضيلاً",
        "days_unit": "يوم", "hours_unit": "س", "radar_sub": "🎯 رادار الأهداف الذكية ومعدلات الإنجاز", "r_daily": "الهدف اليومي", "r_weekly": "الهدف الأسبوعي", "r_monthly": "الهدف الشهري", "r_comp": "من الهدف",
        "grid_sub": "🧱 مخطط الالتزام السنوي المفلتر (GitHub Grid)", "pie_sub": "🍕 distribution", "pie_empty": "لا توجد أنشطة مسجلة في هذا النطاق الزمني لعرض توزيعها.",
        "trend_sub": "📈 منحنى تطور الأداء وحجم الساعات", "trend_empty": "أدخل بيانات أو وسّع النقاط لمشاهدة خط التطور.",
        "ach_sub": "🏆 قائمة الإنجازات المفتوحة (دائمة)", "ach_comp": "(مكتمل)", "ach_prog": "(قيد التقدم)", "gym_def": "الدراسة 📚", "study_def": "النادي 🏋️‍♂️", "work_def": "العمل 💼", "custom_err": "يرجى كتابة اسم النشاط المخصص أولاً!",
        "login_title": "🔒 نظام تسجيل الدخول الموحد", "username_lbl": "اسم المستخدم", "password_lbl": "كلمة المرور", "login_btn": "🚪 تسجيل الدخول", "logout_btn": "🚪 تسجيل الخروج", "invalid_login": "❌ اسم المستخدم أو كلمة المرور غير صحيحة",
        "admin_scope": "🔍 استعراض بيانات مستخدم محدد (نطاق المدير):", "all_users_opt": "👥 كل المستخدمين معاً", "create_user_sub": "➕ إنشاء حساب مستخدم جديد", "new_user_lbl": "اسم المستخدم الجديد", "new_pass_lbl": "كلمة المرور الجديدة", "role_lbl": "الصلاحية", "create_btn": "💼 إنشاء الحساب وحفظه برمز مشفر"
    },
    "EN": {
        "nav_title": "🧭 Navigation", "page_log": "📥 Log New Activity", "page_dash": "📊 Analytics Dashboard", "page_admin": "👑 User Management (Admin)",
        "goals_setup": "🎯 Smart Goals Setup", "g_daily": "Daily Goal (Hours):", "g_weekly": "Weekly Goal (Hours):", "g_monthly": "Monthly Goal (Hours):",
        "duration_lbl": "Activity Duration (Hours)", "presets_lbl": "⏱️ Quick presets:", "m30": "30 m", "h1": "1 h", "h15": "1.5 h", "h2": "2 h",
        "del_dialog_title": "⚠️ Confirm Deletion", "del_all_warn": "🚨 Are you absolutely sure? This action cannot be undone!", "del_all_btn": "❌ Yes, wipe all data",
        "del_sel_warn": "Are you sure you want to permanently delete the selected activities? Count:", "del_sel_btn": "🗑️ Confirm Permanent Delete", "log_header": "🟢 Track & Log Activities",
        "focus_hub": "⏱️ Focus Hub (Stopwatch Engine)", "focus_sys": "Focus System:", "f_sw": "⏱️ Standard Stopwatch", "f_pomo": "🎯 Pomodoro Timer",
        "pomo_sel": "Select Session Duration (Minutes):", "sw_active": "Active Session:", "sw_start_btn": "▶️ Start Focus Session Now", "sw_stop_btn": "⏸️ Complete Current Session & Populate Time",
        "sw_running_lbl": "⏳ Stopwatch Running", "sw_remaining_lbl": "🎯 Remaining Time", "pomo_done": "🎉 Pomodoro session complete.",
        "sw_updated_toast": "📥 Duration field updated with {} hours!", "sw_ready": "⏱️ Pending Tracked Time", "sw_reset": "🔄 Reset Timer", "form_sub": "📥 Input Form & Smart Prefills",
        "form_auto": "⚡ Real-time instant stamping (Current time & date)", "act_cat": "Activity Category", "act_custom_opt": "➕ Add Custom Activity...", "act_custom_lbl": "Enter custom activity name:",
        "notes_lbl": "✍️ Notes & Comments (Optional):", "notes_ph": "e.g., Workout, coding app block", "notes_ph_manual": "e.g., Extensive review of legacy assets",
        "cal_lbl": "Select Calendar Date 📅", "clock_lbl": "Set Timestamp ⌚", "submit_btn": "➕ Submit & Log Activity", "success_toast": "✅ Activity ({}) successfully logged!",
        "history_sub": "📋 Historical Registry & Row Disposal Management", "col_del": "Delete?", "col_user": "User", "col_ts": "Timestamp", "col_cat": "Category", "col_hours": "Hours", "col_notes": "Notes", "col_wd": "Weekday", "col_time": "Time",
        "del_selected_trigger": "🗑️ Delete Selected Rows", "dl_excel": "📥 Download Structured Excel Spreadsheet (.xlsx)", "wipe_all_trigger": "🚨 Wipe Entire Data Logs",
        "dash_header": "📊 Performance & Analytics Matrix", "filter_sub": "🔍 Temporal Range Filtration", "filter_lbl": "Choose evaluation interval to align charts and metrics:",
        "f_all": "🔄 Full History (All Data)", "f_today": "📅 Today", "f_week": "📆 This Week", "f_month": "🗓️ This Month", "f_90": "🚀 Last 90 Days", "f_custom": "✏️ Custom Date Range...",
        "date_from": "Start Date:", "date_to": "End Date:",
        "metric_curr_streak": "🔥 Current Streak", "metric_max_streak": "🏆 Longest Streak", "metric_scoped_hrs": "⏱️ Scoped Duration", "metric_entries": "📋 Log Entries Count", "metric_today_vol": "🎯 Today's Volume", "metric_dominant": "⭐ Dominant Activity",
        "days_unit": "Days", "hours_unit": "Hrs", "radar_sub": "🎯 Smart Goals Objective Monitor", "r_daily": "Daily Target", "r_weekly": "Weekly Target", "r_monthly": "Monthly Target", "r_comp": "Completed",
        "grid_sub": "🧱 Annual Consistency Grid", "pie_sub": "🍕 Allocation", "pie_empty": "No distribution entries found inside current evaluation range.",
        "trend_sub": "📈 Performance Trend Evolution", "trend_empty": "Log additional activities or expand timeline criteria to map progress charts.",
        "ach_sub": "🏆 Permanent Achievement Milestones", "ach_comp": "(Unlocked)", "ach_prog": "(In Progress)", "gym_def": "Studying 📚", "study_def": "Gym 🏋️‍♂️", "work_def": "Work 💼", "custom_err": "Please enter a custom activity label first!",
        "login_title": "🔒 Secure Unified Login System", "username_lbl": "Username", "password_lbl": "Password", "login_btn": "🚪 Sign In", "logout_btn": "🚪 Log Out", "invalid_login": "❌ Invalid Username or Password",
        "admin_scope": "🔍 Review specific user logs (Admin Scope):", "all_users_opt": "👥 All Users Combined", "create_user_sub": "➕ Create New User Account", "new_user_lbl": "New Username", "new_pass_lbl": "New Password", "role_lbl": "Role", "create_btn": "💼 Register Encrypted User Account"
    }
}

# شريط اللغة الجانبي
st.sidebar.title("🌐 Language / اللغة")
lang = st.sidebar.selectbox("Choose Application Language:", ["العربية", "English"], index=0)
L = LEXICON["AR"] if lang == "العربية" else LEXICON["EN"]

# ==========================================
# 🛑 واجهة تسجيل الدخول
# ==========================================
if not st.session_state.logged_in:
    st.markdown(f"<h2 style='text-align: center;'>{L['login_title']}</h2>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        with st.form("login_form"):
            user_input = st.text_input(L["username_lbl"]).strip()
            pass_input = st.text_input(L["password_lbl"], type="password").strip()
            submitted = st.form_submit_button(L["login_btn"], use_container_width=True)
            if submitted:
                users_df = load_users_db()
                hashed_input = make_hashes(pass_input)
                matched = users_df[(users_df["Username"] == user_input) & (users_df["Password"] == hashed_input)]
                if not matched.empty:
                    st.session_state.logged_in = True
                    st.session_state.username = user_input
                    st.session_state.user_role = matched.iloc[0]["Role"]
                    st.success("Welcome!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(L["invalid_login"])
    st.stop()

# قراءة قاعدة البيانات الموحدة
df_db_all = load_data()

# الخيارات الجانبية بعد تسجيل الدخول
st.sidebar.markdown(f"#### 👤 {st.session_state.username} ({st.session_state.user_role})")
if st.sidebar.button(L["logout_btn"], type="secondary", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.user_role = "User"
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.title(L["nav_title"])
pages_available = [L["page_log"], L["page_dash"]]
if st.session_state.user_role == "Admin":
    pages_available.append(L["page_admin"])
page = st.sidebar.radio("", pages_available)

# تصفية وفلترة نطاق البيانات حسب الصلاحية
if st.session_state.user_role == "Admin":
    unique_users_in_db = ["👥 الكل" if lang=="العربية" else "👥 All"] + list(load_users_db()["Username"].unique())
    selected_scope = st.sidebar.selectbox(L["admin_scope"], unique_users_in_db)
    if "All" in selected_scope or "الكل" in selected_scope:
        df_db = df_db_all.copy()
    else:
        df_db = df_db_all[df_db_all["المستخدم"] == selected_scope].copy()
else:
    df_db = df_db_all[df_db_all["المستخدم"] == st.session_state.username].copy()

st.sidebar.markdown("---")
st.sidebar.subheader(L["goals_setup"])
DAILY_GOAL = st.sidebar.number_input(L["g_daily"], min_value=0.5, max_value=24.0, value=2.0, step=0.5)
WEEKLY_GOAL = st.sidebar.number_input(L["g_weekly"], min_value=1.0, max_value=168.0, value=14.0, step=1.0)
MONTHLY_GOAL = st.sidebar.number_input(L["g_monthly"], min_value=5.0, max_value=744.0, value=60.0, step=5.0)

def render_duration_section(col_context):
    with col_context:
        # حل مشكلة تعديل الـ widget: ربط القيمة بمتغير ديناميكي مستقل
        st.number_input(L["duration_lbl"], min_value=0.1, max_value=24.0, step=0.1, key="duration_val")
        st.caption(L["presets_lbl"])
        b1, b2, b3, b4 = st.columns(4)
        if b1.button(L["m30"], key="b30", use_container_width=True): set_duration(0.5); st.rerun()
        if b2.button(L["h1"], key="b1h", use_container_width=True): set_duration(1.0); st.rerun()
        if b3.button(L["h15"], key="b15", use_container_width=True): set_duration(1.5); st.rerun()
        if b4.button(L["h2"], key="b2h", use_container_width=True): set_duration(2.0); st.rerun()

@st.dialog(L["del_dialog_title"])
def confirm_delete_dialog(indices, is_all=False):
    if is_all:
        st.warning(L["del_all_warn"])
        if st.button(L["del_all_btn"], type="primary", use_container_width=True):
            if st.session_state.user_role == "Admin":
                sheet_main.clear()
                sheet_main.append_row(COLUMNS)
            else:
                fresh_df = df_db_all[df_db_all["المستخدم"] != st.session_state.username]
                save_data(fresh_df)
            st.success("Wiped!")
            time.sleep(1)
            st.rerun()
    else:
        st.warning(f"{L['del_sel_warn']} {len(indices)}")
        if st.button(L["del_sel_btn"], type="primary", use_container_width=True):
            # استخدام الفهرس الفعلي الرئيسي لقاعدة البيانات لمنع أخطاء الحذف العشوائي
            updated_df = df_db_all.drop(indices).reset_index(drop=True)
            save_data(updated_df)
            st.toast("Deleted!", icon="🗑️")
            time.sleep(1)
            st.rerun()

now = datetime.datetime.now()
today_date = now.date()
current_year = now.year

if not df_db.empty:
    df_db_calc = df_db.copy()
    df_db_calc['parsed_date'] = pd.to_datetime(df_db_calc['التاريخ'], errors='coerce')
    df_db_calc['short_date'] = df_db_calc['parsed_date'].dt.strftime('%Y-%m-%d')
    df_db_calc['المدة_بالدقائق'] = pd.to_numeric(df_db_calc['المدة_بالدقائق'], errors='coerce').fillna(0)
    df_db_calc["date_only"] = df_db_calc["parsed_date"].dt.date
else:
    df_db_calc = df_db.copy()
    df_db_calc['short_date'] = pd.Series(dtype='str')
    df_db_calc["date_only"] = pd.Series(dtype='object')

# ==========================================
# 1. الصفحة الأولى: تسجيل الأنشطة
# ==========================================
if page == L["page_log"]:
    st.header(L["log_header"])
    st.markdown(f"### {L['focus_hub']}")
    
    if not st.session_state.sw_running:
        mode_choice = st.radio(L["focus_sys"], [L["f_sw"], L["f_pomo"]], horizontal=True)
        st.session_state.sw_mode = "free" if mode_choice == L["f_sw"] else "pomodoro"
        if st.session_state.sw_mode == "pomodoro":
            st.session_state.sw_pomo_mins = st.selectbox(L["pomo_sel"], [25, 50, 15, 5], index=0)
    else:
        current_mode_text = L["f_sw"] if st.session_state.sw_mode == "free" else f"{L['f_pomo']} ({st.session_state.sw_pomo_mins})"
        st.info(f"{L['sw_active']} **{current_mode_text}** 🔒")

    stop_col1, stop_col2 = st.columns([2, 1])
    
    with stop_col1:
        if not st.session_state.sw_running:
            if st.button(L["sw_start_btn"], use_container_width=True, type="primary"):
                st.session_state.sw_running = True
                st.session_state.sw_start = time.time() - st.session_state.sw_elapsed
                save_stopwatch_state(True, st.session_state.sw_start, st.session_state.sw_elapsed, st.session_state.sw_mode, st.session_state.sw_pomo_mins)
                st.rerun()
        else:
            current_elapsed = time.time() - st.session_state.sw_start
            if st.session_state.sw_mode == "pomodoro":
                target_seconds = st.session_state.sw_pomo_mins * 60
                if current_elapsed >= target_seconds:
                    st.session_state.sw_running = False
                    st.session_state.sw_elapsed = 0
                    st.session_state.duration_val = round(st.session_state.sw_pomo_mins / 60, 2)
                    save_stopwatch_state(False, None, 0, st.session_state.sw_mode, st.session_state.sw_pomo_mins)
                    st.balloons()
                
            if st.session_state.sw_running:
                if st.button(L["sw_stop_btn"], use_container_width=True):
                    st.session_state.sw_running = False
                    st.session_state.sw_elapsed = current_elapsed
                    calc_hours = round(current_elapsed / 3600, 2)
                    st.session_state.duration_val = max(calc_hours, 0.1)
                    save_stopwatch_state(False, None, st.session_state.sw_elapsed, st.session_state.sw_mode, st.session_state.sw_pomo_mins)
                    st.rerun()
                
    with stop_col2:
        if st.session_state.sw_running:
            current_elapsed = time.time() - st.session_state.sw_start
            if st.session_state.sw_mode == "free":
                mins, secs = divmod(int(current_elapsed), 60)
                hrs, mins = divmod(mins, 60)
                st.metric(L["sw_running_lbl"], f"{hrs:02d}:{mins:02d}:{secs:02d}")
            else:
                target_seconds = st.session_state.sw_pomo_mins * 60
                remaining_seconds = max(int(target_seconds - current_elapsed), 0)
                rem_mins, rem_secs = divmod(remaining_seconds, 60)
                st.metric(L["sw_remaining_lbl"], f"{rem_mins:02d}:{rem_secs:02d}")
        else:
            if st.session_state.sw_elapsed > 0:
                mins, secs = divmod(int(st.session_state.sw_elapsed), 60)
                hrs, mins = divmod(mins, 60)
                st.metric(L["sw_ready"], f"{hrs:02d}:{mins:02d}:{secs:02d}")
                if st.button(L["sw_reset"]):
                    st.session_state.sw_elapsed = 0
                    st.session_state.duration_val = 1.0
                    save_stopwatch_state(False, None, 0, st.session_state.sw_mode, st.session_state.sw_pomo_mins)
                    st.rerun()

    st.markdown("---")
    st.subheader(L["form_sub"])
    auto_time = st.toggle(L["form_auto"], value=True)

    default_activities = [L["gym_def"], L["study_def"], L["work_def"]]
    existing_activities = df_db_all['النشاط'].dropna().unique().tolist() if 'النشاط' in df_db_all.columns else []
    activities_list = list(set(default_activities + [x for x in existing_activities if x]))

    if L["act_custom_opt"] not in activities_list: activities_list.append(L["act_custom_opt"])
    months_list = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

    target_date = today_date
    chosen_time_str = now.strftime('%H:%M')

    if auto_time:
        c1, c2 = st.columns(2)
        with c1:
            selected_activity = st.selectbox(L["act_cat"], activities_list, key="act_auto")
            if selected_activity == L["act_custom_opt"]: custom_activity = st.text_input(L["act_custom_lbl"], key="cust_auto")
            activity_notes = st.text_input(L["notes_lbl"], placeholder=L["notes_ph"], key="notes_auto")
        render_duration_section(c2)
    else:
        c1, c2, c3 = st.columns([2, 1.5, 1.5])
        with c1:
            selected_activity = st.selectbox(L["act_cat"], activities_list, key="act_manual")
            if selected_activity == L["act_custom_opt"]: custom_activity = st.text_input(L["act_custom_lbl"], key="cust_manual")
            activity_notes = st.text_input(L["notes_lbl"], placeholder=L["notes_ph_manual"], key="notes_manual")
        render_duration_section(c1)
        with c2: target_date = st.date_input(L["cal_lbl"], value=today_date)
        with c3:
            clock_html = f"""
            <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; font-family:sans-serif; width: 100%;">
                <label style='font-size:14px; font-weight:bold; color:#216e39; margin-bottom:8px; text-align:center;'>{L['clock_lbl']}</label>
                <input type="time" id="analog_picker" value="{chosen_time_str}" style="font-size:20px; padding:8px; border-radius:8px; border:2px solid #40c463; text-align:center; width:170px; font-weight:bold; color:#216e39; background-color:#fff;">
            </div>
            <script>
                var picker = document.getElementById('analog_picker');
                function emitTime() {{ window.parent.postMessage({{type: 'streamlit:setComponentValue', value: picker.value}}, '*'); }}
                picker.addEventListener('input', emitTime); picker.addEventListener('change', emitTime);
                setTimeout(emitTime, 250);
            </script>
            """
            clock_return = components.html(clock_html, height=130)
            if clock_return: chosen_time_str = str(clock_return)

    if st.button(L["submit_btn"], use_container_width=True, type="primary"):
        if selected_activity == L["act_custom_opt"]:
            if 'custom_activity' in locals() and custom_activity.strip() != "": final_activity = custom_activity.strip()
            else:
                st.error(L["custom_err"])
                st.stop()
        else: final_activity = selected_activity

        if auto_time: target_time = now.time()
        else:
            try:
                t_parts = chosen_time_str.split(":")
                target_time = datetime.time(int(t_parts[0]), int(t_parts[1]))
            except: target_time = now.time()

        combined_datetime = datetime.datetime.combine(target_date, target_time)
        duration_minutes = int(st.session_state.duration_val * 60)
        
        new_row = {
            'ID': int(datetime.datetime.now().timestamp() * 1000),
            'المستخدم': st.session_state.username,
            'التاريخ': combined_datetime.strftime('%Y-%m-%d %H:%M:%S'),
            'السنة': int(combined_datetime.year),
            'الشهر': str(months_list[combined_datetime.month - 1]),
            'الأسبوع': int(combined_datetime.isocalendar().week),
            'اليوم': str(combined_datetime.strftime('%A')),
            'الساعة': str(combined_datetime.strftime('%H:%M')),
            'النشاط': str(final_activity),
            'المدة_بالدقائق': duration_minutes,
            'الملاحظات': str(activity_notes.strip())
        }
        
        df_db_all = pd.concat([df_db_all, pd.DataFrame([new_row])], ignore_index=True)
        save_data(df_db_all)
        st.toast(L["success_toast"].format(final_activity), icon="🔥")
        st.rerun()

    # قسم الحذف الآمن والمصحح
    if not df_db.empty:
        st.markdown("---")
        st.subheader(L["history_sub"])
        display_df = df_db.copy()
        
        # حماية ضد أخطاء فقدان الأعمدة عند التهيئة الصفرية للجدول
        for c in COLUMNS:
            if c not in display_df.columns: display_df[c] = ""
            
        display_df[L['col_del']] = False
        
        # حماية عملية تحويل البيانات الحسابية من أخطاء الـ TypeError
        display_df['المدة_بالدقائق'] = pd.to_numeric(display_df['المدة_بالدقائق'], errors='coerce').fillna(0)
        display_df[L['col_hours']] = round(display_df['المدة_بالدقائق'] / 60, 2)
        
        display_df[L['col_notes']] = display_df['الملاحظات'].astype(str).replace("nan", "")
        display_df[L['col_ts']] = display_df['التاريخ']
        display_df[L['col_user']] = display_df['المستخدم']
        display_df[L['col_cat']] = display_df['النشاط']
        display_df[L['col_wd']] = display_df['اليوم']
        display_df[L['col_time']] = display_df['الساعة']
        
        cols = [L['col_del'], L['col_user'], L['col_ts'], L['col_cat'], L['col_hours'], L['col_notes'], L['col_wd'], L['col_time']]
        display_df = display_df[cols]
        
        edited_display = st.data_editor(
            display_df, column_config={L['col_del']: st.column_config.CheckboxColumn(L['col_del'], default=False)},
            disabled=[col for col in display_df.columns if col != L['col_del']], hide_index=True, use_container_width=True, key="editor_delete"
        )
        
        indices_to_delete = edited_display[edited_display[L['col_del']] == True].index
        if len(indices_to_delete) > 0:
            master_indices = df_db.index[indices_to_delete]
            if st.button(L["del_selected_trigger"], type="primary"):
                confirm_delete_dialog(master_indices, is_all=False)

        st.markdown("---")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_db.drop(columns=['ID'], errors='ignore').to_excel(writer, index=False, sheet_name='Logs')
        st.download_button(label=L["dl_excel"], data=buffer.getvalue(), file_name="registry.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
        
        if st.button(L["wipe_all_trigger"]): confirm_delete_dialog(None, is_all=True)

# ==========================================
# 2. الصفحة الثانية: الإحصاءات والرسوم البيانية
# ==========================================
elif page == L["page_dash"]:
    st.header(L["dash_header"])
    st.subheader(L["filter_sub"])
    time_filter = st.selectbox(L["filter_lbl"], [L["f_all"], L["f_today"], L["f_week"], L["f_month"], L["f_90"], L["f_custom"]])
    
    start_filter_date = None
    end_filter_date = today_date
    
    if time_filter == L["f_today"]: start_filter_date = today_date
    elif time_filter == L["f_week"]: start_filter_date = today_date - timedelta(days=today_date.weekday())
    elif time_filter == L["f_month"]: start_filter_date = datetime.date(today_date.year, today_date.month, 1)
    elif time_filter == L["f_90"]: start_filter_date = today_date - timedelta(days=90)
    elif time_filter == L["f_custom"]:
        c_date1, c_date2 = st.columns(2)
        with c_date1: start_filter_date = st.date_input(L["date_from"], value=today_date - timedelta(days=7))
        with c_date2: end_filter_date = st.date_input(L["date_to"], value=today_date)

    if start_filter_date is not None and not df_db_calc.empty:
        df_filtered = df_db_calc[(df_db_calc["date_only"] >= start_filter_date) & (df_db_calc["date_only"] <= end_filter_date)].copy()
    else:
        df_filtered = df_db_calc.copy()

    current_streak, best_streak = 0, 0
    today_hours, week_hours, month_hours, total_hours, activities_count = 0, 0, 0, 0, 0
    most_activity = "-"

    if not df_db_calc.empty:
        unique_days = sorted(set(df_db_calc["date_only"].dropna()))
        streak = 0
        check_day = today_date
        while check_day in unique_days:
            streak += 1
            check_day -= timedelta(days=1)
        current_streak = streak

        best = 0
        temp = 1
        if len(unique_days) > 0:
            for i in range(1, len(unique_days)):
                if unique_days[i] == unique_days[i-1] + timedelta(days=1): temp += 1
                else:
                    best = max(best, temp)
                    temp = 1
            best = max(best, temp)
        best_streak = best

        today_hours = round(df_db_calc[df_db_calc["date_only"] == today_date]["المدة_بالدقائق"].sum()/60, 1)
        start_week = today_date - timedelta(days=today_date.weekday())
        week_hours = round(df_db_calc[df_db_calc["date_only"] >= start_week]["المدة_بالدقائق"].sum()/60, 1)
        month_hours = round(df_db_calc[(pd.to_datetime(df_db_calc["date_only"]).dt.month == today_date.month) & (pd.to_datetime(df_db_calc["date_only"]).dt.year == today_date.year)]["المدة_بالدقائق"].sum()/60, 1)

    if not df_filtered.empty:
        total_hours = round(df_filtered["المدة_بالدقائق"].sum()/60, 1)
        activities_count = len(df_filtered)
        if not df_filtered["النشاط"].dropna().empty: most_activity = df_filtered.groupby("النشاط")["المدة_بالدقائق"].sum().idxmax()

    st.markdown(f"### {L['filter_sub']}")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric(L["metric_curr_streak"], f"{current_streak} {L['days_unit']}")
    c2.metric(L["metric_max_streak"], f"{best_streak} {L['days_unit']}")
    c3.metric(L["metric_scoped_hrs"], f"{total_hours} {L['hours_unit']}")
    c4.metric(L["metric_entries"], activities_count)
    c5.metric(L["metric_today_vol"], f"{today_hours} {L['hours_unit']}")
    c6.metric(L["metric_dominant"], most_activity)

    st.markdown("---")
    st.subheader(L["radar_sub"])
    goal1, goal2, goal3 = st.columns(3)
    with goal1:
        p_today = min(today_hours / DAILY_GOAL, 1.0) if DAILY_GOAL > 0 else 0
        st.metric(L["r_daily"], f"{today_hours:.1f} / {DAILY_GOAL} {L['hours_unit']}", f"{p_today*100:.0f}% {L['r_comp']}")
        st.progress(p_today)
    with goal2:
        p_week = min(week_hours / WEEKLY_GOAL, 1.0) if WEEKLY_GOAL > 0 else 0
        st.metric(L["r_weekly"], f"{week_hours:.1f} / {WEEKLY_GOAL} {L['hours_unit']}", f"{p_week*100:.0f}% {L['r_comp']}")
        st.progress(p_week)
    with goal3:
        p_month = min(month_hours / MONTHLY_GOAL, 1.0) if MONTHLY_GOAL > 0 else 0
        st.metric(L["r_monthly"], f"{month_hours:.1f} / {MONTHLY_GOAL} {L['hours_unit']}", f"{p_month*100:.0f}% {L['r_comp']}")
        st.progress(p_month)

    st.markdown("---")
    col_graph1, col_graph2 = st.columns([2,1])
    with col_graph1:
        st.subheader(L["grid_sub"])
        all_days = pd.date_range(start=datetime.date(current_year, 1, 1), end=datetime.date(current_year, 12, 31))
        df_year_grid = pd.DataFrame({'parsed_date': all_days})
        df_year_grid['short_date'] = df_year_grid['parsed_date'].dt.strftime('%Y-%m-%d')
        df_year_grid['week_num'] = df_year_grid['parsed_date'].dt.isocalendar().week
        df_year_grid['day_num'] = df_year_grid['parsed_date'].dt.dayofweek
        github_day_order = [6, 0, 1, 2, 3, 4, 5]
        days_names = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']

        if not df_filtered.empty:
            user_summary = df_filtered.groupby('short_date')['المدة_بالدقائق'].sum().reset_index()
            user_summary['Hours'] = user_summary['المدة_بالدقائق'] / 60
            df_year_grid = pd.merge(df_year_grid, user_summary[['short_date', 'Hours']], on='short_date', how='left').fillna(0)
        else: df_year_grid['Hours'] = 0.0

        weeks_indices = sorted(df_year_grid['week_num'].unique())
        z_matrix, text_matrix = [], []
        for d in github_day_order:
            row_z, row_text = [], []
            for w in weeks_indices:
                day_data = df_year_grid[(df_year_grid['week_num'] == w) & (df_year_grid['day_num'] == d)]
                if not day_data.empty:
                    val = day_data['Hours'].values[0]
                    row_z.append(val)
                    row_text.append(f"Date: {day_data['short_date'].values[0]}<br>Volume: {val} Hours")
                else: row_z.append(0); row_text.append("")
            z_matrix.append(row_z); text_matrix.append(row_text)

        fig_heatmap = go.Figure(data=go.Heatmap(z=z_matrix, x=weeks_indices, y=days_names, text=text_matrix, hoverinfo='text', xgap=1, ygap=1, colorscale=[[0.0, '#ebedf0'], [0.01, '#9be9a8'], [0.3, '#40c463'], [0.6, '#30a14e'], [1.0, '#216e39']], showscale=False))
        fig_heatmap.update_layout(height=280, margin=dict(t=10, b=10, l=5, r=5), xaxis=dict(showgrid=False), yaxis=dict(showgrid=False, autorange='reversed'))
        st.plotly_chart(fig_heatmap, use_container_width=True, config={"displayModeBar": False})

    with col_graph2:
        st.subheader(L["pie_sub"])
        if not df_filtered.empty and df_filtered['المدة_بالدقائق'].sum() > 0:
            pie_data = df_filtered.groupby('النشاط')['المدة_بالدقائق'].sum().reset_index()
            fig_pie = px.pie(pie_data, values='المدة_بالدقائق', names='النشاط', hole=0.4)
            fig_pie.update_layout(height=280, margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)
        else: st.info(L["pie_empty"])

# ==========================================
# 3. الصفحة الثالثة: إدارة حسابات المستخدمين (للمدير)
# ==========================================
elif page == L["page_admin"] and st.session_state.user_role == "Admin":
    st.header(L["page_admin"])
    st.subheader(L["create_user_sub"])
    with st.form("create_user_form"):
        new_username = st.text_input(L["username_lbl"]).strip()
        new_password = st.text_input(L["password_lbl"], type="password").strip()
        new_role = st.selectbox(L["role_lbl"], ["User", "Admin"])
        create_submitted = st.form_submit_button(L["create_btn"], use_container_width=True)
        
        if create_submitted:
            users_df = load_users_db()
            if new_username in users_df["Username"].values:
                st.error("Username already exists!")
            elif new_username == "" or new_password == "":
                st.error("Fields cannot be empty!")
            else:
                hashed_pass = make_hashes(new_password)
                sheet_users.append_row([new_username, hashed_pass, new_role])
                st.cache_data.clear()
                st.success(f"Account for '{new_username}' created successfully!")
                time.sleep(1)
                st.rerun()

    st.markdown("---")
    st.subheader("👥 Existing User Accounts")
    current_users = load_users_db()
    st.dataframe(current_users[["Username", "Role"]], use_container_width=True, hide_index=True)
