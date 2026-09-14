from __future__ import annotations

from dataclasses import asdict

from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_schema import (
    AnalyticClaim,
    StateAssessment,
    SupportAssessment,
    USPresenceSite,
)

BISHKEK = (42.8746, 74.5698)
OSH = (40.5140, 72.8161)

AMERICAN_SPACES_SOURCE = "https://americanspaces.info/locator/spaces/KG"
EDUCATIONUSA_SOURCE = "https://educationusa.state.gov/node/421"


def _evidence(url: str, *, source_type: str, title: str) -> EvidenceReference:
    return EvidenceReference(
        url=url,
        title=title,
        source_type=source_type,
        collected_at="2026-09-14T00:00:00Z",
    )


def _observation(
    *,
    observation_type: str,
    title: str,
    summary: str,
    observed_at: str,
    city: str,
    coords: tuple[float, float],
    url: str,
    source_type: str,
    institution_name: str = "",
    program_name: str = "",
    actors: list[str] | None = None,
    audiences: list[str] | None = None,
    themes: list[str] | None = None,
    triage_labels: list[str] | None = None,
) -> ResearchObservation:
    evidence = _evidence(url, source_type=source_type, title=title)
    return ResearchObservation(
        observation_type=observation_type,
        title=title,
        summary=summary,
        observed_at=observed_at,
        activity_status="observed",
        location_label=city,
        country="Kyrgyzstan",
        city=city,
        latitude=coords[0],
        longitude=coords[1],
        location_basis="reported_city",
        location_confidence=0.80,
        institution_name=institution_name,
        program_name=program_name,
        actors=actors or [],
        audiences=audiences or [],
        themes=themes or [],
        evidence=[evidence],
        source_record_keys=[url],
        relevance="relevant",
        relevance_confidence=0.95,
        triage_labels=triage_labels or [],
        triage_evidence=[url],
        ai_confidence=0.90,
        ai_model="research_assistant",
        ai_reason="Public-source record is directly relevant to the bounded Kyrgyzstan public-diplomacy case; coding remains subject to human review.",
        verification_state="ai_triaged",
        verification_notes="AI-triaged public-source case record. Not human verified.",
    )


