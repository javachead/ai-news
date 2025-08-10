import os
import time
import re
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser

# ---- 環境変数 ----
# 空や未設定でも 70 にフォールバック
WINDOWMIN = int((os.getenv("POST_WINDOW_MIN") or "70").strip())
FEED_URLS = os.getenv("FEED_URLS", "")
WEBHOOK   = os.getenv("SLACK_WEBHOOK_URL", "")
