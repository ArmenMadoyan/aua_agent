import base64
import os
import re
import time
from datetime import datetime 

import httpx
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Q&A Agent",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []

BATCH_UPLOAD_SESSION_KEY = "batch_attachments"

_MAX_RETRIES = 30
_RETRY_DELAY = 2


def _api(method: str, path: str, **kwargs) -> httpx.Response:
    url = f"{API_BASE}{path}"
    for attempt in range(_MAX_RETRIES):
        try:
            with httpx.Client(timeout=300) as client:
                return getattr(client, method)(url, **kwargs)
        except (httpx.ConnectError, httpx.RemoteProtocolError):
            if attempt == _MAX_RETRIES - 1:
                raise
            time.sleep(_RETRY_DELAY)


def load_chat_messages(chat_id: int):
    resp = _api("post", "/chat/get_messages", json={"chat_id": chat_id})
    resp.raise_for_status()
    data = resp.json()
    st.session_state.messages = data.get("messages", [])
    st.session_state.current_chat_id = chat_id


def create_new_chat():
    resp = _api("post", "/chat/create", json={})
    resp.raise_for_status()
    chat_id = resp.json()["chat_id"]
    st.session_state.current_chat_id = chat_id
    st.session_state.messages = []
    return chat_id


def list_sessions():
    resp = _api("get", "/chat/list")
    resp.raise_for_status()
    return resp.json().get("sessions", [])


def delete_session(chat_id: int):
    _api("delete", "/chat/delete", params={"chat_id": chat_id})


def format_timestamp(timestamp_str: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return timestamp_str


with st.sidebar:
    st.title("💬 Q&A Agent")
    st.markdown("---")

    st.subheader("Chat Management")

    if st.button("➕ New Chat", use_container_width=True):
        create_new_chat()
        st.rerun()

    st.markdown("---")

    st.subheader("Chat History")
    sessions = list_sessions()

    if not sessions:
        st.info("No chats yet. Create a new chat to get started!")
    else:
        for session_item in sessions:
            col1, col2 = st.columns([4, 1])
            with col1:
                is_selected = st.button(
                    f"Chat #{session_item['id']}",
                    key=f"chat_{session_item['id']}",
                    use_container_width=True,
                )
                if is_selected:
                    load_chat_messages(session_item["id"])
                    st.rerun()

            with col2:
                if st.button("🗑️", key=f"delete_{session_item['id']}"):
                    delete_session(session_item["id"])
                    if st.session_state.current_chat_id == session_item["id"]:
                        st.session_state.current_chat_id = None
                        st.session_state.messages = []
                    st.rerun()

    st.markdown("---")

    st.subheader("📚 Knowledge Base")

    uploaded_file = st.file_uploader(
        "Upload Document",
        type=["txt"],
        help="Upload a .txt file to add to the knowledge base",
    )

    if uploaded_file is not None:
        if st.button("Upload to Knowledge Base", use_container_width=True):
            try:
                content = uploaded_file.read().decode("utf-8")
                resp = _api(
                    "post",
                    "/knowledge/add",
                    json={"content": content, "file_name": uploaded_file.name},
                )
                resp.raise_for_status()
                data = resp.json()
                st.success("✅ Document uploaded successfully!")
                st.info(f"Document hash: {data['doc_hash'][:16]}...")
            except Exception as e:
                st.error(f"Error uploading document: {e}")

st.title("💬 Question-Answering Agent")
st.markdown(
    "Drag and drop **any mix** of files below (syllabus, rubric, student work, notes). "
    "Then describe in the chat what each file is and what you want."
)

batch_files = st.file_uploader(
    "Attachments for your next message",
    type=["pdf", "txt", "docx", "png", "jpg", "jpeg", "webp", "gif"],
    accept_multiple_files=True,
    help="Only files selected right now are sent with your next message.",
    key=BATCH_UPLOAD_SESSION_KEY,
)

if st.session_state.current_chat_id:
    st.caption(f"Chat #{st.session_state.current_chat_id}")

chat_container = st.container()
with chat_container:
    for message in st.session_state.messages:
        role = message["role"]
        content = message["content"]

        with st.chat_message(role):
            st.markdown(content)

if prompt := st.chat_input("Ask a question..."):
    if st.session_state.current_chat_id is None:
        create_new_chat()

    attachments: list[dict] = []
    filenames: list[str] = []
    uploads = list(batch_files) if batch_files else []
    for u in uploads:
        name = getattr(u, "name", "file")
        filenames.append(name)
        raw = u.getvalue()
        b64 = base64.standard_b64encode(raw).decode("ascii")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        mime_map = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif", "pdf": "application/pdf",
        }
        mime = mime_map.get(ext, "application/octet-stream")
        attachments.append({"mime_type": mime, "base64": b64})

    display_content = prompt
    if filenames:
        display_content = f"{prompt}\n\n*Attached ({len(filenames)}): {', '.join(filenames)}*"

    with st.chat_message("user"):
        st.markdown(display_content)

    st.session_state.messages.append({"role": "user", "content": display_content})

    with st.chat_message("assistant"):
        try:
            body = {
                "chat_id": st.session_state.current_chat_id,
                "question": prompt,
                "agent": "auto",
            }
            if attachments:
                body["attachments"] = attachments

            collected_tokens: list[str] = []

            try:
                with httpx.Client(timeout=300) as client:
                    with client.stream(
                        "POST",
                        f"{API_BASE}/chat/stream",
                        json=body,
                        headers={"Accept": "text/event-stream"},
                    ) as response:
                        response.raise_for_status()
                        placeholder = st.empty()
                        for line in response.iter_lines():
                            if line.startswith("data: "):
                                token = line[6:]
                                collected_tokens.append(token)
                                placeholder.markdown("".join(collected_tokens))
            except httpx.RemoteProtocolError:
                pass

            reply = "".join(collected_tokens)
            if not reply:
                resp = _api("post", "/chat/answer", json=body)
                resp.raise_for_status()
                result = resp.json()
                reply = result["answer"]
                st.markdown(reply)

            artifact = re.search(r"saved as '([^']+\.(?:pptx|pdf))'", reply)
            if artifact:
                name = artifact.group(1)
                download_url = f"{API_BASE}/course/artifacts/{name}"
                st.markdown(f"[Download {name}]({download_url})")

            st.session_state.messages.append({"role": "assistant", "content": reply})

        except Exception as e:
            error_msg = f"❌ Error: {e}"
            st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})

    st.session_state.pop(BATCH_UPLOAD_SESSION_KEY, None)
    st.rerun()