def build_observations() -> list[ResearchObservation]:
    return [
        _observation(
            observation_type="event",
            title="Chinese painting exhibition at the National Historical Museum",
            summary=(
                "A March 10 exhibition in Bishkek presented more than 50 horse-themed Chinese paintings. "
                "The Chinese Embassy reported that the China Cultural Center in Bishkek and the Kyrgyz National Historical Museum co-organized the exhibition."
            ),
            observed_at="2026-03-10",
            city="Bishkek",
            coords=BISHKEK,
            url="https://kg.china-embassy.gov.cn/dssghd/202603/t20260312_11873181.htm",
            source_type="official_prc_source",
            institution_name="Kyrgyz National Historical Museum",
            program_name="Horse-themed Chinese painting exhibition",
            actors=["China Cultural Center in Bishkek", "Kyrgyz National Historical Museum", "PRC Embassy in Kyrgyzstan"],
            audiences=["general public", "cultural community"],
            themes=["Chinese visual arts", "civilizational exchange"],
            triage_labels=["culture_arts", "official_prc_support", "local_partnership"],
        ),
        _observation(
            observation_type="program",
            title="Osh State University–Xinjiang Normal University Confucius Institute cooperation extended",
            summary=(
                "At the April 13 Confucius Institute board meeting, Osh State University and Xinjiang Normal University extended their cooperation agreement, "
                "reviewed the institute's 2026 work plan and funding directions, and included a student cultural program focused on Chinese culture."
            ),
            observed_at="2026-04-13",
            city="Osh",
            coords=OSH,
            url="https://www.oshsu.kg/public/en/news/4245",
            source_type="official_host_source",
            institution_name="Osh State University",
            program_name="Confucius Institute at Osh State University",
            actors=["Osh State University", "Xinjiang Normal University", "Confucius Institute at Osh State University"],
            audiences=["university students", "faculty"],
            themes=["Chinese language education", "higher education cooperation", "Chinese culture"],
            triage_labels=["language_education", "higher_education", "confucius_institute", "local_partnership"],
        ),
        _observation(
            observation_type="event",
            title="Chinese-language university teaching materials presented in Bishkek",
            summary=(
                "The PRC Embassy reported an April 15 presentation of Chinese-language teaching materials for Kyrgyz universities at the National Library, "
                "with representatives of Osh State University, Kyrgyz National University, and other higher-education institutions."
            ),
            observed_at="2026-04-15",
            city="Bishkek",
            coords=BISHKEK,
            url="https://kg.china-embassy.gov.cn/rus/dssghd/202604/t20260417_11893762.htm",
            source_type="official_prc_source",
            institution_name="Alykul Osmonov National Library of Kyrgyzstan",
            program_name="Chinese-language teaching materials presentation",
            actors=["PRC Embassy in Kyrgyzstan", "Osh State University", "Kyrgyz National University"],
            audiences=["university students", "educators"],
            themes=["Chinese language education", "higher education"],
            triage_labels=["language_education", "higher_education", "official_prc_support"],
        ),
        _observation(
            observation_type="event",
            title="International Chinese Language Day events at Bishkek universities",
            summary=(
                "Chinese Language Day programming at the International University of Kyrgyzstan and Bishkek State University included Chinese poetry and calligraphy exhibits and wushu performances. "
                "The PRC Embassy reported participation by Kyrgyz officials, university communities, Confucius Institute teachers and students, and visiting Chinese performers."
            ),
            observed_at="2026-04-24",
            city="Bishkek",
            coords=BISHKEK,
            url="https://kg.china-embassy.gov.cn/chn/dssghd/202604/t20260424_11899331.htm",
            source_type="official_prc_source",
            program_name="International Chinese Language Day",
            actors=["PRC Embassy in Kyrgyzstan", "International University of Kyrgyzstan", "Bishkek State University", "Confucius Institutes"],
            audiences=["students", "youth", "educators"],
            themes=["Chinese language education", "poetry", "calligraphy", "wushu"],
            triage_labels=["language_education", "culture_arts", "official_prc_support"],
        ),
        _observation(
            observation_type="event",
            title="Chinese Bridge school competition Kyrgyzstan qualifier",
            summary=(
                "Kyrgyz National University reported that the May 14 national qualifier for the Chinese Bridge school competition was supported by the PRC Embassy and organized by the KNU Confucius Institute. "
                "Thirteen finalists from different regions competed for a place in the world final in China."
            ),
            observed_at="2026-05-14",
            city="Bishkek",
            coords=BISHKEK,
            url="https://www.knu.kg/ky/en/archives/3184",
            source_type="official_host_source",
            institution_name="Kyrgyz National University named after Jusup Balasagyn",
            program_name="Chinese Bridge",
            actors=["Kyrgyz National University", "Confucius Institute at KNU", "PRC Embassy in Kyrgyzstan"],
            audiences=["school students", "youth"],
            themes=["Chinese language education", "youth exchange", "competition"],
            triage_labels=["language_education", "youth", "confucius_institute", "official_prc_support"],
        ),
        _observation(
            observation_type="event",
            title="Chinese cultural programming at Kyrgyz diplomatic charity bazaar",
            summary=(
                "The PRC Embassy reported a Chinese booth at the June 13 diplomatic charity bazaar in Bishkek featuring Chinese crafts and food, with embassy diplomats and Confucius Institute teachers and students performing pipa, dance, and wushu."
            ),
            observed_at="2026-06-13",
            city="Bishkek",
            coords=BISHKEK,
            url="https://kg.china-embassy.gov.cn/chn/dssghd/202606/t20260614_11944379.htm",
            source_type="official_prc_source",
            program_name="Diplomatic charity bazaar Chinese cultural booth",
            actors=["PRC Embassy in Kyrgyzstan", "Confucius Institute teachers and students"],
            audiences=["general public"],
            themes=["Chinese culture", "food", "crafts", "performing arts"],
            triage_labels=["culture_arts", "public_event", "official_prc_support"],
        ),
        _observation(
            observation_type="partnership",
            title="Kyrgyz and Chinese writers organizations sign cooperation agreement",
            summary=(
                "Kabar reported that the Writers' Union of Kyrgyzstan and the Chinese Writers' Association signed a cooperation agreement in Bishkek after talks on mutual visits, translation, and joint literary projects."
            ),
            observed_at="2026-06-17",
            city="Bishkek",
            coords=BISHKEK,
            url="https://en.kabar.kg/news/writers-from-kyrgyzstan-and-china-signed-cooperation-agreement/",
            source_type="national_news_agency",
            institution_name="Writers' Union of Kyrgyzstan",
            program_name="Kyrgyz–Chinese literary cooperation",
            actors=["Writers' Union of Kyrgyzstan", "Chinese Writers' Association"],
            audiences=["writers", "cultural community"],
            themes=["literature", "translation", "cultural exchange"],
            triage_labels=["culture_arts", "local_partnership", "institutional_network"],
        ),
        _observation(
            observation_type="event",
            title="Presentation of Xi Jinping's The Governance of China in Bishkek",
            summary=(
                "Kabar reported a July 14 presentation of the fifth volume of Xi Jinping's The Governance of China in Bishkek. "
                "Related reporting described roughly 300 participants from political parties, media, think tanks, and other sectors discussing Chinese modernization, global governance, Belt and Road cooperation, and civilizational exchange."
            ),
            observed_at="2026-07-14",
            city="Bishkek",
            coords=BISHKEK,
            url="https://en.kabar.kg/news/presentation-of-xi-jinpings-book-the-governance-of-chinaheld-in-bishkek/",
            source_type="national_news_agency",
            program_name="The Governance of China book presentation",
            actors=["Kyrgyz government representatives", "Chinese and Kyrgyz participants"],
            audiences=["government officials", "media", "think tanks", "academics"],
            themes=["Chinese governance", "modernization", "global governance", "Belt and Road"],
            triage_labels=["narrative", "elite_engagement", "governance_discourse"],
        ),
        _observation(
            observation_type="event",
            title="SCO Civilizations Dialogue at the National Historical Museum",
            summary=(
                "A July 14 civilizations dialogue in Bishkek brought together roughly 200 government, media, cultural, and academic representatives. "
                "The Chinese Embassy reported that the event was co-organized by the PRC State Council Information Office, SCO Secretariat, Kyrgyz Ministry of Culture, China International Communications Group, and the PRC Embassy."
            ),
            observed_at="2026-07-14",
            city="Bishkek",
            coords=BISHKEK,
            url="https://kg.china-embassy.gov.cn/zjsbwl/202607/t20260715_11982757.htm",
            source_type="official_prc_source",
            institution_name="Kyrgyz National Historical Museum",
            program_name="2026 SCO Civilizations Dialogue",
            actors=["PRC State Council Information Office", "SCO Secretariat", "Kyrgyz Ministry of Culture, Information and Youth Policy", "China International Communications Group", "PRC Embassy in Kyrgyzstan"],
            audiences=["government officials", "media", "academics", "cultural community"],
            themes=["civilizational dialogue", "SCO", "global governance"],
            triage_labels=["culture_arts", "elite_engagement", "official_prc_support", "multilateral"],
        ),
        _observation(
            observation_type="event",
            title="Chinese-produced Manas dance drama premieres in Kyrgyzstan",
            summary=(
                "The PRC Embassy reported the August 21 Kyrgyzstan premiere of a Manas dance drama performed by a troupe from the Kizilsu Kyrgyz Autonomous Prefecture in Xinjiang. "
                "The source reported attendance by more than 1,000 officials and members of the public."
            ),
            observed_at="2026-08-21",
            city="Bishkek",
            coords=BISHKEK,
            url="https://kg.china-embassy.gov.cn/dssghd/202608/t20260822_12008606.htm",
            source_type="official_prc_source",
            program_name="Manas dance drama Kyrgyzstan premiere",
            actors=["Kizilsu Kyrgyz Autonomous Prefecture song and dance troupe", "PRC Embassy in Kyrgyzstan"],
            audiences=["general public", "government officials", "cultural community"],
            themes=["Manas", "shared cultural heritage", "performing arts"],
            triage_labels=["culture_arts", "public_event", "official_prc_support"],
        ),
        _observation(
            observation_type="event",
            title="Nanjing Week opens at the Osmonov National Library",
            summary=(
                "Kabar reported the August 26 opening of Nanjing Week at the Osmonov National Library in Bishkek. "
                "The event was organized by the Nanjing City People's Government and included Chinese and Kyrgyz cultural and scientific representatives, including the director of the China Cultural Center in Bishkek."
            ),
            observed_at="2026-08-26",
            city="Bishkek",
            coords=BISHKEK,
            url="https://en.kabar.kg/news/nanjing-week-in-bishkek-opens-platform-for-cultural-and-literary-exchange/",
            source_type="national_news_agency",
            institution_name="Alykul Osmonov National Library of Kyrgyzstan",
            program_name="Nanjing Week in China – 2026",
            actors=["Nanjing City People's Government", "China Cultural Center in Bishkek", "Kyrgyz cultural and scientific organizations"],
            audiences=["general public", "cultural community", "academics"],
            themes=["city diplomacy", "literature", "cultural exchange"],
            triage_labels=["culture_arts", "subnational_diplomacy", "local_partnership"],
        ),
    ]


