import streamlit as st
import fitz  # PyMuPDF
import easyocr
import pandas as pd
from PIL import Image
import io
import os
import ssl
import sys
import re

# Reconfigure stdout/stderr to UTF-8 to prevent Windows character mapping (UnicodeEncodeError) issues
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
if sys.stderr is not None:
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Bypass SSL certificate verification for model downloads
ssl._create_default_https_context = ssl._create_unverified_context

# Set page configuration to wide layout and modern page title
st.set_page_config(
    page_title="PDF OCR & Text Extractor",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for modern premium look
st.markdown("""
<style>
    .main {
        background-color: #f8f9fa;
    }
    .stButton>button {
        background-color: #0F52BA;
        color: white;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
        border: none;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #1e6bf2;
        box-shadow: 0 4px 12px rgba(15, 82, 186, 0.2);
        transform: translateY(-1px);
    }
    .header-container {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        padding: 2.5rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }
    .header-title {
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    .header-subtitle {
        font-size: 1.1rem;
        opacity: 0.9;
    }
    .card {
        background-color: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.04);
        margin-bottom: 1.5rem;
    }
    .sidebar-section {
        background-color: #f1f3f5;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# Cache EasyOCR Reader to avoid reloading it on every run
@st.cache_resource(show_spinner="กำลังโหลดโมเดล OCR (ภาษาไทย/อังกฤษ)...")
def load_ocr_reader(langs):
    # langs is a tuple to ensure it is hashable for caching
    return easyocr.Reader(list(langs), verbose=False)

# Header
st.markdown("""
<div class="header-container">
    <div class="header-title">📄 PDF OCR & Text Extractor</div>
    <div class="header-subtitle">แปลงไฟล์เอกสาร PDF เป็นข้อความภาษาไทยและอังกฤษได้อย่างง่ายดายด้วย AI OCR ประสิทธิภาพสูง</div>
</div>
""", unsafe_allow_html=True)

# Sidebar configurations
st.sidebar.markdown("### ⚙️ การตั้งค่าระบบ (Settings)")

# Select languages
lang_options = {
    "ไทย + English": ("th", "en"),
    "ภาษาไทยอย่างเดียว": ("th",),
    "English Only": ("en",)
}
selected_lang_label = st.sidebar.selectbox(
    "ภาษาที่ต้องการอ่าน (Languages)",
    options=list(lang_options.keys())
)
langs = lang_options[selected_lang_label]

# Extraction Mode
mode = st.sidebar.radio(
    "โหมดการดึงข้อความ (Extraction Mode)",
    options=["Smart Mode (ดึงข้อความปกติก่อน / ใช้ OCR เมื่อเป็นรูปภาพ)", "OCR Only (ใช้ OCR สแกนรูปภาพทุกหน้า)"],
    index=0
)
force_ocr = "OCR Only" in mode

# File uploader
uploaded_file = st.sidebar.file_uploader("อัปโหลดไฟล์ PDF ของคุณที่นี่", type=["pdf"])

import re

def normalize_thai_text(text):
    if not text:
        return text
    
    # 1. Combine นฤคหิต (ํ) + สระอา (า) into สระอำ (ำ)
    # \u0e4d = ํ, \u0e32 = า, \u0e33 = ำ
    text = re.sub(r'\u0e4d\s*\u0e32', '\u0e33', text)
    
    # 2. Combine เ + เ into แ (เเ -> แ)
    text = re.sub(r'\u0e40\s*\u0e40', '\u0e41', text)
    
    # 3. Remove spaces before tone marks and upper/lower vowels
    # Upper/lower vowels and tone marks: ไม้หันอากาศ, สระอิ, สระอี, สระอึ, สระอือ, ไม้ไต่คู้, สระอุ, สระอู, ไม้เอก, ไม้โท, ไม้ตรี, ไม้จัตวา, การันต์
    text = re.sub(r'\s+([\u0e31\u0e34-\u0e39\u0e47-\u0e4c])', r'\1', text)
    
    # 4. Advanced: Fix common business/company terms and split "ำ" errors (e.g. "จ ากัด" -> "จำกัด")
    # - "จ ากัด", "จากัด", "จ ำกัด" -> "จำกัด"
    text = re.sub(r'จ\s*[าำ]\s*ก\s*ั\s*ด', 'จำกัด', text)
    
    # - "มหาชน" split -> "มหาชน"
    text = re.sub(r'ม\s*ห\s*า\s*ช\s*น', 'มหาชน', text)
    
    # - "บริษัท" split -> "บริษัท"
    text = re.sub(r'บ\s*ร\s*ิ\s*ษ\s*ั\s*ท', 'บริษัท', text)
    
    # - "ผลิตภัณฑ์" split -> "ผลิตภัณฑ์"
    text = re.sub(r'ผ\s*ล\s*ิ\s*ต\s*ภ\s*ั\s*ณ\s*ฑ\s*์', 'ผลิตภัณฑ์', text)
    
    # - "อาหาร" split -> "อาหาร"
    text = re.sub(r'อ\s*า\s*ห\s*า\s*ร', 'อาหาร', text)
    
    # - "กว้างไพศาล" split -> "กว้างไพศาล"
    text = re.sub(r'ก\s*ว\s*้\s*า\s*ง\s*ไ\s*พ\s*ศ\s*า\s*ล', 'กว้างไพศาล', text)
    
    # 5. General spacing fixes for Thai words split with single character spaces
    # E.g. "ป ล า" -> "ปลา" or "ก า ร" -> "การ" or "ท า" -> "ทำ"
    # Remove spacing inside consonant + space + ำ
    text = re.sub(r'([ก-ฮ][\u0e31\u0e34-\u0e37\u0e47-\u0e4c]?)\s+ำ', r'\1ำ', text)
    
    return text

def extract_text_from_pdf_page(page, page_num, force_ocr, reader):
    """Extracts text from a single PDF page. Uses direct text extraction or OCR."""
    # Attempt direct text extraction first
    direct_text = page.get_text().strip()
    
    if direct_text and not force_ocr:
        return normalize_thai_text(direct_text), "Direct Text Extraction"
    
    # Render page as image for OCR
    pix = page.get_pixmap(dpi=150)
    img_data = pix.tobytes("png")
    image = Image.open(io.BytesIO(img_data))
    
    # Run EasyOCR
    result = reader.readtext(image, detail=0)
    ocr_text = "\n".join(result)
    
    return normalize_thai_text(ocr_text), "AI OCR Engine"

if uploaded_file is not None:
    # Read PDF using PyMuPDF
    pdf_bytes = uploaded_file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    num_pages = len(doc)
    
    st.sidebar.success(f"โหลดไฟล์สำเร็จ: {uploaded_file.name} ({num_pages} หน้า)")
    
    # Load OCR Reader
    reader = load_ocr_reader(langs)
    
    # Initialize session state for storing edited extracted text
    if "extracted_texts" not in st.session_state or st.session_state.get("file_name") != uploaded_file.name:
        st.session_state["extracted_texts"] = {}
        st.session_state["extraction_methods"] = {}
        st.session_state["file_name"] = uploaded_file.name
    
    # Layout tabs
    tab1, tab2 = st.tabs(["🔍 ดูทีละหน้าและแก้ไข (Interactive View)", "⚡ ประมวลผลทั้งหมด (Bulk Process)"])
    
    with tab1:
        st.write("---")
        # Page selector
        page_num = st.number_input("เลือกหน้าที่ต้องการตรวจสอบ (Page)", min_value=1, max_value=num_pages, value=1, step=1) - 1
        
        # Load PDF Page
        page = doc[page_num]
        
        # UI Columns
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown(f"#### 📄 ภาพหน้าเอกสาร (Page Preview - {page_num + 1})")
            # Render page to display in Streamlit
            pix = page.get_pixmap(dpi=120)
            img_data = pix.tobytes("png")
            st.image(img_data, use_container_width=True)
            
        with col2:
            st.markdown(f"#### ✍️ ข้อความที่สกัดได้ (Extracted Text)")
            
            # Action button to extract/re-run for this page
            btn_extract = st.button("ประมวลผลหน้านี้ (Run Extraction)")
            
            # Perform extraction if requested or if not cached
            if btn_extract or page_num not in st.session_state["extracted_texts"]:
                with st.spinner("กำลังดึงข้อมูลข้อความ..."):
                    text, method = extract_text_from_pdf_page(page, page_num, force_ocr, reader)
                    st.session_state["extracted_texts"][page_num] = text
                    st.session_state["extraction_methods"][page_num] = method
            
            extracted_text = st.session_state["extracted_texts"].get(page_num, "")
            method_used = st.session_state["extraction_methods"].get(page_num, "-")
            
            st.info(f"วิธีการสกัดข้อความ: **{method_used}**")
            
            # Editable Text Area for the user to make corrections
            edited_text = st.text_area(
                "คุณสามารถแก้ไขข้อความที่ได้ด้านล่างนี้ได้โดยตรง:",
                value=extracted_text,
                height=450,
                key=f"text_area_{page_num}"
            )
            # Update state on edit
            st.session_state["extracted_texts"][page_num] = edited_text
            
            # Download current page option
            st.download_button(
                label="📥 ดาวน์โหลดข้อความหน้านี้ (.txt)",
                data=edited_text,
                file_name=f"{os.path.splitext(uploaded_file.name)[0]}_page_{page_num+1}.txt",
                mime="text/plain"
            )
            
    with tab2:
        st.write("---")
        st.markdown("### ⚡ ประมวลผลและสกัดข้อความทั้งไฟล์")
        st.write("ระบบจะทำการสแกนและสกัดข้อความจากเอกสาร PDF ทุกหน้าตามการตั้งค่าของคุณ")
        
        col_run, col_status = st.columns([1, 2])
        
        with col_run:
            run_all_btn = st.button("🚀 เริ่มประมวลผลทุกหน้า (Process All Pages)", key="run_all")
            
        if run_all_btn:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i in range(num_pages):
                status_text.text(f"กำลังประมวลผล หน้าที่ {i+1} จากทั้งหมด {num_pages} หน้า...")
                page = doc[i]
                text, method = extract_text_from_pdf_page(page, i, force_ocr, reader)
                st.session_state["extracted_texts"][i] = text
                st.session_state["extraction_methods"][i] = method
                progress_bar.progress((i + 1) / num_pages)
                
            status_text.text("🎉 ประมวลผลหน้าเอกสารทั้งหมดเรียบร้อยแล้ว!")
            st.balloons()
            
        # Check if we have any processed pages to display/download
        if len(st.session_state["extracted_texts"]) > 0:
            st.write("---")
            st.markdown("### 📥 ส่งออกข้อมูล (Export Results)")
            
            # Create a dataframe for preview and excel download
            data_rows = []
            full_text_list = []
            
            # Loop through sorted pages in session state
            for i in sorted(st.session_state["extracted_texts"].keys()):
                page_text = st.session_state["extracted_texts"][i]
                data_rows.append({
                    "Page": i + 1,
                    "Text": page_text,
                    "Extraction Method": st.session_state["extraction_methods"].get(i, "N/A")
                })
                full_text_list.append(f"--- PAGE {i+1} ---\n{page_text}")
                
            df = pd.DataFrame(data_rows)
            full_combined_text = "\n\n".join(full_text_list)
            
            # Show interactive data frame preview
            st.dataframe(df[["Page", "Text", "Extraction Method"]], use_container_width=True, height=250)
            
            # Export buttons side by side
            exp_col1, exp_col2 = st.columns(2)
            
            with exp_col1:
                st.download_button(
                    label="📄 ดาวน์โหลดข้อความทั้งหมด (.txt)",
                    data=full_combined_text,
                    file_name=f"{os.path.splitext(uploaded_file.name)[0]}_full_extracted.txt",
                    mime="text/plain"
                )
                
            with exp_col2:
                # Convert DataFrame to Excel in memory
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name="OCR_Results")
                excel_data = excel_buffer.getvalue()
                
                st.download_button(
                    label="📊 ดาวน์โหลดตารางข้อมูลทั้งหมด (.xlsx)",
                    data=excel_data,
                    file_name=f"{os.path.splitext(uploaded_file.name)[0]}_OCR_Results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            st.write("---")
            st.markdown("### 🟢 ส่งข้อมูลไป Google Sheets (Export to Google Sheets)")
            
            # Google Sheets URL input
            gsheets_url = st.text_input(
                "กรอก URL ของ Google Sheets Web App:",
                placeholder="https://script.google.com/macros/s/.../exec"
            )
            
            with st.expander("💡 วิธีการตั้งค่า Google Sheets เพื่อรับข้อมูล (คลิกเพื่อดูวิธีทำ)"):
                st.markdown("""
                1. เปิด **Google Sheets** ที่คุณต้องการส่งข้อมูลไปเก็บ
                2. เลือกเมนู **Extensions (ส่วนขยาย)** -> **Apps Script**
                3. ลบโค้ดเดิมทั้งหมดในหน้านั้นออก แล้วคัดลอกโค้ดด้านล่างนี้ไปวาง:
                
                ```javascript
                function doPost(e) {
                  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
                  try {
                    var data = JSON.parse(e.postData.contents);
                    var rows = data.rows;
                    
                    // เพิ่มแถวหัวตารางหากแผ่นงานยังไม่มีข้อมูล
                    if (sheet.getLastRow() == 0) {
                      sheet.appendRow(["หน้า (Page)", "ข้อความ (Text)", "วิธีการสกัด (Method)", "วันที่อัปเดต (Timestamp)"]);
                    }
                    
                    // วนลูปบันทึกข้อมูลทุกหน้า
                    for (var i = 0; i < rows.length; i++) {
                      sheet.appendRow([
                        rows[i].page,
                        rows[i].text,
                        rows[i].method,
                        new Date()
                      ]);
                    }
                    
                    return ContentService.createTextOutput(JSON.stringify({"status": "success", "message": "บันทึกเรียบร้อย"}))
                      .setMimeType(ContentService.MimeType.JSON);
                  } catch (error) {
                    return ContentService.createTextOutput(JSON.stringify({"status": "error", "message": error.toString()}))
                      .setMimeType(ContentService.MimeType.JSON);
                  }
                }
                ```
                
                4. กดปุ่ม 💾 **บันทึกโครงงาน (Save Project)** ด้านบน
                5. กดปุ่ม **Deploy (การทำงานใช้จริง)** -> **New deployment (การทำงานใช้จริงใหม่)**
                6. คลิกปุ่มฟันเฟืองเลือกประเภทเป็น **Web app (เว็บแอป)**
                7. ตั้งค่าการตั้งค่าต่อไปนี้:
                   - **Execute as (รันในฐานะ):** เลือกบัญชี Google ของคุณ (Me)
                   - **Who has access (ผู้ที่มีสิทธิ์เข้าถึง):** เลือก **Anyone (ทุกคน)** (ขั้นตอนนี้สำคัญมากเพื่อให้แอปส่งข้อมูลได้)
                8. กดปุ่ม **Deploy**
                9. หากระบบขออนุญาตสิทธิ์เข้าถึง (Authorization Required) ให้กด **Authorize Access (อนุญาตการเข้าถึง)** -> เลือกบัญชี Google ของคุณ -> กด **Advanced (ขั้นสูง)** -> กด **Go to Untitled project (unsafe)** -> กด **Allow (อนุญาต)**
                10. คัดลอก **Web App URL** ที่ได้ (ลงท้ายด้วย `/exec`) มาวางในช่องด้านบนของโปรแกรมนี้
                """)
                
            btn_send_gsheet = st.button("📤 ส่งข้อมูลไป Google Sheets (Submit to Google Sheets)")
            
            if btn_send_gsheet:
                if not gsheets_url:
                    st.error("❌ กรุณากรอก URL ของ Google Sheets Web App ก่อนส่งข้อมูล")
                else:
                    with st.spinner("กำลังส่งข้อมูลไปยัง Google Sheets..."):
                        try:
                            import requests
                            import json
                            
                            # Prepare rows data
                            payload = {
                                "rows": [
                                    {
                                        "page": row["Page"],
                                        "text": row["Text"],
                                        "method": row["Extraction Method"]
                                    } for _, row in df.iterrows()
                                ]
                            }
                            
                            response = requests.post(
                                gsheets_url,
                                data=json.dumps(payload),
                                headers={"Content-Type": "application/json"}
                            )
                            
                            res_json = response.json()
                            if response.status_code == 200 and res_json.get("status") == "success":
                                st.success("✅ ส่งข้อมูลและบันทึกลงใน Google Sheets เรียบร้อยแล้ว")
                            else:
                                st.error(f"❌ เกิดข้อผิดพลาดจาก Google Sheets: {res_json.get('message', 'ไม่สามารถบันทึกได้')}")
                        except Exception as e:
                            st.error(f"❌ ไม่สามารถเชื่อมต่อกับ Google Sheets ได้: {str(e)} (กรุณาตรวจสอบว่ากรอก URL ถูกต้อง และเปิดสิทธิ์เป็น Anyone แล้ว)")
else:
    # Welcome and usage instructions
    st.info("👈 กรุณาอัปโหลดไฟล์ PDF ในแถบเมนูด้านซ้ายเพื่อเริ่มต้นใช้งานโปรแกรม")
    
    st.markdown("""
    ### 💡 คำแนะนำในการใช้งานระบบ:
    1. **เลือกภาษาให้เหมาะสม**:
       - หากเอกสารมีภาษาไทยเป็นหลัก ให้เลือกภาษา **ไทย + English** หรือ **ภาษาไทยอย่างเดียว**
       - หากเอกสารเป็นภาษาอังกฤษล้วน ให้เลือก **English Only** เพื่อให้โมเดลประมวลผลได้อย่างแม่นยำและรวดเร็วที่สุด
    2. **สแกนได้ทั้งสองแบบ**:
       - **Smart Mode**: หากเอกสาร PDF มีข้อความดิจิทัลอยู่แล้ว ระบบจะดึงออกมาทันทีด้วยความเร็วสูงและถูกต้อง 100% แต่ถ้าเอกสารเป็นสแกนรูปภาพหรือภาพถ่าย ระบบจะเปลี่ยนไปใช้ AI OCR โดยอัตโนมัติ
       - **OCR Only**: เหมาะสำหรับเอกสารที่ต้องการบังคับให้ AI สแกนทุกตัวอักษรจากภาพโดยตรง
    3. **ความถูกต้องและปลอดภัย**:
       - โปรแกรมนี้ทำงานแบบ **Offline** 100% (บนเครื่องคอมพิวเตอร์ของคุณ) ข้อมูลและความลับของเอกสารจะไม่ถูกส่งไปภายนอกแน่นอน
    """)
    
    # Image mockup to wow user visually if they have not uploaded anything
    st.image("https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=1000&auto=format&fit=crop", caption="OCR & Digital Document Archiving System", use_container_width=True)
