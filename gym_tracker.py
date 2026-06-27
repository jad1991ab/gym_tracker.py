import streamlit as st
import pandas as pd
import gspread
import datetime
import io
import time
import plotly.graph_objects as go
import plotly.express as px
import streamlit.components.v1 as components
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe
from datetime import timedelta

# إعدادات الصفحة والتصميم العام
st.set_page_config(page_title="متابع الأنشطة الاحترافي", layout="wide", page_icon="🟢")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# الأعمدة الرسمية المطلوبة بالتطبيق شاملة الملاحظات
COLUMNS = ['ID', 'التاريخ', 'السنة', 'الشهر', 'الأسبوع', 'اليوم', 'الساعة', 'النشاط', 'المدة_بالدقائق', 'الملاحظات']

@st.cache_resource
def get_sheet_and_init():
    """
    تحسين استقرار: يتم استدعاؤه مرة واحدة فقط عند إقلاع التطبيق لمنع استهلاك الـ Quota.
    """
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    client = gspread.authorize(creds)
    sheet_name = st.secrets["google"]["sheet_name"]
    spreadsheet = client.open(sheet_name)
    worksheet = spreadsheet.sheet1
    
    # التحقق من وجود الأعمدة وتحديث الجدول مرة واحدة فقط
    try:
        first_row = worksheet.row_values(1)
        if not first_row:
            worksheet.append_row(COLUMNS)
        else:
            if 'الملاحظات' not in first_row:
                for idx, col in enumerate(COLUMNS):
                    worksheet.update_cell(1, idx + 1, col)
    except Exception:
        pass
        
    return worksheet

# استدعاء قاعدة البيانات
try:
    sheet = get_sheet_and_init()
except Exception as e:
    st.error(f"خطأ في الاتصال بقاعدة البيانات: {e}")

@st.cache_data(ttl=300)
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
        st.error(f"خطأ أثناء قراءة Google Sheet: {e}")
        return pd.DataFrame(columns=COLUMNS)

def save_data_complete(df):
    """تُستدعى فقط عند مسح الجدول أو إجراء عمليات حذف لأسطر معينة"""
    try:
        clean_df = df[[c for c in COLUMNS if c in df.columns]].copy()
        sheet.clear()
        set_with_dataframe(sheet, clean_df, include_index=False, include_column_header=True, resize=True)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"حدث خطأ أثناء حفظ البيانات: {e}")

if 'db' not in st.session_state:
    st.session_state.db = load_data()

df_db = st.session_state.db

# تجهيز متغيرات الوقت الحالية الأساسية
now = datetime.datetime.now()
today_str = now.strftime('%Y-%m-%d')
current_year = now.year

# ==========================================
# 🧭 نظام القوائم والتنقل
# ==========================================
st.sidebar.title("🧭 قائمة التنقل")
page = st.sidebar.radio("اختر الصفحة:", ["📥 تسجيل نشاط جديد", "📊 لوحة التحكم والإحصاءات"])


# دالة تغيير الحقول السريعة للتوقيت (Callback آمن)
def update_duration(target_value):
    st.session_state.duration_input = target_value


