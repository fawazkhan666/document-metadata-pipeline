from pathlib import Path
import xml.etree.ElementTree as ET

from docx import Document
from pypdf import PdfReader



def _clean_text(text: str) -> str:
    cleaned_lines = [line.strip() for line in text.splitlines()]
    non_empty_lines = [line for line in cleaned_lines if line]
    return "\n".join(non_empty_lines).strip()



def extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    chunks = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return _clean_text("\n".join(chunks))



def extract_docx(path: Path) -> str:
    doc = Document(str(path))
    return _clean_text("\n".join(p.text for p in doc.paragraphs if p.text))



def extract_xml(path: Path) -> str:
    root = ET.parse(path).getroot()
    raw = " ".join(text.strip() for text in root.itertext() if text and text.strip())
    return _clean_text(raw)



def extract_text(file_path: Path, file_name: str) -> str:
    path = Path(file_path)

    if not path.exists() or not path.is_file():
        print(f"Skipping missing or invalid file: {file_name}")
        return ""

    suffix = path.suffix.lower()

    try:
        if suffix == ".pdf":
            text = extract_pdf(path)
        elif suffix == ".docx":
            text = extract_docx(path)
        elif suffix == ".xml":
            text = extract_xml(path)
        else:
            print(f"Skipping unsupported file type for extraction: {file_name}")
            return ""

        if not text:
            print(f"No extractable text found in file: {file_name}")
            return ""

        return text
    except Exception as err:
        print(f"Failed to extract text from {file_name}: {err}")
        return ""



def extract_text_from_file(path: Path) -> str:
    return extract_text(path, path.name)
