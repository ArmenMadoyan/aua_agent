import base64
import re
import sys
from datetime import datetime
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from ai.orchestrator import iter_chat_turn_tokens
from ai.course_output import GENERATED_COURSE_DIR, ensure_generated_dir
from ai.upload_bundle import bundle_chat_uploads
from ai.vector_store import add_document
from backend.db import (
    init_db,
    create_session,
    get_messages,
    list_sessions,
    delete_session,
    add_message,
    get_default_llm_model_id,
)

init_db()
ensure_generated_dir()

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
# Stable key for the main attachment uploader; cleared after each send (see below).
BATCH_UPLOAD_SESSION_KEY = "batch_attachments"


def load_chat_messages(chat_id: int):
    messages = get_messages(chat_id)
    st.session_state.messages = messages
    st.session_state.current_chat_id = chat_id


def create_new_chat():
    chat_id = create_session()
    st.session_state.current_chat_id = chat_id
    st.session_state.messages = []
    return chat_id


def format_timestamp(timestamp_str: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
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
        for session in sessions:
            col1, col2 = st.columns([4, 1])
            with col1:
                is_selected = st.button(
                    f"Chat #{session['id']}",
                    key=f"chat_{session['id']}",
                    use_container_width=True,
                )
                if is_selected:
                    load_chat_messages(session["id"])
                    st.rerun()

            with col2:
                if st.button("🗑️", key=f"delete_{session['id']}"):
                    delete_session(session["id"])
                    if st.session_state.current_chat_id == session["id"]:
                        st.session_state.current_chat_id = None
                        st.session_state.messages = []
                    st.rerun()

    st.markdown("---")

    st.subheader("📚 Knowledge Base")

    uploaded_file = st.file_uploader(
        "Upload Document",
        type=["txt"],
        help="Upload a .txt file to add to the knowledge base (optional; main source is AUA policy PDFs)",
    )

    if uploaded_file is not None:
        if st.button("Upload to Knowledge Base", use_container_width=True):
            try:
                content = uploaded_file.read().decode("utf-8")
                doc_hash = add_document(content, file_name=uploaded_file.name)
                st.success(f"✅ Document uploaded successfully!")
                st.info(f"Document hash: {doc_hash[:16]}...")
            except Exception as e:
                st.error(f"Error uploading document: {str(e)}")

st.title("💬 Question-Answering Agent")
st.markdown(
    "Drag and drop **any mix** of files below (syllabus, rubric, student work, notes). "
    "Then describe in the chat what each file is and what you want—e.g. *this PDF is the rubric, "
    "that one is the submission; grade with Scores and Feedback only*. "
    "Images and **scanned** PDFs go to the vision model; text-heavy PDFs / TXT / DOCX are read as text."
)

batch_files = st.file_uploader(
    "Attachments for your next message",
    type=["pdf", "txt", "docx", "png", "jpg", "jpeg", "webp", "gif"],
    accept_multiple_files=True,
    help="Only files selected right now are sent with your next message. After each reply the picker clears.",
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
            atts = message.get("attachments") or []
            for spec in atts[:6]:
                try:
                    raw = base64.standard_b64decode(spec.get("base64") or "")
                    st.image(raw, use_container_width=True)
                except Exception:
                    st.caption("(Could not preview an attached image.)")
            if len(atts) > 6:
                st.caption(f"+ {len(atts) - 6} more page(s) / image(s)")

if prompt := st.chat_input("Ask a question..."):
    if st.session_state.current_chat_id is None:
        create_new_chat()

    uploads = list(batch_files) if batch_files else []
    bundle = bundle_chat_uploads(prompt=prompt, uploads=uploads)

    user_entry: dict = {"role": "user", "content": bundle["display_content"]}
    if bundle["model_content"] != bundle["display_content"]:
        user_entry["model_content"] = bundle["model_content"]
    if bundle["attachments"]:
        user_entry["attachments"] = bundle["attachments"]

    with st.chat_message("user"):
        st.markdown(bundle["display_content"])
        if bundle["attachments"]:
            for spec in bundle["attachments"][:8]:
                try:
                    raw = base64.standard_b64decode(spec.get("base64") or "")
                    st.image(raw, use_container_width=True)
                except Exception:
                    st.caption("(Could not preview an image.)")
            if len(bundle["attachments"]) > 8:
                st.caption(f"+ {len(bundle['attachments']) - 8} more page(s) / image(s)")

    st.session_state.messages.append(user_entry)

    with st.chat_message("assistant"):
        try:
            agent_messages: list[dict] = []
            for msg in st.session_state.messages:
                text = msg.get("model_content")
                if text is None:
                    text = msg["content"]
                d: dict = {"role": msg["role"], "content": text}
                if msg.get("attachments"):
                    d["attachments"] = msg["attachments"]
                agent_messages.append(d)

            syllabus = None
            stream_meta: dict = {}
            token_iter = iter_chat_turn_tokens(
                agent_messages,
                syllabus_text=syllabus,
                force_agent="auto",
                meta=stream_meta,
            )
            reply = st.write_stream(token_iter) or ""

            artifact = re.search(r"saved as '([^']+\.(?:pptx|pdf))'", reply)
            if artifact:
                local_path = GENERATED_COURSE_DIR / artifact.group(1)
                if local_path.is_file():
                    data = local_path.read_bytes()
                    name = artifact.group(1)
                    mime = (
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                        if name.lower().endswith(".pptx")
                        else "application/pdf"
                    )
                    st.download_button(
                        label=f"Download {name}",
                        data=data,
                        file_name=name,
                        mime=mime,
                        key=f"dl_{name}_{len(st.session_state.messages)}",
                    )

            st.session_state.messages.append({"role": "assistant", "content": reply})

            # Drop binary attachments and long model text from the user turn we just finished so
            # the thread UI and future turns do not replay homework pages or huge extracts.
            if len(st.session_state.messages) >= 2:
                prev = st.session_state.messages[-2]
                if prev.get("role") == "user":
                    prev.pop("attachments", None)
                    prev.pop("model_content", None)

            agent_label = stream_meta.get("agent_used") or "general"
            tools = stream_meta.get("tool_names") or []
            llm_id = get_default_llm_model_id()
            persist_user = bundle["display_content"]
            if bundle["filenames"]:
                persist_user = (
                    f"[Files: {', '.join(bundle['filenames'])} — binary / extracted text not stored in DB]\n\n"
                    + bundle["display_content"]
                )
            add_message(
                st.session_state.current_chat_id,
                "user",
                persist_user,
                agent_name=agent_label,
            )
            add_message(
                st.session_state.current_chat_id,
                "assistant",
                reply,
                agent_name=agent_label,
                llm_model_id=llm_id,
                tools_called=tools or None,
            )

        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
            if len(st.session_state.messages) >= 2:
                prev = st.session_state.messages[-2]
                if prev.get("role") == "user":
                    prev.pop("attachments", None)
                    prev.pop("model_content", None)

    # Reset the file uploader so the next message can attach new files. Incrementing widget
    # keys breaks multi-turn uploads; clearing session state + rerun is the supported pattern.
    st.session_state.pop(BATCH_UPLOAD_SESSION_KEY, None)
    st.rerun()