# ==========================================
# 1. صفحة: تسجيل نشاط جديد (أصبحت خفيفة وسريعة جداً)
# ==========================================
if page == "📥 تسجيل نشاط جديد":
    st.header("🟢 نظام تسجيل ومتابعة الأنشطة")
    
    # ساعة الإيقاف التفاعلية الذكية
    st.markdown("### ⏱️ ساعة الإيقاف والتركيز الحي")
    stop_col1, stop_col2 = st.columns([2, 1])
    
    if "stopwatch_running" not in st.session_state:
        st.session_state.stopwatch_running = False
        st.session_state.stopwatch_start = None
        st.session_state.elapsed_time = 0

    with stop_col1:
        if not st.session_state.stopwatch_running:
            if st.button("▶️ ابدأ نشاط حياً الآن (تشغيل العداد المستمر)", use_container_width=True):
                st.session_state.stopwatch_running = True
                st.session_state.stopwatch_start = time.time() - st.session_state.elapsed_time
                st.rerun()
        else:
            st.session_state.elapsed_time = time.time() - st.session_state.stopwatch_start
            if st.button("⏸️ إنهاء النشاط المباشر وتعبئة الوقت المكتسب تلقائياً", use_container_width=True, type="primary"):
                st.session_state.stopwatch_running = False
                calc_hours = round(st.session_state.elapsed_time / 3600, 2)
                st.session_state.duration_input = max(calc_hours, 0.1)
                st.toast(f"تم ملء حقل الساعات بالأسفل بـ {max(calc_hours, 0.1)} ساعة!", icon="⏱️")
                st.rerun()
                
    with stop_col2:
        if st.session_state.stopwatch_running:
            st.session_state.elapsed_time = time.time() - st.session_state.stopwatch_start
            mins, secs = divmod(int(st.session_state.elapsed_time), 60)
            hrs, mins = divmod(mins, 60)
            st.metric("⏳ العداد يعمل حالياً", f"{hrs:02d}:{mins:02d}:{secs:02d}")
            time.sleep(1)
            st.rerun()
        else:
            if st.session_state.elapsed_time > 0:
                mins, secs = divmod(int(st.session_state.elapsed_time), 60)
                hrs, mins = divmod(mins, 60)
                st.metric("⏱️ الوقت المسجل الجاهز", f"{hrs:02d}:{mins:02d}:{secs:02d}")
                if st.button("🔄 إعادة تصفير ساعة الإيقاف"):
                    st.session_state.elapsed_time = 0
                    st.rerun()

    st.markdown("---")
    st.subheader("📥 نموذج البيانات والملء اليدوي")
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
    target_date = now.date()
    chosen_time_str = now.strftime('%H:%M')

    if "duration_input" not in st.session_state:
        st.session_state.duration_input = 1.0

    if auto_time:
        c1, c2 = st.columns(2)
        with c1:
            selected_activity = st.selectbox("النشاط", activities_list)
            if selected_activity == "➕ إضافة نشاط مخصص...":
                custom_activity = st.text_input("اكتب اسم النشاط الجديد هنا:")
            activity_notes = st.text_input("✍️ ملاحظات وتعليقات على النشاط (اختياري):", placeholder="مثال: تمرين أرجل، إنهاء الفصل الثالث")
        with c2:
            duration_hours = st.number_input("مدة النشاط (بالساعات)", min_value=0.1, max_value=24.0, step=0.5, key="duration_input")
            st.caption("⏱️ أزرار تعيين الوقت السريعة:")
            b1, b2, b3, b4 = st.columns(4)
            with b1: st.button("⏱️ 30 د", use_container_width=True, on_click=update_duration, args=(0.5,))
            with b2: st.button("⏱️ 1 ساعة", use_container_width=True, on_click=update_duration, args=(1.0,))
            with b3: st.button("⏱️ 1.5 س", use_container_width=True, on_click=update_duration, args=(1.5,))
            with b4: st.button("⏱️ 2 ساعتين", use_container_width=True, on_click=update_duration, args=(2.0,))
    else:
        c1, c2, c3 = st.columns([2, 1.5, 1.5])
        with c1:
            selected_activity = st.selectbox("النشاط", activities_list)
            if selected_activity == "➕ إضافة نشاط مخصص...":
                custom_activity = st.text_input("اكتب اسم النشاط الجديد هنا:")
            duration_hours = st.number_input("المدة (بالساعات)", min_value=0.1, max_value=24.0, step=0.5, key="duration_input")
            st.caption("⏱️ أزرار تعيين الوقت السريعة:")
            b1, b2, b3, b4 = st.columns(4)
            with b1: st.button("⏱️ 30 د", use_container_width=True, key="m1", on_click=update_duration, args=(0.5,))
            with b2: st.button("⏱️ 1 ساعة", use_container_width=True, key="m2", on_click=update_duration, args=(1.0,))
            with b3: st.button("⏱️ 1.5 س", use_container_width=True, key="m3", on_click=update_duration, args=(1.5,))
            with b4: st.button("⏱️ 2 ساعتين", use_container_width=True, key="m4", on_click=update_duration, args=(2.0,))
            activity_notes = st.text_input("✍️ ملاحظات وتعليقات على النشاط (اختياري):", placeholder="مثال: مراجعة شيفرة التطبيق")
        with c2:
            target_date = st.date_input("اختر التاريخ من التقويم 📅", value=now.date())
        with c3:
            clock_html = f"""
            <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; font-family:sans-serif; width: 100%;">
                <label style='font-size:14px; font-weight:bold; color:#216e39; margin-bottom:8px; text-align:center;'>اضبط الوقت ⌚</label>
                <input type="time" id="analog_picker" value="{chosen_time_str}" style="font-size: 18px; padding: 6px; border-radius: 8px; border: 2px solid #40c463; text-align: center; width: 150px; font-weight:bold; color:#216e39;">
            </div>
            <script>
                var picker = document.getElementById('analog_picker');
                function emitTime() {{ window.parent.postMessage({{type: 'streamlit:setComponentValue', value: picker.value}}, '*'); }}
                picker.addEventListener('input', emitTime); picker.addEventListener('change', emitTime);
                setTimeout(emitTime, 250);
            </script>
            """
            clock_return = components.html(clock_html, height=120)
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
        duration_minutes = int(duration_hours * 60)
        
        # تجهيز المصفوفة الترتيبية لإرسالها
        row_to_append = [
            int(datetime.datetime.now().timestamp() * 1000),             # ID
            combined_datetime.strftime('%Y-%m-%d %H:%M:%S'),            # التاريخ
            int(combined_datetime.year),                                 # السنة
            str(months_list[combined_datetime.month - 1]),               # الشهر
            int(combined_datetime.isocalendar().week),                   # الأسبوع
            str(combined_datetime.strftime('%A')),                       # اليوم
            str(combined_datetime.strftime('%H:%M')),                    # الساعة
            str(final_activity),                                         # النشاط
            duration_minutes,                                            # المدة_بالدقائق
            str(activity_notes.strip())                                  # الملاحظات
        ]
        
        try:
            # 🚀 تحسين الأداء: استخدام append_row مباشرة بدلاً من مسح وإعادة رفع الجدول بالكامل
            sheet.append_row(row_to_append)
            st.cache_data.clear() # تفريغ الكاش الموضعي لجلب المدخل الجديد فوراً
            st.session_state.db = load_data()
            st.session_state.elapsed_time = 0
            st.toast(f"✅ تم حفظ السطر الجديد مباشرة في Google Sheet بنجاح!", icon="🚀")
            st.rerun()
        except Exception as e:
            st.error(f"فشل الحفظ المباشر، جاري الحفظ الاحتياطي: {e}")

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
            display_df,
            column_config={"حذف؟": st.column_config.CheckboxColumn("إجراء الحذف", default=False)},
            disabled=[col for col in display_df.columns if col != 'حذف؟'],
            hide_index=True, use_container_width=True, key="data_editor_delete"
        )
        
        indices_to_delete = edited_display[edited_display['حذف؟'] == True].index
        if len(indices_to_delete) > 0:
            if st.button("🗑️ تأكيد حذف الأنشطة المحددة", type="primary"):
                df_db = df_db.drop(indices_to_delete).reset_index(drop=True)
                save_data_complete(df_db)
                st.session_state.db = df_db
                st.toast("تم حذف الأنشطة المحددة بنجاح!", icon="🗑️")
                st.rerun()


