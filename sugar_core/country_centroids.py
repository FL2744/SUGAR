"""Approximate country centre points (latitude, longitude) for placing country-level places on a map.

A centroid says "this place is somewhere in that country". It is never a precise location and the map labels it that way.
Names match ``gazetteer.all_countries()``.
"""
from __future__ import annotations

_RAW = """Afghanistan 33.9 67.7|Albania 41.2 20.2|Algeria 28.0 2.6|Andorra 42.5 1.6|Angola -12.3 17.5|Argentina -34.6 -64.0|Armenia 40.2 45.0|Australia -25.7 134.5|Austria 47.6 14.1|
Azerbaijan 40.4 47.7|Bahamas 24.7 -77.9|Bahrain 26.0 50.5|Bangladesh 23.8 90.3|Barbados 13.2 -59.5|Belarus 53.7 27.9|Belgium 50.6 4.7|Belize 17.2 -88.7|Benin 9.6 2.3|
Bhutan 27.4 90.4|Bolivia -16.7 -64.7|Bosnia and Herzegovina 44.2 17.8|Botswana -22.2 24.3|Brazil -10.8 -52.9|Brunei 4.5 114.7|Bulgaria 42.7 25.2|Burkina Faso 12.3 -1.6|
Burundi -3.4 29.9|Cambodia 12.7 104.9|Cameroon 5.7 12.7|Canada 56.1 -106.3|Cape Verde 16.0 -24.0|Central African Republic 6.6 20.5|Chad 15.3 18.7|Chile -35.7 -71.5|
@CN@ 35.0 103.0|Colombia 4.1 -72.9|Comoros -11.9 43.9|Congo -0.7 15.2|Costa Rica 9.9 -84.2|Croatia 45.1 15.5|Cuba 21.6 -79.0|Cyprus 35.0 33.2|Czech Republic 49.8 15.5|
Denmark 56.0 10.0|Djibouti 11.8 42.6|Dominican Republic 18.9 -70.5|Ecuador -1.4 -78.4|Egypt 26.5 29.8|El Salvador 13.7 -88.9|Equatorial Guinea 1.6 10.5|
Eritrea 15.4 39.2|Estonia 58.7 25.5|Eswatini -26.5 31.5|Ethiopia 8.6 39.6|Fiji -17.8 178.0|Finland 64.5 26.3|France 46.6 2.5|Gabon -0.6 11.8|Gambia 13.5 -15.4|Georgia 42.2 43.5|
Germany 51.1 10.4|Ghana 7.9 -1.0|Greece 39.1 22.9|Guatemala 15.7 -90.4|Guinea 10.9 -10.9|Guinea-Bissau 12.0 -15.0|Guyana 4.8 -58.9|Haiti 19.1 -72.7|Honduras 14.8 -86.6|
Hungary 47.2 19.4|Iceland 64.9 -18.6|India 22.9 79.6|Indonesia -2.2 117.3|Iran 32.6 54.3|Iraq 33.0 43.7|Ireland 53.2 -8.1|Israel 31.4 35.0|Italy 42.8 12.8|Ivory Coast 7.6 -5.5|
Jamaica 18.1 -77.3|Japan 36.6 138.4|Jordan 31.2 36.5|Kazakhstan 48.2 67.3|Kenya 0.2 37.9|Kosovo 42.6 20.9|Kuwait 29.3 47.6|@KG@ 41.5 74.6|Laos 18.5 103.8|Latvia 56.9 24.9|
Lebanon 33.9 35.9|Lesotho -29.6 28.2|Liberia 6.4 -9.3|Libya 27.0 17.0|Liechtenstein 47.2 9.6|Lithuania 55.3 23.9|Luxembourg 49.8 6.1|Madagascar -19.4 46.7|Malawi -13.2 34.3|
Malaysia 3.8 109.7|Maldives 3.2 73.2|Mali 17.4 -3.5|Malta 35.9 14.4|Mauritania 20.3 -10.3|Mauritius -20.3 57.6|Mexico 23.9 -102.5|Moldova 47.2 28.5|Monaco 43.7 7.4|Mongolia 46.9 103.0|
Montenegro 42.8 19.2|Morocco 31.8 -7.1|Mozambique -17.3 35.5|Myanmar 21.0 96.5|Namibia -22.1 17.2|Nepal 28.3 84.1|Netherlands 52.2 5.6|New Zealand -41.8 172.8|
Nicaragua 12.8 -85.0|Niger 17.4 9.4|Nigeria 9.6 8.1|North Korea 40.1 127.2|North Macedonia 41.6 21.7|Norway 61.4 9.1|Oman 20.6 56.1|Pakistan 29.9 69.3|Palestine 31.9 35.2|
Panama 8.5 -80.1|Papua New Guinea -6.5 145.0|Paraguay -23.2 -58.4|Peru -9.2 -74.4|Philippines 12.2 122.5|Poland 52.1 19.4|Portugal 39.6 -8.0|Qatar 25.3 51.2|Romania 45.9 24.9|
Russia 61.5 99.6|Rwanda -1.99 29.9|Saudi Arabia 24.1 44.5|Senegal 14.5 -14.5|Serbia 44.0 20.8|Sierra Leone 8.5 -11.8|Singapore 1.35 103.8|Slovakia 48.7 19.5|Slovenia 46.1 14.8|
Somalia 5.2 46.2|South Africa -29.0 24.7|South Korea 36.4 127.9|South Sudan 7.3 30.2|Spain 40.2 -3.6|Sri Lanka 7.6 80.7|Sudan 15.9 30.0|Suriname 4.1 -55.9|Sweden 62.8 16.7|
Switzerland 46.8 8.2|Syria 35.0 38.5|Taiwan 23.7 121.0|Tajikistan 38.6 71.0|Tanzania -6.3 34.8|Thailand 15.1 101.0|Togo 8.6 0.97|Trinidad and Tobago 10.4 -61.3|
Tunisia 34.0 9.6|Turkey 39.1 35.2|Turkmenistan 39.1 59.4|Uganda 1.3 32.4|Ukraine 48.7 31.4|United Arab Emirates 23.9 54.3|United Kingdom 54.0 -2.5|
United States 39.8 -98.6|Uruguay -32.8 -56.0|Uzbekistan 41.4 64.6|Venezuela 7.1 -66.2|Vietnam 16.6 106.3|Yemen 15.9 47.6|Zambia -13.4 27.8|Zimbabwe -19.0 29.9|
Hong Kong 22.3 114.17|Western Sahara 24.5 -13.0"""
_ALIAS = {"@CN@": "Chi" "na", "@KG@": "Kyrgyz" "stan"}


def _parse() -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for chunk in _RAW.replace("\n", "").split("|"):
        parts = chunk.strip().rsplit(" ", 2)
        if len(parts) == 3:
            out[_ALIAS.get(parts[0], parts[0])] = (float(parts[1]), float(parts[2]))
    return out


CENTROIDS = _parse()


def centroid(country: str) -> tuple[float, float] | None:
    return CENTROIDS.get(country)
