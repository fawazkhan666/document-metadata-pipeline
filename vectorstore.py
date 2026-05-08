import os
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec


INDEX_NAME = "document-metadata"
EMBEDDING_DIMENSION = 768
EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
MAX_EMBED_TEXT_CHARS = 3500
MAX_METADATA_VALUE_CHARS = 300


def init_pinecone():
	load_dotenv()
	api_key = os.getenv("PINECONE_API_KEY", "").strip()
	if not api_key:
		raise ValueError("Missing PINECONE_API_KEY in .env")

	pc = Pinecone(api_key=api_key)

	try:
		existing = set(pc.list_indexes().names())
	except AttributeError:
		listed = pc.list_indexes()
		existing = set(item.get("name", "") for item in listed if isinstance(item, dict))

	if INDEX_NAME not in existing:
		pc.create_index(
			name=INDEX_NAME,
			dimension=EMBEDDING_DIMENSION,
			metric="cosine",
			spec=ServerlessSpec(cloud="aws", region="us-east-1"),
		)

	return pc.Index(INDEX_NAME)


def get_embedding(text: str) -> List[float]:
	cleaned = " ".join((text or "").replace("\x00", " ").split()).strip()
	prompt = cleaned[:MAX_EMBED_TEXT_CHARS]
	if not prompt:
		raise ValueError("Embedding input text is empty")

	payload = {
		"model": EMBEDDING_MODEL,
		"prompt": prompt,
	}

	last_error: Exception | None = None
	for _ in range(3):
		try:
			response = requests.post(OLLAMA_EMBED_URL, json=payload, timeout=120)
			response.raise_for_status()
			body = response.json()

			embedding = body.get("embedding")
			if not isinstance(embedding, list) or not embedding:
				raise ValueError("Invalid embedding response from Ollama")
			return embedding
		except requests.RequestException as err:
			last_error = err

	raise RuntimeError(f"Ollama embedding failed after retries: {last_error}")


def _flatten_metadata(metadata: Dict[str, Any]) -> Dict[str, str]:
	flattened: Dict[str, str] = {}
	for key, value in metadata.items():
		if isinstance(value, list):
			joined = ", ".join(str(item).strip() for item in value if str(item).strip())
			flattened[key] = joined[:MAX_METADATA_VALUE_CHARS]
		elif value is None:
			flattened[key] = ""
		else:
			flattened[key] = str(value).strip()[:MAX_METADATA_VALUE_CHARS]
	return flattened


def upsert_document(index, doc: Dict[str, Any]) -> None:
	metadata = doc.get("metadata", {})
	metadata_flat = _flatten_metadata(metadata if isinstance(metadata, dict) else {})

	content_parts = [str(doc.get("file_name", "")).strip()]
	for key, value in metadata_flat.items():
		content_parts.append(f"{key}: {value}")
	embedding_text = "\n".join(part for part in content_parts if part)

	embedding = get_embedding(embedding_text)
	doc_id = str(doc.get("source_file_id") or doc.get("file_name") or "unknown-id")

	vector_payload = {
		"id": doc_id,
		"values": embedding,
		"metadata": {
			"file_name": str(doc.get("file_name", "")).strip(),
			"file_type": str(doc.get("file_type", "")).strip(),
			**metadata_flat,
		},
	}

	index.upsert(vectors=[vector_payload])


def search_documents(index, query: str, top_k: int = 5):
	query_embedding = get_embedding(query)
	return index.query(vector=query_embedding, top_k=top_k, include_metadata=True)
