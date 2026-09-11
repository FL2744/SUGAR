# SUGAR folder guide

The project root is the current working source. On September 10, 2026 it was
updated from the imported nested `SUGAR/` folder, which contained newer macOS
compatibility, Activity streaming, provider selection, and Word packaging fixes.
The core SUGAR.py, sugar_analysis.py, requirements, and logo matched both copies.

- `SUGAR.py`, `sugar_analysis.py`, `sugar_bridge.py`: current Python source.
- `SUGAR-macOS/`: current native macOS source, scripts, and regression checks.
- `examples/`: sample map, spreadsheet, and Word/PDF analysis.
- `outputs/2026-09-09/`: existing generated research results.
- `scratch/`: the existing test HTML file, preserved for reference.
- `private-notes/`: existing RTF notes, including credential notes; kept local and ignored by Git.
- `archive/2026-09-10-cleanup/imported-source-original/`: untouched imported source snapshot.
- `archive/2026-09-10-cleanup/previous-working-copy/`: previous root source and its
  `.build` and `.build-native` directories, including the existing unsigned DMG.
  Those artifacts belong to the older source, not the current working version.
  Moved build environments may contain absolute paths; treat them as historical
  artifacts rather than reusable build environments.

The existing `.git` history and `.venv` remain in place. `.x_bearer_token` and
`geocode_cache.json` remain at the root because the Python app uses those paths.
Archive, outputs, scratch, and private notes are ignored by Git. Nothing was
deleted, built, signed, published, or committed during this cleanup. Files outside
this project were not moved. The existing README and macOS README still describe
the application and its build process.

The archive's `inventory.json` records source checksums and relocated files.
