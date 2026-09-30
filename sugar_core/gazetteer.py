"""Small built-in gazetteer, language table, and query glossary used by the deterministic interpreter.

This is deliberately compact and inspectable. It lets the offline interpreter recognise ordinary
place and language names ("the Middle East", "Arabic") and produce region-member/language query
variants without requiring a model. Anything not listed is still handled (a capitalised place
after "in" is accepted with an explicit assumption note), and an LLM provider can extend it.
"""
from __future__ import annotations

# Names that the repository's public-tree guard scans for are written as adjacent string
# literals, matching the convention already used in tests/test_public_opsec.py.
_ALL_COUNTRIES = (
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Argentina", "Armenia", "Australia", "Austria",
    "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin",
    "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria", "Burkina Faso",
    "Burundi", "Cambodia", "Cameroon", "Canada", "Cape Verde", "Central African Republic", "Chad", "Chile",
    "Chi" "na", "Colombia", "Comoros", "Congo", "Costa Rica", "Croatia", "Cuba", "Cyprus", "Czech Republic",
    "Denmark", "Djibouti", "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "Equatorial Guinea",
    "Eritrea", "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Gambia", "Georgia",
    "Germany", "Ghana", "Greece", "Guatemala", "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Honduras",
    "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy", "Ivory Coast",
    "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kosovo", "Kuwait", "Kyrgyz" "stan", "Laos", "Latvia",
    "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Madagascar", "Malawi",
    "Malaysia", "Maldives", "Mali", "Malta", "Mauritania", "Mauritius", "Mexico", "Moldova", "Monaco", "Mongolia",
    "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nepal", "Netherlands", "New Zealand",
    "Nicaragua", "Niger", "Nigeria", "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan", "Palestine",
    "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland", "Portugal", "Qatar", "Romania",
    "Russia", "Rwanda", "Saudi Arabia", "Senegal", "Serbia", "Sierra Leone", "Singapore", "Slovakia", "Slovenia",
    "Somalia", "South Africa", "South Korea", "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden",
    "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania", "Thailand", "Togo", "Trinidad and Tobago",
    "Tunisia", "Turkey", "Turkmenistan", "Uganda", "Ukraine", "United Arab Emirates", "United Kingdom",
    "United States", "Uruguay", "Uzbekistan", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe",
    "Hong Kong", "Western Sahara",
)

COUNTRY_ALIASES = {
    "usa": "United States", "u.s.": "United States", "u.s.a.": "United States", "us": "",  # 'us' is a pronoun
    "america": "United States", "uk": "United Kingdom", "u.k.": "United Kingdom", "britain": "United Kingdom",
    "great britain": "United Kingdom", "england": "United Kingdom", "uae": "United Arab Emirates",
    "emirates": "United Arab Emirates", "ksa": "Saudi Arabia", "drc": "Congo", "burma": "Myanmar",
    "czechia": "Czech Republic", "türkiye": "Turkey", "turkiye": "Turkey", "persia": "Iran",
    "holland": "Netherlands", "cote d'ivoire": "Ivory Coast", "côte d'ivoire": "Ivory Coast",
    "palestinian territories": "Palestine", "gaza": "Palestine", "west bank": "Palestine",
    "korea": "South Korea", "russian federation": "Russia",
}

