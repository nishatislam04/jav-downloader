import sys
import types


def _stub_runtime_dependency(name, factory=None):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = factory() if factory else types.ModuleType(name)


def _m3u8_stub():
    mod = types.ModuleType("m3u8")
    mod.load = lambda *args, **kwargs: None
    mod.loads = lambda *args, **kwargs: None
    return mod


_stub_runtime_dependency("m3u8", _m3u8_stub)

from bs4 import BeautifulSoup

from jav_downloader import sites as M3U8Sites
from jav_downloader.core.video_identity import (
    site_from_url,
    trusted_chinese_subtitle_evidence,
)
from jav_downloader.sites import hanime1 as hanime_mod
from jav_downloader.sites.hanime1 import (
    SiteHanime1,
    _extract_sources,
    _select_source,
)

WATCH_HTML = """
<html>
  <head>
    <meta property="og:title" content="Fallback title - Hanime1.me">
    <meta property="og:image" content="https://vdownload.hembed.com/image/thumbnail/42l.jpg?secure=thumb">
  </head>
  <body>
    <h3 class="video-details-wrapper">A &amp; B</h3>
    <video poster="https://vdownload.hembed.com/image/thumbnail/42l.jpg?secure=poster">
      <source src="https://vdownload.hembed.com/video/42-480p.mp4?secure=low">
      <source src="https://vdownload.hembed.com/video/42-1080p.mp4?secure=high">
      <source src="https://vdownload.hembed.com/video/42-720p.mp4?secure=mid">
      <source src="javascript:alert(1)">
    </video>
  </body>
</html>
"""


def test_hanime1_validate_url_is_strict_and_anchored():
    assert SiteHanime1.validate_url("https://hanime1.me/watch?v=407751") == "407751"
    assert SiteHanime1.validate_url("https://www.hanime1.me/watch?v=42") == "42"
    assert SiteHanime1.validate_url("http://hanime1.me/watch?v=42") is None
    assert SiteHanime1.validate_url("https://hanime1.me/watch?v=42&next=1") is None
    assert SiteHanime1.validate_url("https://hanime1.me/watch?v=42#x") is None
    assert SiteHanime1.validate_url("https://hanime1.me/watch/v=42") is None
    assert SiteHanime1.validate_url("https://evil.test/watch?v=42") is None


def test_hanime1_extracts_https_mp4_sources_and_honours_resolution():
    sources = _extract_sources(BeautifulSoup(WATCH_HTML, "html.parser"))
    assert [(item["height"], item["url"]) for item in sources] == [
        (480, "https://vdownload.hembed.com/video/42-480p.mp4?secure=low"),
        (1080, "https://vdownload.hembed.com/video/42-1080p.mp4?secure=high"),
        (720, "https://vdownload.hembed.com/video/42-720p.mp4?secure=mid"),
    ]
    assert _select_source(sources, "highest")["height"] == 1080
    assert _select_source(sources, "lowest")["height"] == 480
    assert _select_source(sources, "720")["height"] == 720
    assert _select_source(sources, "480")["height"] == 480
    assert _select_source(sources, "360")["height"] == 480


def test_hanime1_get_url_infos_primes_session_and_uses_fresh_signed_source(monkeypatch):
    calls = []

    class Response:
        def __init__(self, url, text, status_code=200):
            self.url = url
            self.text = text
            self.content = text.encode("utf-8")
            self.status_code = status_code
            self.headers = {}

    class Session:
        def get(self, url, **kwargs):
            calls.append(url)
            if url == "https://hanime1.me/":
                return Response(url, "<html>home</html>")
            assert url == "https://hanime1.me/watch?v=42"
            return Response(url, WATCH_HTML)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(hanime_mod, "_make_scraper", lambda: Session())
    monkeypatch.setattr(hanime_mod, "get_resolution_pref", lambda: "720")

    crawler = SiteHanime1("https://hanime1.me/watch?v=42", silence=True)

    assert calls == ["https://hanime1.me/", "https://hanime1.me/watch?v=42"]
    assert crawler.is_url_vaildate()
    assert crawler.target_name() == "A & B"
    assert crawler._direct_url.endswith("42-720p.mp4?secure=mid")
    assert crawler._direct_referer == "https://hanime1.me/watch?v=42"
    assert crawler._imageUrl.endswith("42l.jpg?secure=thumb")


def test_hanime1_is_registered_for_site_creation(monkeypatch):
    monkeypatch.setattr(
        SiteHanime1,
        "get_url_infos",
        lambda self: (
            setattr(self, "_targetName", "Hanime video"),
            setattr(
                self, "_direct_url", "https://vdownload.hembed.com/video/42-720p.mp4"
            ),
            setattr(self, "_direct_referer", self._url),
            setattr(self, "_m3u8url", None),
        ),
    )
    assert M3U8Sites.VaildateUrl("https://hanime1.me/watch?v=42") is SiteHanime1
    created = M3U8Sites.CreateSite("https://hanime1.me/watch?v=42", silence=True)
    assert isinstance(created, SiteHanime1)
    assert created.is_url_vaildate()


def test_hanime1_identity_and_chinese_subtitle_listing_evidence_are_fail_closed():
    video_url = "https://hanime1.me/watch?v=407751"
    trusted = {
        "url": video_url,
        "_site": "Hanime1",
        "_source_listing_url": (
            "https://hanime1.me/search?tags%5B%5D=%E4%B8%AD%E6%96%87%E5%AD%97%E5%B9%95"
        ),
    }
    assert site_from_url(video_url) == "Hanime1"
    assert trusted_chinese_subtitle_evidence(trusted) == (
        "hanime1-tag-chinese-subtitle",
    )
    assert (
        trusted_chinese_subtitle_evidence(
            {
                **trusted,
                "_source_listing_url": (
                    "https://attacker.invalid/search?tags%5B%5D="
                    "%E4%B8%AD%E6%96%87%E5%AD%97%E5%B9%95"
                ),
            }
        )
        == ()
    )


