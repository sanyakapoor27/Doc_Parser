import streamlit as st
import google.generativeai as genai
from io import BytesIO
import base64
import tempfile
from google.generativeai import types
from PIL import Image
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.enum.table import WD_TABLE_ALIGNMENT
import re
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Streamlit page config
import streamlit as st
from PIL import Image

st.set_page_config(
    page_title="Disaster Situation Reporting",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------- HEADER SECTION --------

# Create two columns: logo (small) + text (wide)
col1, col2 = st.columns([1, 6])

with col1:
    st.image("dmc_srilanka.jpg", width=100)  # adjust width as needed

with col2:
    st.markdown("""
        <div style="display: flex; flex-direction: column; justify-content: center;">
            <h1 style="margin-bottom:0;">Disaster Situation Reporting</h1>
            <h3 style="margin-top:0; margin-bottom:0;">Disaster Management Centre</h3>
            <h4 style="font-style: italic; font-weight: normal; margin-top:2px;">Powered by International Water Management Institute</p>
        </div>
    """, unsafe_allow_html=True)

st.markdown("---")

def setup_gemini(api_key):
    if not api_key:
        st.error("Gemini API key missing. Add GEMINI_API to your .env.")
        return False
    try:
        genai.configure(api_key=api_key)   # DOES NOT RETURN ANY CLIENT
        return True
    except Exception as e:
        st.error(f"Error initializing Gemini: {e}")
        return False


# -----------------------------
# PDF Generator (unchanged)
# -----------------------------
def generate_docx_bytes(extracted_text: str, logo_path="dmc_srilanka.jpg") -> bytes:
    """
    Create a .docx in-memory with:
    - Logo on left
    - Title + Subtitle on right
    - Markdown table conversion
    """
    doc = Document()

    # ---------------------------
    # HEADER WITH LOGO + TITLES
    # ---------------------------
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    # --- Left Cell: Logo ---
    left_cell = table.cell(0, 0)
    try:
        paragraph = left_cell.paragraphs[0]
        run = paragraph.add_run()
        run.add_picture(logo_path, width=Inches(1.0))  # adjust size as needed
    except Exception:
        left_cell.text = ""  # prevents crash if logo missing

    # --- Right Cell: Headings ---
    right_cell = table.cell(0, 1)
    right_para = right_cell.paragraphs[0]
    right_para.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT

    # Title
    title_run = right_para.add_run("Disaster Situation Reporting\n")
    title_run.bold = True
    title_run.font.size = Pt(20)

    # Subtitle (smaller)
    subtitle_run = right_para.add_run("Disaster Management Centre\n")
    subtitle_run.font.size = Pt(12)
    subtitle_run.bold = False

    subtitle_run = right_para.add_run("Powered by IWMI")
    subtitle_run.font.size = Pt(12)
    subtitle_run.bold = False

    doc.add_paragraph("")  # spacing after header

    # ---------------------------
    # TEXT + TABLE PARSING
    # ---------------------------

    lines = extracted_text.splitlines()
    i = 0
    n = len(lines)

    def is_table_sep(line: str) -> bool:
        return bool(re.match(r'^\s*\|?\s*[:\- ]+(\s*\|\s*[:\- ]+)+\s*\|?\s*$', line))

    while i < n:
        line = lines[i].rstrip('\n')
        stripped = line.strip()

        # Detect markdown table
        if '|' in stripped and (i + 1 < n) and is_table_sep(lines[i + 1]):
            header_cells = [c.strip() for c in stripped.strip().strip('|').split('|')]
            i += 2

            table_rows = []
            while i < n:
                row_line = lines[i].strip()
                if not row_line or '|' not in row_line:
                    break
                cells = [c.strip() for c in row_line.strip().strip('|').split('|')]
                table_rows.append(cells)
                i += 1

            cols = len(header_cells)
            rows = 1 + len(table_rows)
            tbl = doc.add_table(rows=rows, cols=cols)
            tbl.style = "Table Grid"

            for ci, h in enumerate(header_cells):
                tbl.rows[0].cells[ci].text = h

            for r_idx, row in enumerate(table_rows, start=1):
                for ci, cell in enumerate(row):
                    if ci < cols:
                        tbl.rows[r_idx].cells[ci].text = cell

            doc.add_paragraph("")
            continue

        # Regular paragraph
        clean_line = stripped.replace("**", "").replace("##", "").replace("###", "").strip()
        if clean_line:
            doc.add_paragraph(clean_line)
        else:
            doc.add_paragraph("")

        i += 1

    # ---------------------------
    # RETURN BYTES
    # ---------------------------
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()

# -----------------------------
# FIXED: Run extraction WITHOUT using a client object
# -----------------------------
def run_extraction(file_handle):
    system_instruction = (
        "You are an expert document extraction and summarization agent. "
        "Extract ALL structured and unstructured information from the input document, "
        "preserving layout and tables in Markdown. "
        "Return three sections: "
        "## Content (English) — translated to English, "
        "## Content, "
        "## Summary — short English summary."
    )

    user_prompt = (
        "Analyze the uploaded document and extract all content. "
        "Output the three required sections using the correct headings."
    )

    uploaded = None
    try:
        with st.spinner("Uploading document…"):

            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_file.write(file_handle.read())
            temp_path = temp_file.name
            temp_file.close()   
            # ---------------------------------------
            # 2. UPLOAD USING FILE PATH ONLY
            # ---------------------------------------
            uploaded = genai.upload_file(
                path=temp_path,             # MUST be path
                display_name=file_handle.name,   
                mime_type=file_handle.type
            )

        st.success(f"File uploaded: {uploaded.name}")

        contents = [user_prompt, uploaded]

        with st.spinner("Extracting content…"):

            model = genai.GenerativeModel('gemini-2.5-flash', system_instruction=system_instruction)
            response = model.generate_content(
                contents=contents
            )

        return response.text

    except Exception as e:
        st.error(f"Gemini API Error: {e}")
        return None

    finally:
        if uploaded:
            try:
                genai.delete_file(name=uploaded.name)
                st.info("Temporary file cleaned.")
            except Exception as e:
                print("Cleanup failed:", e)

        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass


# -----------------------------
# UI
# -----------------------------
st.title("📄 Multi-lingual Document Extractor & Summarizer")
st.markdown("Upload a document to extract & summarize content in English and original language.")

with st.sidebar:
    st.markdown("### Instructions")
    st.markdown("""
        1. Upload PDF or Image  
        2. Click Extract  
        3. Download PDF of extracted content  
    """)

uploaded_file = st.file_uploader(
    "Upload Document (PDF or Image)",
    type=["pdf", "jpg", "jpeg", "png"]
)

api_key = os.getenv("GEMINI_API")

# Always show button after upload
if uploaded_file:
    # Setup Gemini once
    gemini_ok = setup_gemini(api_key)

    if gemini_ok and st.button("🚀 Extract & Summarize Document", type="primary"):
        # --- 1. EXTRACTION LOGIC (Only runs when button is clicked) ---
        extracted_content = run_extraction(uploaded_file)
        
        # Store results in session state
        if extracted_content:
            st.session_state["full_output"] = extracted_content
            st.session_state["has_results"] = True
        else:
            st.session_state["full_output"] = ""
            st.session_state["has_results"] = False


# --- 2. DISPLAY AND DOWNLOAD LOGIC (Runs on every rerun if results exist) ---
if st.session_state.get("has_results", False):
    full_output = st.session_state.get("full_output", "")
    st.header("✅ Extraction Results")

    # Regular expression to find the start of the Summary section
    pattern = r"\s*##\s*Summary"
    match = re.search(pattern, full_output, re.IGNORECASE)

    content_for_pdf = full_output
    summary_section = ""

    if match:
        idx = match.start()
        # Content is everything BEFORE the Summary heading
        content_for_pdf = full_output[:idx].strip()
        # Summary is the Summary heading and everything AFTER it
        summary_section = full_output[idx:].strip()
        
        # Display content
        st.markdown(content_for_pdf)

        st.markdown("---")
        st.subheader("Summary")
        # Display summary, removing the heading
        st.markdown(summary_section.replace("## Summary", "", 1).strip())
        st.markdown("---")
    else:
        # Display full output if no summary heading found
        st.markdown(full_output)
        st.warning("Summary section not found — exporting whole output to DOCX.")

    # DOCX Download
    try:
        # Pass only the non-summary content for DOCX generation
        docx_bytes = generate_docx_bytes(content_for_pdf, "dmc_srilanka.jpg")
        st.download_button(
            label="⬇️ Download Extracted Content (DOCX)",
            data=docx_bytes,
            file_name="extracted_document_content.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    except Exception as e:
        st.error(f"DOCX generation error: {e}")