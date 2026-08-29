from langchain.prompts import ChatPromptTemplate
from utils import llm


def get_farming_query(query: str, history: list | None) -> str:
    """Rewrite the latest question as a standalone query using conversation history.

    With no history there is nothing to resolve, so the query is returned as-is.
    A rewrite failure also falls back to the original query rather than erroring.
    """
    if not history:
        return query

    history_text = "\n".join(
        f"{h.get('role', 'user').capitalize()}: {h.get('content', '')}"
        for h in history
    )

    prompt = ChatPromptTemplate.from_template("""
    You are a farming assistant. A farmer is asking questions.
    Use the conversation history to understand context and rewrite the latest
    question as a complete, standalone query.

    Conversation so far:
    {history}

    Farmer's latest question:
    {query}

    Rewritten standalone query:
    """)

    try:
        response = (prompt | llm).invoke({"history": history_text, "query": query})
        return response.content.strip() or query
    except Exception as e:
        print(f"Query refinement failed, using original query: {e}")
        return query
