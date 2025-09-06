import os
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma as ChromaCommunity
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import ChatPromptTemplate
from langchain.schema.runnable import RunnableMap, RunnablePassthrough
from langchain.schema import StrOutputParser
import re
from typing import List, Dict, Any
from langchain.schema import Document
import json
from datetime import datetime
import os
from langchain.retrievers import EnsembleRetriever
from flask import Flask, request, jsonify
from flask_cors import CORS
from langchain_community.retrievers import BM25Retriever
loader = DirectoryLoader(
    "leph2dd",            
    glob="**/*.pdf",      
    loader_cls=PyPDFLoader
)

document = loader.load()
text_spillter  = RecursiveCharacterTextSplitter(chunk_size = 1000 , chunk_overlap = 200)
text = text_spillter.split_documents(document)
from langchain import embeddings
persist_directory = 'db'
embedding = OpenAIEmbeddings()
vectordb = ChromaCommunity.from_documents(documents=text ,
                                 embedding=embedding,
                                 persist_directory=persist_directory)

vectordb = ChromaCommunity(persist_directory=persist_directory, embedding_function=embedding)
dense_ret = vectordb.as_retriever(search_kwargs={"k": 8})
bm25 = BM25Retriever.from_documents(text)
bm25.k = 8


retriever = EnsembleRetriever(retrievers=[bm25, dense_ret], weights=[0.5, 0.5])
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

SYSTEM_PROMPT = "Answer using only the provided context. If not present, give genric responce. Keep answers concise."
HUMAN_PROMPT = """Context:
{context}

Question:
{question}
"""

