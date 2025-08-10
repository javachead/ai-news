# rss_to_slack.py
import os, sys, time, re, traceback
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

import requests
import feedparser
from dateutil import parser as dateparser

UTC = timezone.utc

# ==== 環境変数 ====
FEED_URLS = (os.getenv("FEED_URLS") or "").strip()
WEBHOOK   = (os.getenv("SLACK_WEBHOOK_URL") or "").strip()
WINDOWMIN = int((os.getenv("POST_WINDOW_MIN") or "1440").strip())   # 既定24h
MAX_POSTS = int((os.getenv("MAX_POSTS") or "30").strip())           # 既定30件/実行
DRY_RUN   = (os.getenv("DRY_RUN") or "").lower() in ("1","true","yes","on")

if not FEED_URLS or not WEBHOOK:
    print("FEED_URLS / SLACK_WEBHOOK_URL が未設定です。", file=sys.stderr)
    sys.exit(1)

def strip_html(s: str) -> str:
    if not s: return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;?", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def post_to_slack(text: str) -> bool:
    """Slackにプレーンテキストを投稿。失敗時はstderrに詳細を出す。"""
    try:
        resp = requests.post(WEBHOOK, json={"text": text}, timeout=20)
        if 200 <= resp.status_code < 300:
            return True
        print(f"Slack post failed: {resp.status_code} {resp.text}", file=sys.stderr)
    except Exception as e:
        print(f"Slack post error: {e}", file=sys.stderr)
    return False

def parse_pubdate(entry: Dict[str, Any]) -> Optional[datetime]:
    # feedparserが用意する time.struct_time 優先
    for key in ("published_parsed","updated_parsed"):
        t = getattr(entry, key, None) if hasattr(entry, key) else entry.get(key)
        if t:  # struct_time -> datetime (UTC 前提)
            return datetime(*t[:6], tzinfo=UTC)
    # 文字列日付を解釈
    for key in ("published","updated","created"):
        s = entry.get(key)
        if not s: 
            continue
        try:
            dt = dateparser.parse(s)
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except Exception:
            pass
    return None

def make_item_text(entry: Dict[str, Any]) -> str:
    title   = entry.get("title") or "(no title)"
    link    = entry.get("link") or ""
    summary = strip_html(entry.get("summary") or entry.get("description") or "")
    txt = f"*New:* {title}\n{link}"
    if summary:
        txt += f"\n{summary[:300]}{'…' if len(summary) > 300 else ''}"
    return txt

def main() -> int:
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=WINDOWMIN)
    feeds = [u.strip() for u in FEED_URLS.split(",") if u.strip()]

    total_posted = 0
    debug_lines = []
    err_snippets = []

    header = (
        f"[DEBUG] Feed scan summary\n"
        f"- now(UTC): {now:%Y-%m-%d %H:%M}\n"
        f"- window  : last {WINDOWMIN} min\n"
        f"- dry_run : {DRY_RUN}\n"
        f"- max_posts: {MAX_POSTS}\n"
        f"- feeds   : {len(feeds)}"
    )
    debug_lines.append(header)

    for idx, url in enumerate(feeds, 1):
        stats = {
            "total": 0,
            "in_window": 0,
            "posted": 0,
            "skipped_no_date": 0,
            "skipped_old": 0,
            "errors": 0
        }
        try:
            feed = feedparser.parse(url)
            entries = feed.entries or []
            stats["total"] = len(entries)

            for entry in entries:
                pub = parse_pubdate(entry)
                if not pub:
                    stats["skipped_no_date"] += 1
                    continue
                if pub < cutoff:
                    stats["skipped_old"] += 1
                    continue

                stats["in_window"] += 1
                if total_posted >= MAX_POSTS:
                    # 上限に達したら投稿は打ち切るがカウントは継続
                    continue

                text = make_item_text(entry)
                ok = True
                if not DRY_RUN:
                    ok = post_to_slack(text)
                    time.sleep(0.3)  # スパム防止
                if ok:
                    stats["posted"] += 1
                    total_posted += 1

        except Exception as e:
            stats["errors"] += 1
            err_snippets.append(f"- {url} -> {repr(e)}")
            traceback.print_exc()

        # 各フィードのサマリ行
        debug_lines.append(
            f"{idx}) {url}\n"
            f"   result: total={stats['total']}, "
            f"in_window={stats['in_window']}, posted={stats['posted']}, "
            f"skipped(no_date={stats['skipped_no_date']}, old={stats['skipped_old']}), "
            f"errors={stats['errors']}"
        )

    # まとめをSlackへ常に送信（DRY_RUN中も送る）
    debug_lines.append(f"\n[DEBUG] posted(total) = {total_posted}")
    if err_snippets:
        debug_lines.append("\n[DEBUG] errors:")
        debug_lines.extend(err_snippets)

    post_to_slack("\n".join(debug_lines))

    # 進捗を標準出力にも
    print("\n".join(debug_lines))
    return 0

if __name__ == "__main__":
    sys.exit(main())