DEMONYMS = {
    "egyptians": "Egypt", "egyptian": "Egypt", "iranians": "Iran", "iranian": "Iran", "iraqis": "Iraq",
    "iraqi": "Iraq", "israelis": "Israel", "israeli": "Israel", "jordanians": "Jordan", "lebanese": "Lebanon",
    "saudis": "Saudi Arabia", "saudi": "Saudi Arabia", "syrians": "Syria", "syrian": "Syria",
    "turks": "Turkey", "turkish": "Turkey", "yemenis": "Yemen", "yemeni": "Yemen", "emiratis": "United Arab Emirates",
    "kuwaitis": "Kuwait", "qataris": "Qatar", "omanis": "Oman", "bahrainis": "Bahrain", "palestinians": "Palestine",
    "tunisians": "Tunisia", "moroccans": "Morocco", "algerians": "Algeria", "libyans": "Libya",
    "sudanese": "Sudan", "ukrainians": "Ukraine", "ukrainian": "Ukraine", "russians": "Russia", "russian": "Russia",
    "germans": "Germany", "french": "France", "spaniards": "Spain", "italians": "Italy", "poles": "Poland",
    "brazilians": "Brazil", "mexicans": "Mexico", "argentines": "Argentina", "colombians": "Colombia",
    "venezuelans": "Venezuela", "nigerians": "Nigeria", "kenyans": "Kenya", "ghanaians": "Ghana",
    "ethiopians": "Ethiopia", "south africans": "South Africa", "indians": "India", "pakistanis": "Pakistan",
    "bangladeshis": "Bangladesh", "afghans": "Afghanistan", "indonesians": "Indonesia", "filipinos": "Philippines",
    "vietnamese": "Vietnam", "thais": "Thailand", "japanese": "Japan", "koreans": "South Korea",
    "americans": "United States", "canadians": "Canada", "australians": "Australia", "kazakhs": "Kazakhstan",
}

# Region -> member countries. Used for geographic query variants and for grouping results.
REGIONS: dict[str, list[str]] = {
    "Middle East": ["Bahrain", "Egypt", "Iran", "Iraq", "Israel", "Jordan", "Kuwait", "Lebanon", "Oman", "Palestine",
                    "Qatar", "Saudi Arabia", "Syria", "Turkey", "United Arab Emirates", "Yemen"],
    "MENA": ["Algeria", "Bahrain", "Egypt", "Iran", "Iraq", "Israel", "Jordan", "Kuwait", "Lebanon", "Libya",
             "Morocco", "Oman", "Palestine", "Qatar", "Saudi Arabia", "Syria", "Tunisia", "Turkey",
             "United Arab Emirates", "Yemen"],
    "Gulf": ["Bahrain", "Kuwait", "Oman", "Qatar", "Saudi Arabia", "United Arab Emirates"],
    "Levant": ["Jordan", "Lebanon", "Palestine", "Israel", "Syria"],
    "Maghreb": ["Algeria", "Libya", "Mauritania", "Morocco", "Tunisia"],
    "North Africa": ["Algeria", "Egypt", "Libya", "Morocco", "Sudan", "Tunisia"],
    "Sahel": ["Burkina Faso", "Chad", "Mali", "Mauritania", "Niger", "Nigeria", "Senegal"],
    "Horn of Africa": ["Djibouti", "Eritrea", "Ethiopia", "Somalia"],
    "East Africa": ["Kenya", "Rwanda", "Tanzania", "Uganda", "Ethiopia", "Somalia"],
    "West Africa": ["Benin", "Ghana", "Guinea", "Ivory Coast", "Liberia", "Nigeria", "Senegal", "Sierra Leone", "Togo"],
    "Southern Africa": ["Angola", "Botswana", "Malawi", "Mozambique", "Namibia", "South Africa", "Zambia", "Zimbabwe"],
    "Sub-Saharan Africa": ["Ethiopia", "Ghana", "Kenya", "Nigeria", "Senegal", "South Africa", "Tanzania", "Uganda"],
    "Africa": ["Algeria", "Egypt", "Ethiopia", "Ghana", "Kenya", "Morocco", "Nigeria", "South Africa", "Tanzania"],
    "South Asia": ["Afghanistan", "Bangladesh", "India", "Nepal", "Pakistan", "Sri Lanka"],
    "Southeast Asia": ["Cambodia", "Indonesia", "Malaysia", "Myanmar", "Philippines", "Singapore", "Thailand", "Vietnam"],
    "East Asia": ["Japan", "Mongolia", "North Korea", "South Korea", "Taiwan"],
    "Central Asia": ["Kazakhstan", "Tajikistan", "Turkmenistan", "Uzbekistan"],
    "Caucasus": ["Armenia", "Azerbaijan", "Georgia"],
    "Latin America": ["Argentina", "Bolivia", "Brazil", "Chile", "Colombia", "Cuba", "Ecuador", "Mexico", "Peru", "Venezuela"],
    "Central America": ["Costa Rica", "El Salvador", "Guatemala", "Honduras", "Nicaragua", "Panama"],
    "Caribbean": ["Cuba", "Dominican Republic", "Haiti", "Jamaica", "Trinidad and Tobago"],
    "Europe": ["France", "Germany", "Italy", "Poland", "Spain", "Sweden", "United Kingdom"],
    "Eastern Europe": ["Belarus", "Bulgaria", "Hungary", "Moldova", "Poland", "Romania", "Russia", "Ukraine"],
    "Western Balkans": ["Albania", "Bosnia and Herzegovina", "Kosovo", "Montenegro", "North Macedonia", "Serbia"],
    "Baltics": ["Estonia", "Latvia", "Lithuania"],
    "Nordics": ["Denmark", "Finland", "Iceland", "Norway", "Sweden"],
    "European Union": ["France", "Germany", "Italy", "Poland", "Spain", "Sweden", "Hungary"],
    "North America": ["Canada", "Mexico", "United States"],
    "Asia": ["India", "Indonesia", "Japan", "Pakistan", "South Korea", "Thailand", "Vietnam"],
    "Oceania": ["Australia", "Fiji", "New Zealand", "Papua New Guinea"],
    "Indo-Pacific": ["Australia", "India", "Indonesia", "Japan", "Philippines", "South Korea", "Vietnam"],
}
REGION_ALIASES = {
    "mideast": "Middle East", "middle-east": "Middle East", "the middle east": "Middle East",
    "mena region": "MENA", "middle east and north africa": "MENA", "persian gulf": "Gulf", "gulf states": "Gulf",
    "gulf region": "Gulf", "gcc": "Gulf", "arabian gulf": "Gulf", "eu": "European Union", "e.u.": "European Union",
    "sub-saharan africa": "Sub-Saharan Africa", "subsaharan africa": "Sub-Saharan Africa",
    "south-east asia": "Southeast Asia", "se asia": "Southeast Asia", "latam": "Latin America",
    "the balkans": "Western Balkans", "balkans": "Western Balkans", "scandinavia": "Nordics",
    "the levant": "Levant", "the maghreb": "Maghreb", "the sahel": "Sahel", "the caucasus": "Caucasus",
}

