from pathlib import Path

from sugar_core.models import PostRecord
from sugar_core.weibo_investigation import WeiboInvestigation
from sugar_core.weibo_seed_harvest import SeedHarvestConfig, SeedHarvestStore, run_weibo_seed_harvest


def investigation(seed: str, **kwargs) -> WeiboInvestigation:
    root = PostRecord(platform="weibo", native_id=seed, canonical_url=f"https://m.weibo.cn/detail/{seed}", query="", source_mode="weibo_public_status", source_url=f"https://m.weibo.cn/statuses/show?id={seed}", published_at="2026-09-01T12:00:00Z", author_name="seed-author", original_text=f"seed {seed}", engagement={"likes": 1, "replies": 1, "reposts": 0})
    comment = PostRecord(platform="weibo", native_id=f"c{seed}", canonical_url=f"https://m.weibo.cn/detail/{seed}#comment-c{seed}", query="", content_type="comment", parent_record_key=root.record_key, thread_root_key=root.record_key, conversation_id=root.native_id, source_mode="weibo_public_comments", source_url=f"https://m.weibo.cn/api/comments/show?id={seed}", published_at="2026-09-01T13:00:00Z", author_name="commenter", original_text="public comment")
    return WeiboInvestigation(seed=root, comments=[comment], reposts=[], author_posts=[], original=None, surface_status={"seed": {"status": "ok"}, "comments": {"status": "ok"}, "reposts": {"status": "not_requested"}, "author_timeline": {"status": "not_requested"}}, insights={})


def test_thousand_seed_run_persists_and_resumes_without_recollection(tmp_path: Path):
    seeds = tuple(str(5300000000000000 + index) for index in range(1000))
    config = SeedHarvestConfig(seeds=seeds, name="bulk", inter_seed_delay_seconds=0)
    calls = {"count": 0}

    def counted(seed: str, **kwargs):
        calls["count"] += 1
        return investigation(seed, **kwargs)

    outputs = run_weibo_seed_harvest(config, tmp_path, investigator=counted, sleeper=lambda _: None)
    assert calls["count"] == 1000
    assert any(path.endswith("bulk.seedharvest.sqlite3") for path in outputs)
    with SeedHarvestStore(tmp_path / "bulk.seedharvest.sqlite3") as store:
        assert store.counts() == {"completed": 1000}
        assert len(store.records()) == 2000

    def forbidden(*args, **kwargs):
        raise AssertionError("completed seeds must not be recollected")

    run_weibo_seed_harvest(config, tmp_path, investigator=forbidden, sleeper=lambda _: None)
    with SeedHarvestStore(tmp_path / "bulk.seedharvest.sqlite3") as store:
        assert store.counts() == {"completed": 1000}
        assert len(store.records()) == 2000


def test_plan_change_and_access_mode_are_guarded(tmp_path: Path):
    config = SeedHarvestConfig(seeds=("5320265912291527",), name="guard", inter_seed_delay_seconds=0)
    run_weibo_seed_harvest(config, tmp_path, investigator=investigation, sleeper=lambda _: None)

    changed = SeedHarvestConfig(seeds=("5320265912291527", "5320265912291528"), name="guard", inter_seed_delay_seconds=0)
    try:
        run_weibo_seed_harvest(changed, tmp_path, investigator=investigation, sleeper=lambda _: None)
    except ValueError as exc:
        assert "different seed/depth plan" in str(exc)
    else:
        raise AssertionError("changed seed plan must not reuse checkpoint")

    try:
        run_weibo_seed_harvest(config, tmp_path, cookie="legitimate-existing-session", investigator=investigation, sleeper=lambda _: None)
    except ValueError as exc:
        assert "cannot resume" in str(exc)
        assert "anonymous" in str(exc) and "session" in str(exc)
    else:
        raise AssertionError("anonymous/session coverage must not mix inside one checkpoint")
