from __future__ import annotations

import pytest

from sugar_core.public_items import (
    fetch_douyin_public_item,
    fetch_wechat_article,
    fetch_zhihu_public_item,
)


class FakeResponse:
    def __init__(self, text: str, *, url: str, status_code: int = 200, content_type: str = "text/html; charset=utf-8"):
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_wechat_public_article_extracts_source_text_and_provenance():
    html = """
    <html><head>
      <meta property="og:title" content="Chinese Language Day" />
      <link rel="canonical" href="https://mp.weixin.qq.com/s?__biz=abc&mid=123&idx=1&sn=deadbeef" />
    </head><body>
      <div id="js_name">Example Official Account</div>
      <div id="js_content"><p>First paragraph.</p><p>Second paragraph.</p></div>
      <script>var ct = "1710000000";</script>
    </body></html>
    """
    session = FakeSession(FakeResponse(html, url="https://mp.weixin.qq.com/s/example"))
    record = fetch_wechat_article("https://mp.weixin.qq.com/s/example", session=session)

    assert record.platform == "wechat"
    assert record.content_type == "article"
    assert record.source_mode == "wechat_public_url"
    assert record.author_name == "Example Official Account"
    assert "First paragraph." in record.original_text
    assert "Second paragraph." in record.original_text
    assert record.native_id == "abc:123:1:deadbeef"
    assert record.published_at.startswith("2024-")
    assert session.calls[0][1]["allow_redirects"] is True


def test_douyin_public_video_import_uses_public_metadata_only():
    html = """
    <html><head>
      <meta property="og:title" content="Public Douyin video" />
      <meta property="og:description" content="A public video description #topic" />
      <link rel="canonical" href="https://www.douyin.com/video/7351234567890123456" />
    </head><body></body></html>
    """
    session = FakeSession(FakeResponse(html, url="https://www.douyin.com/video/7351234567890123456"))
    record = fetch_douyin_public_item("https://v.douyin.com/example/", session=session)

    assert record.platform == "douyin"
    assert record.native_id == "7351234567890123456"
    assert record.content_type == "video"
    assert record.original_text == "A public video description #topic"
    assert record.raw_stats["access_mode"] == "anonymous_public_url"


def test_zhihu_public_url_import_has_stable_identity():
    html = """
    <html><head>
      <meta property="og:title" content="Example answer" />
      <meta name="description" content="Answer summary" />
      <link rel="canonical" href="https://www.zhihu.com/question/123/answer/456" />
    </head><body><article><p>Full public answer text.</p></article></body></html>
    """
    session = FakeSession(FakeResponse(html, url="https://www.zhihu.com/question/123/answer/456"))
    record = fetch_zhihu_public_item("https://www.zhihu.com/question/123/answer/456", session=session)

    assert record.platform == "zhihu"
    assert record.native_id == "answer-456"
    assert record.content_type == "answer"
    assert record.original_text == "Full public answer text."


def test_public_item_redirect_to_unexpected_host_fails_closed():
    session = FakeSession(FakeResponse("<html></html>", url="https://example.com/capture"))
    with pytest.raises(RuntimeError, match="unexpected host"):
        fetch_wechat_article("https://mp.weixin.qq.com/s/example", session=session)


def test_public_item_access_gate_is_not_treated_as_zero_activity():
    session = FakeSession(
        FakeResponse("<html><body>安全验证</body></html>", url="https://www.douyin.com/video/7351234567890123456")
    )
    with pytest.raises(RuntimeError, match="access/verification marker"):
        fetch_douyin_public_item("https://www.douyin.com/video/7351234567890123456", session=session)


def test_platform_host_allowlist_blocks_unrelated_urls_before_request():
    session = FakeSession(FakeResponse("<html></html>", url="https://example.com"))
    with pytest.raises(ValueError, match="not an allowed wechat public host"):
        fetch_wechat_article("https://example.com/not-wechat", session=session)
    assert session.calls == []
