# AI Metadata Enrichment Pipeline

Enterprise-style AI metadata enrichment and document indexing pipeline built using:

- Google Drive API
- Ollama (Llama 3)
- Pinecone Vector Database
- Python

---

# Project Goal

This project solves a major RAG/retrieval problem:

> AI systems often return diluted or mixed answers because documents lack structured metadata.

This pipeline enriches document metadata using LLMs before indexing into a vector database.

The result:
- better filtering
- better retrieval
- less hallucination
- more accurate enterprise search

---

# Architecture

## Layer 1 — Metadata Authoring

Documents are fetched from Google Drive.

Pipeline:
- downloads files
- extracts text
- sends context to Ollama
- generates structured metadata schema

Example metadata:

```json
{
  "document_type": "Test Plan",
  "customer": "Globex Industries",
  "project_phase": "UAT",
  "systems": ["SAP", "Azure DevOps"]
}
```

---

## Layer 2 — Index + Enrich

The pipeline:
- chunks documents
- generates embeddings
- stores vectors in Pinecone
- attaches enriched metadata to vectors

This enables:
- semantic search
- metadata filtering
- retrieval grounding

---

## Layer 3 — Retrieval (Future)

Future retrieval layer will:
- parse user intent
- extract filters
- perform hybrid retrieval
- generate grounded RAG responses

Example query:

```text
Show me UAT test plans for SAP migration projects
```

Metadata filters:

```json
{
  "document_type": "Test Plan",
  "project_phase": "UAT",
  "systems": ["SAP"]
}
```

---

# Features

- Google Drive integration
- DOCX/PDF/XML extraction
- AI metadata enrichment
- Pinecone vector indexing
- Automated watcher pipeline
- Retrieval-ready architecture
- Enterprise metadata schema support

---

# Tech Stack

| Component | Technology |
|---|---|
| LLM | Ollama + Llama3 |
| Vector Database | Pinecone |
| Storage | Google Drive |
| Language | Python |
| Extraction | python-docx / PDF parsers |
| Automation | Watcher pipeline |

---

# Project Structure

```text
project/
│
├── drive.py
├── extractor.py
├── metadata.py
├── vectorstore.py
├── watcher.py
├── main.py
├── requirements.txt
├── README.md
└── .gitignore
```

---

# Setup

## Clone Repo

```bash
git clone https://github.com/fawazkhan666/document-metadata-pipeline.git
```

---

## Create Virtual Environment

```bash
python -m venv .venv
```

Activate:

```bash
.venv\Scripts\activate
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Run Ollama

```bash
ollama run llama3
```

---

## Run Pipeline

```bash
python main.py
```

---

## Run Watcher

```bash
python watcher.py
```

---

# Metadata Schema

Current schema includes:

- document_type
- document_status
- customer
- project
- project_phase
- systems
- workstream
- tags
- data_sensitivity
- contains_pii
- summary

---

# Example Use Cases

- Enterprise search
- RAG pipelines
- SharePoint indexing
- AI copilots
- Knowledge management
- Metadata governance
- Document intelligence

---

# Future Improvements

- Agentic retrieval layer
- Hybrid search
- Azure AI Search integration
- LangGraph orchestration
- Multi-agent workflows
- SharePoint connector
- Reranking pipeline
- Incremental indexing

---

# Author

Fawaz Khan
