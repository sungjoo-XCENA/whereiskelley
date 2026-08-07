import json
import sys
from pathlib import Path

from pypdf import PdfReader


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "text": "", "error": "PDF path is required."}))
        return 2

    path = Path(sys.argv[1])
    try:
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text(extraction_mode="layout") or "")
        text = "\n\f\n".join(pages).strip()
        print(
            json.dumps(
                {
                    "ok": True,
                    "text": text,
                    "pages": len(reader.pages),
                    "needsOcr": not bool(text),
                    "error": "" if text else "PDF contains no extractable text; OCR review is required.",
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "text": "", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
