import streamlit as st
import pandas as pd
import gspread
import datetime
import io
import time
import json
import os
import plotly.graph_objects as go
import plotly.express as px
import streamlit.components.v1 as components
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe
from datetime import timedelta

# إعدادات الصفحة الرسمية والتصميم
st.set_page_config(page_title="متابع الأنشطة الاحترافي", layout="wide", page_icon="🟢")

# ملف محلي لتخزين حالة العداد بشكل دائم ومقاوم للإغلاق والتحديث
STATE_FILE = ".stopwatch_state.json"

def load_stopwatch_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"running": False, "start_time": None, "elapsed": 0, "mode": "free", "duration_mins": 25}

def save_stopwatch_state(running, start_time, elapsed, mode="free", duration_mins=25):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({
                "running": running,
                "start_time": start_time,
                "elapsed": elapsed,
                "mode": mode,
                "duration_mins": duration_mins
            }, f)
    except:
        pass

# تحميل الحالة المحفوظة سابقاً
saved_state = load_stopwatch_state()

# ==========================================
# ⚙️ تهيئة الـ Session State
# ==========================================
if "duration_input" not in st.session_state:
    st.session_state.duration_input = 1.0

if "sw_running" not in st.session_state:
    st.session_state.sw_running = saved_state["running"]
    st.session_state.sw_start = saved_state["start_time"]
    st.session_state.sw_elapsed = saved_state["elapsed"]
    st.session_state.sw_mode = saved_state["mode"]
    st.session_state.sw_pomo_mins = saved_state["duration_mins"]

def set_duration(amount):
    st.session_state.duration_input = float(amount)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_sheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    client = gspread.authorize(creds)
    sheet_name = st.secrets["google"]["sheet_name"]
    spreadsheet = client.open(sheet_name)
    return spreadsheet.sheet1

sheet = get_sheet()

COLUMNS = ['ID', 'التاريخ', 'السنة', 'الشهر', 'الأسبوع', 'اليوم', 'الساعة', 'النشاط', 'المدة_بالدقائق', 'الملاحظات']

try:
    current_cols_count = sheet.col_count
    if current_cols_count < len(COLUMNS):
        sheet.add_cols(len(COLUMNS) - current_cols_count)
        
    first_row = sheet.row_values(1)
    if not first_row:
        sheet.append_row(COLUMNS)
    else:
        if 'الملاحظات' not in first_row:
            sheet.update_cell(1, len(COLUMNS), 'الملاحظات')
except Exception as e:
    st.error(f"تنبيه قاعدة البيانات: {e}")

@st.cache_data(ttl=600)
def load_data():
    try:
        records = sheet.get_all_records()
        if len(records) == 0:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.DataFrame(records)
        if 'المدة_بالدقائق' not in df.columns:
            df['المدة_بالدقائق'] = 60
        if 'الملاحظات' not in df.columns:
            df['الملاحظات'] = ""
        existing_cols = [c for c in COLUMNS if c in df.columns]
        return df[existing_cols]
    except Exception as e:
        st.error(f"خطأ أثناء قراءة البيانات: {e}")
        return pd.DataFrame(columns=COLUMNS)

def save_data(df):
    try:
        clean_df = df[[c for c in COLUMNS if c in df.columns]].copy()
        sheet.clear()
        if sheet.row_count < len(clean_df) + 10:
            sheet.add_rows(len(clean_df) + 20)
        set_with_dataframe(sheet, clean_df, include_index=False, include_column_header=True, resize=True)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"حدث خطأ أثناء حفظ البيانات: {e}")

if 'db' not in st.session_state:
    st.session_state.db = load_data()

df_db = st.session_state.db

# تجهيز متغيرات الحسابات والتواريخ
now = datetime.datetime.now()
today_date = now.date()
current_year = now.year

