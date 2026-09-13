from __future__ import annotations

import json
import os

import pytest

from sugar_core.weibo_seed_harvest import SeedHarvestConfig, SeedHarvestStore, run_weibo_seed_harvest


pytestmark = pytest.mark.skipif(
    os.environ.get("SUGAR_LIVE_WEIBO") != "1",
    reason="set SUGAR_LIVE_WEIBO=1 to run bounded public Weibo seed-harvest smoke",
)


def test_live_seed_harvest_persists_real_post_and_public_comments(tmp_path):
    config = SeedHarvestConfig(
        seeds=("5320265912291527",),
        name="live_seed",
        max_comments=5,
        comment_pages=1,
        max_reposts=0,
        author_posts=0,
        inter_seed_delay_seconds=0,
    )
    outputs = run_weibo_seed_harvest(config, tmp_path, cookie="")
    checkpoint = tmp_path / "live_seed.seedharvest.sqlite3"
    manifest = json.loads((tmp_path / "live_seed.seedharvest.json").read_text(encoding="utf-8"))

    assert manifest["access_mode"] == "anonymous"
    assert manifest["seed_counts"] == {"completed": 1}
    assert manifest["unique_records"] >= 2
    assert any(path.endswith("live_seed.jsonl") for path in outputs)

    with SeedHarvestStore(checkpoint) as store:
        rows = store.seed_rows()
        records = store.records()
    assert rows[0]["status"] == "completed"
    assert rows[0]["comments_retrieved"] > 0
    assert rows[0]["surface_status"]["seed"]["status"] == "ok"
    assert rows[0]["surface_status"]["comments"]["status"] == "ok"
    assert any(record.native_id == "5320265912291527" for record in records)
    assert any(record.content_type == "comment" for record in records)

    print("LIVE_SEED_HARVEST_MANIFEST", manifest)
    print("LIVE_SEED_HARVEST_STATUS", rows[0])
