from __future__ import annotations

from dataclasses import dataclass

from sugar_core.observations import EvidenceReference, ObservationLocation, ResearchObservation
from sugar_core.state_schema import USPresenceSite


@dataclass(frozen=True)
class LocationReference:
    label: str
    latitude: float
    longitude: float
    source_url: str
    note: str


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
    "bsu_main": LocationReference(
        label="Bishkek State University named after Academician Kusein Karasaev, 27 Chyngyz Aitmatov Avenue, Bishkek",
        latitude=42.85035,
        longitude=74.58509,
        source_url="https://mapcarta.com/W321082545",
        note="OpenStreetMap-derived coordinate for K. Karasaev Bishkek State University; the university's official site lists 27 Chyngyz Aitmatov Avenue as its address.",
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

# Service delivery/coverage is source semantics, not a property that can be inferred from whether
# coordinates happen to be present. This explicit declaration reflects the current EducationUSA
# directory used by the case. Missing coordinates on any other physical/hybrid record remain a
# spatial data gap and must never silently expand that record into a country-wide virtual service.
US_SERVICE_TOPOLOGY = {
    "EducationUSA Kyrgyzstan (fully online from April 1, 2026)": {
        "delivery_mode": "virtual",
        "coverage_scope": "country",
        "location_basis": "official_service_directory_nonspatial",
    },
}

CHINESE_LANGUAGE_DAY_TITLE = "International Chinese Language Day events at Bishkek universities"
CHINESE_LANGUAGE_DAY_SOURCE = "https://kg.china-embassy.gov.cn/chn/dssghd/202604/t20260424_11899331.htm"
BSU_OFFICIAL_SOURCE = "https://bhu.kg/en/universitet/"
IUK_OFFICIAL_SOURCE = "https://iuc.edu.kg/"
BISHKEK_CITY_CENTROID = (42.8746, 74.5698)


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


def _append_evidence_once(observation: ResearchObservation, evidence: EvidenceReference) -> None:
    if not any(item.url == evidence.url for item in observation.evidence):
        observation.evidence.append(evidence)


def _apply_chinese_language_day_locations(observation: ResearchObservation) -> None:
    bsu = LOCATION_REFERENCES["bsu_main"]
    observation.locations = [
        ObservationLocation(
            label=bsu.label,
            country="Kyrgyzstan",
            city="Bishkek",
            latitude=bsu.latitude,
            longitude=bsu.longitude,
            precision="site",
            confidence=0.90,
            uncertainty_km=0.75,
            basis="source_named_institution_official_address_public_coordinate_reference",
            source_ref=BSU_OFFICIAL_SOURCE,
            note="The Embassy source names Bishkek State University as a venue. Official BSU material supplies the address; the public OSM-derived reference supplies the coordinate.",
        ),
        ObservationLocation(
            label="International University of Kyrgyzstan — reported Bishkek venue; specific campus unresolved",
            country="Kyrgyzstan",
            city="Bishkek",
            latitude=BISHKEK_CITY_CENTROID[0],
            longitude=BISHKEK_CITY_CENTROID[1],
            precision="city",
            confidence=0.75,
            uncertainty_km=12.0,
            basis="source_named_institution_campus_unresolved_city_centroid",
            source_ref=CHINESE_LANGUAGE_DAY_SOURCE,
            note="The Embassy source names International University of Kyrgyzstan, but current university material exposes multiple campus/service locations. The case therefore retains only city-level placement instead of selecting a campus without event-specific evidence.",
        ),
    ]
    # The legacy scalar fields remain a backwards-compatible summary geography, not a venue claim.
    observation.location_label = "Bishkek, Kyrgyzstan — multi-site activity"
    observation.latitude = BISHKEK_CITY_CENTROID[0]
    observation.longitude = BISHKEK_CITY_CENTROID[1]
    observation.location_basis = "multi_site_summary_city"
    observation.location_confidence = 0.75
    _append_location_reference(observation, bsu)
    _append_evidence_once(
        observation,
        EvidenceReference(
            url=BSU_OFFICIAL_SOURCE,
            title="Bishkek State University official address",
            source_type="official_host_location_reference",
            collected_at="2026-09-15T00:00:00Z",
            note="Official BSU site lists 27 Chyngyz Aitmatov Avenue, Bishkek.",
        ),
    )
    _append_evidence_once(
        observation,
        EvidenceReference(
            url=IUK_OFFICIAL_SOURCE,
            title="International University of Kyrgyzstan current site",
            source_type="official_host_location_reference",
            collected_at="2026-09-15T00:00:00Z",
            note="Current university material is retained to document campus ambiguity; it is not used to assert a specific event campus.",
        ),
    )
    observation.touch()


def apply_observation_location_enrichment(
    observations: list[ResearchObservation],
) -> dict[str, int]:
    refined = 0
    unchanged_city = 0
    multi_site_observations = 0
    structured_activity_locations = 0
    for observation in observations:
        if observation.title == CHINESE_LANGUAGE_DAY_TITLE:
            _apply_chinese_language_day_locations(observation)
            multi_site_observations += 1
            structured_activity_locations += len(observation.locations)
            continue
        key = OBSERVATION_LOCATION_KEYS.get(observation.title)
        if key is None:
            unchanged_city += 1
            continue
        reference = LOCATION_REFERENCES[key]
        observation.location_label = reference.label
        observation.latitude = reference.latitude
        observation.longitude = reference.longitude
        observation.location_basis = "source_named_site_public_location_reference"
        observation.location_confidence = 0.90
        _append_location_reference(observation, reference)
        observation.touch()
        refined += 1
    return {
        "site_refined_observations": refined,
        "city_level_observations": unchanged_city,
        "multi_site_observations": multi_site_observations,
        "structured_activity_locations": structured_activity_locations,
    }


def apply_us_site_location_enrichment(sites: list[USPresenceSite]) -> dict[str, int]:
    keys_by_name = {
        "America Borboru Bishkek": "america_borboru_bishkek",
        "American Corner Osh": "american_corner_osh",
    }
    refined = 0
    city_centroid = 0
    nonspatial = 0
    unresolved_physical = 0
    for site in sites:
        key = keys_by_name.get(site.name)
        declared_topology = US_SERVICE_TOPOLOGY.get(site.name)
        if declared_topology is not None:
            site.delivery_mode = declared_topology["delivery_mode"]
            site.coverage_scope = declared_topology["coverage_scope"]
            site.latitude = None
            site.longitude = None
            site.location_precision = "unknown"
            site.location_confidence = None
            site.location_uncertainty_km = None
            site.location_basis = declared_topology["location_basis"]
            nonspatial += 1
        elif key is not None:
            reference = LOCATION_REFERENCES[key]
            site.latitude = reference.latitude
            site.longitude = reference.longitude
            site.location_precision = "site"
            site.location_confidence = 0.95
            site.location_uncertainty_km = 0.25
            site.location_basis = "official_address_public_coordinate_reference"
            refined += 1
        elif site.latitude is None or site.longitude is None:
            # Fail closed: missing spatial data does not change delivery or coverage semantics.
            # A physical/hybrid site with unresolved coordinates remains physical/hybrid and
            # non-mappable until better evidence appears; it must not become a virtual service.
            site.location_precision = "unknown"
            site.location_confidence = None
            site.location_uncertainty_km = None
            if site.delivery_mode == "virtual":
                site.location_basis = site.location_basis or "declared_nonspatial_service"
                nonspatial += 1
            else:
                site.location_basis = "unresolved_physical_site_missing_coordinates"
                unresolved_physical += 1
        else:
            site.location_precision = "city"
            site.location_confidence = 0.75
            site.location_uncertainty_km = 12.0
            site.location_basis = "city_centroid_reference_not_building"
            city_centroid += 1
    return {
        "address_refined_physical_us_sites": refined,
        "city_centroid_physical_us_sites": city_centroid,
        "nonspatial_us_services": nonspatial,
        "unresolved_physical_us_sites": unresolved_physical,
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
