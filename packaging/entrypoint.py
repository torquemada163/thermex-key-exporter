"""PyInstaller entry point with an absolute package import."""

from thermex_key_exporter.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