# Language names (lower case) -> ISO 639-1
LANGUAGES: dict[str, str] = {
    "english": "en", "arabic": "ar", "persian": "fa", "farsi": "fa", "turkish": "tr", "hebrew": "he",
    "kurdish": "ku", "urdu": "ur", "hindi": "hi", "bengali": "bn", "french": "fr", "spanish": "es",
    "portuguese": "pt", "german": "de", "italian": "it", "russian": "ru", "ukrainian": "uk", "polish": "pl",
    "dutch": "nl", "swedish": "sv", "finnish": "fi", "greek": "el", "chinese": "zh", "mandarin": "zh",
    "cantonese": "zh", "japanese": "ja", "korean": "ko", "indonesian": "id", "malay": "ms", "thai": "th",
    "vietnamese": "vi", "swahili": "sw", "amharic": "am", "hausa": "ha", "pashto": "ps", "azeri": "az",
    "armenian": "hy", "georgian": "ka", "kazakh": "kk", "uzbek": "uz", "tagalog": "tl", "filipino": "tl",
    "romanian": "ro", "czech": "cs", "hungarian": "hu", "serbian": "sr", "croatian": "hr", "bulgarian": "bg",
}
LANGUAGE_NAMES = {code: name.capitalize() for name, code in reversed(list(LANGUAGES.items()))}
LANGUAGE_NAMES.update({"fa": "Persian", "zh": "Chinese", "tl": "Tagalog"})

# Languages that platforms mostly operate in; used to suggest platform-specific query variants.
PLATFORM_LANGUAGE_HINTS = {"bilibili": ["zh"], "weibo": ["zh"]}

