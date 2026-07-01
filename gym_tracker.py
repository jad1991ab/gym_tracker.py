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

OFFLINE_CACHE_FILE = ".offline_cache.json"

# تهيئة قيم الجلسة الآمنة
if "duration_val" not in st.session_state:
    st.session_state.duration_val = 1.0

def make_hashes(password): 
    return hashlib.sha256(str.encode(password)).hexdigest()

# تعيين صلاحيات جوجل درايف وجوجل شيتس
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_spreadsheet():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet_name = st.secrets["google"]["sheet_name"]
    return client.open(sheet_name)

spreadsheet = get_spreadsheet()
sheet_main = spreadsheet.sheet1

# التحقق من وجود ورقة المستخدمين
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

# دالة مطورة ومحدثة لإصلاح تواريخ وساعات جوجل شيت ومنع التناقض
def fix_google_serial_date(val, is_time_only=False):
    if not val or pd.isna(val):
        return ""
    val_str = str(val).strip()
    
    # إذا كانت القيمة مخزنة مسبقاً كنص يحتوي على تاريخ ووقت معاً (سبب المشكلة الأساسي)
    if " " in val_str and not is_time_only:
        return val_str.split(" ")[0] # خذ التاريخ النقي فقط
        
    clean_numeric_check = val_str.replace('.', '', 1).replace('-', '', 1)
    if clean_numeric_check.isdigit():
        try:
            serial_num = float(val_str)
            base_date = datetime.datetime(1899, 12, 30)
            
            if is_time_only:
                if serial_num < 1:
                    fraction = serial_num
                else:
                    fraction = serial_num - int(serial_num)
                total_seconds = int(round(fraction * 86400))
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                # خذ الجزء الصحيح فقط لاستخراج التاريخ النقي وتفادي الحسابات العشرية للوقت
                days_to_add = int(serial_num)
                converted_dt = base_date + datetime.timedelta(days=days_to_add)
                return converted_dt.strftime('%Y-%m-%d')
        except:
            pass
    return val_str

@st.cache_data(ttl=5)
def load_data():
    try:
        records = sheet_main.get_all_records(value_render_option='UNFORMATTED_VALUE')
        if len(records) == 0: 
            return pd.DataFrame(columns=COLUMNS)
        
        df = pd.DataFrame(records)
        df.dropna(how='all', inplace=True)
        
        for col in COLUMNS:
            if col not in df.columns: 
                df[col] = ""
        
        # تطبيق المعالجة المنفصلة والدقيقة لمنع تكرار تداخل الساعات مع التاريخ
        if 'التاريخ' in df.columns:
            df['التاريخ'] = df['التاريخ'].apply(lambda x: fix_google_serial_date(x, is_time_only=False))
        if 'الساعة' in df.columns:
            df['الساعة'] = df['الساعة'].apply(lambda x: fix_google_serial_date(x, is_time_only=True))
                
        # فرز السجلات برمجياً من الأحدث للأقدم لضمان اتساق الواجهات
        if 'التاريخ' in df.columns and 'الساعة' in df.columns:
            df['datetime_helper'] = pd.to_datetime(df['التاريخ'] + ' ' + df['الساعة'], errors='coerce')
            df = df.sort_values(by='datetime_helper', ascending=False).drop(columns=['datetime_helper'])
            
        return df[COLUMNS].reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame(columns=COLUMNS)

# دالة حفظ البيانات مع نظام الكاش الاحتياطي
def save_data(df):
    try:
        clean_df = df[COLUMNS].copy()
        try:
            sheet_main.clear()
        except:
            pass
            
        req_rows = max(len(clean_df) + 50, 100)
        req_cols = len(COLUMNS) + 5
        if sheet_main.row_count < req_rows or sheet_main.col_count < req_cols:
            sheet_main.resize(rows=req_rows, cols=req_cols)
            
        set_with_dataframe(sheet_main, clean_df, include_index=False, include_column_header=True, resize=True)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"⚠️ فشل الاتصال بجوجل شيتس. جاري تفعيل الحفظ الاحتياطي المحلي لتجنب فقدان البيانات.")
        return False

