import streamlit as st
import google.generativeai as genai
from io import BytesIO
import base64
from google.generativeai import types
from PIL import Image
from docx import Document
import re
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Streamlit page config
st.set_page_config(
    page_title="Gemini Document Extractor",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------
# FIXED: Proper Gemini setup
# -----------------------------
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
def generate_docx_bytes(extracted_text: str) -> bytes:
    """
    Create a .docx in-memory from extracted_text and return bytes.
    This also converts simple markdown-style pipe tables into real docx tables.
    """
    doc = Document()
    doc.add_heading("Extracted Document Content", level=1)

    lines = extracted_text.splitlines()
    i = 0
    n = len(lines)

    # helper to detect a separator row like: | --- | ---: | :---: |
    def is_table_sep(line: str) -> bool:
        # Allow leading/trailing pipes and spaces, and : or - characters and pipes
        return bool(re.match(r'^\s*\|?\s*[:\- ]+(\s*\|\s*[:\- ]+)+\s*\|?\s*$', line))

    while i < n:
        line = lines[i].rstrip('\n')
        stripped = line.strip()

        # Start of a markdown table: header row followed by separator row
        if '|' in stripped and (i + 1 < n) and is_table_sep(lines[i + 1]):
            # parse header
            header_cells = [c.strip() for c in stripped.strip().strip('|').split('|')]
            i += 2  # skip header + separator
            # gather rows
            table_rows = []
            while i < n:
                row_line = lines[i].strip()
                if not row_line or '|' not in row_line:
                    break
                cells = [c.strip() for c in row_line.strip().strip('|').split('|')]
                table_rows.append(cells)
                i += 1

            # create docx table: 1 header row + data rows
            cols = len(header_cells)
            rows = 1 + len(table_rows)
            table = doc.add_table(rows=rows, cols=cols)
            table.style = 'Table Grid'  # optional; remove if you do not want style

            # fill header
            for ci, h in enumerate(header_cells):
                try:
                    table.rows[0].cells[ci].text = h
                except IndexError:
                    # guard in case of inconsistent column counts
                    pass

            # fill data rows
            for r_idx, row in enumerate(table_rows, start=1):
                for ci, cell in enumerate(row):
                    try:
                        table.rows[r_idx].cells[ci].text = cell
                    except IndexError:
                        pass

            doc.add_paragraph("")  # spacing after the table
            continue  # skip the usual i += 1 since we've already advanced
        else:
            # Normal paragraph line: strip common markdown headings/asterisks
            clean_line = stripped.replace("**", "").replace("##", "").replace("###", "").strip()
            if clean_line:
                doc.add_paragraph(clean_line)
            else:
                # preserve blank line
                doc.add_paragraph("")
            i += 1

    # save to bytes buffer
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
        "## Extracted Content (English) — translated to English, "
        "## Original Language Content — same formatting as document, "
        "## Summary — short English summary."
    )

    user_prompt = (
        "Analyze the uploaded document and extract all content. "
        "Output the three required sections using the correct headings."
    )

    uploaded = None
    try:
        with st.spinner("Uploading document…"):

            # FIXED: Correct upload call
            uploaded = genai.upload_file(
                file_handle,
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

    """finally:
        if uploaded:
            try:
                genai.files.delete(name=uploaded.name)
                st.info("Temporary file cleaned.")
            except Exception as e:
                print("Cleanup failed:", e)"""


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
        full_output = run_extraction(uploaded_file)

        if full_output:
            st.header("✅ Extraction Results")

            pattern = r"\s*##\s*Summary"
            match = re.search(pattern, full_output, re.IGNORECASE)

            content_for_pdf = full_output

            if match:
                idx = match.start()
                content_for_pdf = full_output[:idx].strip()
                summary_section = full_output[idx:].strip()

                st.markdown(content_for_pdf)

                st.markdown("---")
                st.subheader("Summary (not included in DOC)")
                st.markdown(summary_section.replace("## Summary", "", 1).strip())
                st.markdown("---")
            else:
                st.markdown(full_output)
                st.warning("Summary section not found — exporting whole output to PDF.")

            # PDF Download
            try:
                docx_bytes = generate_docx_bytes(content_for_pdf)
                st.download_button(
                    label="⬇️ Download Extracted Content (DOCX)",
                    data=docx_bytes,
                    file_name="extracted_document_content.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            except Exception as e:
                st.error(f"DOCX generation error: {e}")