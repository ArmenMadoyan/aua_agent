def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "evaluation: RAG evaluation tests (slow; require live DB + OpenAI + Anthropic + Gemini API keys)",
    )
