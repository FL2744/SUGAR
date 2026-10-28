import json
from types import SimpleNamespace

import pytest

from sugar_core.post_locations import LocationStore, fingerprint, infer_post_locations, normalise
from sugar_core.post_map import post_pins
from sugar_core.research_items import ResearchItem, tag_geography
from sugar_core.research_runs import ResearchProject
from sugar_core.workspace import SugarWorkspace
from sugar_core.llm_providers import LLMBudget, ProviderError


def item(text='The Knesset held a debate on democratic reforms.', key='it_1'):
    record = ResearchItem(item_id=key, run_id='run_1', project_id='p', platform='x', original_text=text)
    tag_geography(record, [])
    return record


def suggestion(record, **overrides):
    return {'item_id': record.item_id, 'country': 'Israel', 'city': '', 'region': '', 'confidence': .75,
            'evidence': 'Knesset', 'reason': 'The named parliament provides geographic context.', **overrides}


class Provider:
    model = 'case-sensitive-Model'

    def __init__(self, row=None, fail=False):
        self.row, self.calls, self.fail = row, 0, fail

    def chat_json(self, messages, schema, **kwargs):
        self.calls += 1
        if self.fail:
            raise ProviderError('Offline', stage='reachable')
        records = json.loads(messages[1]['content'])
        return {'locations': [self.row or {'item_id': r['item_id'], 'country': 'Israel', 'city': '', 'region': '', 'confidence': .75,
                    'evidence': 'Knesset', 'reason': 'Named parliament.'} for r in records]}, SimpleNamespace()


@pytest.fixture
def project(tmp_path):
    return ResearchProject(SugarWorkspace.create(tmp_path / 'ws', name='Locations'))


def test_model_inference_is_about_not_posting_origin_and_confidence_filters(project):
    record = item()
    result = infer_post_locations(project, [record], provider=Provider())
    assert result['proposed'] == 1
    mapped = post_pins(project, [record])
    assert mapped['pins'][0]['origin'] is None
    assert mapped['pins'][0]['inferred_location']['confidence'] == .75
    assert mapped['pins'][0]['inferred_location']['evidence'] == 'Knesset'
    assert mapped['pins'][0]['targets'][0]['name'] == 'Israel'
    assert post_pins(project, [record], min_confidence=.8)['pins'] == []
    assert post_pins(project, [record], min_confidence=.7)['pins']
    assert post_pins(project, [record], min_confidence=.8)['coverage']['below_confidence'] == 1


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1, 1.1, True])
def test_invalid_confidence_is_rejected(value):
    assert normalise(suggestion(item(), confidence=value), item()) is None


def test_uncited_unknown_and_fabricated_places_are_not_mapped(project):
    record = item()
    assert normalise(suggestion(record, evidence='not in the source'), record) is None
    assert normalise(suggestion(record, country='Atlantis'), record) is None
    assert normalise(suggestion(record, country='Japan', city='Tokyo', evidence=''), record) is None
    assert normalise(None, record) is None
    assert normalise(suggestion(record, confidence='invalid'), record) is None


def test_region_stays_region_not_arbitrary_country(project):
    record = item('Governance in the Middle East is changing.')
    row = suggestion(record, country='', region='Middle East', evidence='Middle East', confidence=.9)
    result = normalise(row, record)
    assert result['precision'] == 'region' and result['name'] == 'Middle East'
    assert result['confidence'] == .6
    LocationStore(project).append([{'item_id': record.item_id, 'fingerprint': fingerprint(record), 'location': result}])
    pin = post_pins(project, [record])['pins'][0]
    assert pin['latitude'] == 29 and pin['longitude'] == 43


def test_cached_results_reused_but_changed_text_reprocessed(project):
    record, provider = item(), Provider()
    infer_post_locations(project, [record], provider=provider)
    infer_post_locations(project, [record], provider=provider)
    assert provider.calls == 1
    record.original_text += ' More on the Knesset.'
    infer_post_locations(project, [record], provider=provider)
    assert provider.calls == 2
    assert LocationStore(project).latest()[record.item_id]['fingerprint'] == fingerprint(record)


def test_budget_no_provider_and_failure_preserve_results(project):
    records = [item(key=f'it_{i}') for i in range(9)]
    provider = Provider()
    assert infer_post_locations(project, records, provider=provider, budget=LLMBudget(1))['remaining'] == 1
    assert provider.calls == 1
    assert infer_post_locations(project, [item(key='new')])['warnings']
    assert infer_post_locations(project, [item(key='new')], provider=Provider(fail=True))['warnings']
    assert len(LocationStore(project).latest()) == 8


def test_demonyms_and_aliases_map_without_a_model(project):
    record = item('Palestinian democratic institutions and Egyptian elections.')
    targets = post_pins(project, [record])['pins'][0]['targets']
    assert {r['name'] for r in targets} == {'Palestine', 'Egypt'}


def test_exact_platform_origin_is_never_removed_by_estimate_filter(project):
    record = item('Nothing locatable here.')
    record.coordinates = {'lat': 0, 'lon': 0}
    assert post_pins(project, [record], min_confidence=1)['pins'][0]['origin']['kind'] == 'platform coordinates'
    with pytest.raises(ValueError):
        post_pins(project, [record], min_confidence=float('nan'))


def test_api_infers_existing_run_and_rejects_bad_confidence(project):
    from sugar_core.research_api import _research_routes
    from sugar_core.research_plan import ResearchPlanSpec
    from sugar_core.workbench import WorkbenchError
    plan = project.save_plan(ResearchPlanSpec(topic='Governance'))
    run = project.new_run(kind='run', plan=plan)
    project.save_items(run.run_id, [item()])
    class Workbench:
        list_runs = staticmethod(lambda p: p.list_runs())
        items = staticmethod(lambda p, rid: p.load_items(rid))
        resolve_provider = staticmethod(lambda plan, project: Provider())
    wb = Workbench()
    code, result = _research_routes('POST', 'map/infer', {}, {}, wb, project)
    assert code == 200 and result['proposed'] == 1
    _, mapped = _research_routes('GET', 'map/posts', {'min_confidence': '.8'}, {}, wb, project)
    assert mapped['pins'] == []
    for method, path in [('GET', 'map/posts'), ('POST', 'map/export')]:
        with pytest.raises(WorkbenchError):
            _research_routes(method, path, {'min_confidence': 'bad'}, {'min_confidence': 'bad'}, wb, project)