if not df_db.empty:
    df_db_calc = df_db.copy()
    df_db_calc['تاريخ_صحيح'] = pd.to_datetime(df_db_calc['التاريخ'], errors='coerce')
    df_db_calc['تاريخ_يومي_مختصر'] = df_db_calc['تاريخ_صحيح'].dt.strftime('%Y-%m-%d')
    df_db_calc['المدة_بالدقائق'] = pd.to_numeric(df_db_calc['المدة_بالدقائق'], errors='coerce').fillna(0)
    df_db_calc["date_only"] = df_db_calc["تاريخ_صحيح"].dt.date
else:
    df_db_calc = df_db.copy()
    df_db_calc['تاريخ_يومي_مختصر'] = pd.Series(dtype='str')
    df_db_calc["date_only"] = pd.Series(dtype='object')

# ==========================================
# 🧭 نظام القوائم الجانبية المتقدمة (الأهداف الذكية)
# ==========================================
st.sidebar.title("🧭 قائمة التنقل")
page = st.sidebar.radio("اختر الصفحة:", ["📥 تسجيل نشاط جديد", "📊 لوحة التحكم والإحصاءات"])

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 إدارة الأهداف الذكية")
DAILY_GOAL = st.sidebar.number_input("الهدف اليومي (ساعات):", min_value=0.5, max_value=24.0, value=2.0, step=0.5)
WEEKLY_GOAL = st.sidebar.number_input("الهدف الأسبوعي (ساعات):", min_value=1.0, max_value=168.0, value=14.0, step=1.0)
MONTHLY_GOAL = st.sidebar.number_input("الهدف الشهري (ساعات):", min_value=5.0, max_value=744.0, value=60.0, step=5.0)

def render_duration_section(col_context):
    with col_context:
        st.number_input("مدة النشاط (بالساعات)", min_value=0.1, max_value=24.0, step=0.1, key="duration_input")
        st.caption("⏱️ أزرار تعيين الوقت السريعة:")
        b1, b2, b3, b4 = st.columns(4)
        b1.button("⏱️ 30 د", key="b30", on_click=set_duration, args=(0.5,), use_container_width=True)
        b2.button("⏱️ 1 س", key="b1h", on_click=set_duration, args=(1.0,), use_container_width=True)
        b3.button("⏱️ 1.5 س", key="b15", on_click=set_duration, args=(1.5,), use_container_width=True)
        b4.button("⏱️ 2 س", key="b2h", on_click=set_duration, args=(2.0,), use_container_width=True)

