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

    labels = (data / "natural-earth-country-labels.json").read_text(encoding="utf-8")

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
        // Country names belong to the downloaded map only. Declutter at each
        // zoom level so small countries become readable as the user zooms in.
        const map = this;
        const pane = map.createPane('countryLabels');
        pane.style.zIndex = 350;
        pane.style.pointerEvents = 'none';
        const names = L.layerGroup().addTo(map);
        const measure = document.createElement('canvas').getContext('2d');
        measure.font = '11px Arial';
        function labelCountries() {
            names.clearLayers();
            const occupied = [], size = map.getSize(), zoom = map.getZoom();
            COUNTRY_LABELS.forEach(function (country) {
                if (zoom < country.zoom) return;
                const point = map.latLngToContainerPoint([country.lat, country.lon]);
                const width = measure.measureText(country.name).width + 8;
                const box = [point.x-width/2, point.y-9, point.x+width/2, point.y+9];
                if (box[0]<0 || box[1]<0 || box[2]>size.x || box[3]>size.y) return;
                if (occupied.some(b => box[0]<b[2] && box[2]>b[0] && box[1]<b[3] && box[3]>b[1])) return;
                occupied.push(box);
                const text = document.createElement('span');
                text.textContent = country.name;
                text.style.cssText = 'font:11px Arial;color:#334155;white-space:nowrap;text-shadow:0 0 3px white,0 0 3px white;';
                L.marker([country.lat,country.lon], {
                    pane:'countryLabels', interactive:false, keyboard:false,
                    icon:L.divIcon({className:'sugar-country-label', html:text,
                        iconSize:[width,18], iconAnchor:[width/2,9]})
                }).addTo(names);
            });
        }
        map.on('zoomend moveend resize', labelCountries);
        map.whenReady(labelCountries);
        this.setMaxBounds([[-85, -180], [85, 180]]);
    });
    </script>'''.replace('LAND_DATA', land).replace('COUNTRY_DATA', countries).replace('COUNTRY_LABELS', labels)
    page = re.sub(r'<script\s+src="(https[^"]+)"[^>]*>\s*</script>', script, page)
    page = re.sub(r'<link\s+rel="stylesheet"\s+href="(https[^"]+)"[^>]*>', style, page)
    licenses = json.dumps((data / 'html-map-licenses.md').read_text(encoding='utf-8')).replace('<', '\\u003c')
    setup += '<script type="application/json" id="sugar-map-licenses">' + licenses + '</script>'
    page = page.replace('</head>', setup + '\n</head>', 1)
    policy = "default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; base-uri 'none'"
    page = page.replace('<head>', '<head>\n<meta http-equiv="Content-Security-Policy" content="' + policy + '">', 1)
    target.write_text(page, encoding="utf-8")
