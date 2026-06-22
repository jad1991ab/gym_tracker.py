import streamlit as st
import pandas as pd
import gspread
import datetime
import io
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

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


if len(sheet.get_all_values()) == 0:

    sheet.append_row([
        'ID',
        'التاريخ',
        'السنة',
        'الشهر',
        'الأسبوع',
        'اليوم',
        'الساعة',
        'النشاط'
    ])

# إعدادات الصفحة
st.set_page_config(page_title="متابع الأنشطة اليومية المطور", layout="wide")
st.title("📊 نظام متابعة وإحصائيات الأنشطة اليومية")



# دالة لتحميل البيانات المخزنة أو إنشاء ملف جديد إذا لم يوجد
def load_data():

    try:

        records = sheet.get_all_records()

        if len(records) == 0:

            return pd.DataFrame(
                columns=[
                    'ID',
                    'التاريخ',
                    'السنة',
                    'الشهر',
                    'الأسبوع',
                    'اليوم',
                    'الساعة',
                    'النشاط'
                ]
            )

        return pd.DataFrame(records)

        

    except Exception as e:

        st.error(f"خطأ أثناء قراءة Google Sheet: {e}")

        return pd.DataFrame(
            columns=[
                'ID',
                'التاريخ',
                'السنة',
                'الشهر',
                'الأسبوع',
                'اليوم',
                'الساعة',
                'النشاط'
            ]
        )



def save_data(df):

    sheet.clear()

    set_with_dataframe(
        sheet,
        df,
        include_index=False,
        include_column_header=True,
        resize=True
    )

# تحميل البيانات في الجلسة
if 'db' not in st.session_state:
    st.session_state.db = load_data()

df_db = st.session_state.db

# ==========================================
# 1. قسم الإحصائيات (أعلى الصفحة)
# ==========================================
st.subheader("📈 لوحة الإحصائيات العامة")

if not df_db.empty:
    now = datetime.datetime.now()
    current_year = now.year
    current_month = now.strftime('%B')
    current_week = now.isocalendar().week

    # حساب العدادات
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 🏋️‍♂️ النادي")
        total_gym = len(df_db[df_db['النشاط'] == 'النادي 🏋️‍♂️'])
        month_gym = len(df_db[(df_db['النشاط'] == 'النادي 🏋️‍♂️') & (df_db['الشهر'] == current_month) & (df_db['السنة'] == current_year)])
        week_gym = len(df_db[(df_db['النشاط'] == 'النادي 🏋️‍♂️') & (df_db['الأسبوع'] == current_week) & (df_db['السنة'] == current_year)])
        st.metric("إجمالي السنة", f"{total_gym} مرة")
        st.caption(f"هذا الشهر: {month_gym} | هذا الأسبوع: {week_gym}")

    with col2:
        st.markdown("### 📚 الدراسة")
        total_study = len(df_db[df_db['النشاط'] == 'الدراسة 📚'])
        month_study = len(df_db[(df_db['النشاط'] == 'الدراسة 📚') & (df_db['الشهر'] == current_month) & (df_db['السنة'] == current_year)])
        week_study = len(df_db[(df_db['النشاط'] == 'الدراسة 📚') & (df_db['الأسبوع'] == current_week) & (df_db['السنة'] == current_year)])
        st.metric("إجمالي السنة", f"{total_study} مرة")
        st.caption(f"هذا الشهر: {month_study} | هذا الأسبوع: {week_study}")

    with col3:
        st.markdown("### 💼 العمل")
        total_work = len(df_db[df_db['النشاط'] == 'العمل 💼'])
        month_work = len(df_db[(df_db['النشاط'] == 'العمل 💼') & (df_db['الشهر'] == current_month) & (df_db['السنة'] == current_year)])
        week_work = len(df_db[(df_db['النشاط'] == 'العمل 💼') & (df_db['الأسبوع'] == current_week) & (df_db['السنة'] == current_year)])
        st.metric("إجمالي السنة", f"{total_work} مرة")
        st.caption(f"هذا الشهر: {month_work} | هذا الأسبوع: {week_work}")
        
    # رسم بياني للمقارنة بين الأنشطة
    st.markdown("#### مقارنة الأنشطة شهرياً")
    summary = df_db.groupby(['الشهر', 'النشاط']).size().unstack(fill_value=0)
    st.bar_chart(summary)
else:
    st.info("لا توجد بيانات مسجلة بعد. قم بإدخال أول نشاط لك من القوائم أدناه لتظهر الإحصائيات هنا.")

st.markdown("---")

# ==========================================
# 2. قسم إدخال البيانات (Drop Menus المطور)
# ==========================================
st.subheader("📥 تسجيل نشاط جديد")

this_year = datetime.datetime.now().year
years_list = list(range(this_year, this_year + 21))
months_list = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
days_list = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
hours_list = [f"{str(i).zfill(2)}:00" for i in range(24)]
activities_list = ["النادي 🏋️‍♂️", "الدراسة 📚", "العمل 💼"]

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    selected_activity = st.selectbox("النشاط", activities_list)
with c2:
    selected_year = st.selectbox("السنة", years_list, index=0) 
