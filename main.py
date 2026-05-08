import os
from pathlib import Path

from drive import (
	SUPPORTED_MIME_TYPES,
	authenticate_drive,
	download_file,
	list_files_in_folder,
	update_file_metadata,
)
from extractor import extract_text
from metadata import generate_metadata, is_unknown_metadata, safe_parse
from utils import ensure_directories, get_context, write_json


def run_pipeline() -> None:
	folder_id = "1sMZXfh8cfOwrN4sdQvfHSDyrUhS39HfA"
	credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json").strip()

	if not folder_id:
		raise ValueError("Set GOOGLE_DRIVE_FOLDER_ID in your environment.")

	data_dir = Path("data")
	output_path = Path("output") / "data.json"
	ensure_directories([data_dir, output_path.parent])

	print("Step 1: Authenticating Google Drive")
	authenticate_drive(credentials_path=credentials_path)

	print("Step 2: Getting files from folder")
	files = list_files_in_folder(folder_id)

	results = []
	for item in files:
		file_id = item.get("id", "")
		file_name = item.get("name", "")
		mime_type = item.get("mimeType", "")
		file_stem = Path(file_name).stem.lower()

		if "_enriched" in file_stem:
			print(f"Skipping already enriched file: {file_name}")
			continue

		if mime_type not in SUPPORTED_MIME_TYPES:
			print(f"Skipping unsupported file: {file_name} ({mime_type or 'unknown'})")
			continue

		print(f"Processing file: {file_name}")
		try:
			local_path = download_file(file_id, file_name)
			if not local_path:
				print(f"Failure: {file_name} - download failed")
				continue

			text = extract_text(Path(local_path), file_name)
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

			metadata_ok = not is_unknown_metadata(metadata)

			results.append(
				{
					"source_file_id": file_id,
					"file_name": file_name,
					"file_type": Path(file_name).suffix.lstrip(".").lower() or "unknown",
					"text": text,
					"metadata": metadata,
				}
			)

			if metadata_ok:
				updated_file = update_file_metadata(
					file_id=file_id,
					metadata=metadata,
				)
				if updated_file:
					results[-1]["updated_drive_file"] = updated_file
					print(f"Updated metadata on Drive: {updated_file.get('name', '')}")
				else:
					results[-1]["updated_drive_file"] = None
					print(f"Metadata update failed for: {file_name}")
				print(f"Success: {file_name}")
			else:
				results[-1]["updated_drive_file"] = None
				print(f"Skipped Drive metadata update due to LLM failure: {file_name}")
				print(f"Failure: {file_name} - metadata generation returned defaults")
		except Exception as err:
			print(f"Failure: {file_name} - {err}")

	print("Step 4: Saving results")
	write_json(output_path, results)
	print(f"Pipeline complete. Wrote {len(results)} records to {output_path}")

	print("Step 5: Ingesting to Pinecone...")
	from ingest_to_pinecone import ingest
	ingest(output_path)
    

if __name__ == "__main__":
	run_pipeline()