def _assessment(
    observation: ResearchObservation,
    *,
    audiences: list[str],
    domains: list[str],
    narratives: list[str],
    sponsors: list[str],
    hosts: list[str],
    support_basis: str,
    support_rationale: str,
    delivery_modes: list[str],
    policy_relevance: list[str],
    priority: str = "normal",
) -> StateAssessment:
    source = observation.primary_source_url
    return StateAssessment(
        observation_id=observation.observation_id,
        strategic_audiences=audiences,
        program_domains=domains,
        narrative_tags=narratives,
        sponsor_entities=sponsors,
        host_entities=hosts,
        delivery_modes=delivery_modes,
        policy_relevance=policy_relevance,
        prc_support=SupportAssessment(
            level="probable",
            bases=[support_basis],
            rationale=support_rationale,
            confidence=0.90,
            evidence_refs=[source],
            review_state="ai_triaged",
        ),
        observability_level="activity_observed",
        claims=[
            AnalyticClaim(
                statement=support_rationale,
                claim_type="support_relationship",
                epistemic_status="analytic_assessment",
                confidence=0.90,
                evidence_refs=[source],
                review_state="ai_triaged",
            )
        ],
        review_state="ai_triaged",
        review_note="AI-triaged for the reproducible Kyrgyzstan 2026 case. Human verification required before State-facing briefing use.",
        analytic_priority=priority,
    )