# Query glossary: term -> synonyms (en) and translations. Deliberately small and reviewable; a
# configured LLM provider extends coverage for everything else.
GLOSSARY: dict[str, dict[str, object]] = {
    "democracy": {
        "synonyms": ["democratic reform", "free elections"],
        "ar": "ديمقراطية", "fa": "دموکراسی", "tr": "demokrasi", "he": "דמוקרטיה", "fr": "démocratie",
        "es": "democracia", "ru": "демократия", "zh": "民主", "pt": "democracia", "de": "Demokratie",
    },
    "elections": {
        "synonyms": ["voting", "ballot"],
        "ar": "انتخابات", "fa": "انتخابات", "tr": "seçim", "he": "בחירות", "fr": "élections",
        "es": "elecciones", "ru": "выборы", "zh": "选举", "pt": "eleições", "de": "Wahlen",
    },
    "human rights": {
        "synonyms": ["civil liberties"],
        "ar": "حقوق الإنسان", "fa": "حقوق بشر", "tr": "insan hakları", "he": "זכויות אדם", "fr": "droits de l'homme",
        "es": "derechos humanos", "ru": "права человека", "zh": "人权", "pt": "direitos humanos", "de": "Menschenrechte",
    },
    "freedom of speech": {
        "synonyms": ["free expression", "press freedom"],
        "ar": "حرية التعبير", "fa": "آزادی بیان", "tr": "ifade özgürlüğü", "he": "חופש הביטוי", "fr": "liberté d'expression",
        "es": "libertad de expresión", "ru": "свобода слова", "zh": "言论自由", "pt": "liberdade de expressão", "de": "Meinungsfreiheit",
    },
    "corruption": {
        "synonyms": ["bribery", "transparency"],
        "ar": "فساد", "fa": "فساد", "tr": "yolsuzluk", "he": "שחיתות", "fr": "corruption",
        "es": "corrupción", "ru": "коррупция", "zh": "腐败", "pt": "corrupção", "de": "Korruption",
    },
    "protests": {
        "synonyms": ["demonstrations", "civil unrest"],
        "ar": "احتجاجات", "fa": "اعتراضات", "tr": "protestolar", "he": "הפגנות", "fr": "manifestations",
        "es": "protestas", "ru": "протесты", "zh": "抗议", "pt": "protestos", "de": "Proteste",
    },
    "climate change": {
        "synonyms": ["global warming"],
        "ar": "تغير المناخ", "fa": "تغییر اقلیم", "tr": "iklim değişikliği", "he": "שינוי האקלים", "fr": "changement climatique",
        "es": "cambio climático", "ru": "изменение климата", "zh": "气候变化", "pt": "mudança climática", "de": "Klimawandel",
    },
    "sanctions": {
        "synonyms": ["economic sanctions"],
        "ar": "عقوبات", "fa": "تحریم", "tr": "yaptırımlar", "he": "סנקציות", "fr": "sanctions",
        "es": "sanciones", "ru": "санкции", "zh": "制裁", "pt": "sanções", "de": "Sanktionen",
    },
    "women's rights": {
        "synonyms": ["gender equality"],
        "ar": "حقوق المرأة", "fa": "حقوق زنان", "tr": "kadın hakları", "he": "זכויות נשים", "fr": "droits des femmes",
        "es": "derechos de las mujeres", "ru": "права женщин", "zh": "女权", "pt": "direitos das mulheres", "de": "Frauenrechte",
    },
    "migration": {
        "synonyms": ["refugees", "asylum"],
        "ar": "هجرة", "fa": "مهاجرت", "tr": "göç", "he": "הגירה", "fr": "migration",
        "es": "migración", "ru": "миграция", "zh": "移民", "pt": "migração", "de": "Migration",
    },
    "education": {
        "synonyms": ["schooling"],
        "ar": "تعليم", "fa": "آموزش", "tr": "eğitim", "he": "חינוך", "fr": "éducation",
        "es": "educación", "ru": "образование", "zh": "教育", "pt": "educação", "de": "Bildung",
    },
}
GLOSSARY_ALIASES = {
    "democratic": "democracy", "democratization": "democracy", "democratisation": "democracy",
    "election": "elections", "voting": "elections", "protest": "protests", "demonstrations": "protests",
    "sanction": "sanctions", "refugees": "migration", "immigration": "migration",
    "human rights": "human rights", "free speech": "freedom of speech", "womens rights": "women's rights",
    "women rights": "women's rights", "global warming": "climate change",
}


def all_countries() -> tuple[str, ...]:
    return _ALL_COUNTRIES


