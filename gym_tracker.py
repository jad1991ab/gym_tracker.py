import streamlit as st
import pandas as pd
import gspread
import datetime
import io
import plotly.graph_objects as go
import streamlit.components.v1 as components
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

# إعدادات الصفحة
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

# الأعمدة الأساسية المعتمدة فقط في الـ Google Sheet
COLUMNS = ['ID', 'التاريخ', 'السنة', 'الشهر', 'الأسبوع', 'اليوم', 'الساعة', 'النشاط', 'المدة_بالدقائق']

try:
    first_row = sheet.row_values(1)
    if not first_row:
        sheet.append_row(COLUMNS)
except Exception as e:
    st.error(f"خطأ في الاتصال الأولي بقاعدة البيانات: {e}")

st.title("🟢 نظام متابعة الأنشطة المطور (مخطط الالتزام السنوي الكامل)")

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

# تجهيز التواريخ للإحصائيات
now = datetime.datetime.now()
today_str = now.strftime('%Y-%m-%d')
current_year = now.year

if not df_db.empty:
    df_db_calc = df_db.copy()
    df_db_calc['تاريخ_صحيح'] = pd.to_datetime(df_db_calc['التاريخ'], errors='coerce')
    df_db_calc['تاريخ_يومي_مختصر'] = df_db_calc['تاريخ_صحيح'].dt.strftime('%Y-%m-%d')
    df_db_calc['المدة_بالدقائق'] = pd.to_numeric(df_db_calc['المدة_بالدقائق'], errors='coerce').fillna(0)
else:
    df_db_calc = df_db.copy()
    df_db_calc['تاريخ_يومي_مختصر'] = pd.Series(dtype='str')

# ==========================================
# 1. شريط الإنجاز اليومي ومقارنة الأداء
# ==========================================
st.subheader("🎯 مؤشر الإنجاز ومقارنة الأداء")

today_activities = df_db_calc[df_db_calc['تاريخ_يومي_مختصر'] == today_str] if not df_db_calc.empty else pd.DataFrame()
total_today_hours = round(today_activities['المدة_بالدقائق'].sum() / 60, 1) if not today_activities.empty else 0.0

if not df_db_calc.empty and len(df_db_calc['تاريخ_يومي_مختصر'].unique()) > 1:
    daily_summary = df_db_calc.groupby('تاريخ_يومي_مختصر')['المدة_بالدقائق'].sum() / 60
    previous_days = daily_summary.drop(index=today_str, errors='ignore')
    avg_previous_hours = round(previous_days.mean(), 1) if not previous_days.empty else 0.0
    delta_performance = round(total_today_hours - avg_previous_hours, 1)
else:
    avg_previous_hours = 0.0
    delta_performance = total_today_hours

col_p1, col_p2, col_p3 = st.columns([3, 1, 1])
with col_p1:
    progress_percent = min(int((total_today_hours / 2.0) * 100), 100) if total_today_hours > 0 else 0
    st.caption(f"التقدم نحو الهدف اليومي (ساعتين): {progress_percent}%")
    st.progress(progress_percent / 100)
with col_p2:
    st.metric("إنجاز اليوم الفعلي", f"{total_today_hours} ساعة", delta=f"{delta_performance} عن المعتاد" if delta_performance != total_today_hours else "أول نشاط")
with col_p3:
    st.metric("متوسط إنجازك اليومي السابق", f"{avg_previous_hours} ساعة")

st.markdown("---")

# ==========================================
# 2. مخطط الالتزام السنوي المصحح والمطور (GitHub Heatmap)
# ==========================================
st.subheader("🧱 مخطط الالتزام السنوي (GitHub Contributions Grid)")

# بناء مصفوفة كاملة ثابتة للسنة الحالية لجميع الأشهر والأيام بشكل متناسق
start_date = datetime.date(current_year, 1, 1)
end_date = datetime.date(current_year, 12, 31)
all_days = pd.date_range(start=start_date, end=end_date)

