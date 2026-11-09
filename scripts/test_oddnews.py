#!/usr/bin/env python3
"""Offline tests for feed parsing and URL identity."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import oddnews

RSS = """<?xml version="1.0"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>Example</title>
    <item>
      <title><![CDATA[Hello &amp; odd world - NDTV]]></title>
      <link>https://www.example.com/stories/hello/?utm_source=rss</link>
      <description><![CDATA[A short lede about an odd hello that is long enough to keep.]]></description>
      <pubDate>Sun, 08 Nov 2026 12:00:00 +0000</pubDate>
      <media:content url="https://cdn.example.com/a.jpg" medium="image"/>
    </item>
    <item>
      <title>Skip me</title>
      <link>https://example.com/other</link>
      <description>This one is filtered by linkIncludes and is also long enough.</description>
    </item>
  </channel>
</rss>
"""

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>nottheonion</title>
  <entry>
    <title>Train delivers bananas to a flooded sanctuary</title>
    <link href="https://www.reddit.com/r/nottheonion/comments/abc/train/"/>
    <updated>2026-11-08T12:00:00+00:00</updated>
    <content type="html">&lt;a href="https://www.ndtv.com/offbeat/bananas-123"&gt;[link]&lt;/a&gt;
      &lt;img src="https://external-preview.redd.it/abc.jpeg" /&gt;</content>
  </entry>
</feed>
"""


class ParseTests(unittest.TestCase):
    def test_normalize_strips_tracking_and_www(self):
        url = oddnews.normalize_url("https://www.Example.com/a/b/?utm_source=rss&id=1#x")
        self.assertEqual(url, "https://example.com/a/b?id=1")

    def test_rss_item_image_and_filter(self):
        items = oddnews.parse_feed_items(RSS, link_includes="example.com/stories")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://example.com/stories/hello")
        self.assertEqual(items[0]["title"], "Hello & odd world")
        self.assertEqual(items[0]["image"], "https://cdn.example.com/a.jpg")
        self.assertIn("short lede", items[0]["summary"])
        self.assertTrue(items[0]["publishedAt"].startswith("2026-11-08"))

    def test_reddit_atom_prefers_outbound_link(self):
        items = oddnews.parse_feed_items(ATOM)
        self.assertEqual(items[0]["url"], "https://ndtv.com/offbeat/bananas-123")
        self.assertIn("reddit.com", items[0]["discussionUrl"])
        self.assertIn("external-preview.redd.it", items[0]["image"])

    def test_ndtv_card(self):
        html = """
        <li class="NwsLstPg-a-li">
          <a href="https://www.ndtv.com/offbeat/ceo-takes-a-train-1229">
            <img alt="CEO takes a long train home" src="https://c.ndtvimg.com/pic.jpg" />
          </a>
        </li>
        """
        items = oddnews.parse_ndtv(html, "https://www.ndtv.com/offbeat")
        self.assertEqual(items[0]["title"], "CEO takes a long train home")
        self.assertEqual(items[0]["image"], "https://c.ndtvimg.com/pic.jpg")

    def test_absurd_story_outranks_feelgood(self):
        bizarre, bizarre_points, _feel = oddnews.score_taste(
            "Man marries 120 wives in a bizarre ceremony that stunned the village"
        )
        warm, _bizarre, warm_feel = oddnews.score_taste(
            "Adorable puppy reunion melts hearts and leaves everyone in tears of joy"
        )
        self.assertGreaterEqual(bizarre, 7)
        self.assertIn("离谱", oddnews.taste_labels(bizarre, bizarre_points, 0))
        self.assertLess(warm, 0)
        self.assertIn("温情", oddnews.taste_labels(warm, 0, warm_feel))

    def test_assign_tags_stacks_tribe_and_drops_other(self):
        regions = [
            {"id": "africa", "nameZh": "非洲", "hints": ["kenya", "maasai"]},
            {"id": "india", "nameZh": "印度", "hints": ["india", "delhi"]},
            {"id": "philippines", "nameZh": "菲律宾", "hints": ["manila"]},
            {"id": "pakistan", "nameZh": "巴基斯坦", "hints": ["karachi"]},
            {"id": "tribe", "nameZh": "部落", "hints": ["tribe", "tribal", "maasai", "uncontacted"]},
            {"id": "other", "nameZh": "其他", "hints": []},
        ]
        tribal = {"title": "Maasai ceremony draws crowds in Kenya", "summary": "Families walked in from remote homesteads."}
        oddnews.assign_tags(tribal, {"region": "other", "country": "INT"}, regions)
        self.assertEqual(tribal["tags"], ["非洲", "部落", "猎奇"])
        plain = {"title": "Florida parking dispute ends with a trumpet", "summary": "Nobody was hurt and the video spread."}
        oddnews.assign_tags(plain, {"region": "other", "country": "US"}, regions)
        self.assertEqual(plain["tags"], ["其他"])

    def test_subject_country_is_single_hit_only(self):
        countries = [
            {"code": "IN", "hints": ["india", "delhi"]},
            {"code": "PK", "hints": ["pakistan", "karachi"]},
        ]
        self.assertEqual(oddnews.subject_country("A donkey wandered through Karachi", countries, "INT"), "PK")
        self.assertEqual(
            oddnews.subject_country("India and Pakistan both claimed the trophy", countries, "INT"),
            "INT",
        )


if __name__ == "__main__":
    unittest.main()