# أدوات التخزين المؤقت المحلي
def cache_offline_activity(row_dict):
    cached_data = []
    if os.path.exists(OFFLINE_CACHE_FILE):
        try:
            with open(OFFLINE_CACHE_FILE, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
        except: pass
    cached_data.append(row_dict)
    with open(OFFLINE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cached_data, f, ensure_ascii=False, indent=4)

def sync_offline_cache():
    if os.path.exists(OFFLINE_CACHE_FILE):
        try:
            with open(OFFLINE_CACHE_FILE, "r", encoding="utf-8") as f:
                cached_rows = json.load(f)
            if cached_rows:
                st.info(f"🔄 تم اكتشاف {len(cached_rows)} أنشطة محفوظة محلياً أثناء انقطاع الإنترنت، جاري المزامنة...")
                current_df = load_data()
                new_df = pd.concat([current_df, pd.DataFrame(cached_rows)], ignore_index=True)
                if save_data(new_df):
                    os.remove(OFFLINE_CACHE_FILE)
                    st.success("✅ تمت مزامنة كافة الأنشطة المحلية بنجاح!")
                    time.sleep(1)
                    st.rerun()
        except Exception as e:
            pass

# تشغيل الفحص الآلي للمزامنة فور تحميل التطبيق
sync_offline_cache()

# ==========================================
# 🔐 نظام إدارة الترجمة واللغات
# ==========================================
LEXICON = {
    "AR": {
        "nav_title": "🧭 قائمة التنقل", "page_log": "📥 تسجيل نشاط جديد", "page_dash": "📊 لوحة التحكم والإحصاءات", "page_admin": "👑 إدارة المستخدمين وسجلات الإدارة",
        "goals_setup": "🎯 إدارة الأهداف الذكية", "g_daily": "الهدف اليومي (ساعات):", "g_weekly": "الهدف الأسبوعي (ساعات):", "g_monthly": "الهدف الشهري (ساعات):",
        "duration_lbl": "مدة النشاط (بالساعات)", 
        "del_dialog_title": "⚠️ تأكيد عملية الحذف", "del_all_warn": "🚨 هل أنت متأكد تماماً؟ لا يمكن التراجع عن هذا الإجراء!", "del_all_btn": "❌ نعم، امسح السجل بالكامل",
        "del_sel_warn": "هل أنت متأكد أنك تريد حذف الأنشطة المحددة؟ العدد:", "del_sel_btn": "🗑️ تأكيد الحذف النهائي", "log_header": "🟢 تسجيل ومتابعة الأنشطة",
        "form_sub": "📥 نموذج البيانات والملء الذكي",
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
        "grid_sub": "🧱 مخطط الالتزام السنوي المفلتر (GitHub Grid)", "pie_sub": "🍕 التوزيع النظري للأنشطة", "pie_empty": "لا توجد أنشطة مسجلة في هذا النطاق الزمني لعرض توزيعها.",
        "gym_def": "الدراسة 📚", "study_def": "النادي 🏋️‍♂️", "work_def": "العمل 💼", "custom_err": "يرجى كتابة اسم النشاط المخصص أولاً!",
        "login_title": "🔒 نظام تسجيل الدخول الموحد", "username_lbl": "اسم المستخدم", "password_lbl": "كلمة المرور", "login_btn": "🚪 تسجيل الدخول", "logout_btn": "🚪 تسجيل الخروج", "invalid_login": "❌ اسم المستخدم أو كلمة المرور غير صحيحة",
        "admin_scope": "🔍 استعراض بيانات مستخدم محدد (نطاق المدير):", "all_users_opt": "👥 كل المستخدمين معاً", "create_user_sub": "➕ إنشاء حساب مستخدم جديد", "new_user_lbl": "اسم المستخدم الجديد", "new_pass_lbl": "كلمة المرور الجديدة", "role_lbl": "الصلاحية", "create_btn": "💼 إنشاء الحساب وحفظه برمز مشفر",
        "gam_level": "المستوى", "gam_xp": "نقاط الخبرة", "gam_leaderboard": "🏆 لوحة الصدارة (هذا الأسبوع)", "gam_rank": "الترتيب", "gam_badges": "🏅 الشارات الرقمية والميداليات"
    },
    "EN": {
        "nav_title": "🧭 Navigation", "page_log": "📥 Log New Activity", "page_dash": "📊 Analytics Dashboard", "page_admin": "👑 Users & Identity Administration",
        "goals_setup": "🎯 Smart Goals Setup", "g_daily": "Daily Goal (Hours):", "g_weekly": "Weekly Goal (Hours):", "g_monthly": "Monthly Goal (Hours):",
        "duration_lbl": "Activity Duration (Hours)",
        "del_dialog_title": "⚠️ Confirm Deletion", "del_all_warn": "🚨 Are you absolutely sure? This action cannot be undone!", "del_all_btn": "❌ Yes, wipe all data",
        "del_sel_warn": "Are you sure you want to permanently delete the selected activities? Count:", "del_sel_btn": "🗑️ Confirm Permanent Delete", "log_header": "🟢 Track & Log Activities",
        "form_sub": "📥 Input Form & Smart Prefills",
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
        "grid_sub": "🧱 Annual Consistency Grid", "pie_sub": "🍕 Allocation Distribution", "pie_empty": "No distribution entries found inside current evaluation range.",
        "gym_def": "Studying 📚", "study_def": "Gym 🏋️‍♂️", "work_def": "Work 💼", "custom_err": "Please enter a custom activity label first!",
        "login_title": "🔒 Secure Unified Login System", "username_lbl": "Username", "password_lbl": "Password", "login_btn": "🚪 Sign In", "logout_btn": "🚪 Log Out", "invalid_login": "❌ Invalid Username or Password",
        "admin_scope": "🔍 Review specific user logs (Admin Scope):", "all_users_opt": "👥 All Users Combined", "create_user_sub": "➕ Create New User Account", "new_user_lbl": "New Username", "new_pass_lbl": "New Password", "role_lbl": "Role", "create_btn": "💼 Register Encrypted User Account",
        "gam_level": "Level", "gam_xp": "Experience Points", "gam_leaderboard": "🏆 Leaderboard (This Week)", "gam_rank": "Rank", "gam_badges": "🏅 Digital Badges & Medals"
    }
}

st.sidebar.title("🌐 Language / اللغة")
lang = st.sidebar.selectbox("Choose Application Language:", ["العربية", "English"], index=0)
L = LEXICON["AR"] if lang == "العربية" else LEXICON["EN"]

# نظام الجلسة وتأمين الدخول
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "username" not in st.session_state: st.session_state.username = ""
if "user_role" not in st.session_state: st.session_state.user_role = "User"

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

df_db_all = load_data()

# حساب بيانات الـ Gamification للمستخدم الحالي ديناميكياً
user_all_logs = df_db_all[df_db_all["المستخدم"] == st.session_state.username].copy() if not df_db_all.empty else pd.DataFrame()
user_total_hours = 0.0
if not user_all_logs.empty:
    user_all_logs['المدة_بالدقائق'] = pd.to_numeric(user_all_logs['المدة_بالدقائق'], errors='coerce').fillna(0)
    user_total_hours = float(user_all_logs['المدة_بالدقائق'].sum() / 60)

# معادلة حساب الـ XP والمستويات
total_xp = int(user_total_hours * 100)
current_level = 1
xp_needed = 500
temp_xp = total_xp

while temp_xp >= xp_needed:
    temp_xp -= xp_needed
    current_level += 1
    xp_needed = current_level * 500

progress_to_next_level = float(temp_xp / xp_needed) if xp_needed > 0 else 0.0

# عرض معلومات المستوى ونقاط الخبرة في الشريط الجانبي
st.sidebar.markdown(f"#### 👤 {st.session_state.username} ({st.session_state.user_role})")
st.sidebar.markdown(f"**⭐ {L['gam_level']} {current_level}** ({total_xp} XP)")
st.sidebar.progress(progress_to_next_level)

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

def render_duration_section(col_context, key_prefix="default"):
    with col_context:
        duration_input = st.number_input(
            L["duration_lbl"], 
            min_value=0.1, 
            max_value=24.0, 
            step=0.1, 
            value=float(st.session_state.duration_val),
            key=f"num_in_{key_prefix}"
        )
        st.session_state.duration_val = duration_input

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
            updated_df = df_db_all.drop(indices).reset_index(drop=True)
            if save_data(updated_df):
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
# 1. شاشة تسجيل الأنشطة
# ==========================================
if page == L["page_log"]:
    st.header(L["log_header"])
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
        render_duration_section(c2, key_prefix="auto_layout")
    else:
        c1, c2, c3 = st.columns([2, 1.5, 1.5])
        with c1:
            selected_activity = st.selectbox(L["act_cat"], activities_list, key="act_manual")
            if selected_activity == L["act_custom_opt"]: custom_activity = st.text_input(L["act_custom_lbl"], key="cust_manual")
            activity_notes = st.text_input(L["notes_lbl"], placeholder=L["notes_ph_manual"], key="notes_manual")
        render_duration_section(c1, key_prefix="manual_layout")
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
            'التاريخ': combined_datetime.strftime('%Y-%m-%d'), # تعديل حاسم: حفظ التاريخ الصافي فقط لمنع التناقض
            'السنة': int(combined_datetime.year),
            'الشهر': str(months_list[combined_datetime.month - 1]),
            'الأسبوع': int(combined_datetime.isocalendar().week),
            'اليوم': str(combined_datetime.strftime('%A')),
            'الساعة': str(combined_datetime.strftime('%H:%M:%S')),
            'النشاط': str(final_activity),
            'المدة_بالدقائق': duration_minutes,
            'الملاحظات': str(activity_notes.strip())
        }
        
        updated_df_all = pd.concat([df_db_all, pd.DataFrame([new_row])], ignore_index=True)
        
        success = save_data(updated_df_all)
        if not success:
            cache_offline_activity(new_row)
            st.toast("⚠️ تم حفظ النشاط محلياً في الكاش المؤقت لعدم وجود إنترنت!", icon="💾")
        else:
            st.toast(L["success_toast"].format(final_activity), icon="🔥")
            
        time.sleep(1)
        st.rerun()

    if not df_db.empty:
        st.markdown("---")
        st.subheader(L["history_sub"])
        display_df = df_db.copy()
        
        for c in COLUMNS:
            if c not in display_df.columns: display_df[c] = ""
            
        display_df[L['col_del']] = False
        display_df['المدة_بالدقائق'] = pd.to_numeric(display_df['المدة_بالدقائق'], errors='coerce').fillna(0)
        display_df[L['col_hours']] = round(display_df['المدة_بالدقائق'] / 60, 2)
        
        display_df[L['col_notes']] = display_df['الملاحظات'].astype(str).replace(["nan", "None", ""], "-")
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
# 2. شاشة الإحصاءات والرسوم البيانية
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
    
    # قسم الألعاب والتشجيع المطور (Gamification)
    st.subheader(L["gam_badges"])
    badge_col1, badge_col2 = st.columns([1, 1])
    
    with badge_col1:
        st.markdown(f"#### 🏆 {L['gam_level']} {current_level} (إجمالي: {total_xp} XP)")
        badges_earned = []
        if user_total_hours >= 100:
            badges_earned.append("🎖️ **شارة تخطي 100 ساعة عمل:** دليل على التفاني والالتزام العميق الساحق.")
        if best_streak >= 7:
            badges_earned.append("🔥 **شارة التزام 7 أيام متتالية:** ثبات أسطوري متواصل لأسبوع كامل.")
        if user_total_hours >= 10:
            badges_earned.append("🌱 **شارة الانطلاقة الأولى:** إكمال أول 10 ساعات عمل داخل المنصة بنجاح.")
            
        if badges_earned:
            for b in badges_earned:
                st.success(b)
        else:
            st.info("تابع التسجيل بانتظام لفتح الشارات والميداليات الرقمية قريباً! 🎯")

    with badge_col2:
        st.markdown(f"#### {L['gam_leaderboard']}")
        if not df_db_all.empty:
            df_lb = df_db_all.copy()
            df_lb['parsed_date'] = pd.to_datetime(df_lb['التاريخ'], errors='coerce')
            start_current_week = today_date - timedelta(days=today_date.weekday())
            
            df_lb_week = df_lb[df_lb['parsed_date'].dt.date >= start_current_week].copy()
            if not df_lb_week.empty:
                df_lb_week['المدة_بالدقائق'] = pd.to_numeric(df_lb_week['المدة_بالدقائق'], errors='coerce').fillna(0)
                leaderboard_df = df_lb_week.groupby('المستخدم')['المدة_بالدقائق'].sum().reset_index()
                leaderboard_df['ساعات الالتزام'] = round(leaderboard_df['المدة_بالدقائق'] / 60, 1)
                leaderboard_df = leaderboard_df.sort_values(by='ساعات الالتزام', ascending=False).reset_index(drop=True)
                leaderboard_df.index += 1
                leaderboard_df = leaderboard_df.rename_axis(L["gam_rank"]).reset_index()
                
                st.dataframe(leaderboard_df[[L["gam_rank"], 'المستخدم', 'ساعات الالتزام']], use_container_width=True, hide_index=True)
            else:
                st.write("لا توجد سجلات كافية لبناء لوحة الصدارة لهذا الأسبوع حتى الآن.")
        else:
            st.write("قاعدة البيانات فارغة حالياً.")

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
# 3. شاشة لوحة تحكم الإدارة (المدير الحصري)
# ==========================================
elif page == L["page_admin"] and st.session_state.user_role == "Admin":
    st.header("👑 لوحة تحكم وصلاحيات الإدارة الفائقة")
    
    admin_tab1, admin_tab2, admin_tab3 = st.tabs(["👥 الحسابات والتعيين", "🔒 استعادة كلمات المرور", "📋 سجل الأنشطة العام"])
    
    with admin_tab1:
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
        st.subheader("👥 الحسابات المسجلة حالياً")
        current_users = load_users_db()
        st.dataframe(current_users[["Username", "Role"]], use_container_width=True, hide_index=True)

    with admin_tab2:
        st.subheader("🔑 أداة استعادة وإعادة تعيين كلمة المرور")
        st.info("تتيح هذه الأداة للمسؤول تصفير كلمة مرور أي مستخدم فوراً وتعيين كلمة مرور مؤقتة جديدة له.")
        
        users_df = load_users_db()
        if not users_df.empty:
            reset_user_list = [u for u in users_df["Username"].unique() if u != st.session_state.username]
            
            if reset_user_list:
                selected_reset_user = st.selectbox("اختر الحساب المراد تصفير كلمته:", reset_user_list)
                new_temp_password = st.text_input("اكتب كلمة المرور الجديدة للمستخدم:", type="password", key="admin_pwd_reset_field")
                
                if st.button("🔄 تأكيد تعيين كلمة المرور الجديدة", type="primary", use_container_width=True):
                    if new_temp_password.strip() == "":
                        st.error("لا يمكن ترك حقل كلمة المرور فارغاً!")
                    else:
                        try:
                            all_user_records = sheet_users.get_all_records()
                            row_index_to_update = None
                            
                            for idx, record in enumerate(all_user_records):
                                if record["Username"] == selected_reset_user:
                                    row_index_to_update = idx + 2
                                    break
                            
                            if row_index_to_update:
                                new_hashed_pwd = make_hashes(new_temp_password.strip())
                                sheet_users.update_cell(row_index_to_update, 2, new_hashed_pwd)
                                st.cache_data.clear()
                                st.success(f"✅ تم تحديث كلمة مرور الحساب '{selected_reset_user}' بنجاح!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("تعذر العثور على سطر المستخدم في قاعدة البيانات.")
                        except Exception as ex:
                            st.error(f"حدث خطأ أثناء الاتصال بقاعدة البيانات للتحديث: {ex}")
            else:
                st.write("لا يوجد مستخدمون آخرون مسجلون لتعديل بياناتهم.")
        else:
            st.write("قاعدة بيانات المستخدمين فارغة.")

    with admin_tab3:
        st.subheader("📋 سجل مراقبة الأنشطة العام (Admin Registry Review)")
        st.caption("عرض شامل وتفصيلي لجميع الحسابات والعمليات المدخلة على قاعدة البيانات.")
        if not df_db_all.empty:
            st.dataframe(df_db_all.drop(columns=['ID'], errors='ignore'), use_container_width=True)
        else:
            st.info("لا توجد سجلات أنشطة لعرضها حالياً.")
