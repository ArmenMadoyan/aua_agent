## Q&A agent API 

### Objective
Agent that answers questions about **American University of Armenia (AUA) policies** using OpenAI and a local knowledge base built from AUA policy PDFs.

### Project Structure

The project is organized into three main components:

- **`frontend/`** - Streamlit web UI
- **`backend/`** - FastAPI REST API
- **`ai/`** - AI components (agents, tools, vector store)
- **`aua_policy_pdfs/`** - AUA policy PDF documents (primary data source for retrieval)

### What this project does

Q&A agent using:
- **LangChain** + **`langchain-openai`**
- **OpenAI GPT-4.1** (or compatible model via API key)
- **AUA policy PDFs** in `aua_policy_pdfs/` as the data source for retrieval (text is chunked, embedded with OpenAI, stored in **PostgreSQL** as `double precision[]` per chunk; similarity search runs in the app using cosine distance—**no** `vector` extension required)

### Setup

- **Python**: 3.11+  
- Create a virtual environment (recommended) and install dependencies from `requirements.txt`:
  ```bash
  python -m venv venv
  source venv/bin/activate   # Windows: venv\Scripts\activate
  pip install -r requirements.txt
  ```
- Set `OPENAI_API_KEY` (via `.env` or environment variable)
- Set **`DATABASE_URL`** in `.env` to a real PostgreSQL URL. The **username** must be an existing Postgres role (not the placeholder word `user`). On a typical local Mac install, that is often your macOS login name, e.g. `postgresql://yourname@localhost:5432/postgres` (no password if using peer/trust), or `postgresql://yourname:yourpassword@localhost:5432/dbname`. Create the database first if needed (`createdb mydb`). No PostgreSQL extensions are required; embeddings use the built-in `double precision[]` type. Optional: set **`EMBEDDING_DIMENSION`** (default `1536`) to match your embedding model and re-run migrations if you change it on a fresh database.
- **Migrations**: from the project root (venv activated, `DATABASE_URL` set), apply the schema with:
  ```bash
  alembic upgrade head
  ```
  Alternatively, starting the API or Streamlit runs `init_db()`, which performs the same `alembic upgrade head` for you.
- **Changing the schema**: add a **new** revision under `alembic/versions/` (e.g. `alembic revision -m "describe change"`), edit the generated file with `upgrade()` / `downgrade()` steps (`op.add_column`, `op.create_table`, etc.), then run `alembic upgrade head` again. Avoid editing `0001_initial` once it has been applied anywhere you care about; stack new migrations on top instead.

### How to run (Backend - FastAPI)

From the project root, with your venv activated:

```bash
uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

Then open the interactive Swagger UI:

- API docs: `http://127.0.0.1:8000/docs`

From there you can:

- **List messages for a chat**:  
  - Endpoint: `POST /chat/get_messages`  
  - Example body:
    ```json
    {
      "chat_id": 1
    }
    ```

- **Ask a question in a chat (orchestrator picks specialist, or you force one)**:  
  - Endpoint: `POST /chat/answer`  
  - Example body (`agent` defaults to `auto`; use `kb`, `course`, or `general` to skip routing):
    ```json
    {
      "chat_id": 1,
      "question": "What is the add/drop policy?",
      "agent": "auto",
      "syllabus_text": null
    }
    ```
  - Response includes `agent_used`: `general`, `kb`, or `course`.

- **Delete a chat**:  
  - Endpoint: `DELETE /chat/delete?chat_id=1` (e.g. `DELETE /chat/delete?chat_id=1`)

### How to run (Frontend - Streamlit UI)

Start the Streamlit web interface (from project root, venv activated):

```bash
streamlit run frontend/app.py
```

The UI will open automatically in your browser at `http://127.0.0.1:8501`.

**Features:**
- 💬 **Chat Interface**: each turn is routed automatically; the assistant reply **streams** token-by-token (Streamlit `write_stream` + LangGraph `stream_mode=["messages","updates"]`)
- 📚 **Knowledge Base**: AUA policy PDFs in `aua_policy_pdfs/` are ingested into PostgreSQL on API startup; you can also upload `.txt` files via the UI or API
- 📝 **Chat History**: View and manage multiple chat sessions
- 🔍 **Smart Search**: The agent uses vector search over embedded policy chunks when answering policy-related questions

