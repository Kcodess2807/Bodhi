"""CLI tool for ingesting company interview prep documents into the RAG knowledge base.

Usage:
    python ingest_docs.py --company "Google" --role "SDE-2" --file prep_notes.txt
    python ingest_docs.py --company "Google" --role "SDE-2" --text "Google focuses on..."
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest company interview prep materials into Bodhi's RAG knowledge base."
    )
    parser.add_argument("--company", required=True, help="Company name (e.g. Google)")
    parser.add_argument("--role", default="general", help="Role (e.g. SDE-2). Defaults to 'general'.")
    parser.add_argument("--file", type=str, help="Path to a text file to ingest")
    parser.add_argument("--text", type=str, help="Inline text to ingest")
    parser.add_argument("--source", default="", help="Optional source label (e.g. 'glassdoor', 'prep_doc')")
    parser.add_argument("--contributor", default="cli_user", help="Who contributed this data")

    args = parser.parse_args()

    if not args.file and not args.text:
        parser.error("Provide either --file or --text")

    if args.file:
        path = Path(args.file)
        if not path.is_file():
            print(f"Error: File not found: {path}")
            sys.exit(1)
        content = path.read_text(encoding="utf-8")
    else:
        content = args.text

    if not content or not content.strip():
        print("Error: Empty content — nothing to ingest.")
        sys.exit(1)

    from src.storage import BodhiStorage
    from src.rag import ingest_document

    print(f"Connecting to NeonDB...")
    storage = BodhiStorage()
    storage.init_tables()

    print(f"Ingesting for {args.company} / {args.role}...")
    n = ingest_document(
        company=args.company,
        role=args.role,
        text=content,
        storage=storage,
        source_label=args.source,
        contributed_by=args.contributor,
    )
    print(f"Done — {n} chunk(s) embedded and stored.")
    storage.close()


if __name__ == "__main__":
    main()