# ==========================================
# 2. صفحة لوحة التحكم والإحصاءات (Lazy Evaluation)
# ==========================================
elif page == "📊 لوحة التحكم والإحصاءات":
    st.header("📊 لوحة التحكم والأداء العام")
    
    # ⚙️ تحسين الأداء: معالجة وتحويل البيانات والإحصاءات تتم هنا فقط عند فتح الصفحة
    if not df_db.empty:
        df_db_calc_base = df_db.copy()
        df_db_calc_base['تاريخ_صحيح'] = pd.to_datetime(df_db_calc_base['التاريخ'], errors='coerce')
        df_db_calc_base['تاريخ_يومي_مختصر'] = df_db_calc_base['تاريخ_صحيح'].dt.strftime('%Y-%m-%d')
        df_db_calc_base['المدة_بالدقائق'] = pd.to_numeric(df_db_calc_base['المدة_بالدقائق'], errors='coerce').fillna(0)
        df_db_calc_base['الملاحظات'] = df_db_calc_base['الملاحظات'].fillna("")
        df_db_calc_base["date_only"] = df_db_calc_base["تاريخ_صحيح"].dt.date
    else:
        df_db_calc_base = df_db.copy()
        df_db_calc_base['تاريخ_يومي_مختصر'] = pd.Series(dtype='str')
        df_db_calc_base['الملاحظات'] = pd.Series(dtype='str')
        df_db_calc_base["date_only"] = pd.Series(dtype='object')

    # حساب السلاسل الالتزامية (Streaks) الكلية
    current_streak = 0
    best_streak = 0
    activities_count = len(df_db_calc_base)

    if not df_db_calc_base.empty and 'date_only' in df_db_calc_base.columns:
        today = datetime.date.today()
        unique_days = sorted(set(df_db_calc_base["date_only"].dropna()))
        
        streak = 0
        check_day = today
        while check_day in unique_days:
            streak += 1
            check_day -= timedelta(days=1)
        current_streak = streak

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

    # نظام الفلاتر المتقدمة
    st.markdown("### 🔍 نظام التصفية والفلترة المتقدم للرسوم البيانية")
    f_col1, f_col2 = st.columns(2)
    
    act_options = ["الكل"] + (df_db_calc_base['النشاط'].unique().tolist() if not df_db_calc_base.empty else [])
    month_options = ["الكل"] + ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    
    with f_col1:
        f_activity = st.selectbox("🎯 فلترة حسب نوع النشاط المحدد:", act_options)
    with f_col2:
        f_month = st.selectbox("📅 فلترة حسب الشهر المطلوب الاستعلام عنه:", month_options)
        
    # تطبيق الفلترة التفاعلية ديناميكياً
    df_db_calc = df_db_calc_base.copy()
    if f_activity != "الكل":
        df_db_calc = df_db_calc[df_db_calc['النشاط'] == f_activity]
    if f_month != "الكل":
        df_db_calc = df_db_calc[df_db_calc['الشهر'] == f_month]

    DAILY_GOAL, WEEKLY_GOAL, MONTHLY_GOAL = 2, 14, 60
    today_hours, week_hours, month_hours, total_hours, f_count, most_activity = 0, 0, 0, 0, 0, "-"

    if not df_db_calc.empty:
        total_hours = round(df_db_calc["المدة_بالدقائق"].sum()/60, 1)
        f_count = len(df_db_calc)
        most_activity = df_db_calc.groupby("النشاط")["المدة_بالدقائق"].sum().idxmax()
        today = datetime.date.today()
        today_hours = round(df_db_calc[df_db_calc["date_only"] == today]["المدة_بالدقائق"].sum()/60, 1)
        start_week = today - timedelta(days=today.weekday())
        week_hours = round(df_db_calc[df_db_calc["date_only"] >= start_week]["المدة_بالدقائق"].sum()/60, 1)
        month_hours = round(df_db_calc[(pd.to_datetime(df_db_calc["date_only"]).dt.month == today.month) & (pd.to_datetime(df_db_calc["date_only"]).dt.year == today.year)]["المدة_بالدقائق"].sum()/60, 1)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("🔥 السلسلة الكلية", f"{current_streak} يوم")
    c2.metric("🏆 أفضل سلسلة", f"{best_streak} يوم")
    c3.metric("⏱ ساعات الفلتر", total_hours)
    c4.metric("📋 أنشطة الفلتر", f_count)
    c5.metric("🎯 ساعات اليوم", today_hours)
    c6.metric("⭐ النشاط الأكبر", most_activity)

    st.markdown("---")
    st.subheader("🎯 مؤشر الإنجاز ومقارنة الأداء اليومي")
    today_activities = df_db_calc[df_db_calc['تاريخ_يومي_مختصر'] == today_str] if not df_db_calc.empty else pd.DataFrame()
    total_today_hours = round(today_activities['المدة_بالدقائق'].sum() / 60, 1) if not today_activities.empty else 0.0

    if not df_db_calc.empty and len(df_db_calc['تاريخ_يومي_مختصر'].unique()) > 1:
        daily_summary = df_db_calc.groupby('تاريخ_يومي_مختصر')['المدة_بالدقائق'].sum() / 60
        previous_days = daily_summary.drop(index=today_str, errors='ignore')
        avg_previous_hours = round(previous_days.mean(), 1) if not previous_days.empty else 0.0
        delta_performance = round(total_today_hours - avg_previous_hours, 1)
    else:
        avg_previous_hours, delta_performance = 0.0, total_today_hours

    col_p1, col_p2, col_p3 = st.columns([3, 1, 1])
    with col_p1:
        progress_percent = min(int((total_today_hours / 2.0) * 100), 100) if total_today_hours > 0 else 0
        st.caption(f"التقدم نحو الهدف اليومي الحالي بالفلتر: {progress_percent}%")
        st.progress(progress_percent / 100)
    with col_p2: st.metric("إنجاز اليوم المفلتر", f"{total_today_hours} ساعة", delta=f"{delta_performance}" if delta_performance != total_today_hours else "نشاط جديد")
    with col_p3: st.metric("متوسط الإنجاز السابق", f"{avg_previous_hours} ساعة")

    st.markdown("---")
    st.subheader("🧱 مخطط الالتزام السنوي المفلتر (GitHub Grid)")
    
    all_days = pd.date_range(start=datetime.date(current_year, 1, 1), end=datetime.date(current_year, 12, 31))
    df_year_grid = pd.DataFrame({'تاريخ_صحيح': all_days})
    df_year_grid['تاريخ_يومي_مختصر'] = df_year_grid['تاريخ_صحيح'].dt.strftime('%Y-%m-%d')
    df_year_grid['الأسبوع_السنوي'] = df_year_grid['تاريخ_صحيح'].dt.isocalendar().week
    df_year_grid['اليوم_رقم'] = df_year_grid['تاريخ_صحيح'].dt.dayofweek
    df_year_grid['الشهر_رقم'] = df_year_grid['تاريخ_صحيح'].dt.month
    df_year_grid.loc[(df_year_grid['الشهر_رقم'] == 1) & (df_year_grid['الأسبوع_السنوي'] >= 52), 'الأسبوع_السنوي'] = 0
    df_year_grid.loc[(df_year_grid['الشهر_رقم'] == 12) & (df_year_grid['الأسبوع_السنوي'] == 1), 'الأسبوع_السنوي'] = 53

    if not df_db_calc.empty:
        user_summary = df_db_calc.groupby('تاريخ_يومي_مختصر')['المدة_بالدقائق'].sum().reset_index()
        user_summary['الساعات'] = user_summary['المدة_بالدقائق'] / 60
        df_year_grid = pd.merge(df_year_grid, user_summary[['تاريخ_يومي_مختصر', 'الساعات']], on='تاريخ_يومي_مختصر', how='left').fillna(0)
    else: df_year_grid['الساعات'] = 0.0

    github_day_order = [6, 0, 1, 2, 3, 4, 5]
    days_names = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
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
            else: row_z.append(0); row_text.append("")
        z_matrix.append(row_z); text_matrix.append(row_text)

    fig_heatmap = go.Figure(data=go.Heatmap(
        z=z_matrix, x=weeks_indices, y=days_names, text=text_matrix, hoverinfo='text', xgap=1, ygap=1,
        colorscale=[[0.0, '#ebedf0'], [0.01, '#9be9a8'], [0.3, '#40c463'], [0.6, '#30a14e'], [1.0, '#216e39']], showscale=False
    ))
    fig_heatmap.update_layout(height=240, margin=dict(t=20, b=10, l=5, r=5), xaxis=dict(showgrid=False), yaxis=dict(showgrid=False, autorange='reversed'))
    st.plotly_chart(fig_heatmap, use_container_width=True, config={"displayModeBar": False})

    g_col1, g_col2 = st.columns([1, 1])
    with g_col1:
        st.subheader("🍕 توزيع المجهود المفلتر")
        if not df_db_calc.empty and df_db_calc['المدة_بالدقائق'].sum() > 0:
            pie_data = df_db_calc.groupby('النشاط')['المدة_بالدقائق'].sum().reset_index()
            fig_pie = px.pie(pie_data, values='المدة_بالدقائق', names='النشاط', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
        else: st.info("لا توجد بيانات متاحة لهذا الفلتر المختار لإنشاء الرسم الدائري.")
        
    with g_col2:
        st.subheader("📈 الأداء التراكمي المفلتر (آخر 30 يوماً)")
        if not df_db_calc.empty:
            last30 = datetime.date.today() - datetime.timedelta(days=29)
            trend = df_db_calc[df_db_calc["date_only"] >= last30].groupby("date_only")["المدة_بالدقائق"].sum().reset_index()
            trend["الساعات"] = trend["المدة_بالدقائق"] / 60
            fig_line = px.line(trend, x="date_only", y="الساعات", markers=True)
            st.plotly_chart(fig_line, use_container_width=True)
        else: st.info("لا توجد بيانات خطية كافية للفلاتر الحالية.")
