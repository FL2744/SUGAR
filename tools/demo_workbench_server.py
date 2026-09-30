#!/usr/bin/env python3
"""Offline demo of the SUGAR research workbench.

Runs the real HTTP API and pipeline, but with **simulated platforms and a simulated model**, so the
whole workflow (interpret -> plan preview -> live activity -> translations -> results -> export) can be
explored without credentials or network access. All posts are synthetic demo data.

    python tools/demo_workbench_server.py            # API on http://127.0.0.1:8765
    cd SUGAR-Desktop && npm run dev                  # UI on http://127.0.0.1:1420

The simulated platforms behave like real ones do on a bad day: one is slow, one rate-limits once, one
refuses access, and one needs a credential that is not configured.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sugar_api  # noqa: E402
from sugar_core.collector_registry import CollectorCapabilities, CollectorSpec  # noqa: E402
from sugar_core.credential_store import CredentialStore  # noqa: E402
from sugar_core.llm_providers import ProviderProfile, ProviderRegistry  # noqa: E402
from sugar_core.models import PostRecord  # noqa: E402
from sugar_core.nl_interpreter import interpret_deterministic  # noqa: E402
from sugar_core.workbench import ResearchWorkbench  # noqa: E402

DEMO_KEY = "demo-key-not-a-secret"
POSTS = {
    "en": ["Democracy only works when institutions are trusted and elections are free. (demo data)",
           "Young people here want a real say in how the country is run. (demo data)",
           "Local councils are experimenting with open budgets and public hearings. (demo data)",
           "Reform without accountability is just rebranding. (demo data)"],
    "ar": ["الديمقراطية تحتاج إلى مؤسسات قوية وانتخابات نزيهة (بيانات تجريبية)",
           "الشباب يريدون صوتاً حقيقياً في إدارة البلاد (بيانات تجريبية)",
           "المجالس المحلية تجرب الميزانيات المفتوحة والجلسات العامة (بيانات تجريبية)"],
    "fa": ["دموکراسی بدون نهادهای قابل اعتماد معنا ندارد (داده آزمایشی)", "جوانان خواهان نقش واقعی در اداره کشور هستند (داده آزمایشی)"],
    "tr": ["Demokrasi ancak güvenilir kurumlarla çalışır (deneme verisi)", "Gençler ülkenin yönetiminde söz sahibi olmak istiyor (deneme verisi)"],
    "zh": ["民主需要可信的制度和自由的选举（演示数据）", "年轻人希望在国家治理中有真正的发言权（演示数据）"],
}
GLOSSARY = {POSTS["ar"][0]: "Democracy needs strong institutions and fair elections (demo translation)",
            POSTS["ar"][1]: "Young people want a real voice in running the country (demo translation)",
            POSTS["ar"][2]: "Local councils are trying open budgets and public hearings (demo translation)",
            POSTS["fa"][0]: "Democracy is meaningless without trustworthy institutions (demo translation)",
            POSTS["fa"][1]: "Young people want a real role in running the country (demo translation)",
            POSTS["tr"][0]: "Democracy only works with trusted institutions (demo translation)",
            POSTS["tr"][1]: "Young people want a say in governing the country (demo translation)",
            POSTS["zh"][0]: "Democracy needs credible institutions and free elections (demo translation)",
            POSTS["zh"][1]: "Young people want a real voice in governance (demo translation)"}


def _record(platform: str, key: str, text: str, n: int, *, lang: str = "") -> PostRecord:
    return PostRecord(platform=platform, native_id=f"{platform}-{key}-{n}", canonical_url=f"https://demo.invalid/{platform}/{key}/{n}", query=key,
                      original_text=text, author_name=f"demo_user_{n % 7 + 1}", published_at="2026-08-%02dT12:00:00Z" % (n % 27 + 1), platform_language=lang)


def _source(name: str, languages: list[str], *, delay: float, fail: str = "", rate_limit_first: bool = False, secrets=()) -> CollectorSpec:
    state = {"calls": 0}

    def search(request):
        state["calls"] += 1
        time.sleep(delay)
        if fail:
            raise RuntimeError(fail)
        if rate_limit_first and state["calls"] == 1:
            raise RuntimeError(f"{name.capitalize()} rate limit reached (429).")
        term = request.search_terms[0]
        rows = []
        seed = sum(ord(c) for c in term + name)
        pool = [(lang, text) for lang in languages for text in POSTS[lang]]
        for i in range(min(request.max_posts_per_query, 6)):
            lang, text = pool[(seed + i) % len(pool)]
            rows.append(_record(name, str(seed % 997), text + ("" if i % 5 else " memes"), (seed + i) % 40, lang=""))
        rows.append(rows[0])            # the same post again: exercises duplicate handling
        return rows

    return CollectorSpec(name=name, search=search, required_secrets=tuple(secrets),
                         capabilities=CollectorCapabilities(keyword_search=True, anonymous_search=not secrets),
                         description=f"Simulated {name} for the offline demo.")


class DemoModel(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get("Authorization") != f"Bearer {DEMO_KEY}":
            return self._json(401, {"error": {"message": "Incorrect API key provided", "code": "invalid_api_key"}})
        self._json(200, {"data": [{"id": "demo-model"}, {"id": "demo-model-large"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        if self.headers.get("Authorization") != f"Bearer {DEMO_KEY}":
            return self._json(401, {"error": {"message": "Incorrect API key provided", "code": "invalid_api_key"}})
        time.sleep(0.35)
        user = body["messages"][-1]["content"]
        if "<request>" in user:
            request = user.split("<request>")[1].split("</request>")[0].strip()
            p = interpret_deterministic(request, today=date.today()).payload
            text = json.dumps({
                "topic": p.get("topic", ""), "research_question": p.get("research_question", ""), "geography": p.get("geography", []), "actors": [],
                "timeframe_start": (p.get("timeframe") or {}).get("start", ""), "timeframe_end": (p.get("timeframe") or {}).get("end", ""),
                "languages": p.get("languages", ["auto"]), "all_platforms": p.get("source_scope") != "selected", "platforms": p.get("platforms", []),
                "search_terms": p.get("search_terms", []), "exclusions": p.get("exclusions", []), "depth": p.get("depth", "standard"),
                "collection_mode": p.get("collection_mode", "discovery"), "translation_policy": "auto", "analysis_goals": p.get("analysis_goals", []),
                "assumptions": ["(demo model) No date range was given, so none is applied."], "clarifications": []})
        elif "<research>" in user:
            text = json.dumps({"queries": [{"text": "civic participation", "language": "", "rationale": "Close synonym (demo model)."}]})
        elif "<content>" in user:
            original = user.split("<content>\n")[1].split("\n</content>")[0]
            text = GLOSSARY.get(original, "(demo translation) " + original[:80])
        else:
            text = "ok"
        self._json(200, {"model": body.get("model"), "choices": [{"message": {"role": "assistant", "content": text}}],
                         "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})


def build(home: Path) -> tuple[ResearchWorkbench, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), DemoModel)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    store = CredentialStore(home, backend="file")
    providers = ProviderRegistry(home, store)
    providers.upsert(ProviderProfile(id="demo", name="Demo model (simulated)", type="openai_compatible", endpoint=url, model="demo-model"),
                     secret=DEMO_KEY, make_default=True)
    registry = {
        "bluesky": _source("bluesky", ["en", "ar"], delay=0.7),
        "mastodon": _source("mastodon", ["en", "tr", "fa"], delay=0.5, rate_limit_first=True, secrets=("mastodon_token",)),
        "bilibili": _source("bilibili", ["zh"], delay=0.9),
        "weibo": _source("weibo", ["zh", "en"], delay=0.4, fail="Weibo access control blocked the request (HTTP 403)."),
        "x": _source("x", ["en", "ar"], delay=0.3, secrets=("x_bearer_token",)),
    }
    return ResearchWorkbench(providers=providers, store=store, registry=registry), url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--home", default="", help="Folder for demo credentials and projects (default: a temporary folder).")
    parser.add_argument("--mastodon-token", action="store_true", help="Pretend a Mastodon token is configured (the demo then rate-limits once and recovers).")
    args = parser.parse_args()
    home = Path(args.home) if args.home else Path(tempfile.mkdtemp(prefix="sugar-demo-"))
    home.mkdir(parents=True, exist_ok=True)
    wb, model_url = build(home)
    if args.mastodon_token:
        wb.set_platform_secret("mastodon_token", "demo-token-not-a-secret")
    sugar_api._workspace_root = home / "workspaces"
    sugar_api._workspace_root.mkdir(parents=True, exist_ok=True)
    sugar_api._workbench = wb
    sugar_api.SugarApiHandler.allowed_origins = set(sugar_api.DEFAULT_DEV_ORIGINS)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), sugar_api.SugarApiHandler)
    server.daemon_threads = True
    print(f"SUGAR demo API ready at http://127.0.0.1:{server.server_address[1]}/api/health  (simulated model at {model_url})", flush=True)
    print(f"Demo data folder: {home}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
