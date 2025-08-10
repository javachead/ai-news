package ai.newsbot;

import com.google.gson.Gson;
import com.google.gson.annotations.SerializedName;
import com.rometools.rome.feed.synd.SyndEntry;
import com.rometools.rome.io.SyndFeedInput;
import com.rometools.rome.io.XmlReader;
import okhttp3.*;

import java.io.IOException;
import java.net.URL;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.*;
import java.util.stream.Collectors;

/**
 * 指定したRSSの新着をSlackに投稿する最小実装。
 * 環境変数:
 *  - FEED_URLS (必須, カンマ区切りRSS URL)
 *  - SLACK_WEBHOOK_URL (必須)
 *  - POST_WINDOW_MIN (任意, 直近N分だけ投稿。Actionsで状態管理を省略するための重複抑制。デフォルト70)
 *
 * NOTE: 毎時実行を想定。直近70分以内に公開されたエントリのみ投稿し、重複を抑えます。
 */
public class App {

  private static final Gson GSON = new Gson();
  private static final MediaType JSON = MediaType.parse("application/json; charset=utf-8");

  public static void main(String[] args) throws Exception {
    String feedUrlsEnv = System.getenv("FEED_URLS");
    String webhook = System.getenv("SLACK_WEBHOOK_URL");
    int windowMin = parseInt(System.getenv("POST_WINDOW_MIN"), 70);

    if (feedUrlsEnv == null || feedUrlsEnv.isBlank() || webhook == null || webhook.isBlank()) {
      System.err.println("FEED_URLS と SLACK_WEBHOOK_URL を設定してください。");
      System.exit(1);
    }

    List<String> feeds = Arrays.stream(feedUrlsEnv.split(","))
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toList());

    OkHttpClient http = new OkHttpClient.Builder()
        .callTimeout(Duration.ofSeconds(20))
        .build();

    int posted = 0;
    OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
    OffsetDateTime cutoff = now.minusMinutes(windowMin);

    for (String feedUrl : feeds) {
      try (XmlReader reader = new XmlReader(new URL(feedUrl))) {
        var feed = new SyndFeedInput().build(reader);
        for (SyndEntry e : feed.getEntries()) {
          OffsetDateTime published = null;
          if (e.getPublishedDate() != null) {
            published = OffsetDateTime.ofInstant(e.getPublishedDate().toInstant(), ZoneOffset.UTC);
          } else if (e.getUpdatedDate() != null) {
            published = OffsetDateTime.ofInstant(e.getUpdatedDate().toInstant(), ZoneOffset.UTC);
          }

          // 公開時刻が分かればウィンドウ判定、無ければスキップ
          if (published == null || published.isBefore(cutoff)) continue;

          // Slack本文
          String title = Optional.ofNullable(e.getTitle()).orElse("(no title)");
          String link = Optional.ofNullable(e.getLink()).orElse("");
          String summary = e.getDescription() != null ? strip(e.getDescription().getValue()) : "";

          StringBuilder text = new StringBuilder();
          text.append("*New:* ").append(title).append("\n").append(link);
          if (!summary.isBlank()) {
            text.append("\n").append(truncate(summary, 300));
          }

          SlackPayload payload = SlackPayload.simple(text.toString());
          Request req = new Request.Builder()
              .url(webhook)
              .post(RequestBody.create(GSON.toJson(payload), JSON))
              .build();

          try (Response res = http.newCall(req).execute()) {
            if (!res.isSuccessful()) {
              System.err.println("Slack post failed: " + res.code() + " " + res.message());
            } else {
              posted++;
            }
          }
        }
      } catch (Exception ex) {
        System.err.println("Feed error: " + feedUrl + " -> " + ex.getMessage());
      }
    }

    System.out.println("Posted: " + posted);
  }

  static class SlackPayload {
    @SerializedName("text")
    String text;
    SlackPayload(String t) { this.text = t; }
    static SlackPayload simple(String t) { return new SlackPayload(t); }
  }

  private static int parseInt(String s, int def) {
    try { return s == null ? def : Integer.parseInt(s.trim()); }
    catch (NumberFormatException e) { return def; }
  }

  private static String strip(String html) {
    return html.replaceAll("<[^>]*>", "").replace("&nbsp;", " ").trim();
  }
  private static String truncate(String s, int max) {
    return s.length() <= max ? s : s.substring(0, max - 1) + "…";
  }
}
