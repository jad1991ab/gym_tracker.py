import streamlit as st
import pandas as pd
import gspread
import datetime
import io
import plotly.express as px
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

# إعدادات الصفحة (يجب أن تكون في أول السطر)
st.set_page_config(page_title="متابع الأنشطة الذكي", layout="wide", page_icon="📊")

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

# الأعمدة المحدثة لتشمل المدة بالدقائق
COLUMNS = ['ID', 'التاريخ', 'السنة', 'الشهر', 'الأسبوع', 'اليوم', 'الساعة', 'النشاط', 'المدة_بالدقائق']

# التحقق من الهيكل الأولي للجداول لتقليل استهلاك الـ API
try:
    first_row = sheet.row_values(1)
    if not first_row:
        sheet.append_row(COLUMNS)
except Exception as e:
    st.error(f"خطأ في الاتصال الأولي بقاعدة البيانات: {e}")

st.title("📊 نظام متابعة وإحصائيات الأنشطة اليومية الذكي")

# استخدام الكاش وتسريعه لـ 10 دقائق
@st.cache_data(ttl=600)
def load_data():
    try:
        records = sheet.get_all_records()
        if len(records) == 0:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.DataFrame(records)
        # التأكد من وجود عمود المدة في البيانات القديمة إن وجدت
        if 'المدة_بالدقائق' not in df.columns:
            df['المدة_بالدقائق'] = 60 # قيمة افتراضية للبيانات القديمة
        return df
    except Exception as e:
        st.error(f"خطأ أثناء قراءة Google Sheet: {e}")
        return pd.DataFrame(columns=COLUMNS)

def save_data(df):
    try:
        sheet.clear()
        set_with_dataframe(sheet, df, include_index=False, include_column_header=True, resize=True)
        st.cache_data.clear() # تنظيف الكاش فوراً لتحديث الشاشة
    except Exception as e:
        st.error(f"حدث خطأ أثناء حفظ البيانات: {e}")

# تحميل البيانات في الجلسة
if 'db' not in st.session_state:
    st.session_state.db = load_data()

df_db = st.session_state.db

# ==========================================
# 1. شريط التحفيز والتقدم اليومي (جديد)
# ==========================================
now = datetime.datetime.now()
today_str = now.strftime('%Y-%m-%d')
df_db['التاريخ_اليومي'] = df_db['التاريخ'].apply(lambda x: str(x).split(' ')[0])
today_activities = df_db[df_db['التاريخ_اليومي'] == today_str]
total_today_minutes = today_activities['المدة_بالدقائق'].sum()
total_today_hours = round(total_today_minutes / 60, 1)

st.subheader("🎯 مؤشر الإنجاز اليومي")
col_p1, col_p2 = st.columns([4, 1])
with col_p1:
    # هدف يومي افتراضي: ساعتين إنجاز (120 دقيقة)
    progress_percent = min(int((total_today_minutes / 120) * 100), 100)
    st.progress(progress_percent / 100)
with col_p2:
    if total_today_hours >= 2:
        st.success(f"🔥 بطل! أنجزت {total_today_hours} ساعة اليوم")
    else:
        st.info(f"⚡ إنجاز اليوم: {total_today_hours} ساعة")

st.markdown("---")

# ==========================================
# 2. لوحة الإحصائيات العامة والرسوم المتقدمة
# ==========================================
st.subheader("📈 لوحة الإحصائيات والتحليلات")

if not df_db.empty:
    current_year = now.year
    current_month = now.strftime('%B')
    
    try:
        df_db['السنة'] = pd.to_numeric(df_db['السنة'], errors='coerce')
        df_db['الأسبوع'] = pd.to_numeric(df_db['الأسبوع'], errors='coerce')
        df_db['المدة_بالدقائق'] = pd.to_numeric(df_db['المدة_بالدقائق'], errors='coerce')
        current_week = int(now.isocalendar().week)
    except:
        current_week = now.isocalendar().week

    # حساب العدادات بناءً على إجمالي عدد الساعات المستغرقة
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 🏋️‍♂️ النادي")
        gym_df = df_db[df_db['النشاط'] == 'النادي 🏋️‍♂️']
        total_gym_hours = round(gym_df['المدة_بالدقائق'].sum() / 60, 1)
        month_gym = len(gym_df[(gym_df['الشهر'] == current_month) & (gym_df['السنة'] == current_year)])
        st.metric("إجمالي الساعات هذا العام", f"{total_gym_hours} ساعة")
        st.caption(f"عدد المرات هذا الشهر: {month_gym}")

    with col2:
        st.markdown("### 📚 الدراسة")
        study_df = df_db[df_db['النشاط'] == 'الدراسة 📚']
        total_study_hours = round(study_df['المدة_بالدقائق'].sum() / 60, 1)
        month_study = len(study_df[(study_df['الشهر'] == current_month) & (study_df['السنة'] == current_year)])
        st.metric("إجمالي الساعات هذا العام", f"{total_study_hours} ساعة")
        st.caption(f"عدد المرات هذا الشهر: {month_study}")

    with col3:
        st.markdown("### 💼 العمل")
        work_df = df_db[df_db['النشاط'] == 'العمل 💼']
        total_work_hours = round(work_df['المدة_بالدقائق'].sum() / 60, 1)
        month_work = len(work_df[(work_df['الشهر'] == current_month) & (work_df['السنة'] == current_year)])
        st.metric("إجمالي الساعات هذا العام", f"{total_work_hours} ساعة")
        st.caption(f"عدد المرات هذا الشهر: {month_work}")
        
    # الرسوم البيانية المتقدمة باستخدام Plotly
    g_col1, g_col2 = st.columns(2)
    
    with g_col1:
        st.markdown("#### 🔄 نسبة توزيع الأنشطة (حسب الدقائق)")
        fig_pie = px.pie(df_db, names='النشاط', values='المدة_بالدقائق', hole=0.4,
                         color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig_pie, use_container_width=True)
        
    with g_col2:
        st.markdown("#### 📅 حجم الإنجاز الشهري للأنشطة")
        summary = df_db.groupby(['الشهر', 'النشاط'])['المدة_بالدقائق'].sum().unstack(fill_value=0) / 60
        st.bar_chart(summary)
