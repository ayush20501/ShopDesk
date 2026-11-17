import sys

from .config import load_settings
from .rag.retriever import ingest

if __name__ == "__main__":
    settings = load_settings()
    modes = sys.argv[1:] or [settings.chunking]
    for mode in modes:
        print(f"indexed {ingest(settings, mode)} chunks with '{mode}' chunking")
