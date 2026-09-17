# Third-party software notices

SUGAR is licensed under the Apache License, Version 2.0. It also uses third-party software whose licenses remain in force independently of the SUGAR license.

This document is a release-facing summary of SUGAR's direct dependencies. It is not a substitute for the complete license text shipped by each dependency. Packaged distributions must preserve all notices and license materials required by the exact dependency versions included in that build.

## Runtime dependencies

| Component | License family | Role in SUGAR |
| --- | --- | --- |
| Beautiful Soup (`beautifulsoup4`) | MIT | HTML parsing |
| certifi | Mozilla Public License 2.0 | CA certificate bundle |
| folium | MIT | interactive map generation |
| geopy | MIT | geocoding and distance utilities |
| langdetect | Apache License 2.0 | language detection |
| Matplotlib | Matplotlib/PSF-style license | charts and figures |
| OpenAI Python library | Apache License 2.0 | optional OpenAI-compatible LLM client |
| openpyxl | MIT | XLSX input/output |
| pandas | BSD 3-Clause | tabular processing |
| python-docx | MIT | DOCX reporting |
| ReportLab | BSD-style | PDF reporting |
| Requests | Apache License 2.0 | HTTP client |

## Optional and packaging dependencies

| Component | License family | Notes |
| --- | --- | --- |
| PySide6 / Qt for Python | LGPLv3/GPLv3 or commercial Qt license | Used by the Windows desktop application. SUGAR community Windows builds select the LGPLv3 option for LGPL-covered Qt/PySide6 components actually bundled with the application. |
| PyInstaller | GPLv2 with the PyInstaller bootloader exception; some files Apache-2.0 | Used to create packaged applications. PyInstaller's exception permits generated bundles to use the application's license subject to bundled dependency licenses. |
| arabic-reshaper | MIT | Optional RTL text support |
| python-bidi | LGPL | Optional bidirectional-text support |

## Packaged desktop applications

The Windows portable application bundles third-party runtime libraries, including Qt/PySide6. The Windows build is intentionally produced as an `onedir` application for the PySide6 GUI, leaving Qt libraries as separate files in the application directory rather than statically incorporating them into SUGAR source code. Release packages include this file, SUGAR's `LICENSE` and `NOTICE`, a generated `licenses/` directory containing license/notice files discovered from the exact installed dependency set used for that build, and `third_party_licenses/qt/` containing the LGPLv3/GPLv3 texts and SUGAR's Qt source/relinking notice.

The macOS application bundles SUGAR's Python backend. Release packages include SUGAR's `LICENSE`, `NOTICE`, this notice file, and the generated dependency-license directory in the application resources.

## Data, services, and platform content

The Apache-2.0 license applies to SUGAR software; it does **not** grant rights in third-party social-media content, APIs, websites, datasets, trademarks, platform materials, or research data collected with SUGAR. Users remain responsible for the terms, permissions, retention requirements, and laws applicable to the material they collect or process.

## Release verification

Dependency versions and licensing can change. Before each public binary release, maintainers should regenerate or review the dependency inventory, verify licenses for the actual resolved versions, and preserve any required attribution/license files inside the release artifact.
