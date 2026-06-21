import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection

# إعدادات الصفحة
st.set_page_config(page_title="متابع الأنشطة اليومية السحابي", layout="wide")
st.title("📊 نظام متابعة الأنشطة (متصل بـ Google Sheets)")

# إنشاء الاتصال بـ Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# دالة تحميل البيانات
def load_data():
    try:
        df = conn.read(worksheet="Sheet1", ttl="10m")
        df = df.dropna(how="all")
        return df
    except Exception as e:
        st.error(f"حدث خطأ أثناء تحميل البيانات: {e}")
        return pd.DataFrame(columns=['ID', 'التاريخ', 'السنة', 'الشهر', 'الأسبوع', 'اليوم', 'الساعة', 'النشاط'])

# دالة حفظ البيانات
def save_data(df):
    conn.update(worksheet="Sheet1", data=df)

# تحميل البيانات في الجلسة
if 'db' not in st.session_state:
    st.session_state.db = load_data()

df_db = st.session_state.db

# ==========================================
# 1. قسم الإحصائيات
# ==========================================
st.subheader("📈 لوحة الإحصائيات")
if not df_db.empty:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("إجمالي النادي", len(df_db[df_db['النشاط'] == 'النادي 🏋️‍♂️']))
    with col2:
        st.metric("إجمالي الدراسة", len(df_db[df_db['النشاط'] == 'الدراسة 📚']))
    with col3:
        st.metric("إجمالي العمل", len(df_db[df_db['النشاط'] == 'العمل 💼']))
else:
    st.info("لا توجد بيانات حالياً.")

st.markdown("---")

# ==========================================
# 2. قسم الإدخال
# ==========================================
st.subheader("📥 تسجيل نشاط جديد")

c1, c2, c3, c4, c5 = st.columns(5)
with c1: selected_activity = st.selectbox("النشاط", ["النادي 🏋️‍♂️", "الدراسة 📚", "العمل 💼"])
with c2: selected_year = st.selectbox("السنة", [2026, 2027])
with c3: selected_month = st.selectbox("الشهر", ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])
with c4: selected_day = st.selectbox("اليوم", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
with c5: selected_hour = st.selectbox("الساعة", [f"{str(i).zfill(2)}:00" for i in range(24)])

if st.button("➕ تسجيل النشاط"):
    # تعريف المتغير داخل النطاق الصحيح
    new_row = {
        'ID': int(datetime.datetime.now().timestamp() * 1000),
        'التاريخ': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'السنة': selected_year,
        'الشهر': selected_month,
        'الأسبوع': datetime.datetime.now().isocalendar().week,
        'اليوم': selected_day,
        'الساعة': selected_hour,
        'النشاط': selected_activity
    }
    
    # دمج البيانات
    new_df = pd.concat([st.session_state.db, pd.DataFrame([new_row])], ignore_index=True)
    
    # الحفظ في السحابة
    save_data(new_df)
    st.session_state.db = new_df
    st.success("تم الحفظ في Google Sheets بنجاح!")
    st.rerun()

# ==========================================
# 3. قسم إدارة البيانات
# ==========================================
if not st.session_state.db.empty:
    st.subheader("📋 سجل الأنشطة")
    edited_df = st.data_editor(st.session_state.db, use_container_width=True)
    
    if st.button("🔄 حفظ التعديلات أو الحذف"):
        save_data(edited_df)
        st.session_state.db = edited_df
        st.success("تم تحديث السجلات في Google Sheets!")
        st.rerun()
