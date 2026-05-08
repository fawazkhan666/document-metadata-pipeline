import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from drive import (
    SUPPORTED_MIME_TYPES,
    authenticate_drive,
    download_file,
    list_files_in_folder,
    update_file_metadata,
)
from extractor import extract_text
from metadata import generate_metadata, safe_parse
from utils import ensure_directories, get_context
from vectorstore import init_pinecone, upsert_document


CHECK_INTERVAL_SECONDS = 5 * 60
DEFAULT_FOLDER_ID = "1sMZXfh8cfOwrN4sdQvfHSDyrUhS39HfA"
PROCESSED_PATH = Path("output") / "processed.json"


def load_processed(path: Path) -> Dict[str, str]:
    if not path.exists() or not path.is_file():
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    processed: Dict[str, str] = {}

    if isinstance(raw, dict):
        for file_id, modified_time in raw.items():
            if isinstance(file_id, str) and isinstance(modified_time, str):
                processed[file_id] = modified_time
        return processed

    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            file_id = item.get("file_id")
            modified_time = item.get("modifiedTime")
            if isinstance(file_id, str) and isinstance(modified_time, str):
                processed[file_id] = modified_time

    return processed


def save_processed(path: Path, processed: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, str]] = []
    for file_id in sorted(processed.keys()):
        rows.append(
            {
                "file_id": file_id,
                "modifiedTime": processed[file_id],
            }
        )

    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_modified_time(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_new_or_modified(file_info: Dict[str, str], processed: Dict[str, str]) -> bool:
    file_id = file_info.get("id", "")
    current_modified = file_info.get("modifiedTime", "")

    if not file_id:
        return False

    previous_modified = processed.get(file_id)
    if previous_modified is None:
        return True

    current_dt = _parse_modified_time(current_modified)
    previous_dt = _parse_modified_time(previous_modified)

    if current_dt and previous_dt:
        return current_dt > previous_dt

    return current_modified > previous_modified


def process_file(file_info: Dict[str, str], index) -> bool:
    file_id = file_info.get("id", "")
    file_name = file_info.get("name", "")
    mime_type = file_info.get("mimeType", "")

    if not file_id or not file_name:
        return False

    if mime_type not in SUPPORTED_MIME_TYPES:
        print(f"Skipping unsupported file: {file_name} ({mime_type or 'unknown'})")
        return False

    try:
        local_path = download_file(file_id, file_name)
        if not local_path:
            print(f"Failed to process {file_name}: download failed")
            return False

        text = extract_text(Path(local_path), file_name)
        if not text:
            print(f"Failed to process {file_name}: no extractable text")
            return False

        context = get_context(text)

        metadata_result = generate_metadata(
            context=context,
            file_name=file_name,
            file_type=Path(file_name).suffix.lstrip(".").lower() or mime_type,
        )

        if isinstance(metadata_result, dict):
            metadata = metadata_result
        else:
            metadata = safe_parse(str(metadata_result))

        update_file_metadata(file_id=file_id, metadata=metadata)

        record = {
            "source_file_id": file_id,
            "file_name": file_name,
            "file_type": Path(file_name).suffix.lstrip(".").lower() or "unknown",
            "text": text,
            "metadata": metadata,
        }

        upsert_document(index, record)
        print(f"Processed and upserted: {file_name}")
        return True
    except Exception as err:
        print(f"Failed to process {file_name}: {err}")
        return False


def run_watcher() -> None:
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", DEFAULT_FOLDER_ID).strip()
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json").strip()

    if not folder_id:
        raise ValueError("Set GOOGLE_DRIVE_FOLDER_ID in your environment.")

    ensure_directories([Path("data"), PROCESSED_PATH.parent])

    authenticate_drive(credentials_path=credentials_path)
    index = init_pinecone()
    processed = load_processed(PROCESSED_PATH)

    print("Watching for changes... checking every 5 minutes")

    try:
        while True:
            files = list_files_in_folder(folder_id)

            for item in files:
                if not is_new_or_modified(item, processed):
                    continue

                file_name = item.get("name", "unknown")
                file_id = item.get("id", "")
                print(f"New or modified file detected: {file_name} ({file_id})")

                if process_file(item, index):
                    processed[file_id] = item.get("modifiedTime", "")
                    save_processed(PROCESSED_PATH, processed)

            time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("Watcher stopped.")


if __name__ == "__main__":
    run_watcher()
