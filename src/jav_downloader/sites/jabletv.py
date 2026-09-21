#!/usr/bin/env python
# coding: utf-8

import re
import cloudscraper
try:
    from curl_cffi import requests as cffi_requests
    _use_cffi = True
except ImportError:
    _use_cffi = False
from jav_downloader.sites.base import *
from bs4 import BeautifulSoup


def _make_scraper():
    """Fresh scraper: curl_cffi (Cloudflare-capable) if available, else cloudscraper."""
    if _use_cffi:
        return cffi_requests.Session(impersonate='chrome')
    return cloudscraper.create_scraper(browser=request_headers, delay=10)


class SiteJableTV(M3U8Crawler):
    website_pattern = r'https://jable\.tv/videos/.+/'
    website_dirname_pattern = r'https://jable\.tv/videos/(.+)/$'

    def get_url_infos(self):
        with _make_scraper() as scraper:
            def _validate(resp):
                return ('og:title' in resp.text) and ('m3u8' in resp.text)
            htmlfile, host, reason = fetch_with_mirrors(scraper, self._url, 'jable', _validate, timeout=30)
        if reason != 'ok':
            if reason == 'blocked':
                raise MirrorsBlockedError("所有鏡像都被 Cloudflare 阻擋（可能是你的網路/IP 信譽問題，請改用 VPN 或不同網路）")
            raise Exception(f"頁面解析失敗（版面改版或影片不存在）: {self._url}")
        parsed = self._parse_page(htmlfile.text)
        if not parsed:
            raise Exception(f"頁面解析失敗（可能被 Cloudflare 阻擋或版面改版）: {self._url}")
        self._targetName, self._imageUrl, self._m3u8url = parsed

    @staticmethod
    def _parse_page(text):
        """Extract (title, image_url, m3u8_url) from a video page, or None if any is
        missing. Precise captures instead of greedy `.+` — on minified/single-line HTML a
        greedy `.+` spans to the LAST delimiter on the line, yielding a wrong title/URL."""
        title = re.search(r'og:title"\s+content="([^"]+)"', text)
        image = re.search(r'og:image"\s+content="([^"]+)"', text)
        m3u8 = re.search(r'https://[^\s"\']+\.m3u8', text)  # bounded to one URL token
        if not (title and image and m3u8):
            return None
        return title.group(1), image.group(1), m3u8.group(0)


class SiteJableTV_Backup(SiteJableTV):
    website_pattern = r'https://fs1\.app/videos/.+/'
    website_dirname_pattern = r'https://fs1\.app/videos/(.+)/$'