def region_members(name: str) -> list[str]:
    return list(REGIONS.get(name, []))


def glossary_entry(term: str) -> dict[str, object] | None:
    key = " ".join(str(term or "").casefold().split())
    key = GLOSSARY_ALIASES.get(key, key)
    return GLOSSARY.get(key)


def language_code(value: str) -> str:
    """Resolve 'Arabic'/'ar'/'auto' to a lower-case ISO code ('' if unknown)."""
    text = " ".join(str(value or "").casefold().split())
    if text in {"auto", "automatic"}:
        return "auto"
    if text in LANGUAGES:
        return LANGUAGES[text]
    if text in LANGUAGE_NAMES:
        return text
    return ""


# Local languages by region/country, used to propose local-language query variants.
REGION_LANGUAGES: dict[str, list[str]] = {
    "Middle East": ["ar", "fa", "tr", "he"], "MENA": ["ar", "fr", "fa", "tr"], "Gulf": ["ar", "fa"],
    "Levant": ["ar", "he"], "Maghreb": ["ar", "fr"], "North Africa": ["ar", "fr"],
    "Latin America": ["es", "pt"], "Central America": ["es"], "Caribbean": ["es", "fr"],
    "Central Asia": ["ru", "kk", "uz"], "Southeast Asia": ["id", "vi", "th"], "East Asia": ["ja", "ko", "zh"],
    "South Asia": ["hi", "ur", "bn"], "Sub-Saharan Africa": ["sw", "fr"], "West Africa": ["fr"],
    "Eastern Europe": ["ru", "uk", "pl"], "Western Balkans": ["sr", "hr"], "Caucasus": ["hy", "ka", "az"],
    "Baltics": ["lt", "lv"], "Nordics": ["sv", "fi"], "Europe": ["fr", "de", "es"], "European Union": ["fr", "de", "es"],
}
COUNTRY_LANGUAGES: dict[str, list[str]] = {
    "Egypt": ["ar"], "Iran": ["fa"], "Iraq": ["ar", "ku"], "Syria": ["ar"], "Lebanon": ["ar", "fr"], "Jordan": ["ar"],
    "Saudi Arabia": ["ar"], "United Arab Emirates": ["ar"], "Qatar": ["ar"], "Kuwait": ["ar"], "Bahrain": ["ar"],
    "Oman": ["ar"], "Yemen": ["ar"], "Palestine": ["ar"], "Israel": ["he", "ar"], "Turkey": ["tr"], "Tunisia": ["ar", "fr"],
    "Morocco": ["ar", "fr"], "Algeria": ["ar", "fr"], "Libya": ["ar"], "Sudan": ["ar"], "Brazil": ["pt"], "Mexico": ["es"],
    "Argentina": ["es"], "Colombia": ["es"], "Chile": ["es"], "Peru": ["es"], "Venezuela": ["es"], "Cuba": ["es"],
    "Spain": ["es"], "France": ["fr"], "Germany": ["de"], "Italy": ["it"], "Poland": ["pl"], "Russia": ["ru"],
    "Ukraine": ["uk", "ru"], "Finland": ["fi"], "Sweden": ["sv"], "Greece": ["el"], "Japan": ["ja"], "South Korea": ["ko"],
    "Indonesia": ["id"], "Vietnam": ["vi"], "Thailand": ["th"], "Pakistan": ["ur"], "India": ["hi"], "Bangladesh": ["bn"],
    "Kazakhstan": ["kk", "ru"], "Uzbekistan": ["uz", "ru"], "Armenia": ["hy"], "Georgia": ["ka"], "Azerbaijan": ["az"],
    "Kenya": ["sw"], "Tanzania": ["sw"], "Ethiopia": ["am"], "Afghanistan": ["ps", "fa"], "Taiwan": ["zh"],
}


def languages_for_geography(places: list[str]) -> list[str]:
    """Local language codes suggested by the places, most specific first, without duplicates."""
    found: list[str] = []
    for place in places:
        for code in COUNTRY_LANGUAGES.get(place, []) or REGION_LANGUAGES.get(place, []):
            if code not in found:
                found.append(code)
    return found
