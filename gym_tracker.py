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

# إعدادات الصفحة الرسمية والتصميم
st.set_page_config(page_title="متابع الأنشطة الاحترافي", layout="wide", page_icon="🟢")

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

# الأعمدة الرسمية في الـ Google Sheet
COLUMNS = ['ID', 'التاريخ', 'السنة', 'الشهر', 'الأسبوع', 'اليوم', 'الساعة', 'النشاط', 'المدة_بالدقائق']

try:
    first_row = sheet.row_values(1)
    if not first_row:
        sheet.append_row(COLUMNS)
except Exception as e:
    st.error(f"خطأ في الاتصال بقاعدة البيانات: {e}")

@st.cache_data(ttl=600)
def load_data():
    try:
        records = sheet.get_all_records()
        if len(records) == 0:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.DataFrame(records)
        if 'المدة_بالدقائق' not in df.columns:
            df['المدة_بالدقائق'] = 60
        existing_cols = [c for c in COLUMNS if c in df.columns]
        return df[existing_cols]
    except Exception as e:
        st.error(f"خطأ أثناء قراءة Google Sheet: {e}")
        return pd.DataFrame(columns=COLUMNS)

def save_data(df):
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

# تجهيز متغيرات الوقت للحسابات
now = datetime.datetime.now()
today_str = now.strftime('%Y-%m-%d')
current_year = now.year

# تهيئة قيمة حقل الإدخال وساعة الإيقاف في الـ Session State في أعلى الملف لمنع أخطاء التحديث
if "duration_input" not in st.session_state:
    st.session_state.duration_input = 1.0

if "stopwatch_running" not in st.session_state:
    st.session_state.stopwatch_running = False
    st.session_state.stopwatch_start = None
    st.session_state.elapsed_time = 0

# دالة الـ Callback لتغيير قيمة الوقت بأمان عند الضغط على الأزرار السريعة
def set_duration(amount):
    st.session_state.duration_input = float(amount)

# معالجة البيانات للإحصائيات والرسومات
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
# 🧭 نظام القوائم والتنقل الجانبي (إعادة التفعيل)
# ==========================================
st.sidebar.title("🧭 قائمة التنقل")
page = st.sidebar.radio("اختر الصفحة:", ["📥 تسجيل نشاط جديد", "📊 لوحة التحكم والإحصاءات"])

# دالة مساعدة لإنشاء حقول وأزرار الوقت بشكل موحد وآمن
def render_duration_section(col_context):
    with col_context:
        st.number_input("مدة النشاط (بالساعات)", min_value=0.1, max_value=24.0, step=0.1, key="duration_input")
        st.caption("⏱️ أزرار تعيين الوقت السريعة:")
        b1, b2, b3, b4 = st.columns(4)
        b1.button("⏱️ 30 د", key="b30", on_click=set_duration, args=(0.5,), use_container_width=True)
        b2.button("⏱️ 1 ساعة", key="b1h", on_click=set_duration, args=(1.0,), use_container_width=True)
        b3.button("⏱️ 1.5 س", key="b15", on_click=set_duration, args=(1.5,), use_container_width=True)
        b4.button("⏱️ 2 ساعتين", key="b2h", on_click=set_duration, args=(2.0,), use_container_width=True)

