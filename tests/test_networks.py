import base64

import pytest

from sugar_core import networks as nets
from sugar_core import seed_sources as seeds
from sugar_core.reference_registry import list_entities, upsert_entity
from sugar_core.research_runs import ResearchProject
from sugar_core.workspace import SugarWorkspace
from test_research_api import api   # noqa: F401
from test_web_sources import FakeResponse, FakeSession


def project(tmp_path):
    return ResearchProject(SugarWorkspace.create(tmp_path / "ws", name="Networks"))


def add(p, name, network, lat, lon, city="", country="Exampleland", status="active", audiences=None, programs=None):
    values = {"name": name, "network": network, "latitude": lat, "longitude": lon, "city": city, "country": country, "status": status,
              "audiences": audiences, "program_domains": programs}
    return upsert_entity(p.workspace, {k: v for k, v in values.items() if v is not None}, evidence_refs=[{"source_url": f"https://src.example/{name.replace(' ', '-')}"}])


CSV = b"name,city,country,lat,lon,status,audience\nNorth Space,Harbor City,Exampleland,10.0,20.0,active,university students\nSouth Space,Port Town,Exampleland,11.0,21.0,closed,general public\n"


def test_upload_preview_then_confirmed_import_sets_the_network_and_role(tmp_path):
    p = project(tmp_path)
    preview = nets.preview_upload(p, "directory.csv", CSV)
    assert preview["row_count"] == 2 and preview["file_id"] and preview["suggested_mapping"]["name"] == "name"
    result = nets.import_upload(p, preview["file_id"], mapping=preview["suggested_mapping"], network="ref-net", role="reference", dataset_name="Directory", license_notes="Public")
    assert result["imported"] if "imported" in result else True
    listed = {n["name"]: n for n in nets.list_networks(p)}
    assert listed["ref-net"]["role"] == "reference" and listed["ref-net"]["institutions"] == 2 and listed["ref-net"]["placed"] == 2
    assert {e["name"] for e in list_entities(p.workspace)} == {"North Space", "South Space"}
    with pytest.raises(ValueError, match="CSV"):
        nets.preview_upload(p, "x.exe", b"MZ")
    with pytest.raises(ValueError, match="Unknown uploaded file"):
        nets.import_upload(p, "../../etc/passwd", mapping={"name": "name"}, network="n", role="reference")
    with pytest.raises(ValueError, match="Name the network"):
        nets.import_upload(p, preview["file_id"], mapping=preview["suggested_mapping"], network=" ", role="reference")


def test_overlap_measures_distance_shared_labels_and_skips_unplaced_or_closed(tmp_path):
    p = project(tmp_path)
    nets.set_network(p, "subject-net", role="subject")
    nets.set_network(p, "ref-net", role="reference")
    add(p, "Subject Near", "subject-net", 10.0, 20.0, "Harbor City", audiences=["university students"], programs=["language learning"])
    add(p, "Subject Far", "subject-net", 40.0, 70.0, "Faraway", country="Otherland")
    add(p, "Subject Unplaced", "subject-net", None, None)
    add(p, "Subject Closed", "subject-net", 10.0, 20.0, status="closed")
    add(p, "Reference A", "ref-net", 10.05, 20.02, "Harbor City", audiences=["university students"], programs=["cultural programming"])
    add(p, "Reference Closed", "ref-net", 10.0, 20.0, status="closed")
    result = nets.overlap(p, subjects=["subject-net"], references=["ref-net"])
    rows = {r["name"]: r for r in result["rows"]}
    assert set(rows) == {"Subject Near", "Subject Far"} and result["counts"]["subjects_not_placed"] == 1 and result["counts"]["reference_institutions"] == 1
    near = rows["Subject Near"]
    assert near["nearest_reference"]["name"] == "Reference A" and near["nearest_reference"]["distance_km"] < 10 and near["nearest_reference"]["same_city"]
    assert near["shared_audiences"] == ["university_students"] and near["shared_programs"] == [] and near["references_within_km"]["25"] == 1
    assert rows["Subject Far"]["nearest_reference"]["distance_km"] > 1000 and rows["Subject Far"]["references_within_km"]["250"] == 0
    summary = {c["country"]: c for c in result["by_country"]}
    assert summary["Exampleland"]["subjects_near_reference"] == 1 and summary["Otherland"]["subjects_near_reference"] == 0
    assert "not findings of influence" in result["method"]
    with_closed = nets.overlap(p, subjects=["subject-net"], references=["ref-net"], include_closed=True)
    assert with_closed["counts"]["reference_institutions"] == 2 and len(with_closed["rows"]) == 3