def build_assessments(observations: list[ResearchObservation]) -> list[StateAssessment]:
    by_title = {row.title: row for row in observations}
    specs = [
        (
            "Chinese painting exhibition at the National Historical Museum",
            ["general_public"], ["culture_arts"], ["culture_civilization", "local_partnership"],
            ["China Cultural Center in Bishkek"], ["Kyrgyz National Historical Museum"], "official_prc_source",
            "Official PRC reporting states that the China Cultural Center in Bishkek co-organized the exhibition with the Kyrgyz National Historical Museum.",
            ["exhibition", "in_person"], ["cultural programming", "institutional partnership"], "normal",
        ),
        (
            "Osh State University–Xinjiang Normal University Confucius Institute cooperation extended",
            ["students", "educators", "researchers_academics"], ["higher_education", "other"], ["education_opportunity", "local_partnership"],
            ["Xinjiang Normal University", "Confucius Institute at Osh State University"], ["Osh State University"], "official_host_source",
            "Official Osh State University reporting states that the partner universities renewed cooperation through the Confucius Institute and reviewed its 2026 plan and funding directions.",
            ["institutional_program", "language_instruction", "cultural_program"], ["Chinese-language education", "higher-education partnership"], "high",
        ),
        (
            "Chinese-language university teaching materials presented in Bishkek",
            ["students", "educators"], ["higher_education", "other"], ["education_opportunity"],
            ["PRC Embassy in Kyrgyzstan"], ["Alykul Osmonov National Library of Kyrgyzstan"], "official_prc_source",
            "Official PRC reporting describes embassy participation in a presentation of Chinese-language teaching materials for Kyrgyz universities.",
            ["materials", "in_person", "language_instruction"], ["Chinese-language education", "curriculum support"], "high",
        ),
        (
            "International Chinese Language Day events at Bishkek universities",
            ["students", "youth", "educators"], ["culture_arts", "other"], ["culture_civilization", "education_opportunity"],
            ["PRC Embassy in Kyrgyzstan", "Confucius Institutes"], ["International University of Kyrgyzstan", "Bishkek State University"], "official_prc_source",
            "Official PRC reporting describes embassy participation and Confucius Institute involvement in Chinese-language and cultural programming at two Bishkek universities.",
            ["language_instruction", "exhibition", "performance", "in_person"], ["Chinese-language education", "youth engagement", "cultural programming"], "high",
        ),
        (
            "Chinese Bridge school competition Kyrgyzstan qualifier",
            ["youth", "students"], ["culture_arts", "other"], ["education_opportunity", "culture_civilization"],
            ["PRC Embassy in Kyrgyzstan", "Confucius Institute at KNU"], ["Kyrgyz National University named after Jusup Balasagyn"], "official_host_source",
            "Official KNU reporting states that the PRC Embassy supported and the KNU Confucius Institute organized the national Chinese Bridge qualifier.",
            ["competition", "language_instruction", "in_person"], ["Chinese-language education", "youth engagement"], "high",
        ),
        (
            "Chinese cultural programming at Kyrgyz diplomatic charity bazaar",
            ["general_public"], ["culture_arts"], ["culture_civilization"],
            ["PRC Embassy in Kyrgyzstan"], ["Kyrgyz Ministry of Foreign Affairs charity bazaar"], "official_prc_source",
            "Official PRC reporting states that embassy personnel and Confucius Institute teachers and students delivered Chinese cultural programming at the public charity bazaar.",
            ["public_event", "performance", "food_and_crafts"], ["public cultural programming"], "normal",
        ),
        (
            "Kyrgyz and Chinese writers organizations sign cooperation agreement",
            ["researchers_academics", "general_public"], ["culture_arts"], ["local_partnership", "culture_civilization"],
            ["Chinese Writers' Association"], ["Writers' Union of Kyrgyzstan"], "credible_secondary_reporting",
            "Kyrgyz national news reporting documents a formal cooperation agreement between the Chinese Writers' Association and the Writers' Union of Kyrgyzstan.",
            ["institutional_partnership", "literary_exchange"], ["literary networks", "translation", "institutional partnership"], "normal",
        ),
        (
            "Presentation of Xi Jinping's The Governance of China in Bishkek",
            ["government_officials", "journalists_media", "researchers_academics"], ["civic_engagement", "other"], ["china_model", "multipolarity"],
            ["Chinese organizers reported by Kabar"], ["Kyrgyz participants"], "credible_secondary_reporting",
            "Kyrgyz national news reporting documents a large public presentation and discussion of Xi Jinping's governance volume and associated themes of Chinese modernization and global governance.",
            ["book_presentation", "elite_dialogue"], ["governance narratives", "elite engagement", "media and think-tank engagement"], "high",
        ),
        (
            "SCO Civilizations Dialogue at the National Historical Museum",
            ["government_officials", "journalists_media", "researchers_academics"], ["culture_arts", "civic_engagement"], ["culture_civilization", "multipolarity"],
            ["PRC State Council Information Office", "China International Communications Group", "PRC Embassy in Kyrgyzstan"], ["Kyrgyz Ministry of Culture, Information and Youth Policy", "Kyrgyz National Historical Museum"], "official_prc_source",
            "Official PRC reporting states that multiple PRC state entities co-organized the SCO Civilizations Dialogue with Kyrgyz and SCO partners.",
            ["conference", "exhibition", "elite_dialogue"], ["multilateral cultural diplomacy", "media cooperation", "governance narratives"], "high",
        ),
        (
            "Chinese-produced Manas dance drama premieres in Kyrgyzstan",
            ["general_public", "government_officials"], ["culture_arts"], ["culture_civilization", "local_partnership"],
            ["Kizilsu Kyrgyz Autonomous Prefecture song and dance troupe", "PRC Embassy in Kyrgyzstan"], ["Kyrgyz cultural institutions"], "official_prc_source",
            "Official PRC reporting documents a Xinjiang-based troupe's Kyrgyzstan premiere of a Manas dance drama with embassy participation.",
            ["performance", "public_event"], ["shared-heritage cultural diplomacy", "mass-audience programming"], "high",
        ),
        (
            "Nanjing Week opens at the Osmonov National Library",
            ["general_public", "researchers_academics"], ["culture_arts"], ["culture_civilization", "local_partnership"],
            ["Nanjing City People's Government"], ["Alykul Osmonov National Library of Kyrgyzstan"], "credible_secondary_reporting",
            "Kyrgyz national news reporting states that Nanjing Week was organized by the Nanjing City People's Government and involved the China Cultural Center in Bishkek and Kyrgyz cultural organizations.",
            ["festival", "literary_exchange", "subnational_diplomacy"], ["city diplomacy", "cultural and literary exchange"], "normal",
        ),
    ]
    assessments: list[StateAssessment] = []
    for title, audiences, domains, narratives, sponsors, hosts, basis, rationale, modes, relevance, priority in specs:
        assessments.append(
            _assessment(
                by_title[title],
                audiences=audiences,
                domains=domains,
                narratives=narratives,
                sponsors=sponsors,
                hosts=hosts,
                support_basis=basis,
                support_rationale=rationale,
                delivery_modes=modes,
                policy_relevance=relevance,
                priority=priority,
            )
        )
    return assessments