# ==========================================
# 1. صفحة: تسجيل نشاط جديد
# ==========================================
if page == "📥 تسجيل نشاط جديد":
    st.header("🟢 تسجيل ومتابعة الأنشطة")
    
    # قسم ساعة الإيقاف الحيّة والذكية
    st.markdown("### ⏱️ ساعة الإيقاف والتركيز الحي")
    stop_col1, stop_col2 = st.columns([2, 1])
    
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
                st.toast(f"📥 تم تحديث حقل المدة بالأسفل بـ {st.session_state.duration_input} ساعة!", icon="⏱️")
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
                    st.session_state.duration_input = 1.0
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

    if auto_time:
        c1, c2 = st.columns(2)
        with c1:
            selected_activity = st.selectbox("النشاط", activities_list, key="activity_auto")
            if selected_activity == "➕ إضافة نشاط مخصص...":
                custom_activity = st.text_input("اكتب اسم النشاط الجديد هنا:", key="custom_auto")
        render_duration_section(c2)
    else:
        c1, c2, c3 = st.columns([2, 1.5, 1.5])
        with c1:
            selected_activity = st.selectbox("النشاط", activities_list, key="activity_manual")
            if selected_activity == "➕ إضافة نشاط مخصص...":
                custom_activity = st.text_input("اكتب اسم النشاط الجديد هنا:", key="custom_manual")
        render_duration_section(c1)
        with c2:
            target_date = st.date_input("اختر التاريخ من التقويم 📅", value=now.date())
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
            'المدة_بالدقائق': duration_minutes
        }
        
        df_db = pd.concat([df_db, pd.DataFrame([new_row])], ignore_index=True)
        save_data(df_db)
        st.session_state.db = df_db
        st.toast(f"✅ تم تسجيل نشاط ({final_activity}) بنجاح!", icon="🔥")
        st.rerun()

    # سجل التحكم والحذف والتصدير
    if not df_db.empty:
        st.markdown("---")
        st.subheader("📋 سجل التحكم بالبيانات وحذف الأسطر")
        display_df = df_db.copy()
        display_df['حذف؟'] = False
        display_df['المدة (ساعات)'] = round(display_df['المدة_بالدقائق'] / 60, 2)
        
        cols = ['حذف؟', 'التاريخ', 'النشاط', 'المدة (ساعات)', 'اليوم', 'الساعة']
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

        st.download_button(label="📥 تحميل سجل تمارينك كملف Excel", data=buffer.getvalue(), file_name="my_gym_activities.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
        
        st.markdown("---")
        if st.button("🚨 مسح السجل بالكامل والبدء من جديد"):
            sheet.clear()
            sheet.append_row(COLUMNS)
            st.cache_data.clear()
            st.session_state.db = pd.DataFrame(columns=COLUMNS)
            st.success("تم تصفير قاعدة البيانات بنجاح!")
            st.rerun()

# ==========================================
# 2. صفحة: لوحة التحكم والإحصاءات
# ==========================================
elif page == "📊 لوحة التحكم والإحصاءات":
    st.header("📊 لوحة التحكم والأداء العام")
    
    DAILY_GOAL, WEEKLY_GOAL, MONTHLY_GOAL = 2, 14, 60     
    current_streak, best_streak, today_hours, week_hours, month_hours, total_hours, activities_count = 0, 0, 0, 0, 0, 0, 0
    most_activity = "-"

    if not df_db_calc.empty:
        total_hours = round(df_db_calc["المدة_بالدقائق"].sum()/60, 1)
        activities_count = len(df_db_calc)
        if not df_db_calc["النشاط"].dropna().empty:
            most_activity = df_db_calc.groupby("النشاط")["المدة_بالدقائق"].sum().idxmax()

        today = datetime.date.today()
        today_hours = round(df_db_calc[df_db_calc["date_only"] == today]["المدة_بالدقائق"].sum()/60, 1)
        start_week = today - timedelta(days=today.weekday())
        week_hours = round(df_db_calc[df_db_calc["date_only"] >= start_week]["المدة_بالدقائق"].sum()/60, 1)
        month_hours = round(df_db_calc[(pd.to_datetime(df_db_calc["date_only"]).dt.month == today.month) & (pd.to_datetime(df_db_calc["date_only"]).dt.year == today.year)]["المدة_بالدقائق"].sum()/60, 1)

        unique_days = sorted(set(df_db_calc["date_only"].dropna()))
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

    # نظام الإنجازات
    achievements = [
        ("🌱", "البداية", activities_count >= 1),
        ("⏱️", "أول 10 ساعات", total_hours >= 10),
        ("💪", "50 ساعة", total_hours >= 50),
        ("🚀", "100 ساعة", total_hours >= 100),
        ("🔥", "7 أيام متتالية", current_streak >= 7),
        ("🏆", "30 يوماً متتالياً", current_streak >= 30),
        ("📋", "100 نشاط", activities_count >= 100)
    ]

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("🔥 السلسلة", current_streak)
    c2.metric("🏆 أفضل سلسلة", best_streak)
    c3.metric("⏱ إجمالي الساعات", total_hours)
    c4.metric("📋 الأنشطة", activities_count)
    c5.metric("🎯 ساعات اليوم", today_hours)
    c6.metric("⭐ النشاط المفضل", most_activity)

    st.markdown("---")
    st.subheader("🏆 الإنجازات المفتوحة")
    cols = st.columns(2)
    for i, (icon, name, unlocked) in enumerate(achievements):
        with cols[i % 2]:
            if unlocked: st.success(f"{icon} {name}")
            else: st.info(f"🔒 {icon} {name}")

    st.subheader("🎯 التقدم نحو الأهداف")
    goal1, goal2, goal3 = st.columns(3)
    with goal1:
        st.metric("🎯 الهدف اليومي", f"{today_hours:.1f}/{DAILY_GOAL} ساعة")
        st.progress(min(today_hours / DAILY_GOAL, 1.0))
    with goal2:
        st.metric("📅 الهدف الأسبوعي", f"{week_hours:.1f}/{WEEKLY_GOAL} ساعة")
        st.progress(min(week_hours / WEEKLY_GOAL, 1.0))
    with goal3:
        st.metric("🗓️ الهدف الشهري", f"{month_hours:.1f}/{MONTHLY_GOAL} ساعة")
        st.progress(min(month_hours / MONTHLY_GOAL, 1.0))

    st.markdown("---")
    col_graph1, col_graph2 = st.columns([2,1])
        
    with col_graph1:
        st.subheader("🧱 مخطط الالتزام السنوي (GitHub Grid)")
        all_days = pd.date_range(start=datetime.date(current_year, 1, 1), end=datetime.date(current_year, 12, 31))
        df_year_grid = pd.DataFrame({'تاريخ_صحيح': all_days})
        df_year_grid['تاريخ_يومي_مختصر'] = df_year_grid['تاريخ_صحيح'].dt.strftime('%Y-%m-%d')
        df_year_grid['الأسبوع_السنوي'] = df_year_grid['تاريخ_صحيح'].dt.isocalendar().week
        df_year_grid['اليوم_رقم'] = df_year_grid['تاريخ_صحيح'].dt.dayofweek
        df_year_grid['الشهر_رقم'] = df_year_grid['تاريخ_صحيح'].dt.month

        github_day_order = [6, 0, 1, 2, 3, 4, 5] 
        days_names = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']

        if not df_db_calc.empty:
            user_summary = df_db_calc.groupby('تاريخ_يومي_مختصر')['المدة_بالدقائق'].sum().reset_index()
            user_summary['الساعات'] = user_summary['المدة_بالدقائق'] / 60
            df_year_grid = pd.merge(df_year_grid, user_summary[['تاريخ_يومي_مختصر', 'الساعات']], on='تاريخ_يومي_مختصر', how='left').fillna(0)
        else: df_year_grid['الساعات'] = 0.0

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
        fig_heatmap.update_layout(height=280, margin=dict(t=10, b=10, l=5, r=5), xaxis=dict(showgrid=False), yaxis=dict(showgrid=False, autorange='reversed'))
        st.plotly_chart(fig_heatmap, use_container_width=True, config={"displayModeBar": False})

    with col_graph2:
        st.subheader("🍕 توزيع المجهود")
        if not df_db_calc.empty and df_db_calc['المدة_بالدقائق'].sum() > 0:
            pie_data = df_db_calc.groupby('النشاط')['المدة_بالدقائق'].sum().reset_index()
            fig_pie = px.pie(pie_data, values='المدة_بالدقائق', names='النشاط', hole=0.4)
            fig_pie.update_layout(height=280, margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)
        else: st.info("سيتوفر الرسم الدائري فور تسجيل الأنشطة.")

    st.markdown("---")
    st.subheader("📈 تطور الأداء خلال آخر 30 يوماً")
    if not df_db_calc.empty:
        last30 = datetime.date.today() - datetime.timedelta(days=29)
        trend = df_db_calc[df_db_calc["date_only"] >= last30].groupby("date_only")["المدة_بالدقائق"].sum().reset_index()
        all_dates = pd.DataFrame({"date_only": pd.date_range(last30, datetime.date.today()).date})
        trend = all_dates.merge(trend, on="date_only", how="left").fillna(0)
        trend["الساعات"] = trend["المدة_بالدقائق"] / 60

        fig_line = px.line(trend, x="date_only", y="الساعات", markers=True)
        fig_line.update_layout(height=300, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig_line, use_container_width=True, config={"displayModeBar": False})