prompt = ChatPromptTemplate.from_messages(
    [("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)]
)

def _format_docs(docs):
    return "\n\n".join(d.page_content for d in docs)

rag_chain = (
    RunnableMap({
        "context": retriever | _format_docs,
        "question": RunnablePassthrough()
    })
    | prompt
    | llm
    | StrOutputParser()
)
def rag_answer(question: str):
    return rag_chain.invoke(question)


def retrieve_topic_chunks(topic: str, k: int = 16) -> List[Document]:
    r = vectordb.as_retriever(search_type="mmr", search_kwargs={"k": k, "fetch_k": 48, "lambda_mult": 0.5})
    return r.get_relevant_documents(topic)

def _format_docs_compact(docs: List[Document]) -> str:
    blocks = []
    for d in docs:
        meta = d.metadata or {}
        src = meta.get("source", "unknown")
        page = meta.get("page_label") or meta.get("page")
        head = f"[Source: {src} | Page: {page}]"
        blocks.append(head + "\n" + d.page_content)
    return "\n\n".join(blocks[:18])

def retrieve_mixed_chunks(topic_a: str, topic_b: str, k_each: int = 12) -> List[Document]:
    ra = vectordb.as_retriever(search_type="mmr", search_kwargs={"k": k_each, "fetch_k": 48, "lambda_mult": 0.5})
    rb = vectordb.as_retriever(search_type="mmr", search_kwargs={"k": k_each, "fetch_k": 48, "lambda_mult": 0.5})
    docs_a = ra.get_relevant_documents(topic_a)
    docs_b = rb.get_relevant_documents(topic_b)
    return docs_a + docs_b

from typing import List
from langchain.schema import Document

def upsert_documents(docs: List[Document]) -> int:
    # Assumes vectordb is initialized at import time in rag.py
    # Example:
    # _ = vectordb.add_documents(docs)
    # vectordb.persist()
    # return len(docs)
    _ = vectordb.add_documents(docs)
    # If using persistent Chroma, uncomment:
    # vectordb.persist()
    return len(docs)

def _mixed_context(x):
    topic = x["topic"]
    # Split on “and” or comma to detect two-topic mixes
    parts = [p.strip() for p in re.split(r"\band\b|,", topic, flags=re.I) if p.strip()]
    if len(parts) >= 2:
        docs = retrieve_mixed_chunks(parts[0], parts[1], k_each=12)
        return _format_docs_compact(docs)
    # Single-topic fallback with a bit more breadth
    return _format_docs_compact(retrieve_topic_chunks(topic, k=24))

TEST_SYSTEM_PROMPT = "You are an examiner. Create tests ONLY from the provided context. Do not use outside knowledge."

# CLEAN prompt: no stray braces, no JSON keys in single braces
TEST_HUMAN_PROMPT = (
    "Topic:\n"
    "{topic}\n\n"
    "Context (from internal PDFs):\n"
    "{context}\n\n"
    "Requirements:\n"
    "- Create exactly {num_questions} questions.\n"
    '- Question type: {qtype}  (allowed: "mcq", "short", "long")\n'
    '- Difficulty: {difficulty}  (allowed: "easy", "medium", "hard")\n'
    "- Cover different sub-concepts from the context (avoid repeating the same fact).\n"
    "- For MCQ:\n"
    "  - Provide 4 options (A-D).\n"
    '  - Mark the correct option with "answer: X" (e.g., "answer: B").\n'
    "- For short:\n"
    '  - Provide a concise answer key after each question with "answer: ...".\n'
    "- For long:\n"
    "  - Provide a structured answer key with multiple points/subheadings and 120–250 words per answer.\n"
    "- Use ONLY the information present in the context. If insufficient, reduce scope and proceed.\n\n"
    "Output JSON ONLY with schema:\n"
    "{{\n"
    '  "topic": "...",\n'
    '  "qtype": "...",\n'
    '  "difficulty": "...",\n'
    '  "questions": [\n'
    "    {{\n"
    '      "id": 1,\n'
    '      "question": "...",\n'
    '      "options": ["A) ...","B) ...","C) ...","D) ..."],\n'
    '      "answer": "B" or "..."\n'
    "    }}\n"
    "  ]\n"
    "}}\n"
)
test_prompt = ChatPromptTemplate.from_messages(
    [("system", TEST_SYSTEM_PROMPT), ("human", TEST_HUMAN_PROMPT)]
)
test_chain = (
    RunnableMap({
        "topic": RunnablePassthrough(),
        "num_questions": RunnablePassthrough(),
        "qtype": RunnablePassthrough(),
        "difficulty": RunnablePassthrough(),
        "context": _mixed_context,
    })
    | test_prompt
    | llm
    | StrOutputParser()
)

def generate_test(topic: str, num_questions: int = 8, qtype: str = "mcq", difficulty: str = "medium") -> Dict[str, Any]:
    payload = {
        "topic": topic,
        "num_questions": str(num_questions),
        "qtype": qtype.lower(),
        "difficulty": difficulty.lower(),
    }
    raw = test_chain.invoke(payload)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{"); end = raw.rfind("}")
        data = json.loads(raw[start:end+1])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"test_{data.get('qtype','unknown')}_{data.get('difficulty','unknown')}_{num_questions}_{ts}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

def print_test(test_json: Dict[str, Any]) -> None:
    print(f"Topic: {test_json.get('topic')}")
    print(f"Type: {test_json.get('qtype')} | Difficulty: {test_json.get('difficulty')}\n")
    for q in test_json.get("questions", []):
        print(f"Q{q['id']}. {q['question']}")
        if test_json.get("qtype") == "mcq":
            for opt in q.get("options", []):
                print(f"   {opt}")
            print(f"Answer: {q.get('answer')}\n")
        else:
            print(f"Answer: {q.get('answer')}\n")

# Optional: quick sanity check of the prompt formatting
'''chk = test_prompt.format_messages(
    topic="Chapter 9 Ray Optics",
    context="sample context",
    num_questions="5",
    qtype="mcq",
    difficulty="medium",
)'''
#t = generate_test(topic="ChemicalKinetics and  RayOptics", num_questions=8, qtype="short", difficulty="hard")
#print_test(t)
#ans = rag_answer("What is the angle of refraction at the second face of the prism referred to in the context?")
#print(ans)


