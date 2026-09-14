from __future__ import annotations

from dataclasses import dataclass

from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_schema import USPresenceSite


@dataclass(frozen=True)
class LocationReference:
    label: str
    latitude: float
    longitude: float
    source_url: str
    note: str


# Public map/directory coordinates are used only when the underlying activity source names the
# venue/institution. They refine the display/analysis location; they do not add evidence that the
# activity itself occurred beyond what the activity source already states.
LOCATION_REFERENCES = {
    "national_history_museum": LocationReference(
        label="National Historical Museum of the Kyrgyz Republic, Chui Avenue 203A, Bishkek",
        latitude=42.877733,
        longitude=74.603827,
        source_url="https://yandex.com/maps/10309/bishkek/house/Y00YcAdjQUcAQFpofXR2dntgZw%3D%3D/",
        note="Chui Avenue 203A; public map coordinate for the named museum building.",
    ),
    "national_library": LocationReference(
        label="Alykul Osmonov National Library of the Kyrgyz Republic, 208 Abdrahmanov Street, Bishkek",
        latitude=42.881321,
        longitude=74.610835,
        source_url="https://kg.near-place.com/national-library-of-kyrgyzstan-208-usup-abdrahmanov-street-bishkek/en",
        note="208 Abdrahmanov Street; public location reference for the named National Library building.",
    ),
    "knu_main": LocationReference(
        label="Kyrgyz National University named after Jusup Balasagyn, 547 Frunze Street, Bishkek",
        latitude=42.882404,
        longitude=74.587145,
        source_url="https://yandex.com/maps/10309/bishkek/house/Y00Ycw9nSEECQFpofXR5c3hjYA%3D%3D/",
        note="547 Frunze Street; public map coordinate for KNU's main building.",
    ),
    "oshsu_main": LocationReference(
        label="Osh State University, 331 Alymbek Datka Street, Osh",
        latitude=40.531673,
        longitude=72.794907,
        source_url="https://yandex.com/maps/10310/osh/house/Y0sYcQ5kQEUAQFpqfXlycHpkZw%3D%3D/",
        note="331 Alymbek Datka Street; OshSU's official site lists the main campus at this address and the map reference supplies the coordinate.",
    ),
    "national_philharmonic": LocationReference(
        label="Toktogul Satylganov Kyrgyz National Philharmonic, 253 Chui Avenue, Bishkek",
        latitude=42.8779773,
        longitude=74.5876247,
        source_url="https://www.wikidata.org/wiki/Q25578268",
        note="Public coordinate for the named Kyrgyz National Philharmonic venue.",
    ),
    "america_borboru_bishkek": LocationReference(
        label="America Borboru Bishkek, 242 Tynystanov Street, Bishkek",
        latitude=42.8776054,
        longitude=74.6105334,
        source_url="https://americanspaces.info/locator/acamericaborborubishkek",
        note="Official American Spaces locator lists 242 Tynystanov Street; coordinate corresponds to that building address.",
    ),
    "american_corner_osh": LocationReference(
        label="American Corner Osh, Osh Oblast Library, 271 Kurmanjan Datka Street, Osh",
        latitude=40.533470,
        longitude=72.792545,
        source_url="https://americanspaces.info/locator/acosh",
        note="Official American Spaces locator lists the Osh Oblast Library at 271 Kurmanjan Datka Street; coordinate corresponds to the library building area.",
    ),
}


OBSERVATION_LOCATION_KEYS = {
    "Chinese painting exhibition at the National Historical Museum": "national_history_museum",
    "Osh State University–Xinjiang Normal University Confucius Institute cooperation extended": "oshsu_main",
    "Chinese-language university teaching materials presented in Bishkek": "national_library",
    "Chinese Bridge school competition Kyrgyzstan qualifier": "knu_main",
    "SCO Civilizations Dialogue at the National Historical Museum": "national_history_museum",
    "Chinese-produced Manas dance drama premieres in Kyrgyzstan": "national_philharmonic",
    "Nanjing Week opens at the Osmonov National Library": "national_library",
}


def _append_location_reference(observation: ResearchObservation, reference: LocationReference) -> None:
    if any(item.url == reference.source_url for item in observation.evidence):
        return
    observation.evidence.append(
        EvidenceReference(
            url=reference.source_url,
            title=reference.label,
            source_type="location_reference",
            collected_at="2026-09-14T00:00:00Z",
            note=reference.note,
        )
    )


def apply_observation_location_enrichment(
    observations: list[ResearchObservation],
) -> dict[str, int]:
    refined = 0
    unchanged_city = 0
    for observation in observations:
        key = OBSERVATION_LOCATION_KEYS.get(observation.title)
        if key is None:
            unchanged_city += 1
            continue
        reference = LOCATION_REFERENCES[key]
        observation.location_label = reference.label
        observation.latitude = reference.latitude
        observation.longitude = reference.longitude
        observation.location_basis = "source_named_site+public_location_reference"
        observation.location_confidence = 0.90
        _append_location_reference(observation, reference)
        observation.touch()
        refined += 1
    return {
        "site_refined_observations": refined,
        "city_level_observations": unchanged_city,
    }


def apply_us_site_location_enrichment(sites: list[USPresenceSite]) -> dict[str, int]:
    keys_by_name = {
        "America Borboru Bishkek": "america_borboru_bishkek",
        "American Corner Osh": "american_corner_osh",
    }
    refined = 0
    city_centroid = 0
    nonspatial = 0
    for site in sites:
        key = keys_by_name.get(site.name)
        if key is not None:
            reference = LOCATION_REFERENCES[key]
            site.latitude = reference.latitude
            site.longitude = reference.longitude
            refined += 1
        elif site.latitude is None or site.longitude is None:
            nonspatial += 1
        else:
            city_centroid += 1
    return {
        "address_refined_physical_us_sites": refined,
        "city_centroid_physical_us_sites": city_centroid,
        "nonspatial_us_services": nonspatial,
    }


def location_reference_manifest() -> list[dict[str, object]]:
    return [
        {
            "key": key,
            "label": value.label,
            "latitude": value.latitude,
            "longitude": value.longitude,
            "source_url": value.source_url,
            "note": value.note,
        }
        for key, value in sorted(LOCATION_REFERENCES.items())
    ]