df_year_grid = pd.DataFrame({'تاريخ_صحيح': all_days})
df_year_grid['تاريخ_يومي_مختصر'] = df_year_grid['تاريخ_صحيح'].dt.strftime('%Y-%m-%d')
df_year_grid['الأسبوع_السنوي'] = df_year_grid['تاريخ_صحيح'].dt.isocalendar().week
df_year_grid['اليوم_رقم'] = df_year_grid['تاريخ_صحيح'].dt.dayofweek # 0=الاثنين, 6=الأحد
df_year_grid['الشهر_رقم'] = df_year_grid['تاريخ_صحيح'].dt.month

# معالجة تداخل أول وأخر أسبوع في السنة رقمياً
df_year_grid.loc[(df_year_grid['الشهر_رقم'] == 1) & (df_year_grid['الأسبوع_السنوي'] >= 52), 'الأسبوع_السنوي'] = 0
df_year_grid.loc[(df_year_grid['الشهر_رقم'] == 12) & (df_year_grid['الأسبوع_السنوي'] == 1), 'الأسبوع_السنوي'] = 53

if not df_db_calc.empty:
    user_summary = df_db_calc.groupby('تاريخ_يومي_مختصر')['المدة_بالدقائق'].sum().reset_index()
    user_summary['الساعات'] = user_summary['المدة_بالدقائق'] / 60
    df_year_grid = pd.merge(df_year_grid, user_summary[['تاريخ_يومي_مختصر', 'الساعات']], on='تاريخ_يومي_مختصر', how='left').fillna(0)
else:
    df_year_grid['الساعات'] = 0.0

weeks_indices = sorted(df_year_grid['الأسبوع_السنوي'].unique())
z_matrix = []
text_matrix = []

days_names = ['الاثنين (Mon)', 'الثلاثاء (Tue)', 'الأربعاء (Wed)', 'الخميس (Thu)', 'الجمعة (Fri)', 'السبت (Sat)', 'الأحد (Sun)']

for d in range(7):
    row_z = []
    row_text = []
    for w in weeks_indices:
        day_data = df_year_grid[(df_year_grid['الأسبوع_السنوي'] == w) & (df_year_grid['اليوم_رقم'] == d)]
        if not day_data.empty:
            val = day_data['الساعات'].values[0]
            date_lbl = day_data['تاريخ_يومي_مختصر'].values[0]
            row_z.append(val)
            row_text.append(f"التاريخ: {date_lbl}<br>الإنجاز: {val} ساعة")
        else:
            row_z.append(0)
            row_text.append("")
    z_matrix.append(row_z)
    text_matrix.append(row_text)

# حساب مواقع الأشهر رقمياً لتجنب الانهيار (ValueError)
month_labels = []
month_positions = []
for m in range(1, 13):
    m_data = df_year_grid[df_year_grid['الشهر_رقم'] == m]
    if not m_data.empty:
        mid_week = m_data['الأسبوع_السنوي'].median()
        month_name = datetime.date(current_year, m, 1).strftime('%b')
        month_labels.append(month_name)
        # استخدام قيمة رقمية صحيحة للموضع لتجنب انهيار التنسيق
        month_positions.append(int(mid_week))

fig_heatmap = go.Figure(data=go.Heatmap(
    z=z_matrix,
    x=weeks_indices,
    y=days_names,
    text=text_matrix,
    hoverinfo='text',
    xgap=3,
    ygap=3,
    colorscale=[
        [0.0, '#ebedf0'],
        [0.01, '#9be9a8'],
        [0.3, '#40c463'],
        [0.6, '#30a14e'],
        [1.0, '#216e39']
    ],
    showscale=True,
    colorbar=dict(title="ساعات الإنجاز", thickness=15)
))

