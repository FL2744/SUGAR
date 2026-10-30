"""Make downloaded Folium HTML self-contained; never used by the in-app map."""
from __future__ import annotations

import json
import re
from pathlib import Path


def make_html_export_offline(path: str | Path) -> None:
    """Finish an HTML export with embedded geography and runtime resources."""
    target = Path(path)
    page = target.read_text(encoding="utf-8")
    data = Path(__file__).parent / "data"
    assets = json.loads((data / "html-map-assets.json").read_text(encoding="utf-8"))
    land = (data / "natural-earth-land.json").read_text(encoding="utf-8")

    countries = (data / "natural-earth-countries.json").read_text(encoding="utf-8")

    def script(match: re.Match) -> str:
        return '<script>' + assets[match.group(1)].replace('</script', '<\\/script') + '</script>'

    def style(match: re.Match) -> str:
        return '<style>' + assets[match.group(1)].replace('</style', '<\\/style') + '</style>'

    # Convert tile layers (including the minimap's) into empty local groups.
    # Preserve their names because the generated controls may reference them.
    page, count = re.subn(r'L\.tileLayer\(\s*"https[^\n]+\n\s*\{[^}]*\}\s*\)', 'L.layerGroup([])', page)
    if 'L.tileLayer(' in page or count == 0:
        raise ValueError('Unsupported HTML tile template; export was not modified.')
    page = re.sub(r'base_layers\s*:\s*\{[^}]*\}', 'base_layers: {}', page)
    page = page.replace('"worldCopyJump": true', '"worldCopyJump": false')
    # Executed after the libraries, before any map is created; applies also to
    # the export's overview minimap, without changing the application renderer.
    setup = '''<script>
    L.Map.addInitHook(function () {
        this.attributionControl && this.attributionControl.setPrefix(false);
        this.attributionControl && this.attributionControl.addAttribution('Land and boundaries: Natural Earth (public domain; de facto)');
        this.getContainer().style.background = '#dceaf2';
        L.geoJSON(LAND_DATA, {
            pane: 'tilePane', interactive: false,
            style: {color: '#94a3b8', weight: 0.7, fillColor: '#e2e8d5', fillOpacity: 1}
        }).addTo(this);
        L.geoJSON(COUNTRY_DATA, {
            pane: 'tilePane', interactive: false,
            style: {color: '#64748b', weight: 0.8, fill: false, opacity: 0.85}
        }).addTo(this);
        this.setMaxBounds([[-85, -180], [85, 180]]);
    });
    </script>'''.replace('LAND_DATA', land).replace('COUNTRY_DATA', countries)
    page = re.sub(r'<script\s+src="(https[^"]+)"[^>]*>\s*</script>', script, page)
    page = re.sub(r'<link\s+rel="stylesheet"\s+href="(https[^"]+)"[^>]*>', style, page)
    licenses = json.dumps((data / 'html-map-licenses.md').read_text(encoding='utf-8')).replace('<', '\\u003c')
    setup += '<script type="application/json" id="sugar-map-licenses">' + licenses + '</script>'
    page = page.replace('</head>', setup + '\n</head>', 1)
    policy = "default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; base-uri 'none'"
    page = page.replace('<head>', '<head>\n<meta http-equiv="Content-Security-Policy" content="' + policy + '">', 1)
    target.write_text(page, encoding="utf-8")