with c3:
    current_month_name = datetime.datetime.now().strftime('%B')
    default_month_idx = months_list.index(current_month_name) if current_month_name in months_list else 0
    selected_month = st.selectbox("الشهر", months_list, index=default_month_idx)
with c4:
    current_day_name = datetime.datetime.now().strftime('%A')
    default_day_idx = days_list.index(current_day_name) if current_day_name in days_list else 0
    selected_day = st.selectbox("اليوم", days_list, index=default_day_idx)
with c5:
    selected_hour = st.selectbox("الساعة", hours_list, index=16)

# زر الحفظ
if st.button("➕ تسجيل النشاط وحفظه", use_container_width=True):
    month_num = months_list.index(selected_month) + 1
    try:
        approx_date = datetime.datetime(selected_year, month_num, 1)
        week_num = approx_date.isocalendar().week
    except:
        week_num = datetime.datetime.now().isocalendar().week
    
    # توليد معرف فريد يعتمد على الوقت الحالي
    unique_id = int(datetime.datetime.now().timestamp() * 1000)
    
    new_row = {
        'ID': unique_id,
        'التاريخ': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'السنة': selected_year,
        'الشهر': selected_month,
        'الأسبوع': week_num,
        'اليوم': selected_day,
        'الساعة': selected_hour,
        'النشاط': selected_activity
    }
    
    df_db = pd.concat([df_db, pd.DataFrame([new_row])], ignore_index=True)
    save_data(df_db)
    st.session_state.db = df_db
    st.success(f"تم تسجيل نشاط ({selected_activity}) بنجاح!")
    st.rerun()

# ==========================================
# 3. عرض السجل مع خاصية حذف سطر معين والتصدير
# ==========================================
if not df_db.empty:
    st.markdown("---")
    st.subheader("📋 إدارة وحذف الأنشطة المدخلة")
    
    # تحضير جدول تفاعلي يحتوي على خانة اختيار للحذف (Delete)
    # نقوم بعمل نسخة للعرض فقط بدون إظهار عمود الـ ID الداخلي للمستخدم
    display_df = df_db.copy()
    display_df['حذف؟'] = False
    
    # إعادة الترتيب ليظهر عمود الحذف كأول عمود تفاعلي
    cols = ['حذف؟'] + [col for col in display_df.columns if col not in ['حذف؟', 'ID']]
    display_df = display_df[cols]
    
    st.write("إذا أردت حذف أي نشاط، ضع علامة (صح) بجانبه في الجدول أدناه ثم اضغط على زر 'تأكيد حذف الأنشطة المحددة':")
    
    edited_display = st.data_editor(
        display_df,
        column_config={
            "حذف؟": st.column_config.CheckboxColumn("إجراء الحذف", help="حدد الخانة لحذف هذا السطر", default=False)
        },
        disabled=[col for col in display_df.columns if col != 'حذف؟'], # منع تعديل باقي البيانات
        hide_index=True,
        use_container_width=True,
        key="data_editor_delete"
    )
    
    # زر تفعيل الحذف للأسطر المحددة
    indices_to_delete = edited_display[edited_display['حذف؟'] == True].index
    
    if len(indices_to_delete) > 0:
        if st.button("🗑️ تأكيد حذف الأنشطة المحددة", type="primary"):
            # تحديد وحذف الأسطر المقابلة في قاعدة البيانات الأصلية
            df_db = df_db.drop(indices_to_delete).reset_index(drop=True)
            save_data(df_db)
            st.session_state.db = df_db
            st.success("تم حذف الأنشطة المحددة بنجاح!")
            st.rerun()

    st.markdown("---")
    # زر تصدير ملف إكسل منسق جاهز ومصلح من اليمين لليسار تلقائياً
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        # تصدير البيانات بدون عمود الـ ID
        df_db.drop(columns=['ID'], errors='ignore').to_excel(writer, index=False, sheet_name='الأنشطة اليومية')
        workbook  = writer.book
        worksheet = writer.sheets['الأنشطة اليومية']
        worksheet.views.sheetView[0].showGridLines = True
        worksheet.sheet_view.rightToLeft = True 

    st.download_button(
        label="📥 تحميل سجل تمارينك كملف Excel منسق جاهز ومصلح",
        data=buffer.getvalue(),
        file_name="my_gym_activities.xlsx",
        mime="application/vnd.ms-excel",
        use_container_width=True
    )
    
    st.markdown("---")

    if st.button("🚨 مسح السجل بالكامل والبدء من جديد"):

        sheet.clear()

        sheet.append_row([
            'ID',
            'التاريخ',
            'السنة',
            'الشهر',
            'الأسبوع',
            'اليوم',
            'الساعة',
            'النشاط'
        ])

        st.session_state.db = pd.DataFrame(
            columns=[
                'ID',
                'التاريخ',
                'السنة',
                'الشهر',
                'الأسبوع',
                'اليوم',
                'الساعة',
                'النشاط'
            ]
        )

        st.success("تم مسح البيانات بالكامل!")

        st.rerun()
