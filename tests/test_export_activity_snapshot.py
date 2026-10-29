import json

import pytest

from sugar_core.research_export import _activity_snapshot, export_run, verify_export
from sugar_core.research_plan import ResearchPlanSpec
from sugar_core.research_runs import ResearchProject
from sugar_core.workspace import SugarWorkspace


@pytest.mark.parametrize('tail', [b'{"message":"unfinished', b'{"message":"\xe4\xb8'])
def test_partial_append_does_not_break_export(tmp_path, tail):
    project = ResearchProject(SugarWorkspace.create(tmp_path / 'project', name='Snapshot'))
    run = project.new_run(plan=ResearchPlanSpec(topic='test'), requirement='test')
    path = project.events_path(run.run_id)
    data = json.dumps({'message': 'complete event'}).encode() + b'\n' + tail
    path.write_bytes(data)
    exported = export_run(project, run.run_id)
    assert exported['manifest']['export_warnings']
    assert 'export-notes.txt' in exported['files']
    assert verify_export(exported['archive'])['ok']
    assert path.read_bytes() == data
    events = (path.parent.parent.parent / 'exports' / run.run_id / 'activity-log.jsonl').read_text()
    assert json.loads(events)['message'] == 'complete event'


def test_complete_last_event_without_newline_is_preserved(tmp_path):
    path = tmp_path / 'events.jsonl'
    path.write_text('{"message":"complete"}')
    assert _activity_snapshot(path) == ([{'message': 'complete'}], [])


def test_invalid_complete_entry_is_reported_not_silently_discarded(tmp_path):
    path = tmp_path / 'events.jsonl'
    path.write_bytes(b'{broken}\n')
    with pytest.raises(ValueError, match='invalid entry on line 1'):
        _activity_snapshot(path)