else:
    st.info("لا توجد بيانات مسجلة بعد. قم بإدخال أول نشاط لك من القوائم أدناه لتظهر الإحصائيات هنا.")

st.markdown("---")

# ==========================================
# 3. قسم إدخال البيانات المطور والذكي
# ==========================================
st.subheader("📥 تسجيل نشاط جديد")

# ميزة مذهلة: اختيار التسجيل السريع أو اليدوي
auto_time = st.toggle("التسجيل التلقائي بالوقت الحالي فوراً ⚡", value=True)

activities_list = ["النادي 🏋️‍♂️", "الدراسة 📚", "العمل 💼"]

if auto_time:
    # واجهة مبسطة جداً عند التفعيل التلقائي
    c1, c2 = st.columns(2)
    with c1:
        selected_activity = st.selectbox("النشاط", activities_list)
    with c2:
        duration_hours = st.number_input("مدة النشاط (بالساعات)", min_value=0.1, max_value=24.0, value=1.0, step=0.5)
    
    # تحديد قيم الوقت الحالية برمجياً
    selected_year = now.year
    selected_month = now.strftime('%B')
    selected_day = now.strftime('%A')
    selected_hour = f"{str(now.hour).zfill(2)}:00"
else:
    # إظهار القوائم الكاملة إذا أراد المستخدم تسجيل وقت سابق يدوياً
    this_year = now.year
    years_list = list(range(this_year, this_year + 5))
    months_list = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    days_list = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    hours_list = [f"{str(i).zfill(2)}:00" for i in range(24)]
    
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        selected_activity = st.selectbox("النشاط", activities_list)
    with c2:
        duration_hours = st.number_input("المدة (ساعة)", min_value=0.1, max_value=24.0, value=1.0, step=0.5)
    with c3:
        selected_year = st.selectbox("السنة", years_list, index=0) 
    with c4:
        default_month_idx = months_list.index(selected_month) if selected_month in months_list else 0
        selected_month = st.selectbox("الشهر", months_list, index=default_month_idx)
    with c5:
        default_day_idx = days_list.index(selected_day) if selected_day in days_list else 0
        selected_day = st.selectbox("اليوم", days_list, index=default_day_idx)
    with c6:
        selected_hour = st.selectbox("الساعة", hours_list, index=now.hour)

# زر الحفظ
if st.button("➕ تسجيل النشاط وحفظه", use_container_width=True, type="primary"):
    if auto_time:
        week_num = int(now.isocalendar().week)
        exact_timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
    else:
        try:
            months_list = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
            month_num = months_list.index(selected_month) + 1
            approx_date = datetime.datetime(selected_year, month_num, 1)
            week_num = int(approx_date.isocalendar().week)
        except:
            week_num = int(now.isocalendar().week)
        exact_timestamp = f"{selected_year}-{selected_month}-01 {selected_hour}:00"
    
    unique_id = int(datetime.datetime.now().timestamp() * 1000)
    duration_minutes = int(duration_hours * 60)
    
    new_row = {
        'ID': unique_id,
        'التاريخ': exact_timestamp,
        'السنة': int(selected_year),
        'الشهر': str(selected_month),
        'الأسبوع': int(week_num),
        'اليوم': str(selected_day),
        'الساعة': str(selected_hour),
        'النشاط': str(selected_activity),
        'المدة_بالدقائق': duration_minutes
    }
    
    df_db = pd.concat([df_db, pd.DataFrame([new_row])], ignore_index=True)
    save_data(df_db)
    st.session_state.db = df_db
    st.toast(f"✅ تم تسجيل نشاط ({selected_activity}) بنجاح!", icon="🔥")
    st.rerun()

# ==========================================
# 4. عرض السجل مع الحذف والتصدير
# ==========================================
if not df_db.empty:
    st.markdown("---")
    st.subheader("📋 إدارة وحذف الأنشطة المدخلة")
    
    display_df = df_db.copy()
    display_df['حذف؟'] = False
    
    # تنسيق العرض للمستخدم
    display_df['المدة (ساعات)'] = round(display_df['المدة_بالدقائق'] / 60, 2)
    
    cols = ['حذف؟', 'التاريخ', 'النشاط', 'المدة (ساعات)', 'اليوم', 'الساعة']
    # التأكد من وجود الأعمدة المحددة فقط للعرض الجمالي
    display_df = display_df[[c for c in cols if c in display_df.columns]]
    
    st.write("إذا أردت حذف أي نشاط، ضع علامة (صح) بجانبه ثم اضغط زر الحذف بالأسفل:")
    
    edited_display = st.data_editor(
        display_df,
        column_config={
            "حذف؟": st.column_config.CheckboxColumn("إجراء الحذف", default=False)
        },
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
    # تصدير ملف إكسل مصلح اتجاه اليمين لليسار
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_db.drop(columns=['ID', 'التاريخ_اليومي'], errors='ignore').to_excel(writer, index=False, sheet_name='الأنشطة اليومية')
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