fig_heatmap.update_layout(
    height=290,
    margin=dict(t=35, b=10, l=10, r=10),
    xaxis=dict(
        showgrid=False, 
        ticks="", 
        tickmode='array',
        tickvals=month_positions,
        ticktext=month_labels,
        side='top'
    ),
    yaxis=dict(showgrid=False, ticks="", autorange="reverse")
)
st.plotly_chart(fig_heatmap, use_container_width=True)

st.markdown("---")

# ==========================================
# 3. قسم إدخال البيانات الذكي مع الساعة الدائرية
# ==========================================
st.subheader("📥 تسجيل نشاط جديد")

auto_time = st.toggle("التسجيل التلقائي بالوقت والتاريخ الحالي فوراً ⚡", value=True)

default_activities = ["النادي 🏋️‍♂️", "الدراسة 📚", "العمل 💼"]
if not df_db.empty:
    existing_activities = df_db['النشاط'].dropna().unique().tolist()
    activities_list = list(set(default_activities + existing_activities))
else:
    activities_list = default_activities

activities_list.append("➕ إضافة نشاط مخصص...")
months_list = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

# إعدادات الوقت الافتراضية
target_date = now.date()
chosen_time_str = now.strftime('%H:%M')

if auto_time:
    c1, c2 = st.columns(2)
    with c1:
        selected_activity = st.selectbox("النشاط", activities_list)
        if selected_activity == "➕ إضافة نشاط مخصص...":
            custom_activity = st.text_input("اكتب اسم النشاط الجديد هنا:")
    with c2:
        duration_hours = st.number_input("مدة النشاط (بالساعات)", min_value=0.1, max_value=24.0, value=1.0, step=0.5)
else:
    c1, c2, c3 = st.columns([2, 1, 2])
    with c1:
        selected_activity = st.selectbox("النشاط", activities_list)
        if selected_activity == "➕ إضافة نشاط مخصص...":
            custom_activity = st.text_input("اكتب اسم النشاط الجديد هنا:")
        duration_hours = st.number_input("المدة (بالساعات)", min_value=0.1, max_value=24.0, value=1.0, step=0.5)
    with c2:
        target_date = st.date_input("اختر التاريخ من التقويم 📅", value=now.date())
    with c3:
        st.markdown("<label style='font-size:14px; font-weight:bold; color:#333;'>اضبط وقت النشاط بدقة ⌚</label>", unsafe_allow_html=True)
        
        # ⌚ ساعة دائرية متطورة وتفاعلية مدمجة للويب تعمل بشكل مثالي ومستقر
        clock_html = f"""
        <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; font-family:sans-serif; padding-top:5px;">
            <input type="time" id="analog_picker" value="{chosen_time_str}" 
                   style="font-size: 22px; padding: 10px; border-radius: 8px; border: 2px solid #40c463; text-align: center; width: 180px; background: #fff; cursor: pointer; font-weight:bold; color:#216e39;">
            <p style="font-size:12px; color:#555; margin-top:8px; text-align:center;">اضغط على التوقيت أعلاه لتظهر لك نافذة الساعة الدائرية الرائعة</p>
        </div>
        <script>
            var picker = document.getElementById('analog_picker');
            function sendValue() {{
                window.parent.postMessage({{type: 'streamlit:setComponentValue', value: picker.value}}, '*');
            }}
            picker.addEventListener('input', sendValue);
            picker.addEventListener('change', sendValue);
            // إرسال القيمة الافتراضية عند التحميل
            setTimeout(sendValue, 300);
        </script>
        """
        clock_return = components.html(clock_html, height=110)
        if clock_return:
            chosen_time_str = str(clock_return)