def build_us_presence_sites() -> list[USPresenceSite]:
    # Coordinates are intentionally city centroids, not claimed building coordinates. The case
    # runner therefore passes a 12 km U.S.-site uncertainty envelope to the proximity model.
    physical = [
        ("America Borboru Bishkek", "Bishkek", 42.8746, 74.5698, ["english_language", "culture", "professional_skills", "makerspace", "stem", "technology", "entrepreneurship"]),
        ("America Corner Jalal-Abad", "Jalal-Abad", 40.9333, 73.0000, ["english_language", "culture", "professional_skills", "media_literacy", "entrepreneurship", "technology"]),
        ("America Ordosu Talas", "Talas", 42.5228, 72.2427, ["english_language", "culture", "professional_skills"]),
        ("American Corner Batken", "Batken", 40.0626, 70.8194, ["english_language", "culture", "professional_skills"]),
        ("American Corner Kant", "Kant", 42.8911, 74.8508, ["english_language", "culture", "professional_skills"]),
        ("American Corner Karakol", "Karakol", 42.4907, 78.3936, ["english_language", "culture", "professional_skills"]),
        ("American Corner Naryn", "Naryn", 41.4287, 75.9911, ["english_language", "culture", "professional_skills"]),
        ("American Corner Osh", "Osh", 40.5140, 72.8161, ["english_language", "culture", "professional_skills"]),
    ]
    sites = [
        USPresenceSite(
            name=name,
            network="american_space",
            subtype="American Corner" if "Borboru" not in name else "American Center",
            country="Kyrgyzstan",
            city=city,
            latitude=lat,
            longitude=lon,
            service_tags=tags,
            source_url=AMERICAN_SPACES_SOURCE,
            status="active",
        )
        for name, city, lat, lon, tags in physical
    ]
    # EducationUSA Kyrgyzstan is a nationally available non-spatial service as of April 1, 2026.
    # It is intentionally represented without coordinates. The current core overlap model does
    # not yet aggregate such virtual services with the nearest physical American Space; the E2E
    # case records that limitation explicitly rather than fabricating a map point.
    sites.append(
        USPresenceSite(
            name="EducationUSA Kyrgyzstan (fully online from April 1, 2026)",
            network="educationusa",
            subtype="Virtual advising service",
            country="Kyrgyzstan",
            city="",
            latitude=None,
            longitude=None,
            service_tags=["educationusa", "study_in_the_us", "higher_education"],
            source_url=EDUCATIONUSA_SOURCE,
            status="active",
        )
    )
    return sites


def sources_manifest(observations: list[ResearchObservation], sites: list[USPresenceSite]) -> dict:
    observation_sources = []
    for observation in observations:
        for evidence in observation.evidence:
            observation_sources.append(
                {
                    "observation_id": observation.observation_id,
                    "title": observation.title,
                    "url": evidence.url,
                    "source_type": evidence.source_type,
                }
            )
    return {
        "research_cutoff": "2026-09-14",
        "observations": observation_sources,
        "us_presence_sources": sorted({site.source_url for site in sites if site.source_url}),
        "us_presence_records": [asdict(site) for site in sites],
    }
