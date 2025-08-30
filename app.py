import os
import pathlib
from typing import List

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename

# LangChain ingestion utilities (used for /upload)
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

# --------- Your RAG pipeline module (must exist) ----------
# rag.py must define:
# - rag_answer(question: str) -> str
# - generate_test(topic: str, num_questions: int, qtype: str, difficulty: str) -> dict
# - upsert_documents(docs: List[Document]) -> int   # add this helper to rag.py
#
# Minimal stub for reference (remove if you already implemented in rag.py):
# def upsert_documents(docs: List[Document]) -> int:
#     # Example:
#     # _ = vectordb.add_documents(docs)
#     # vectordb.persist()
#     # return len(docs)
#     raise NotImplementedError("Implement upsert_documents in rag.py to add docs to Chroma.")
import rag

# ---------------- Flask setup ----------------
app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates",
)
CORS(app, resources={r"/*": {"origins": "*"}})

# JSON and upload config
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True
app.config["JSON_SORT_KEYS"] = False
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB cap

# Uploads dir and allowed extensions
ALLOWED_EXT = {".pdf"}
BASE_DIR = pathlib.Path(__file__).parent.resolve()
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ---------------- Frontend routes ----------------
@app.get("/")
def index():
    # Serve templates/index.html which references /static/style.css and /static/app.js
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

# ---------------- RAG: Q&A ----------------
@app.post("/ask")
def ask():
    try:
        data = request.get_json(force=True, silent=False) or {}
        question = str(data.get("question", "")).strip()
        if not question:
            return jsonify({"error": "Missing 'question'"}), 400

        answer = rag.rag_answer(question)
        return jsonify({"answer": answer}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- Test generation ----------------
@app.post("/test")
def test():
    try:
        data = request.get_json(force=True, silent=False) or {}
        topic = str(data.get("topic", "")).strip()
        if not topic:
            return jsonify({"error": "Missing 'topic'"}), 400

        num_questions = int(data.get("num_questions", 8))
        qtype = str(data.get("qtype", "mcq")).lower()
        difficulty = str(data.get("difficulty", "medium")).lower()

        if qtype not in {"mcq", "short", "long"}:
            return jsonify({"error": "qtype must be one of: mcq, short, long"}), 400
        if difficulty not in {"easy", "medium", "hard"}:
            return jsonify({"error": "difficulty must be one of: easy, medium, hard"}), 400
        if not (1 <= num_questions <= 50):
            return jsonify({"error": "num_questions must be between 1 and 50"}), 400

        # Normalize hidden NBSP so “and” split works for mixed topics in rag.py
        topic = topic.replace("\u00a0", " ")

        test_json = rag.generate_test(
            topic=topic,
            num_questions=num_questions,
            qtype=qtype,
            difficulty=difficulty,
        )
        return jsonify(test_json), 200
    except ValueError:
        return jsonify({"error": "Invalid number for 'num_questions'"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- Upload + index PDFs ----------------
def index_documents(docs: List[Document]) -> int:
    # Delegates to rag.py to index into the same Chroma collection
    return rag.upsert_documents(docs)

@app.post("/upload")
def upload():
    try:
        if "files" not in request.files:
            return jsonify({"error": "No 'files' field in form-data"}), 400

        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "No files uploaded"}), 400

        all_docs: List[Document] = []
        for f in files:
            filename = secure_filename(f.filename or "")
            if not filename:
                return jsonify({"error": "One file has no name"}), 400

            ext = pathlib.Path(filename).suffix.lower()
            if ext not in ALLOWED_EXT:
                return jsonify({"error": f"Unsupported file type: {ext}"}), 400

            save_path = UPLOAD_DIR / filename
            f.save(str(save_path))

            # Load PDF into Document chunks (page-wise)
            loader = PyPDFLoader(str(save_path))
            docs = loader.load()
            # Ensure filename is present
            for d in docs:
                d.metadata = d.metadata or {}
                d.metadata.setdefault("source", filename)
            all_docs.extend(docs)

        # Chunking
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = splitter.split_documents(all_docs)

        # Upsert into your existing Chroma vector DB
        added = index_documents(chunks)

        return jsonify({
            "status": "ok",
            "files": [secure_filename(f.filename or "") for f in files],
            "chunks_indexed": added
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Set PORT via env if deploying
    port = int(os.getenv("PORT", "5000"))
    # For local dev: debug=True; for prod: consider using gunicorn/uwsgi
    app.run(host="0.0.0.0", port=port, debug=True) 