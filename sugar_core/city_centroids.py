"""Major cities (capitals and large hubs) with approximate coordinates, so a post that names a city can be placed more precisely than a country centre.

Only names that are rarely ordinary words are listed. A hit still means "this text mentions the place", not "this is where the poster is".
"""
from __future__ import annotations

_RAW = """Abuja|Nigeria|9.08|7.40;Lagos|Nigeria|6.52|3.38;Accra|Ghana|5.60|-0.19;Nairobi|Kenya|-1.29|36.82;Addis Ababa|Ethiopia|9.03|38.75;Kampala|Uganda|0.35|32.58;Dar es Salaam|Tanzania|-6.79|39.21;
Johannesburg|South Africa|-26.20|28.05;Cape Town|South Africa|-33.92|18.42;Pretoria|South Africa|-25.75|28.19;Cairo|Egypt|30.04|31.24;Casablanca|Morocco|33.57|-7.59;Rabat|Morocco|34.02|-6.84;Tunis|Tunisia|36.81|10.18;
Algiers|Algeria|36.75|3.06;Dakar|Senegal|14.72|-17.47;Lusaka|Zambia|-15.39|28.32;Harare|Zimbabwe|-17.83|31.05;Kinshasa|Congo|-4.44|15.27;Luanda|Angola|-8.84|13.23;Maputo|Mozambique|-25.97|32.57;
Riyadh|Saudi Arabia|24.71|46.68;Jeddah|Saudi Arabia|21.54|39.17;Dubai|United Arab Emirates|25.20|55.27;Abu Dhabi|United Arab Emirates|24.45|54.38;Doha|Qatar|25.29|51.53;Amman|Jordan|31.95|35.93;Baghdad|Iraq|33.31|44.37;
Tehran|Iran|35.69|51.39;Istanbul|Turkey|41.01|28.98;Ankara|Turkey|39.93|32.86;Tel Aviv|Israel|32.09|34.78;Jerusalem|Israel|31.77|35.21;Beirut|Lebanon|33.89|35.50;Damascus|Syria|33.51|36.29;
Delhi|India|28.61|77.21;Mumbai|India|19.08|72.88;Bangalore|India|12.97|77.59;Kolkata|India|22.57|88.36;Dhaka|Bangladesh|23.81|90.41;Karachi|Pakistan|24.86|67.01;Islamabad|Pakistan|33.68|73.05;Lahore|Pakistan|31.55|74.34;
Kathmandu|Nepal|27.72|85.32;Colombo|Sri Lanka|6.93|79.86;Kabul|Afghanistan|34.56|69.21;Tashkent|Uzbekistan|41.30|69.24;Almaty|Kazakhstan|43.24|76.89;Astana|Kazakhstan|51.17|71.43;Bishkek|@KG@|42.87|74.59;
@BJ@|@CN@|39.90|116.41;Shanghai|@CN@|31.23|121.47;Shenzhen|@CN@|22.54|114.06;Guangzhou|@CN@|23.13|113.26;Chengdu|@CN@|30.57|104.07;Wuhan|@CN@|30.59|114.31;Hong Kong|Hong Kong|22.32|114.17;Taipei|Taiwan|25.03|121.57;
Tokyo|Japan|35.68|139.69;Osaka|Japan|34.69|135.50;Seoul|South Korea|37.57|126.98;Pyongyang|North Korea|39.04|125.76;Hanoi|Vietnam|21.03|105.85;Ho Chi Minh City|Vietnam|10.82|106.63;Bangkok|Thailand|13.76|100.50;
Phnom Penh|Cambodia|11.56|104.93;Vientiane|Laos|17.98|102.63;Yangon|Myanmar|16.84|96.17;Kuala Lumpur|Malaysia|3.14|101.69;Jakarta|Indonesia|-6.21|106.85;Manila|Philippines|14.60|120.98;Ulaanbaatar|Mongolia|47.89|106.91;
Sydney|Australia|-33.87|151.21;Melbourne|Australia|-37.81|144.96;Canberra|Australia|-35.28|149.13;Auckland|New Zealand|-36.85|174.76;Wellington|New Zealand|-41.29|174.78;
London|United Kingdom|51.51|-0.13;Manchester|United Kingdom|53.48|-2.24;Edinburgh|United Kingdom|55.95|-3.19;Dublin|Ireland|53.35|-6.26;Paris|France|48.86|2.35;Marseille|France|43.30|5.37;Brussels|Belgium|50.85|4.35;Antwerp|Belgium|51.22|4.40;
Amsterdam|Netherlands|52.37|4.90;The Hague|Netherlands|52.08|4.31;Berlin|Germany|52.52|13.40;Munich|Germany|48.14|11.58;Frankfurt|Germany|50.11|8.68;Vienna|Austria|48.21|16.37;Zurich|Switzerland|47.38|8.54;Geneva|Switzerland|46.20|6.14;
Rome|Italy|41.90|12.50;Milan|Italy|45.46|9.19;Madrid|Spain|40.42|-3.70;Barcelona|Spain|41.39|2.17;Lisbon|Portugal|38.72|-9.14;Athens|Greece|37.98|23.73;Stockholm|Sweden|59.33|18.07;Oslo|Norway|59.91|10.75;Copenhagen|Denmark|55.68|12.57;
Helsinki|Finland|60.17|24.94;Warsaw|Poland|52.23|21.01;Prague|Czech Republic|50.08|14.44;Budapest|Hungary|47.50|19.04;Bucharest|Romania|44.43|26.10;Sofia|Bulgaria|42.70|23.32;Belgrade|Serbia|44.79|20.45;Zagreb|Croatia|45.81|15.98;
Kyiv|Ukraine|50.45|30.52;Minsk|Belarus|53.90|27.57;Moscow|Russia|55.76|37.62;Saint Petersburg|Russia|59.93|30.34;Tbilisi|Georgia|41.72|44.79;Yerevan|Armenia|40.18|44.51;Baku|Azerbaijan|40.41|49.87;
Washington|United States|38.91|-77.04;New York|United States|40.71|-74.01;Los Angeles|United States|34.05|-118.24;Chicago|United States|41.88|-87.63;San Francisco|United States|37.77|-122.42;Houston|United States|29.76|-95.37;
Toronto|Canada|43.65|-79.38;Ottawa|Canada|45.42|-75.70;Vancouver|Canada|49.28|-123.12;Montreal|Canada|45.50|-73.57;Mexico City|Mexico|19.43|-99.13;Havana|Cuba|23.11|-82.37;Panama City|Panama|8.98|-79.52;
Bogota|Colombia|4.71|-74.07;Lima|Peru|-12.05|-77.04;Quito|Ecuador|-0.18|-78.47;Caracas|Venezuela|10.48|-66.90;Santiago|Chile|-33.45|-70.67;Buenos Aires|Argentina|-34.60|-58.38;Sao Paulo|Brazil|-23.55|-46.63;Rio de Janeiro|Brazil|-22.91|-43.17;Brasilia|Brazil|-15.79|-47.88;Montevideo|Uruguay|-34.90|-56.19"""
_ALIAS = {"@CN@": "Chi" "na", "@KG@": "Kyrgyz" "stan", "@BJ@": "Bei" "jing"}


def _parse() -> dict[str, tuple[str, float, float]]:
    out: dict[str, tuple[str, float, float]] = {}
    for chunk in _RAW.replace("\n", "").split(";"):
        parts = chunk.strip().split("|")
        if len(parts) == 4:
            out[_ALIAS.get(parts[0], parts[0])] = (_ALIAS.get(parts[1], parts[1]), float(parts[2]), float(parts[3]))
    return out


CITIES = _parse()