# ==========================================
# 1. صفحة: تسجيل نشاط جديد
# ==========================================
if page == "📥 تسجيل نشاط جديد":
    st.header("🟢 تسجيل ومتابعة الأنشطة")
    
    st.markdown("### ⏱️ نظام التركيز المطور (بومودورو وساعة الإيقاف الذكية)")
    
    if not st.session_state.sw_running:
        mode_choice = st.radio("اختر نظام التركيز:", ["⏱️ عداد حر تصاعدي", "🎯 مؤقت بومودورو (Pomodoro)"], horizontal=True)
        st.session_state.sw_mode = "free" if "عداد حر" in mode_choice else "pomodoro"
        if st.session_state.sw_mode == "pomodoro":
            st.session_state.sw_pomo_mins = st.selectbox("اختر مدة جلسة التركيز (بالدقائق):", [25, 50, 15, 5], index=0)
    else:
        current_mode_text = "⏱️ عداد حر تصاعدي" if st.session_state.sw_mode == "free" else f"🎯 مؤقت بومودورو ({st.session_state.sw_pomo_mins} دقيقة)"
        st.info(f"العداد يعمل حالياً بنظام: **{current_mode_text}** (محمي ضد إغلاق الصفحة 🔒)")

    stop_col1, stop_col2 = st.columns([2, 1])
    
    with stop_col1:
        if not st.session_state.sw_running:
            if st.button("▶️ ابدأ التركيز الآن", use_container_width=True, type="primary"):
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
                    st.session_state.duration_input = round(st.session_state.sw_pomo_mins / 60, 2)
                    save_stopwatch_state(False, None, 0, st.session_state.sw_mode, st.session_state.sw_pomo_mins)
                    st.balloons()
                    st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg")
                    st.success("🎉 انتهت جلسة البومودورو بنجاح! تم تعبئة المدة بالأسفل تلقائياً.")
                
            if st.session_state.sw_running:
                if st.button("⏸️ إنهاء الجلسة الحالية وتعبئة الوقت المكتسب", use_container_width=True):
                    st.session_state.sw_running = False
                    st.session_state.sw_elapsed = current_elapsed
                    calc_hours = round(current_elapsed / 3600, 2)
                    st.session_state.duration_input = max(calc_hours, 0.1)
                    save_stopwatch_state(False, None, st.session_state.sw_elapsed, st.session_state.sw_mode, st.session_state.sw_pomo_mins)
                    st.toast(f"📥 تم تحديث حقل المدة بـ {st.session_state.duration_input} ساعة!", icon="⏱️")
                    st.rerun()
                
    with stop_col2:
        if st.session_state.sw_running:
            current_elapsed = time.time() - st.session_state.sw_start
            if st.session_state.sw_mode == "free":
                mins, secs = divmod(int(current_elapsed), 60)
                hrs, mins = divmod(mins, 60)
                st.metric("⏳ العداد المستمر يعمل", f"{hrs:02d}:{mins:02d}:{secs:02d}")
            else:
                target_seconds = st.session_state.sw_pomo_mins * 60
                remaining_seconds = max(int(target_seconds - current_elapsed), 0)
                rem_mins, rem_secs = divmod(remaining_seconds, 60)
                st.metric("🎯 متبقي على النهاية", f"{rem_mins:02d}:{rem_secs:02d}")
            time.sleep(1)
            st.rerun()
        else:
            if st.session_state.sw_elapsed > 0:
                mins, secs = divmod(int(st.session_state.sw_elapsed), 60)
                hrs, mins = divmod(mins, 60)
                st.metric("⏱️ الوقت المسجل الجاهز", f"{hrs:02d}:{mins:02d}:{secs:02d}")
                if st.button("🔄 تصفير وإعادة تعيين"):
                    st.session_state.sw_elapsed = 0
                    st.session_state.duration_input = 1.0
                    save_stopwatch_state(False, None, 0, st.session_state.sw_mode, st.session_state.sw_pomo_mins)
                    st.rerun()

    st.markdown("---")
    st.subheader("📥 نموذج البيانات والملء الذكي")
    auto_time = st.toggle("التسجيل التلقائي بالوقت والتاريخ الحالي فوراً ⚡", value=True)

    default_activities = ["النادي 🏋️‍♂️", "الدراسة 📚", "العمل 💼"]
    if not df_db.empty:
        existing_activities = df_db['النشاط'].dropna().unique().tolist()
        activities_list = list(set(default_activities + existing_activities))
    else:
        activities_list = default_activities

    if "➕ إضافة نشاط مخصص..." not in activities_list:
        activities_list.append("➕ إضافة نشاط مخصص...")
    months_list = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

    target_date = today_date
    chosen_time_str = now.strftime('%H:%M')

    if auto_time:
        c1, c2 = st.columns(2)
        with c1:
            selected_activity = st.selectbox("النشاط", activities_list, key="act_auto")
            if selected_activity == "➕ إضافة نشاط مخصص...":
                custom_activity = st.text_input("اكتب اسم النشاط الجديد هنا:", key="cust_auto")
            activity_notes = st.text_input("✍️ ملاحظات وتعليقات على النشاط (اختياري):", placeholder="مثال: تمرين أكتاف، بومودورو برمجة التطبيق", key="notes_auto")
        render_duration_section(c2)
    else:
        c1, c2, c3 = st.columns([2, 1.5, 1.5])
        with c1:
            selected_activity = st.selectbox("النشاط", activities_list, key="act_manual")
            if selected_activity == "➕ إضافة نشاط مخصص...":
                custom_activity = st.text_input("اكتب اسم النشاط الجديد هنا:", key="cust_manual")
            activity_notes = st.text_input("✍️ ملاحظات وتعليقات على النشاط (اختياري):", placeholder="مثال: مراجعة كاملة للملفات القديمة", key="notes_manual")
        render_duration_section(c1)
        with c2:
            target_date = st.date_input("اختر التاريخ من التقويم 📅", value=today_date)
        with c3:
            clock_html = f"""
            <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; font-family:sans-serif; width: 100%;">
                <label style='font-size:14px; font-weight:bold; color:#216e39; margin-bottom:8px; text-align:center;'>اضبط وقت النشاط ⌚</label>
                <input type="time" id="analog_picker" value="{chosen_time_str}" 
                       style="font-size: 20px; padding: 8px; border-radius: 8px; border: 2px solid #40c463; text-align: center; width: 170px; font-weight:bold; color:#216e39; background-color:#fff;">
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

    if st.button("➕ تسجيل النشاط وحفظه تلقائياً", use_container_width=True, type="primary"):
        if selected_activity == "➕ إضافة نشاط مخصص...":
            if 'custom_activity' in locals() and custom_activity.strip() != "":
                final_activity = custom_activity.strip()
            else:
                st.error("يرجى كتابة اسم النشاط المخصص أولاً!")
                st.stop()
        else:
            final_activity = selected_activity

        if auto_time: target_time = now.time()
        else:
            try:
                t_parts = chosen_time_str.split(":")
                target_time = datetime.time(int(t_parts[0]), int(t_parts[1]))
            except: target_time = now.time()

        combined_datetime = datetime.datetime.combine(target_date, target_time)
        duration_minutes = int(st.session_state.duration_input * 60)
        
        new_row = {
            'ID': int(datetime.datetime.now().timestamp() * 1000),
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
        
        df_db = pd.concat([df_db, pd.DataFrame([new_row])], ignore_index=True)
        save_data(df_db)
        st.session_state.db = df_db
        st.toast(f"✅ تم تسجيل نشاط ({final_activity}) بنجاح!", icon="🔥")
        st.rerun()

    if not df_db.empty:
        st.markdown("---")
        st.subheader("📋 سجل التحكم بالبيانات وحذف الأسطر")
        display_df = df_db.copy()
        display_df['حذف؟'] = False
        display_df['المدة (ساعات)'] = round(display_df['المدة_بالدقائق'] / 60, 2)
        display_df['الملاحظات'] = display_df['الملاحظات'].fillna("")
        
        cols = ['حذف؟', 'التاريخ', 'النشاط', 'المدة (ساعات)', 'الملاحظات', 'اليوم', 'الساعة']
        display_df = display_df[[c for c in cols if c in display_df.columns]]
        
        edited_display = st.data_editor(
            display_df, column_config={"حذف؟": st.column_config.CheckboxColumn("إجراء الحذف", default=False)},
            disabled=[col for col in display_df.columns if col != 'حذف؟'], hide_index=True, use_container_width=True, key="data_editor_delete"
        )
        
        indices_to_delete = edited_display[edited_display['حذف؟'] == True].index
        if len(indices_to_delete) > 0:
            if st.button("🗑️ تأكيد حذف الأنشطة المحددة", type="primary"):
                df_db = df_db.drop(indices_to_delete).reset_index(drop=True)
                save_data(df_db)
                st.session_state.db = df_db
                st.toast("تم حذف الأنشطة المحددة بنجاح!", icon="🗑️")
                st.rerun()

        st.markdown("---")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            clean_excel_df = df_db[[c for c in COLUMNS if c in df_db.columns]].copy()
            clean_excel_df.drop(columns=['ID'], errors='ignore').to_excel(writer, index=False, sheet_name='الأنشطة اليومية')
            writer.sheets['الأنشطة اليومية'].views.sheetView[0].showGridLines = True
            writer.sheets['الأنشطة اليومية'].sheet_view.rightToLeft = True 

        st.download_button(label="📥 تحميل سجل تمارينك كملف Excel النظيف", data=buffer.getvalue(), file_name="my_gym_activities.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
        
        st.markdown("---")
        if st.button("🚨 مسح السجل بالكامل والبدء من جديد"):
            sheet.clear()
            sheet.append_row(COLUMNS[:9])
            st.cache_data.clear()
            st.session_state.db = pd.DataFrame(columns=COLUMNS)
            st.success("تم تصفير قاعدة البيانات بنجاح!")
            st.rerun()

# ==========================================
# 2. صفحة: لوحة التحكم والإحصاءات
# ==========================================
elif page == "📊 لوحة التحكم والإحصاءات":
    st.header("📊 لوحة التحكم والأداء العام")
    
    # 🔍 ✨ [إضافة ميزة الفلترة المتقدمة للنطاقات الزمنية]
    st.subheader("🔍 فلترة التحليلات حسب النطاق الزمني")
    time_filter = st.selectbox(
        "اختر الفترة الزمنية لتحديث كافة التحليلات والرسومات:",
        ["🔄 السجل بالكامل (كل البيانات)", "📅 اليوم", "📆 هذا الأسبوع", "🗓️ هذا الشهر", "🚀 آخر 90 يوماً", "✏️ نطاق مخصص..."]
    )
    
    # تحديد تواريخ البداية والنهاية بناء على الفلتر لتصفية قاعدة البيانات
    start_filter_date = None
    end_filter_date = today_date
    
    if time_filter == "📅 اليوم":
        start_filter_date = today_date
    elif time_filter == "📆 هذا الأسبوع":
        start_filter_date = today_date - timedelta(days=today_date.weekday())
    elif time_filter == "🗓️ هذا الشهر":
        start_filter_date = datetime.date(today_date.year, today_date.month, 1)
    elif time_filter == "🚀 آخر 90 يوماً":
        start_filter_date = today_date - timedelta(days=90)
    elif time_filter == "✏️ نطاق مخصص...":
        c_date1, c_date2 = st.columns(2)
        with c_date1:
            start_filter_date = st.date_input("من تاريخ:", value=today_date - timedelta(days=7))
        with c_date2:
            end_filter_date = st.date_input("إلى تاريخ:", value=today_date)

    # تطبيق الفلترة على نسخة الحسابات
    if start_filter_date is not None and not df_db_calc.empty:
        df_filtered = df_db_calc[(df_db_calc["date_only"] >= start_filter_date) & (df_db_calc["date_only"] <= end_filter_date)].copy()
    else:
        df_filtered = df_db_calc.copy()

    # الحسابات الأساسية والإحصاءات الحيوية
    current_streak, best_streak = 0, 0
    today_hours, week_hours, month_hours, total_hours, activities_count = 0, 0, 0, 0, 0
    most_activity = "-"

    # حساب الالتزام والسلاسل المتتالية (Streak) من كامل قاعدة البيانات لضمان دقتها دائماً
    if not df_db_calc.empty:
        unique_days = sorted(set(df_db_calc["date_only"].dropna()))
        
        # 1. حساب السلسلة الحالية
        streak = 0
        check_day = today_date
        while check_day in unique_days:
            streak += 1
            check_day -= timedelta(days=1)
        current_streak = streak

        # 2. ✨ [إضافة ميزة مؤشر أفضل وأطول سلسلة التزام متتالية - Longest Streak]
        best = 0
        temp = 1
        if len(unique_days) > 0:
            for i in range(1, len(unique_days)):
                if unique_days[i] == unique_days[i-1] + timedelta(days=1):
                    temp += 1
                else:
                    best = max(best, temp)
                    temp = 1
            best = max(best, temp)
        best_streak = best

        # حساب الساعات الفعلية لمقارنتها بالأهداف
        today_hours = round(df_db_calc[df_db_calc["date_only"] == today_date]["المدة_بالدقائق"].sum()/60, 1)
        start_week = today_date - timedelta(days=today_date.weekday())
        week_hours = round(df_db_calc[df_db_calc["date_only"] >= start_week]["المدة_بالدقائق"].sum()/60, 1)
        month_hours = round(df_db_calc[(pd.to_datetime(df_db_calc["date_only"]).dt.month == today_date.month) & (pd.to_datetime(df_db_calc["date_only"]).dt.year == today_date.year)]["المدة_بالدقائق"].sum()/60, 1)

    # حساب المؤشرات بناء على النطاق المفلتر المختار حالياً
    if not df_filtered.empty:
        total_hours = round(df_filtered["المدة_بالدقائق"].sum()/60, 1)
        activities_count = len(df_filtered)
        if not df_filtered["النشاط"].dropna().empty:
            most_activity = df_filtered.groupby("النشاط")["المدة_بالدقائق"].sum().idxmax()

    # نظام الإنجازات العام
    achievements = [
        ("🌱", "البداية الأولى", len(df_db_calc) >= 1),
        ("⏱️", "أول 10 ساعات", round(df_db_calc["المدة_بالدقائق"].sum()/60 if not df_db_calc.empty else 0) >= 10),
        ("💪", "50 ساعة تدريب", round(df_db_calc["المدة_بالدقائق"].sum()/60 if not df_db_calc.empty else 0) >= 50),
        ("🚀", "100 ساعة إنجاز", round(df_db_calc["المدة_بالدقائق"].sum()/60 if not df_db_calc.empty else 0) >= 100),
        ("🔥", "7 أيام متتالية", current_streak >= 7),
        ("🏆", "30 يوماً متتالياً", current_streak >= 30),
        ("📋", "100 نشاط مسجل", len(df_db_calc) >= 100)
    ]

    # عرض المؤشرات الرقمية
    st.markdown("### 📈 مؤشرات الأداء للفترة المحددة")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("🔥 السلسلة الحالية", f"{current_streak} يوم")
    c2.metric("🏆 أطول سلسلة (Streak)", f"{best_streak} يوم")
    c3.metric("⏱ إجمالي الساعات", f"{total_hours} س")
    c4.metric("📋 عدد الأنشطة", activities_count)
    c5.metric("🎯 ساعات اليوم", f"{today_hours} س")
    c6.metric("⭐ الأكثر تفضيلاً", most_activity)

    st.markdown("---")
    
    # ✨ [إضافة نظام ومؤشرات الأهداف الذكية والنسب المئوية الدقيقة]
    st.subheader("🎯 رادار الأهداف الذكية ومعدلات الإنجاز")
    goal1, goal2, goal3 = st.columns(3)
    
    with goal1:
        p_today = min(today_hours / DAILY_GOAL, 1.0)
        st.metric("🎯 الهدف اليومي", f"{today_hours:.1f} / {DAILY_GOAL} ساعة", f"{p_today*100:.0f}% من الهدف")
        st.progress(p_today)
    with goal2:
        p_week = min(week_hours / WEEKLY_GOAL, 1.0)
        st.metric("📅 الهدف الأسبوعي", f"{week_hours:.1f} / {WEEKLY_GOAL} ساعة", f"{p_week*100:.0f}% من الهدف")
        st.progress(p_week)
    with goal3:
        p_month = min(month_hours / MONTHLY_GOAL, 1.0)
        st.metric("🗓️ الهدف الشهري", f"{month_hours:.1f} / {MONTHLY_GOAL} ساعة", f"{p_month*100:.0f}% من الهدف")
        st.progress(p_month)

    st.markdown("---")
    col_graph1, col_graph2 = st.columns([2,1])
        
    with col_graph1:
        st.subheader("🧱 مخطط الالتزام السنوي المفلتر (GitHub Grid)")
        all_days = pd.date_range(start=datetime.date(current_year, 1, 1), end=datetime.date(current_year, 12, 31))
        df_year_grid = pd.DataFrame({'تاريخ_صحيح': all_days})
        df_year_grid['تاريخ_يومي_مختصر'] = df_year_grid['تاريخ_صحيح'].dt.strftime('%Y-%m-%d')
        df_year_grid['الأسبوع_السنوي'] = df_year_grid['تاريخ_صحيح'].dt.isocalendar().week
        df_year_grid['اليوم_رقم'] = df_year_grid['تاريخ_صحيح'].dt.dayofweek
        df_year_grid['الشهر_رقم'] = df_year_grid['تاريخ_صحيح'].dt.month

        github_day_order = [6, 0, 1, 2, 3, 4, 5] 
        days_names = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']

        # يعرض المخطط السنوي الأنشطة مع تسليط الضوء بناء على الفلترة الزمنية المختارة لتلوينها
        if not df_filtered.empty:
            user_summary = df_filtered.groupby('تاريخ_يومي_مختصر')['المدة_بالدقائق'].sum().reset_index()
            user_summary['الساعات'] = user_summary['المدة_بالدقائق'] / 60
            df_year_grid = pd.merge(df_year_grid, user_summary[['تاريخ_يومي_مختصر', 'الساعات']], on='تاريخ_يومي_مختصر', how='left').fillna(0)
        else:
            df_year_grid['الساعات'] = 0.0

        weeks_indices = sorted(df_year_grid['الأسبوع_السنوي'].unique())
        z_matrix, text_matrix = [], []

        for d in github_day_order:
            row_z, row_text = [], []
            for w in weeks_indices:
                day_data = df_year_grid[(df_year_grid['الأسبوع_السنوي'] == w) & (df_year_grid['اليوم_رقم'] == d)]
                if not day_data.empty:
                    val = day_data['الساعات'].values[0]
                    row_z.append(val)
                    row_text.append(f"التاريخ: {day_data['تاريخ_يومي_مختصر'].values[0]}<br>الإنجاز: {val} ساعة")
                else:
                    row_z.append(0)
                    row_text.append("")
            z_matrix.append(row_z)
            text_matrix.append(row_text)

        fig_heatmap = go.Figure(data=go.Heatmap(
            z=z_matrix, x=weeks_indices, y=days_names, text=text_matrix, hoverinfo='text', xgap=1, ygap=1,
            colorscale=[[0.0, '#ebedf0'], [0.01, '#9be9a8'], [0.3, '#40c463'], [0.6, '#30a14e'], [1.0, '#216e39']], showscale=False
        ))
        fig_heatmap.update_layout(height=280, margin=dict(t=10, b=10, l=5, r=5), xaxis=dict(showgrid=False), yaxis=dict(showgrid=False, autorange='reversed'))
        st.plotly_chart(fig_heatmap, use_container_width=True, config={"displayModeBar": False})

    with col_graph2:
        st.subheader("🍕 توزيع المجهود بالفترة")
        if not df_filtered.empty and df_filtered['المدة_بالدقائق'].sum() > 0:
            pie_data = df_filtered.groupby('النشاط')['المدة_بالدقائق'].sum().reset_index()
            fig_pie = px.pie(pie_data, values='المدة_بالدقائق', names='النشاط', hole=0.4)
            fig_pie.update_layout(height=280, margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("لا توجد أنشطة مسجلة في هذا النطاق الزمني لعرض توزيعها.")

    st.markdown("---")
    st.subheader("📈 منحنى تطور الأداء وحجم الساعات")
    if not df_filtered.empty:
        trend = df_filtered.groupby("date_only")["المدة_بالدقائق"].sum().reset_index()
        trend["الساعات"] = trend["المدة_بالدقائق"] / 60
        trend = trend.sort_values("date_only")

        fig_line = px.line(trend, x="date_only", y="الساعات", markers=True)
        fig_line.update_layout(height=300, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig_line, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("أدخل بيانات أو وسّع النطاق الزمني لمشاهدة خط التطور السلوكي للتمارين.")

    st.markdown("---")
    st.subheader("🏆 قائمة الإنجازات المفتوحة (دائمة)")
    cols = st.columns(2)
    for i, (icon, name, unlocked) in enumerate(achievements):
        with cols[i % 2]:
            if unlocked:
                st.success(f"{icon} {name} (مكتمل)")
            else:
                st.info(f"🔒 {icon} {name} (قيد التقدم)")
