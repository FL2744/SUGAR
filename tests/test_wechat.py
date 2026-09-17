from __future__ import annotations

import pytest

from sugar_core.wechat import WeChatAccessError, fetch_wechat_article


ARTICLE_HTML = """
<!doctype html>
<html>
  <head>
    <meta property="og:title" content="Public diplomacy workshop">
    <meta name="author" content="Example University">
    <meta property="article:published_time" content="2026-09-17 14:30">
  </head>
  <body>
    <div id="js_name">Example University Official Account</div>
    <div id="js_content">
      Students joined a public workshop on language, technology, and cultural exchange.
    </div>
  </body>
</html>
"""


class FakeResponse:
    def __init__(
        self,
        text: str,
        *,
        status_code: int = 200,
        url: str = "https://mp.weixin.qq.com/s/ARTICLE123",
        headers: dict[str, str] | None = None,
    ):
        self.text = text
        self.status_code = status_code
        self.url = url
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_public_wechat_article_normalizes_to_post_record():
    session = FakeSession(FakeResponse(ARTICLE_HTML))

    record = fetch_wechat_article(
        "https://mp.weixin.qq.com/s/ARTICLE123#ignored-fragment",
        query="cultural exchange",
        session=session,
    )

    assert record.platform == "wechat"
    assert record.native_id == "ARTICLE123"
    assert record.content_type == "article"
    assert record.canonical_url == "https://mp.weixin.qq.com/s/ARTICLE123"
    assert record.source_mode == "wechat_public_article"
    assert record.source_host == "mp.weixin.qq.com"
    assert record.author_name == "Example University"
    assert record.author_handle == "Example University"
    assert record.query_matches == ["cultural exchange"]
    assert record.engagement == {}
    assert record.raw_stats["access_mode"] == "anonymous_public"
    assert record.raw_stats["article_title"] == "Public diplomacy workshop"
    assert record.published_at == "2026-09-17T06:30:00Z"
    assert "Students joined a public workshop" in record.original_text
    assert session.calls[0][1]["allow_redirects"] is False


def test_wechat_query_identity_is_stable_when_article_uses_legacy_parameters():
    url = "https://mp.weixin.qq.com/s?__biz=MzA1&mid=123&idx=2&sn=abcdef"
    record = fetch_wechat_article(url, session=FakeSession(FakeResponse(ARTICLE_HTML, url=url)))

    assert record.native_id == "MzA1:123:2:abcdef"
    assert record.raw_stats["identity"] == {"__biz": "MzA1", "mid": "123", "idx": "2", "sn": "abcdef"}


@pytest.mark.parametrize(
    "url",
    [
        "http://mp.weixin.qq.com/s/ARTICLE123",
        "https://weixin.qq.com/s/ARTICLE123",
        "https://example.com/s/ARTICLE123",
        "https://user:pass@mp.weixin.qq.com/s/ARTICLE123",
    ],
)
def test_wechat_rejects_non_public_article_origins(url: str):
    with pytest.raises(ValueError, match="mp.weixin.qq.com|embedded credentials"):
        fetch_wechat_article(url, session=FakeSession(FakeResponse(ARTICLE_HTML)))


def test_wechat_rejects_redirect_off_public_host():
    session = FakeSession(
        FakeResponse(
            "",
            status_code=302,
            headers={"Location": "https://example.com/login"},
        )
    )
    with pytest.raises(ValueError, match="mp.weixin.qq.com"):
        fetch_wechat_article("https://mp.weixin.qq.com/s/ARTICLE123", session=session)


def test_wechat_allows_same_origin_redirect_after_validation():
    class RedirectSession:
        def __init__(self):
            self.calls = []

        def get(self, url: str, **kwargs):
            self.calls.append(url)
            if len(self.calls) == 1:
                return FakeResponse("", status_code=302, url=url, headers={"Location": "/s/FINAL123"})
            return FakeResponse(ARTICLE_HTML, url=url)

    session = RedirectSession()
    record = fetch_wechat_article("https://mp.weixin.qq.com/s/START123", session=session)
    assert session.calls == ["https://mp.weixin.qq.com/s/START123", "https://mp.weixin.qq.com/s/FINAL123"]
    assert record.native_id == "FINAL123"


def test_wechat_http_access_gate_fails_closed():
    session = FakeSession(FakeResponse("Forbidden", status_code=403))
    with pytest.raises(WeChatAccessError, match="will not bypass"):
        fetch_wechat_article("https://mp.weixin.qq.com/s/ARTICLE123", session=session)


def test_wechat_challenge_page_fails_closed():
    session = FakeSession(FakeResponse("<html><body>环境异常，请进行安全验证</body></html>"))
    with pytest.raises(WeChatAccessError, match="will not attempt to bypass"):
        fetch_wechat_article("https://mp.weixin.qq.com/s/ARTICLE123", session=session)


def test_wechat_unrecognized_page_is_not_saved_as_article():
    session = FakeSession(FakeResponse("<html><body>ordinary page without article structure</body></html>"))
    with pytest.raises(RuntimeError, match="recognizable public Official Account article"):
        fetch_wechat_article("https://mp.weixin.qq.com/s/ARTICLE123", session=session)
