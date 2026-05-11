from langchain_core.tools import tool

from backend.ai.vector_store import search


@tool(
    description=(
        "Search the AUA policy PDF knowledge base for information relevant to a question. "
        "Use this tool when you need to find AUA policies, procedures, or official information "
        "from the American University of Armenia policy documents. The tool runs embedding-based "
        "vector similarity search over policy chunks stored in PostgreSQL (embedding arrays). Use it "
        "for questions about AUA rules, academic policies, HR, facilities, admissions, conduct, "
        "etc. If the question is unrelated to AUA policies or general knowledge you already "
        "know, you may answer without this tool. Input: the user's question or a search query."
    )
)
def retrieve_from_knowledge_base(question: str) -> str:
    results = search(query=question, k=5)

    if not results:
        return (
            "No relevant information found in the AUA policy documents. "
            "The collection may be empty or the question doesn't match any stored policy content."
        )

    formatted_results = []
    for chunk in results:
        source = chunk.get("source", "unknown")
        content = chunk.get("content", "")

        formatted_results.append(f"From: {source}\n{content}")

    return "\n\n---\n\n".join(formatted_results)
