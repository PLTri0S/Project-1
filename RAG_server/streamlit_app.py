import streamlit as st
import inngest
from dotenv import load_dotenv
import os
import requests
from pathlib import Path
import time

load_dotenv()

# --- SIDEBAR FOR FILE MANAGEMENT (NotebookLM Style) ---
with st.sidebar:
    st.header("Tài liệu của bạn")

    # Scan the uploads directory for ingested PDFs
    uploads_dir = Path("uploads")
    if uploads_dir.exists():
        available_files = [f.name for f in uploads_dir.glob("*.pdf")]
    else:
        available_files = []

    if available_files:
        st.write("Chọn file bạn muốn hỏi về:")
        selected_docs = st.multiselect(
            "Active Documents",
            options=available_files,
            default=available_files,  # By default, search everything
        )
    else:
        st.info("No documents uploaded yet. Upload a PDF above to get started!")
        selected_docs = []

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


def send_rag_query_event(
    question: str,
    top_k: int,
    model: str = "llama3.2:3b",
    selected_files: list[str] | None = None,
) -> str:
    client = get_inngest_client()
    ids = client.send_sync(
        inngest.Event(
            name="rag/query_pdf_ai",
            data={
                "question": question,
                "top_k": top_k,
                "model": model,
                "selected_files": selected_files or [],
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


def wait_for_run_output(event_id: str, timeout_s: float = 300.0, poll_interval_s: float = 0.2) -> dict:
    start = time.time()
    last_status = None
    while True:
        runs = fetch_runs(event_id)
        if runs:
            run = runs[0]
            status = run.get("status")
            last_status = status or last_status
            if status in ("Completed", "Succeeded", "Success", "Finished"):
                return run.get("output") or {}
            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Function run {status}")
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Timed out waiting for run (last status: {last_status})")
        time.sleep(poll_interval_s)


# Top-K control (kept, but no separate ask/answer form anymore)
top_k = st.slider("Số đoạn tài liệu truy xuất (top_k)", min_value=1, max_value=20, value=8, step=1)
st.caption("Model: Ollama llama3.2:3b (Local)")

st.subheader("💬 Chat with your Document")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sources"):
            st.caption("Nguồn: " + ", ".join(message["sources"]))

if prompt := st.chat_input("Hỏi về tài liệu của bạn..."):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Đang tìm kiếm thông tin..."):
            event_id = send_rag_query_event(
                question=prompt,
                top_k=int(top_k),
                model="llama3.2:3b",
                selected_files=selected_docs,
            )
            output = wait_for_run_output(event_id, poll_interval_s=0.2)

            answer = output.get("answer", "Xin lỗi, tôi không thể tạo câu trả lời.")
            sources = output.get("sources", [])

            st.markdown(answer)
            if sources:
                st.caption("Nguồn: " + ", ".join(sources))

    st.session_state.messages.append({"role": "assistant", "content": answer, "sources": sources})