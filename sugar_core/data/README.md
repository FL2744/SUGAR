Natural Earth land geometry
==========================

`natural-earth-land.json` derives from Natural Earth's 1:110m land polygons,
`nvkelso/natural-earth-vector/geojson/ne_110m_land.geojson`, Git blob
`04811d72fff2701ec67587e30ad8942675b511e3`. Properties were removed and coordinates
rounded to two decimal places for compact, offline country snapshot maps.

Source: https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_land.geojson

Natural Earth data is public domain: https://www.naturalearthdata.com/about/terms-of-use/
The overview shows land rather than political boundary claims. It is not street
mapping and does not improve the precision of imported institution coordinates.

Offline HTML export country boundaries
======================================

`natural-earth-countries.json` uses Natural Earth 1:110m Admin 0 countries,
with properties removed and coordinates rounded to three decimal places.
Used only by the HTML export. Natural Earth depicts de facto boundaries;
this is a generalized overview, not a statement of sovereignty. Public domain.

Source: https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_admin_0_countries.geojson
Source SHA-256: `6866c877d39cba9c357620878839b336d569f8c662d3cfab4cb1dbe2d39c977f`

`natural-earth-country-labels.json` retains English country names, label coordinates,
label rank, and minimum label zoom from the same Natural Earth v5.1.2 source.
Labels are embedded only in HTML exports and decluttered as the user zooms.
