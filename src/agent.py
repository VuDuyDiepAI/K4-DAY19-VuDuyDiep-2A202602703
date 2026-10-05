from typing import Callable

from .store import EmbeddingStore

class KnowledgeBaseAgent:
    """
    An agent that answers questions using a vector knowledge base.

    Retrieval-augmented generation (RAG) pattern:
        1. Retrieve top-k relevant chunks from the store.
        2. Build a prompt with the chunks as context.
        3. Call the LLM to generate an answer.
    """

    def __init__(self, store: EmbeddingStore, llm_fn: Callable[[str], str]) -> None:
        self.store = store
        self.llm_fn = llm_fn

    def answer(self, question: str, top_k: int = 3) -> str:
        chunks = self.store.search(question, top_k=top_k)
        context = "\n\n".join(f"[{i}] {chunk['content']}" for i, chunk in enumerate(chunks, start=1))
        prompt = (
            "Trả lời câu hỏi chỉ dựa trên ngữ cảnh. Nếu ngữ cảnh không đủ, nói không đủ thông tin.\n\n"
            f"Ngữ cảnh:\n{context}\n\nCâu hỏi: {question}\nTrả lời:"
        )
        return self.llm_fn(prompt)
