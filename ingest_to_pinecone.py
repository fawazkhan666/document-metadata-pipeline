import json
from pathlib import Path

from metadata import is_unknown_metadata
from vectorstore import init_pinecone, upsert_document


def ingest(data_file: Path) -> None:
    if not data_file.exists() or not data_file.is_file():
        raise FileNotFoundError(f"Data file not found: {data_file}")

    records = json.loads(data_file.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("output/data.json must contain a list of records")

    index = init_pinecone()

    success_count = 0
    skipped_count = 0
    failed_count = 0

    for record in records:
        file_name = record.get("file_name", "unknown")
        metadata = record.get("metadata", {})

        if is_unknown_metadata(metadata if isinstance(metadata, dict) else {}):
            skipped_count += 1
            print(f"Skipping unknown metadata record: {file_name}")
            continue

        try:
            upsert_document(index, record)
            success_count += 1
            print(f"Upserted: {file_name}")
        except Exception as err:
            failed_count += 1
            print(f"Failed: {file_name} - {err}")

    print(
        f"Ingestion complete. Success={success_count}, Skipped={skipped_count}, Failed={failed_count}"
    )


if __name__ == "__main__":
    ingest(Path("output") / "data.json")
