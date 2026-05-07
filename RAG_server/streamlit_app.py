import streamlit as st
import inngest
from dotenv import load_dotenv
import os
import requests
from pathlib import Path
import time

load_dotenv()

# Check if file uploaded?
if "uploaded_file" not in st.session_state:
    st.session_state.uploaded_file = set()

st.set_page_config(page_title="RAG Ingest PDF", page_icon="📄", layout="centered")

@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    # The Inngest client handles both sync and async operations
    return inngest.Inngest(app_id="rag_app", is_production=False)

def save_uploaded_pdf(file) -> Path:
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.name
    file_bytes = file.getbuffer()
    file_path.write_bytes(file_bytes)
    return file_path

# Change 1: Remove 'async' and use 'send_sync'
def send_rag_ingest_event(pdf_path: Path) -> None:
    client = get_inngest_client()
    client.send_sync(
        inngest.Event(
            name="rag/ingest_pdf",
            data={
                "pdf_path": str(pdf_path.resolve()),
                "source_id": pdf_path.name,
            },
        )
    )

st.title("Upload a PDF to Ingest")
uploaded = st.file_uploader("Choose a PDF", type=["pdf"], accept_multiple_files=False)

if uploaded is not None:
    if uploaded.name not in st.session_state.uploaded_file:
        with st.spinner("Uploading and triggering ingestion..."):
            path = save_uploaded_pdf(uploaded)
            send_rag_ingest_event(path)
            time.sleep(0.3)
            st.session_state.uploaded_file.add(uploaded.name)
        st.success(f"Triggered ingestion for: {path.name}")
        st.caption("You can upload another PDF if you like.")


st.divider()
st.title("Ask a question about your PDFs")

# Change 3: Remove 'async' and use 'send_sync'
def send_rag_query_event(question: str, top_k: int, model: str = "llama") -> str:
    client = get_inngest_client()
    # send_sync returns a list of event IDs
    ids = client.send_sync(
        inngest.Event(
            name="rag/query_pdf_ai",
            data={
                "question": question,
                "top_k": top_k,
                "model": model,
            },
        )
    )
    return ids[0]

def _inngest_api_base() -> str:
    return os.getenv("INNGEST_API_BASE", "http://127.0.0.1:8288/v1")

def fetch_runs(event_id: str) -> list[dict]:
    url = f"{_inngest_api_base()}/events/{event_id}/runs"
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])

def wait_for_run_output(event_id: str, timeout_s: float = 120.0, poll_interval_s: float = 0.5) -> dict:
    start = time.time()
    last_status = None
    while True:
        runs = fetch_runs(event_id)
        if runs:
            run = runs[0]
            status = run.get("status")
            last_status = status or last_status
            # Inngest status names can vary slightly by version; check for common success states
            if status in ("Completed", "Succeeded", "Success", "Finished"):
                return run.get("output") or {}
            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Function run {status}")
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Timed out waiting for run (last status: {last_status})")
        time.sleep(poll_interval_s)

with st.form("rag_query_form"):
    question = st.text_input("Your question")
    col1, col2 = st.columns(2)
    with col1:
        top_k = st.number_input("Chunks to retrieve", min_value=1, max_value=20, value=5, step=1)
    with col2:
        model = st.selectbox("AI Model", ["llama", "gemini"], index=0)
    submitted = st.form_submit_button("Ask")
    

    if submitted and question.strip():
        with st.spinner("Sending event and generating answer..."):
            # Change 4: Call directly without asyncio.run
            event_id = send_rag_query_event(question.strip(), int(top_k), model)
            output = wait_for_run_output(event_id)
            answer = output.get("answer", "")
            sources = output.get("sources", [])

        st.subheader("Answer")
        st.write(answer or "(No answer)")
        if sources:
            st.caption("Sources")
            for s in sources:
                st.write(f"- {s}")