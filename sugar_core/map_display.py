"""Self-contained geographic backgrounds and libraries for exported maps."""


def configure_map_display(map_obj):
    from branca.element import MacroElement, Template

    # Clustering on a canvas without an active tile layer still needs a finite limit.
    map_obj.options['maxZoom'] = 19
    branding = MacroElement()
    branding._template = Template('''{% macro script(this, kwargs) %}
    {{this._parent.get_name()}}.attributionControl.setPrefix(false);
    {% endmacro %}''')
    # Remove only the library branding; tile-provider attribution remains visible.
    map_obj.add_child(branding)


from functools import lru_cache
from pathlib import Path
import json
import re

ASSETS = Path(__file__).with_name('map_assets')


@lru_cache(maxsize=1)
def country_boundaries():
    return json.loads((ASSETS / 'countries.json').read_text(encoding='utf-8'))


def add_offline_basemap(map_obj):
    import folium
    folium.map.CustomPane('country-background', z_index=200, pointer_events=False).add_to(map_obj)
    folium.GeoJson(
        country_boundaries(), name='Countries (offline)', overlay=False, show=True,
        pane='country-background', interactive=False,
        style_function=lambda feature: {'fillColor': '#eef1e6', 'fillOpacity': 1,
                                        'color': '#8797a2', 'weight': 0.7},
    ).add_to(map_obj)
    map_obj.get_root().html.add_child(folium.Element(
        '<style>.leaflet-container { background: #d9eaf2; } .leaflet-heatmap-layer { pointer-events: none !important; }</style>'
    ))
    from branca.element import MacroElement, Template
    credit = MacroElement()
    credit._template = Template('''{% macro script(this, kwargs) %}
    {{this._parent.get_name()}}.attributionControl.addAttribution('Natural Earth');
    {% endmacro %}''')
    map_obj.add_child(credit)


def add_offline_minimap(map_obj):
    from folium.plugins import MiniMap
    from folium.template import Template
    mini = MiniMap(toggle_display=True, minimized=True)
    mini.countries = country_boundaries()
    mini._template = Template('''{% macro script(this, kwargs) %}
    var {{this.get_name()}} = new L.Control.MiniMap(
      L.geoJSON({{this.countries|tojson}}, {style: {fillColor:'#eef1e6', fillOpacity:1, color:'#8797a2', weight:0.5}}),
      {{this.options|tojavascript}}
    ).addTo({{this._parent.get_name()}});
    {% endmacro %}''')
    mini.add_to(map_obj)


def inline_map_assets(text):
    """Embed audited local libraries; map exports must never fetch CDN assets."""
    manifest = json.loads((ASSETS / 'manifest.json').read_text(encoding='utf-8'))
    def asset(url):
        if url not in manifest:
            raise ValueError(f'Map asset is not bundled: {url}')
        return (ASSETS / manifest[url]).read_text(encoding='utf-8')
    text = re.sub(r'<script src="([^"]+)"\s*></script>',
                  lambda m: '<script>' + asset(m[1]).replace('</script', r'<\/script') + '</script>', text)
    text = re.sub(r'<link rel="stylesheet" href="([^"]+)"\s*/?>',
                  lambda m: '<style>' + asset(m[1]).replace('</style', r'<\/style') + '</style>', text)
    return text


def save_offline_map(map_obj, target):
    Path(target).write_text(inline_map_assets(map_obj.get_root().render()), encoding='utf-8')