def test_wikidata_search_returns_dated_placed_candidates_with_sources():
    search = {"search": [{"id": "Q100"}, {"id": "Q200"}]}
    entities = {"entities": {
        "Q100": {"labels": {"en": {"value": "Harbor Reading Room"}}, "descriptions": {"en": {"value": "public library"}}, "aliases": {"en": [{"value": "HRR"}]},
                 "claims": {"P17": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "Q5"}}}}],
                            "P625": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"latitude": 12.5, "longitude": 45.5}}}}],
                            "P571": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"time": "+2015-00-00T00:00:00Z"}}}}],
                            "P576": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"time": "+2023-06-30T00:00:00Z"}}}}],
                            "P856": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": "https://hrr.example.org"}}}]}},
        "Q200": {"labels": {}, "claims": {}}}}
    countries = {"entities": {"Q5": {"labels": {"en": {"value": "Exampleland"}}}}}
    session = FakeSession({"https://www.wikidata.org/w/api.php": FakeResponse(payload=search)})
    responses = iter([FakeResponse(payload=search), FakeResponse(payload=entities), FakeResponse(payload=countries)])
    session.get = lambda url, params=None, timeout=None, **kw: next(responses)
    rows = seeds.search_wikidata("reading room", session=session)
    assert len(rows) == 1                                         # the nameless entity is dropped
    row = rows[0]
    assert row["country"] == "Exampleland" and row["latitude"] == 12.5 and row["opened_date"] == "2015-01-01" and row["closed_date"] == "2023-06-30"
    assert row["status"] == "closed" and row["source_url"] == "https://www.wikidata.org/wiki/Q100" and row["website"] == "https://hrr.example.org"
    with pytest.raises(ValueError, match="three characters"):
        seeds.search_wikidata("ab")


def test_osm_search_validates_input_and_reads_centers_and_nodes():
    payload = {"elements": [{"type": "node", "id": 1, "lat": 1.5, "lon": 2.5, "tags": {"name": "Harbor Library", "amenity": "library", "website": "https://h.example", "addr:city": "Harbor"}},
                            {"type": "way", "id": 2, "center": {"lat": 3.0, "lon": 4.0}, "tags": {"name": "Harbor Hall", "name:fr": "Salle du Port"}},
                            {"type": "node", "id": 3, "lat": 5, "lon": 6, "tags": {"amenity": "bench"}}]}
    seen = {}

    class Session:
        def post(self, url, data=None, timeout=None):
            seen["query"] = data["data"]
            return FakeResponse(payload=payload)
    rows = seeds.search_osm("Harbor", country_code="ke", session=Session())
    assert [r["name"] for r in rows] == ["Harbor Library", "Harbor Hall"] and rows[1]["latitude"] == 3.0 and rows[0]["source_url"] == "https://www.openstreetmap.org/node/1"
    assert 'ISO3166-1"="KE"' in seen["query"]
    for bad in ('x"];out;', "a", "x" * 70):
        with pytest.raises(ValueError):
            seeds.search_osm(bad, session=Session())
    with pytest.raises(ValueError, match="two-letter"):
        seeds.search_osm("Harbor", country_code="KEN", session=Session())


def test_importing_seeds_records_unreviewed_institutions_that_cite_their_source(tmp_path):
    p = project(tmp_path)
    rows = [{"seed_source": "wikidata", "seed_id": "Q100", "name": "Harbor Reading Room", "country": "Exampleland", "latitude": 12.5, "longitude": 45.5, "status": "closed",
             "closed_date": "2023-06-30", "website": "https://hrr.example.org", "source_url": "https://www.wikidata.org/wiki/Q100"},
            {"name": "No source", "source_url": ""}]
    result = seeds.import_seeds(p, rows, network="seed-net", role="subject")
    assert len(result["imported"]) == 1 and result["skipped"] == 1
    entity = list_entities(p.workspace)[0]
    assert entity["status"] == "closed" and entity["latitude"] == 12.5 and entity["claims"][0]["review_state"] == "unreviewed"
    assert entity["claims"][0]["evidence_refs"][0]["source_url"] == "https://www.wikidata.org/wiki/Q100"
    assert {n["name"]: n["role"] for n in nets.list_networks(p)}["seed-net"] == "subject"


def test_network_http_flow(api):   # noqa: F811
    base, session, _ = api
    wid = session.post(f"{base}/api/workspaces", json={"name": "Net"}).json()["id"]
    root = f"{base}/api/workspaces/{wid}/research"
    preview = session.post(f"{root}/networks/preview", json={"filename": "dir.csv", "content_base64": base64.b64encode(CSV).decode()}).json()
    assert preview["row_count"] == 2 and session.post(f"{root}/networks/preview", json={"filename": "dir.csv", "content_base64": "!!!"}).status_code == 400
    done = session.post(f"{root}/networks/import", json={"file_id": preview["file_id"], "mapping": preview["suggested_mapping"], "network": "ref-net", "role": "reference"})
    assert done.status_code == 200
    listed = {n["name"]: n for n in session.get(f"{root}/networks").json()["networks"]}
    assert listed["ref-net"]["role"] == "reference" and listed["ref-net"]["institutions"] == 2
    overlap = session.get(f"{root}/overlap", params={"subject": "ref-net", "reference": "ref-net"}).json()
    assert overlap["counts"]["subject_institutions"] == 1 and "not findings of influence" in overlap["method"]       # the closed site is excluded
    assert session.post(f"{root}/networks/seed", json={"source": "nope"}).status_code == 400
    assert session.post(f"{root}/networks", json={"name": "x", "role": "enemy"}).status_code == 400
