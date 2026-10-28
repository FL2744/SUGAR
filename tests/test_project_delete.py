from types import SimpleNamespace
import uuid
import pytest
import sugar_api as api
from sugar_core.workspace import SugarWorkspace


def test_delete_managed_project_preserves_files_and_hides_project(tmp_path, monkeypatch):
    monkeypatch.setattr(api, '_workspace_root', tmp_path)
    monkeypatch.setattr(api, '_workbench', SimpleNamespace(list_runs=lambda p: []))
    key = str(uuid.uuid4())
    SugarWorkspace.create(tmp_path / key, name='Delete test')
    (tmp_path / key / 'keep.txt').write_text('saved research')
    assert api.delete_project(key)['deleted'] == key
    assert not api.list_research_projects()
    assert next((tmp_path / '.deleted-projects').glob('*/keep.txt')).read_text() == 'saved research'
    with pytest.raises(api.ApiError):
        api.resolve_project(key)


def test_active_project_cannot_be_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(api, '_workspace_root', tmp_path)
    monkeypatch.setattr(api, '_workbench', SimpleNamespace(list_runs=lambda p: [{'run_id': 'run'}], pipeline=lambda *a: SimpleNamespace(active=True)))
    key = str(uuid.uuid4())
    SugarWorkspace.create(tmp_path / key, name='Active')
    with pytest.raises(api.ApiError, match='Stop'):
        api.delete_project(key)
    assert (tmp_path / key / 'sugar-project.json').exists()


def test_external_project_is_unlinked_only(tmp_path, monkeypatch):
    monkeypatch.setattr(api, '_workspace_root', tmp_path / 'managed')
    monkeypatch.setattr(api, '_workbench', SimpleNamespace(list_runs=lambda p: []))
    folder = tmp_path / 'external'
    SugarWorkspace.create(folder, name='External')
    linked = api.link_local_project(str(folder))
    api.delete_project(linked['id'])
    assert (folder / 'sugar-project.json').exists()
    assert not api.list_research_projects()