if st.button("➕ تسجيل النشاط وحفظه تلقائياً", use_container_width=True, type="primary"):
    if selected_activity == "➕ إضافة نشاط مخصص...":
        if 'custom_activity' in locals() and custom_activity.strip() != "":
            final_activity = custom_activity.strip()
        else:
            st.error("يرجى كتابة اسم النشاط المخصص أولاً!")
            st.stop()
    else:
        final_activity = selected_activity

    if auto_time:
        target_time = now.time()
    else:
        try:
            t_parts = chosen_time_str.split(":")
            target_time = datetime.time(int(t_parts[0]), int(t_parts[1]))
        except:
            target_time = now.time()

    combined_datetime = datetime.datetime.combine(target_date, target_time)
    
    exact_timestamp = combined_datetime.strftime('%Y-%m-%d %H:%M:%S')
    saved_year = combined_datetime.year
    saved_month = months_list[combined_datetime.month - 1]
    saved_week = int(combined_datetime.isocalendar().week)
    saved_day = combined_datetime.strftime('%A')
    saved_hour = combined_datetime.strftime('%H:%M')
    
    unique_id = int(datetime.datetime.now().timestamp() * 1000)
    duration_minutes = int(duration_hours * 60)
    
    new_row = {
        'ID': unique_id,
        'التاريخ': exact_timestamp,
        'السنة': int(saved_year),
        'الشهر': str(saved_month),
        'الأسبوع': int(saved_week),
        'اليوم': str(saved_day),
        'الساعة': str(saved_hour),
        'النشاط': str(final_activity),
        'المدة_بالدقائق': duration_minutes
    }
    
    df_db = pd.concat([df_db, pd.DataFrame([new_row])], ignore_index=True)
    save_data(df_db)
    st.session_state.db = df_db
    st.toast(f"✅ تم تسجيل نشاط ({final_activity}) بنجاح!", icon="🔥")
    st.rerun()

# ==========================================
# 4. عرض السجل العام مع الحذف والتصدير
# ==========================================
if not df_db.empty:
    st.markdown("---")
    st.subheader("📋 سجل التحكم بالبيانات وحذف الأسطر")
    
    display_df = df_db.copy()
    display_df['حذف؟'] = False
    display_df['المدة (ساعات)'] = round(display_df['المدة_بالدقائق'] / 60, 2)
    
    cols = ['حذف؟', 'التاريخ', 'النشاط', 'المدة (ساعات)', 'اليوم', 'الساعة']
    display_df = display_df[[c for c in cols if c in display_df.columns]]
    
    edited_display = st.data_editor(
        display_df,
        column_config={"حذف؟": st.column_config.CheckboxColumn("إجراء الحذف", default=False)},
        disabled=[col for col in display_df.columns if col != 'حذف؟'],
        hide_index=True,
        use_container_width=True,
        key="data_editor_delete"
    )
    
    indices_to_delete = edited_display[edited_display['حذف؟'] == True].index
    
    if len(indices_to_delete) > 0:
        if st.button("🗑️ تأكيد حذف الأنشطة المحددة", type="primary"):
            df_db = df_db.drop(indices_to_delete).reset_index(drop=True)
            save_data(df_db)
            st.session_state.db = df_db
            st.toast("تم حذف الأنشطة المحددة!", icon="🗑️")
            st.rerun()

    st.markdown("---")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        clean_excel_df = df_db[[c for c in COLUMNS if c in df_db.columns]].copy()
        clean_excel_df.drop(columns=['ID'], errors='ignore').to_excel(writer, index=False, sheet_name='الأنشطة اليومية')
        workbook  = writer.book
        worksheet = writer.sheets['الأنشطة اليومية']
        worksheet.views.sheetView[0].showGridLines = True
        worksheet.sheet_view.rightToLeft = True 

    st.download_button(
        label="📥 تحميل سجل تمارينك كملف Excel منسق",
        data=buffer.getvalue(),
        file_name="my_gym_activities.xlsx",
        mime="application/vnd.ms-excel",
        use_container_width=True
    )
    
    st.markdown("---")
    if st.button("🚨 مسح السجل بالكامل والبدء من جديد"):
        sheet.clear()
        sheet.append_row(COLUMNS)
        st.cache_data.clear()
        st.session_state.db = pd.DataFrame(columns=COLUMNS)
        st.success("تم تصفير قاعدة البيانات بالكامل!")
        st.rerun()
