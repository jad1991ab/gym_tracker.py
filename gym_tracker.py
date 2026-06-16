import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# إعدادات الصفحة لتكون متوافقة مع الموبايل وإغلاق القائمة الجانبية تلقائياً
st.set_page_config(
    page_title="مفكرة التمارين الرياضية السحابية",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# تصميم الواجهة وتنسيق النصوص العربية
st.markdown("<style>h1, h2, h3, p, div { text-align: right; direction: rtl; }</style>", unsafe_allowed_html=True)


st.title("🏋️‍♂️ مفكرة التمارين الرياضية السحابية")
st.subheader("سجل تمارينك من الموبايل وتابعها من كمبيوترك في أي وقت!")

# إنشاء الاتصال بقاعدة البيانات بجوجل شيتس
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    # قراءة البيانات من الورقة الأولى Sheet1
    df = conn.read(worksheet="Sheet1", ttl="5m")
    # تنظيف الخانات الفارغة
    df = df.dropna(how="all")
except Exception as e:
    st.error("🔄 جاري إعداد قاعدة البيانات السحابية أو تحديث الاتصال...")
    df = pd.DataFrame(columns=["المعرف", "التاريخ", "نوع التمرين", "المدة (دقائق)", "ملاحظات"])

# القائمة الجانبية لإدخال البيانات
st.sidebar.header("📝 تسجيل نشاط جديد")

with st.sidebar.form(key="exercise_form"):
    input_date = st.date_input("تاريخ التمرين", datetime.now())
    input_type = st.selectbox("نوع التمرين", ["حديد / مقاومة", "كارديو / جري", "كرة قدم", "سباحة", "مشي", "أخرى"])
    input_duration = st.number_input("المدة (بالدقائق)", min_value=1, max_value=300, value=30)
    input_notes = st.text_area("ملاحظات إضافية...", placeholder="مثال: تمرين رجلين، شدة عالية...")
    
    submit_button = st.form_submit_button(label="💾 حفظ التمرين سحابياً")

# عند الضغط على زر الحفظ
if submit_button:
    try:
        # تجهيز السطر الجديد لتسجيله
        new_id = int(df["المعرف"].max() + 1) if not df.empty and pd.notna(df["المعرف"].max()) else 1
        
        new_row = pd.DataFrame([{
            "المعرف": new_id,
            "التاريخ": input_date.strftime("%Y-%m-%d"),
            "نوع التمرين": input_type,
            "المدة (دقائق)": int(input_duration),
            "ملاحظات": input_notes if input_notes else "-"
        }])
        
        # دمج السطر الجديد مع البيانات السابقة
        updated_df = pd.concat([df, new_row], ignore_index=True)
        
        # تحديث ملف الجوجل شيت سحابياً
        conn.update(worksheet="Sheet1", data=updated_df)
        
        st.sidebar.success("✅ تم حفظ التمرين بنجاح في الـ Google Sheet!")
        # إعادة قراءة البيانات لتحديث الجدول أمام المستخدم
        df = updated_df
    except Exception as error:
        st.sidebar.error(f"حدث خطأ أثناء الحفظ: {error}")

# عرض التمارين المسجلة في الشاشة الرئيسية
st.header("📊 التمارين المسجلة")

if df.empty:
    st.info("💡 لا توجد تمارين مسجلة سحابياً حتى الآن. ابدأ بتسجيل أول تمرين لك من القائمة الجانبية!")
else:
    # ترتيب الجدول ليظهر الأحدث في الأعلى
    df_display = df.copy()
    if "المعرف" in df_display.columns:
        df_display = df_display.sort_values(by="المعرف", ascending=False)
    
    # عرض الجدول داخل الموقع بتنسيق جميل
    st.dataframe(df_display, use_container_width=True, hide_index=True)
