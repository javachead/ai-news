# rss_to_slack.py  —  RSS→Slack 投稿 (デバッグ出力つき)
# 依存: requests, feedparser, python-dateutil
import os
import re
import time
import traceback
from typing import Optional, Dict, Any, Tuple

import requests
import feedparser
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser

UTC = timezone.utc

# ==== 設定（環境変数） ====
FEED_URLS = os.getenv("FEED_URLS", "").strip()                     # カンマ区切り
WEBHOOK   = os.getenv("SLACK_WEBHOOK_URL", "").strip()
WINDOWMIN = int((os.getenv("POST_WINDOW_MIN") or "70").strip())     # 既定 70分
DRY_RUN   = (os.getenv("DRY_RUN", "false").lower() == "true")       # 送信せずにログのみ

# 1回の実行での投稿上限（スパム防止）。必要なら調整可
MAX_POSTS = int((os.getenv("MAX_POSTS") or "30").strip())

# ==== ユーティリティ ====
def strip_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;?", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def parse_pubdate(entry: Dict[str, Any]) -> Optional[datetime]:
    """
    feedparser の entry から公開日時をできるだけ頑張って取り出す。
    UTC に正規化して返す。失敗したら None。
    """
    # 構造化された時間情報を優先
    for key in ("published_parsed", "updated_parsed"):
        t = getattr(entry, key, None) if hasattr(entry, key) else entry.get(key)
        if t:
            try:
                return datetime(*t[:6], tzinfo=UTC)
            except Exception:
                pass
    # 文字列からパース
    for key in ("published", "updated", "created"):
        s = entry.get(key)
        if s:
            try:
                dt = dateparser.parse(s)
                if not dt.tzinfo:
                    dt = dt.replace(tzinfo=UTC)
                return dt.astimezone(UTC)
            except Exception:
                pass
    return None

def post_to_slack(text: str) -> Tuple[bool, int, str]:
    """
    Slack に投稿。DRY_RUN の時は送信せず成功扱い。
    戻り値: (成功?, status_code, エラーテキストの先頭)
    """
    if DRY_RUN:
        return True, 0, "DRY_RUN"
    try:
        resp = requests.post(WEBHOOK, json={"text": text}, timeout=20)
        ok = 200 <= resp.status_code < 300
        return ok, resp.status_code, (resp.text or "")[:200]
    except Exception as e:
        return False, -1, f"{e.__class__.__name__}: {e}"

# ==== メイン ====
def main() -> int:
    # 入力チェック
    if not WEBHOOK:
        print("[FATAL] SLACK_WEBHOOK_URL が未設定です。Secrets を確認してください。")
        return 2
    if not FEED_URLS:
        print("[WARN] FEED_URLS が空です。処理を終了します。")
        return 0

    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=WINDOWMIN)

    print("===== CONFIG =====")
    print(f"  now(UTC):         {now.isoformat()}")
    print(f"  window minutes:   {WINDOWMIN}  → cutoff: {cutoff.isoformat()}")
    print(f"  dry-run:          {DRY_RUN}")
    print(f"  max posts/run:    {MAX_POSTS}")
    print("==================")

    feeds = [u.strip() for u in FEED_URLS.split(",") if u.strip()]
    grand_total = 0
    grand_in_window = 0
    grand_posted = 0

    for url in feeds:
        print(f"\n--- FEED: {url} ---")
        total = 0
        in_window = 0
        posted = 0
        skipped_old = 0
        skipped_no_date = 0
        skipped_error = 0

        try:
            feed = feedparser.parse(url)
            entries = feed.entries or []
            total = len(entries)
            print(f"  entries: {total}")

            for entry in entries:
                if grand_posted >= MAX_POSTS:
                    print("  [INFO] 投稿上限に達したため、以降の投稿はスキップします。")
                    break

                pub = parse_pubdate(entry)
                if not pub:
                    skipped_no_date += 1
                    continue

                # 窓内チェック
                if pub < cutoff:
                    skipped_old += 1
                    continue

                in_window += 1

                title   = entry.get("title") or "(no title)"
                link    = entry.get("link") or ""
                summary = strip_html(entry.get("summary") or entry.get("description") or "")

                text = f"*New:* {title}\n{link}"
                if summary:
                    text += f"\n{summary[:300]}{'…' if len(summary) > 300 else ''}"

                ok, status, detail = post_to_slack(text)
                if ok:
                    posted += 1
                    grand_posted += 1
                    print(f"  [POSTED] {status}  {title[:60]}")
                    time.sleep(0.3)  # スパム防止
                else:
                    skipped_error += 1
                    print(f"  [ERROR] status={status} detail={detail}")

        except Exception:
            print("  [EXCEPTION] feed parsing error")
            traceback.print_exc()
            skipped_error += 1

        grand_total += total
        grand_in_window += in_window

        print(f"  result: total={total}, in_window={in_window}, posted={posted}, "
              f"skipped(no_date={skipped_no_date}, old={skipped_old}, error={skipped_error})")

    print("\n===== SUMMARY =====")
    print(f"  feeds: {len(feeds)}")
    print(f"  total entries:     {grand_total}")
    print(f"  window-matched:    {grand_in_window}")
    print(f"  posted:            {grand_posted} (dry-run={DRY_RUN})")
    print("===================")
    # GitHub Actions のログで見つけやすく
    print(f"Posted: {grand_posted}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
