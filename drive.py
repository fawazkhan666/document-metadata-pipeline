from pathlib import Path
import json
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from utils import safe_filename


SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/xml",
    "text/xml",
}

SCOPES = ["https://www.googleapis.com/auth/drive"]

_drive_service = None

def authenticate_drive(credentials_path: str = "credentials.json"):
    global _drive_service

    if _drive_service is not None:
        return _drive_service

    token_path = Path("token.json")
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        current_scopes = set(creds.scopes or [])
        required_scopes = set(SCOPES)
        if not required_scopes.issubset(current_scopes):
            creds = None
            token_path.unlink(missing_ok=True)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None
                token_path.unlink(missing_ok=True)
        else:
            if not Path(credentials_path).exists():
                raise FileNotFoundError(
                    f"OAuth credentials file not found: {credentials_path}"
                )

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json(), encoding="utf-8")

    _drive_service = build("drive", "v3", credentials=creds)
    return _drive_service

def list_files_in_folder(folder_id: str) -> List[Dict[str, str]]:
    service = authenticate_drive()
    query = f"'{folder_id}' in parents and trashed = false"

    try:
        response = (
            service.files()
            .list(
                q=query,
                fields="files(id, name, mimeType, modifiedTime)",
                pageSize=1000,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        return response.get("files", [])
    except HttpError as err:
        print(f"Failed to list files in folder {folder_id}: {err}")
        return []

def download_file(file_id: str, file_name: str) -> Optional[str]:
    service = authenticate_drive()

    try:
        metadata = (
            service.files().get(fileId=file_id, fields="id,name,mimeType").execute()
        )
        mime_type = metadata.get("mimeType", "")

        if mime_type not in SUPPORTED_MIME_TYPES:
            print(
                f"Skipping unsupported file '{file_name}' ({mime_type or 'unknown mimeType'})."
            )
            return None

        local_name = safe_filename(file_name)
        destination = Path("data") / local_name
        destination.parent.mkdir(parents=True, exist_ok=True)

        request = service.files().get_media(fileId=file_id)
        with destination.open("wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        return str(destination)
    except HttpError as err:
        print(f"Failed to download file '{file_name}' ({file_id}): {err}")
    except OSError as err:
        print(f"Failed to save file '{file_name}' ({file_id}): {err}")

    return None



def download_supported_files(
    folder_id: str,
    data_dir: Path,
    credentials_path: Optional[str] = None,
) -> List[Dict[str, str]]:
    global _drive_service

    if credentials_path:
        _drive_service = None
        authenticate_drive(credentials_path=credentials_path)
    else:
        authenticate_drive()

    files = list_files_in_folder(folder_id)

    downloaded: List[Dict[str, str]] = []
    for file_info in files:
        mime_type = file_info.get("mimeType", "")
        if mime_type not in SUPPORTED_MIME_TYPES:
            print(
                f"Skipping unsupported file '{file_info.get('name', '')}' ({mime_type or 'unknown mimeType'})."
            )
            continue

        downloaded_path = download_file(file_info["id"], file_info["name"])
        if not downloaded_path:
            continue

        local_path = Path(downloaded_path)

        if local_path.parent.resolve() != data_dir.resolve():
            target = data_dir / local_path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            local_path.replace(target)
            local_path = target

        downloaded.append(
            {
                "id": file_info["id"],
                "name": file_info["name"],
                "mimeType": file_info["mimeType"],
                "local_path": str(local_path),
            }
        )

    return downloaded


def _to_drive_app_properties(metadata: Dict[str, Any]) -> Dict[str, str]:
    def _clean(value: Any, limit: int = 120) -> str:
        if isinstance(value, list):
            value = ", ".join(str(v).strip() for v in value if str(v).strip())
        text = str(value).strip()
        return text[:limit] if text else "unknown"

    return {
        "document_type": _clean(metadata.get("document_type", "unknown")),
        "project": _clean(metadata.get("project", "unknown")),
        "customer": _clean(metadata.get("customer", "unknown")),
        "project_phase": _clean(metadata.get("project_phase", "unknown")),
        "data_sensitivity": _clean(metadata.get("data_sensitivity", "unknown")),
        "contains_pii": _clean(metadata.get("contains_pii", "unknown")),
        "tags": _clean(metadata.get("tags", [])),
    }


def update_file_metadata(
    file_id: str,
    metadata: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    service = authenticate_drive()

    metadata_json = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    file_metadata = {
        "description": f"enriched_metadata={metadata_json[:8000]}",
        "appProperties": _to_drive_app_properties(metadata),
    }

    try:
        updated = (
            service.files()
            .update(
                fileId=file_id,
                body=file_metadata,
                fields="id,name,mimeType,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        return {
            "id": updated.get("id", ""),
            "name": updated.get("name", ""),
            "mimeType": updated.get("mimeType", ""),
            "webViewLink": updated.get("webViewLink", ""),
        }
    except HttpError as err:
        print(f"Failed to update metadata for file '{file_id}': {err}")
        return None
