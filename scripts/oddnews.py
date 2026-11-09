#!/usr/bin/env python3
"""Fetch odd / viral stories and write data/stories.json.

Stdlib only. Chinese text comes from the public Google Translate
endpoint (no API key). Re-runs are idempotent on the normalized source URL.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
PRINT_LOCK = threading.Lock()
MAX_KEEP = 800


def log(message: str) -> None:
    with PRINT_LOCK:
        print(message, flush=True)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if tag else ""


def kids(el: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(el) if local(child.tag) == name]


def text_of(el: ET.Element, name: str) -> str:
    for child in kids(el, name):
        joined = "".join(child.itertext()).strip()
        if joined:
            return joined
    return ""


def inner_blob(el: ET.Element) -> str:
    parts: list[str] = []
    for child in el.iter():
        if child.text:
            parts.append(child.text)
        if child.tail:
            parts.append(child.tail)
    return unescape("\n".join(parts))


def strip_tags(html: str) -> str:
    html = re.sub(r"(?is)<script\b.*?>.*?</script>", " ", html or "")
    html = re.sub(r"(?is)<style\b.*?>.*?</style>", " ", html or "")
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</p>", "\n", html)
    html = re.sub(r"(?is)<[^>]+>", " ", html)
    return unescape(html)


def clean_title(title: str) -> str:
    title = unescape(title or "")
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(
        r"\s+[\|\-–—:]\s+"
        r"(NDTV|Hindustan Times|India Today|Times of India|UPI|Oddity Central|"
        r"HuffPost|The Mirror|Mirror Online|Metro|Rappler|GMA News|ABC News|"
        r"Pedestrian\.TV|Geo News|Express Tribune|Dawn|Legit\.ng|Linda Ikeji).*$",
        "",
        title,
        flags=re.I,
    )
    return title.strip(" |-–—")


def clean_summary(text: str, title: str = "") -> str:
    text = strip_tags(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?i)submitted by\s+/u/\S+", "", text).strip()
    text = re.sub(r"(?i)\[link\]|\[comments\]", "", text).strip()
    if title and text.lower() == title.lower():
        return ""
    if len(text) < 30:
        return ""
    if len(text) > 480:
        cut = text[:480]
        space = cut.rfind(" ")
        text = (cut[:space] if space > 300 else cut).rstrip(" ,;:") + "…"
    return text


def normalize_url(url: str) -> str:
    url = unescape(url or "").strip()
    parts = urllib.parse.urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return ""
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=False)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"fbclid", "ref", "ref_src", "guccounter", "guce_referrer"}
    ]
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), netloc, path, urllib.parse.urlencode(query), "")
    )


def story_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def weak_image(url: str | None) -> bool:
    name = (url or "").split("?", 1)[0].rsplit("/", 1)[-1].lower()
    return "logo" in name or "placeholder" in name or name.startswith("default")


def ok_image(url: str | None) -> bool:
    if not url or not url.startswith("http"):
        return False
    low = url.lower()
    blocked = ("spacer", "pixel.gif", "favicon", "1x1", "blank.gif", "data:image")
    return not any(token in low for token in blocked)


def abs_url(href: str, base: str) -> str:
    return normalize_url(urllib.parse.urljoin(base, unescape(href or "").strip()))


def parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def slug_title(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    slug = path.rstrip("/").split("/")[-1]
    slug = re.sub(r"\.\w+$", "", slug)
    slug = re.sub(r"[-_]+", " ", slug)
    slug = re.sub(r"\b\d{5,}\b", "", slug)
    slug = re.sub(r"\s+", " ", slug).strip()
    return slug[:180]


def fetch_via_curl(url: str, timeout: int, limit: int) -> tuple[str, str, str]:
    proc = subprocess.run(
        [
            "curl",
            "-sL",
            "--compressed",
            "--max-time",
            str(timeout),
            "-A",
            UA,
            "-H",
            "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "-w",
            "\n__ODD_CTYPE__%{content_type}\n__ODD_URL__%{url_effective}",
            url,
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise urllib.error.URLError(f"curl exit {proc.returncode} for {url}")
    text = proc.stdout[:limit].decode("utf-8", errors="replace")
    ctype = ""
    final = url
    if "\n__ODD_CTYPE__" in text:
        body, marker = text.rsplit("\n__ODD_CTYPE__", 1)
        ctype_line, url_line = marker.split("\n__ODD_URL__", 1)
        ctype = ctype_line.strip()
        final = url_line.strip() or url
        text = body
    if not text.strip():
        raise urllib.error.URLError(f"curl returned an empty body for {url}")
    return text, final, ctype


def request_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            urllib.parse.quote(parts.path, safe="/%"),
            urllib.parse.quote(parts.query, safe="=&%+"),
            "",
        )
    )


def fetch(url: str, timeout: int, limit: int = 2_000_000) -> tuple[str, str, str]:
    url = request_url(url)
    origin = urllib.parse.urlsplit(url)
    referer = f"{origin.scheme}://{origin.netloc}/"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8,zh-CN;q=0.5",
            "Referer": referer,
        },
    )
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(limit)
                content_type = response.headers.get("content-type", "")
                final = response.geturl()
            break
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 403:
                return fetch_via_curl(url, timeout, limit)
            if exc.code in {429, 503} and attempt < 3:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise
    else:
        raise last_error or TimeoutError(url)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    charset = "utf-8"
    match = re.search(r"charset=([\w.-]+)", content_type, re.I)
    if match:
        charset = match.group(1)
    return raw.decode(charset, errors="replace"), final, content_type


def parse_xml(text: str) -> ET.Element:
    cleaned = text.lstrip("\ufeff")
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
    try:
        return ET.fromstring(cleaned)
    except ET.ParseError:
        fixed = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)", "&amp;", cleaned)
        return ET.fromstring(fixed)


def extract_img(blob: str) -> str:
    match = re.search(r"""<img[^>]+src=["']([^"']+)["']""", blob or "", re.I)
    if match:
        return unescape(match.group(1))
    match = re.search(r"""<img[^>]+data-src=["']([^"']+)["']""", blob or "", re.I)
    return unescape(match.group(1)) if match else ""


def extract_outbound(blob: str) -> str:
    self_hosts = ("reddit.com", "redd.it", "redditmedia.com", "redditstatic.com")
    for href in re.findall(r"""href=["'](https?://[^"']+)["']""", blob or "", re.I):
        href = unescape(href)
        host = urllib.parse.urlparse(href).netloc.lower()
        if any(host.endswith(item) for item in self_hosts):
            continue
        if any(token in href for token in ("external-preview", "thumbs.reddit", "redditmedia")):
            continue
        return href
    return ""


def image_from_item(el: ET.Element, blob: str) -> str:
    for child in el.iter():
        name = local(child.tag)
        url = child.attrib.get("url") or ""
        if not url:
            continue
        medium = child.attrib.get("medium", "")
        kind = child.attrib.get("type", "")
        if name in {"content", "thumbnail"}:
            if medium and medium != "image":
                continue
            if kind and not kind.startswith("image") and medium != "image":
                continue
            return unescape(url)
        if name == "enclosure" and (kind.startswith("image") or re.search(r"\.(jpe?g|png|webp|gif)(\?|$)", url, re.I)):
            return unescape(url)
    return extract_img(blob)


def date_from_item(el: ET.Element) -> str | None:
    for name in ("pubDate", "published", "updated", "date"):
        found = parse_date(text_of(el, name))
        if found:
            return found
    return None


def parse_feed_items(text: str, link_includes: str | None = None) -> list[dict]:
    head = text[:1200].lower()
    if "<html" in head and "<rss" not in head and "<feed" not in head:
        raise ValueError("response was HTML, not a feed")
    root = parse_xml(text)
    nodes = [el for el in root.iter() if local(el.tag) in {"item", "entry"}]
    items: list[dict] = []
    for node in nodes:
        blob = inner_blob(node)
        links: list[str] = []
        for child in kids(node, "link"):
            href = (child.attrib.get("href") or (child.text or "")).strip()
            if href.startswith("http"):
                links.append(href)
        guid = text_of(node, "guid")
        if guid.startswith("http"):
            links.append(guid)
        if not links:
            continue
        url = normalize_url(links[0])
        discussion = ""
        outbound = extract_outbound(blob)
        host = urllib.parse.urlparse(url).netloc
        if outbound and "reddit.com" in host:
            discussion = url
            url = normalize_url(outbound)
        if not url:
            continue
        if link_includes and link_includes not in url and link_includes not in (links[0] or ""):
            continue
        title = clean_title(text_of(node, "title"))
        summary = clean_summary(
            text_of(node, "description") or text_of(node, "summary") or blob,
            title,
        )
        image = image_from_item(node, blob)
        items.append(
            {
                "url": url,
                "discussionUrl": discussion or None,
                "title": title,
                "summary": summary,
                "image": image if ok_image(image) else "",
                "publishedAt": date_from_item(node),
            }
        )
    if not items:
        raise ValueError("feed had no items")
    return items


def parse_ndtv(html: str, page_url: str) -> list[dict]:
    if "NwsLstPg-a-li" not in html:
        raise ValueError("NDTV listing markup not found")
    items: list[dict] = []
    seen: set[str] = set()
    for block in re.findall(r'(?is)<li class="NwsLstPg-a-li">(.*?)</li>', html):
        href = re.search(r'href="(https://www\.ndtv\.com/offbeat/[^"#]+)"', block)
        if not href:
            continue
        url = normalize_url(href.group(1))
        if not url or url in seen:
            continue
        seen.add(url)
        alt = re.search(r'<img[^>]+alt="([^"]*)"', block)
        title = clean_title(unescape(alt.group(1))) if alt else slug_title(url)
        data_src = re.search(r'data-src="(https://[^"]+)"', block)
        src = re.search(r'\ssrc="(https://[^"]+)"', block)
        image = unescape((data_src or src).group(1)) if (data_src or src) else ""
        items.append(
            {
                "url": url,
                "discussionUrl": None,
                "title": title,
                "summary": "",
                "image": image if ok_image(image) else "",
                "publishedAt": None,
            }
        )
    if not items:
        raise ValueError(f"no NDTV stories on {page_url}")
    return items


def parse_jsonld_list(html: str, page_url: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for raw in re.findall(r'(?is)<script type="application/ld\+json">(.*?)</script>', html):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict) or node.get("@type") != "ItemList":
                continue
            elements = node.get("itemListElement") or []
            flat: list = []
            for element in elements:
                if isinstance(element, list):
                    flat.extend(element)
                else:
                    flat.append(element)
            for element in flat:
                if not isinstance(element, dict):
                    continue
                url = normalize_url(element.get("url") or "")
                title = clean_title(element.get("name") or "")
                if not url or url in seen:
                    continue
                seen.add(url)
                items.append(
                    {
                        "url": url,
                        "discussionUrl": None,
                        "title": title,
                        "summary": "",
                        "image": "",
                        "publishedAt": None,
                    }
                )
    if not items:
        raise ValueError(f"no ItemList stories on {page_url}")
    return items


def parse_html_links(html: str, attempt: dict) -> list[dict]:
    pattern = re.compile(attempt["linkPattern"], re.I)
    base = attempt.get("base") or attempt["url"]
    items: list[dict] = []
    seen: set[str] = set()
    for href, inner in re.findall(r'(?is)<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html):
        if not pattern.search(unescape(href)):
            continue
        url = abs_url(href, base)
        if not url or url in seen:
            continue
        seen.add(url)
        text = clean_title(strip_tags(inner))
        title = text if len(text) >= 8 else slug_title(url)
        image = extract_img(inner)
        items.append(
            {
                "url": url,
                "discussionUrl": None,
                "title": title,
                "summary": "",
                "image": image if ok_image(image) else "",
                "publishedAt": None,
            }
        )
    if not items:
        raise ValueError(f"no links matched {attempt['linkPattern']}")
    return items


def run_attempt(attempt: dict, timeout: int) -> list[dict]:
    kind = attempt["kind"]
    text, final, _ctype = fetch(attempt["url"], timeout=timeout, limit=2_000_000)
    if kind == "rss":
        return parse_feed_items(text, attempt.get("linkIncludes"))
    if kind == "ndtv-list":
        return parse_ndtv(text, final)
    if kind == "jsonld-list":
        return parse_jsonld_list(text, final)
    if kind == "html-links":
        return parse_html_links(text, attempt)
    raise ValueError(f"unknown kind {kind}")


def meta_content(html: str, key: str) -> str:
    patterns = [
        rf'(?is)<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'(?is)<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return unescape(match.group(1)).strip()
    return ""


def apply_og(item: dict, html: str) -> None:
    title = clean_title(meta_content(html, "og:title") or meta_content(html, "twitter:title"))
    summary = clean_summary(
        meta_content(html, "og:description")
        or meta_content(html, "description")
        or meta_content(html, "twitter:description"),
        title or item.get("title") or "",
    )
    image = meta_content(html, "og:image") or meta_content(html, "twitter:image")
    image = abs_url(image, item["url"]) if image else ""
    if title and len(item.get("title") or "") < 8:
        item["title"] = title
    if summary and len(item.get("summary") or "") < len(summary):
        item["summary"] = summary
    current = item.get("image") or ""
    reddit_preview = "redd.it" in current or "redditmedia" in current
    if ok_image(image) and not weak_image(image) and (not ok_image(current) or reddit_preview or weak_image(current)):
        item["image"] = image


def enrich_item(item: dict, timeout: int) -> None:
    try:
        html, _final, ctype = fetch(item["url"], timeout=timeout, limit=700_000)
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError):
        return
    if "html" not in ctype and "<html" not in html[:500].lower() and "og:" not in html[:4000].lower():
        return
    apply_og(item, html)


def enrich_rank(item: dict) -> int:
    image = item.get("image") or ""
    if not ok_image(image) or weak_image(image):
        return 0
    if "redd.it" in image or "redditmedia" in image:
        return 1
    if not item.get("summary"):
        return 2
    return 9


def assign_tags(item: dict, source: dict, regions: list[dict]) -> None:
    """Tag for the feed chips. Priority regions and 部落 can stack; 其他 is the leftover."""
    by_id = {region["id"]: region for region in regions}
    primary = by_id.get(source.get("region") or "other") or by_id.get("other")
    labels: list[str] = []
    if primary:
        labels.append(primary["nameZh"])
    text = f"{item.get('title') or ''} {item.get('summary') or ''}"
    for region in regions:
        if region.get("nameZh") in labels or region.get("id") == "other":
            continue
        if region.get("id") == "india" and re.search(
            r"indian country|american indian|native american", text, re.I
        ):
            continue
        for hint in region.get("hints") or []:
            if hint and re.search(rf"\b{re.escape(hint)}\b", text, re.I):
                labels.append(region["nameZh"])
                break
    priority = {"非洲", "印度", "菲律宾", "巴基斯坦", "部落"}
    if any(label in priority for label in labels):
        labels = [label for label in labels if label != "其他"]
    order = [region["nameZh"] for region in regions]
    item["tags"] = [name for name in order if name in set(labels)] or ["其他"]
    item["region"] = item["tags"][0]
    item["country"] = source.get("country") or ""
    apply_taste(item)


TASTE_TAGS = {"猎奇", "离谱", "温情"}
BIZARRE_PATTERNS = (
    (r"\b(bizarre|weird|odd|strange|outrageous|absurd|ridiculous|shocking|unbelievable)\b", 3),
    (r"\b(uncontacted|cannibal|witchcraft|voodoo|exorcis\w*|haunted|possessed|zombie)\b", 4),
    (r"\b(naked|nude|streaker|two-headed|conjoined|severed|coffin|buried alive)\b", 3),
    (r"\bguinness\b", 4),
    (r"\bworld record\b", 3),
    (r"\b(crocodile|alligator|python|anaconda|swallowed|bites off|ate a|eats? a)\b", 2),
    (r"\b(marry|marries|married|wives|husband)\b", 2),
    (r"\b(ritual|sacrifice|curse|skull|corpse|grave|sorcer\w*|witch)\b", 3),
    (r"\b(goes viral|stunned|baffled|mystery|unexplained|you won't believe)\b", 2),
    (r"\b(sentinelese|yanomami|jarawa|andaman|scarification|lip plate|neck ring)\b", 3),
    (r"离谱|猎奇|奇葩|离奇|震惊|未接触|食人|巫术|吉尼斯|裸体|鳄鱼", 3),
)
FEELGOOD_PATTERNS = (
    (r"\b(heart-?warming|adorable|wholesome|cute|puppy|kitten|melts hearts?|wins hearts)\b", 4),
    (r"\b(reunion|tears of joy|sweet gesture|kindness|inspiring|inspires|good samaritan)\b", 3),
    (r"\b(rescued (a )?(dog|cat|puppy|kitten)|saves (a )?(dog|cat|puppy))\b", 4),
    (r"\b(diwali wish|happy diwali|extends? .*wishes|birthday wish|greeting)\b", 3),
    (r"暖心|感动|可爱|温情|团聚|萌", 3),
)
POLITICS_PATTERN = r"\b(election|parliament|budget|minister|president|assembly|polls|senator|congress)\b|总统|议会|预算|选举"


def score_taste(text: str) -> tuple[int, int, int]:
    """Return (score, bizarre points, feel-good points)."""
    bizarre = 0
    feel = 0
    for pattern, points in BIZARRE_PATTERNS:
        if re.search(pattern, text, re.I):
            bizarre += points
    for pattern, points in FEELGOOD_PATTERNS:
        if re.search(pattern, text, re.I):
            feel += points
    score = bizarre - feel
    if score < 6 and re.search(POLITICS_PATTERN, text, re.I):
        score -= 3
    return score, bizarre, feel


def taste_labels(score: int, bizarre: int, feel: int) -> list[str]:
    if bizarre > 0 and score >= 7:
        return ["猎奇", "离谱"]
    if bizarre > 0 and score >= 3:
        return ["猎奇"]
    if feel > 0 and score <= -2:
        return ["温情"]
    return []


def apply_taste(story: dict) -> None:
    region_tags = [tag for tag in story.get("tags") or [] if tag not in TASTE_TAGS]
    text = " ".join(
        story.get(key) or "" for key in ("title", "summary", "titleZh", "summaryZh")
    )
    score, bizarre, feel = score_taste(text)
    labels = taste_labels(score, bizarre, feel)
    if "部落" in region_tags and score > -2:
        score += 3
        if "猎奇" not in labels and score >= 3:
            labels = ["猎奇", *labels]
    story["tasteScore"] = score
    story["tags"] = region_tags + labels


def subject_country(text: str, countries: list[dict], default: str) -> str:
    hits: list[str] = []
    for country in countries:
        for hint in country.get("hints") or []:
            if re.search(rf"\b{re.escape(hint)}\b", text, re.I):
                hits.append(country["code"])
                break
    unique = list(dict.fromkeys(hits))
    if len(unique) == 1:
        return unique[0]
    return default


def mostly_cjk(text: str) -> bool:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    letters = len(re.findall(r"[A-Za-z]", text or ""))
    return cjk >= 4 and cjk >= letters


class TranslateCache:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.data: dict[str, str] = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.data = {}

    def get(self, key: str) -> str | None:
        with self.lock:
            return self.data.get(key)

    def set(self, key: str, value: str) -> None:
        with self.lock:
            self.data[key] = value

    def save(self) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")


def translate_text(text: str, cache: TranslateCache, timeout: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ""
    if mostly_cjk(text):
        return text
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cached = cache.get(key)
    if cached:
        return cached
    query = urllib.parse.urlencode(
        {"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": text[:1800]}
    )
    url = "https://translate.googleapis.com/translate_a/single?" + query
    last_error: Exception | None = None
    for _try in range(3):
        try:
            body, _final, _ctype = fetch(url, timeout=timeout, limit=500_000)
            data = json.loads(body)
            translated = "".join(segment[0] for segment in data[0] if segment and segment[0]).strip()
            if translated:
                cache.set(key, translated)
                return translated
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, IndexError, TypeError) as exc:
            last_error = exc
    log(f"  translate failed: {last_error}")
    return ""


def attach_source(raw: dict, source: dict) -> dict:
    return {
        "url": raw["url"],
        "discussionUrl": raw.get("discussionUrl"),
        "country": source.get("country") or "",
        "sourceCountry": source.get("country") or "",
        "region": source.get("region") or "other",
        "tags": [],
        "sourceId": source["id"],
        "sourceName": source["name"],
        "sourceNameZh": source["nameZh"],
        "title": raw.get("title") or "",
        "titleZh": "",
        "summary": raw.get("summary") or "",
        "summaryZh": "",
        "image": raw.get("image") or "",
        "imageCredit": source["name"],
        "publishedAt": raw.get("publishedAt"),
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
    }


def collect_source(source: dict, limit: int, timeout: int) -> tuple[list[dict], dict]:
    found: list[dict] = []
    seen: set[str] = set()
    errors: list[str] = []
    for attempt in source["attempts"]:
        if len(found) >= limit:
            break
        try:
            batch = run_attempt(attempt, timeout)
        except (urllib.error.URLError, TimeoutError, OSError, ET.ParseError, ValueError, KeyError) as exc:
            errors.append(f"{attempt.get('kind')} {attempt.get('url')}: {exc}")
            continue
        for raw in batch:
            url = raw.get("url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            found.append(attach_source(raw, source))
            if len(found) >= limit:
                break
    status = "ok" if found else ("error" if errors else "empty")
    meta = {
        "id": source["id"],
        "name": source["name"],
        "nameZh": source["nameZh"],
        "country": source.get("country") or "",
        "region": source.get("region") or "other",
        "homepage": source["homepage"],
        "fetchedCount": len(found),
        "lastStatus": status,
        "lastError": None if found else ("; ".join(errors)[:500] if errors else "no items"),
    }
    sample = found[0]["title"][:90] if found else ""
    log(f"[{source['id']}] {status} {len(found)}" + (f" · {sample}" if sample else ""))
    if not found and errors:
        log(f"    ! {errors[0][:180]}")
    return found, meta


def fill_translations(items: list[dict], cache: TranslateCache, timeout: int, enabled: bool) -> None:
    pending: list[tuple[dict, str, str]] = []
    texts: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item.get("titleZh") and item.get("title"):
            pending.append((item, "titleZh", item["title"]))
        summary = item.get("summary") or ""
        if summary and summary != item.get("title") and not item.get("summaryZh"):
            pending.append((item, "summaryZh", summary))
    for _item, _field, text in pending:
        if text not in seen:
            seen.add(text)
            texts.append(text)
    if not texts:
        return
    log(f"translating {len(texts)} strings…")
    if not enabled:
        for item, field, text in pending:
            item[field] = text
        return
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(translate_text, text, cache, timeout): text for text in texts}
        done = 0
        for future in as_completed(futures):
            text = futures[future]
            results[text] = future.result()
            done += 1
            if done % 25 == 0 or done == len(texts):
                log(f"  translated {done}/{len(texts)}")
    for item, field, text in pending:
        item[field] = results.get(text) or ""
    for item in items:
        if not item.get("summaryZh"):
            item["summaryZh"] = item.get("titleZh") or ""


def load_config(path: Path) -> tuple[list[dict], list[dict]]:
    config = json.loads(path.read_text(encoding="utf-8"))
    regions = config.get("regions") or config.get("countries") or []
    return regions, config["sources"]


def load_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    found: dict[str, dict] = {}
    for story in payload.get("stories") or []:
        url = story.get("url")
        if url:
            found[url] = story
    return found


def merge_story(old: dict | None, new: dict) -> dict:
    if not old:
        new["id"] = story_id(new["url"])
        return new
    merged = dict(old)
    for key in (
        "discussionUrl",
        "title",
        "summary",
        "image",
        "publishedAt",
        "country",
        "sourceCountry",
        "sourceId",
        "sourceName",
        "sourceNameZh",
        "imageCredit",
        "country",
    ):
        if key == "image":
            continue
        if not merged.get(key) and new.get(key):
            merged[key] = new[key]
    if new.get("image") and (
        not ok_image(merged.get("image"))
        or (weak_image(merged.get("image")) and not weak_image(new.get("image")))
    ):
        merged["image"] = new["image"]
    if new.get("tags"):
        merged["tags"] = new["tags"]
        merged["region"] = new.get("region") or merged.get("region")
    if not merged.get("titleZh") and new.get("titleZh"):
        merged["titleZh"] = new["titleZh"]
    if not merged.get("summaryZh") and new.get("summaryZh"):
        merged["summaryZh"] = new["summaryZh"]
    if not merged.get("id"):
        merged["id"] = story_id(merged["url"])
    return merged


def rescore_file(data_path: Path) -> int:
    if not data_path.exists():
        log(f"no stories at {data_path}")
        return 1
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    stories = payload.get("stories") or []
    for story in stories:
        apply_taste(story)
    stories.sort(
        key=lambda story: (
            story.get("tasteScore") or 0,
            story.get("publishedAt") or story.get("fetchedAt") or "",
        ),
        reverse=True,
    )
    payload["stories"] = stories
    payload["generatedAt"] = datetime.now(timezone.utc).isoformat()
    write_payload(payload, data_path, ROOT / "public" / "data" / "stories.json")
    counts: dict[str, int] = {}
    for story in stories:
        for tag in story.get("tags") or []:
            if tag in TASTE_TAGS:
                counts[tag] = counts.get(tag, 0) + 1
    log(
        f"rescored {len(stories)} stories · 猎奇 {counts.get('猎奇', 0)} · "
        f"离谱 {counts.get('离谱', 0)} · 温情 {counts.get('温情', 0)}"
    )
    return 0


def write_payload(payload: dict, data_path: Path, public_path: Path) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    targets = [data_path, public_path]
    exported = ROOT / "out" / "data" / "stories.json"
    if exported.parent.parent.exists():
        targets.append(exported)
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update the odd-news story file.")
    parser.add_argument("--limit", type=int, default=None, help="Max new items per source.")
    parser.add_argument("--source", action="append", help="Only run these source ids. Repeatable.")
    parser.add_argument("--rescore-only", action="store_true", help="Retag saved stories without fetching.")
    parser.add_argument("--no-translate", action="store_true")
    parser.add_argument("--timeout", type=int, default=18)
    parser.add_argument("--enrich-limit", type=int, default=160)
    parser.add_argument("--config", default=str(ROOT / "sources.json"))
    parser.add_argument("--data", default=str(ROOT / "data" / "stories.json"))
    args = parser.parse_args(argv)

    limit = args.limit
    if limit is None:
        raw_limit = __import__("os").environ.get("ODDNEWS_MAX_PER_SOURCE", "12")
        limit = int(raw_limit)
    translate_enabled = not args.no_translate and __import__("os").environ.get("ODDNEWS_TRANSLATE", "1") != "0"
    timeout = int(__import__("os").environ.get("ODDNEWS_TIMEOUT", str(args.timeout)))

    if args.rescore_only:
        return rescore_file(Path(args.data))

    regions, sources = load_config(Path(args.config))
    if args.source:
        wanted = set(args.source)
        sources = [source for source in sources if source["id"] in wanted]
        if not sources:
            log("no matching sources")
            return 1

    log(f"fetching {len(sources)} sources, up to {limit} each")
    collected: list[dict] = []
    metas: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(collect_source, source, limit, timeout): source for source in sources
        }
        for future in as_completed(futures):
            items, meta = future.result()
            collected.extend(items)
            metas.append(meta)

    by_id = {source["id"]: source for source in sources}
    rank = {source["id"]: index for index, source in enumerate(sources)}
    metas.sort(key=lambda meta: rank.get(meta["id"], 999))

    deduped: list[dict] = []
    seen_urls: set[str] = set()
    for item in sorted(collected, key=lambda row: rank.get(row["sourceId"], 999)):
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        deduped.append(item)

    need = [item for item in deduped if enrich_rank(item) < 9]
    need.sort(key=enrich_rank)
    need = need[: args.enrich_limit]
    if need:
        log(f"opening {len(need)} pages for images and ledes…")
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda item: enrich_item(item, timeout), need))

    kept: list[dict] = []
    dropped = 0
    for item in deduped:
        item["title"] = clean_title(item.get("title") or "")
        item["summary"] = clean_summary(item.get("summary") or "", item["title"])
        if len(item["title"]) < 8 or not ok_image(item.get("image")):
            dropped += 1
            continue
        source = by_id[item["sourceId"]]
        assign_tags(item, source, regions)
        kept.append(item)
    log(f"kept {len(kept)} with a title and image, dropped {dropped}")

    data_path = Path(args.data)
    existing = load_existing(data_path)
    cache = TranslateCache(ROOT / "data" / "translate-cache.json")
    merged: dict[str, dict] = dict(existing)
    fresh_for_translation: list[dict] = []
    for item in kept:
        old = merged.get(item["url"])
        if old and old.get("titleZh") and old.get("summaryZh") and ok_image(old.get("image")):
            merged[item["url"]] = merge_story(old, item)
            continue
        combined = merge_story(old, item)
        merged[item["url"]] = combined
        fresh_for_translation.append(combined)

    try:
        fill_translations(fresh_for_translation, cache, timeout, translate_enabled)
    finally:
        cache.save()

    publishable: list[dict] = []
    for story in merged.values():
        if not story.get("titleZh") or not story.get("summaryZh") or not ok_image(story.get("image")):
            continue
        if not story.get("id"):
            story["id"] = story_id(story["url"])
        apply_taste(story)
        publishable.append(story)
    publishable.sort(
        key=lambda story: (
            story.get("tasteScore") or 0,
            story.get("publishedAt") or story.get("fetchedAt") or "",
        ),
        reverse=True,
    )
    publishable = publishable[:MAX_KEEP]

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "regions": [
            {"id": region.get("id") or region.get("code"), "nameZh": region["nameZh"]}
            for region in regions
        ],
        "sources": metas,
        "stories": publishable,
    }
    public_path = ROOT / "public" / "data" / "stories.json"
    write_payload(payload, data_path, public_path)

    counts: dict[str, int] = {}
    for story in publishable:
        for tag in story.get("tags") or [story.get("region") or "其他"]:
            counts[tag] = counts.get(tag, 0) + 1
    log(f"wrote {len(publishable)} stories -> {data_path}")
    for region in regions:
        log(f"  {region['nameZh']}: {counts.get(region['nameZh'], 0)}")
    missing = [region["nameZh"] for region in regions if counts.get(region["nameZh"], 0) == 0]
    if missing:
        log("warning: no stories yet for " + ", ".join(missing))
    return 0 if publishable else 1


if __name__ == "__main__":
    sys.exit(main())
