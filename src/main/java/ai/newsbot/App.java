package ai.newsbot;

import com.google.gson.Gson;
import com.google.gson.annotations.SerializedName;
import com.rometools.rome.feed.synd.SyndEntry;
import com.rometools.rome.io.SyndFeedInput;
import com.rometools.rome.io.XmlReader;
import okhttp3.*;
import java.io.*;
import java.net.URL;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.stream.Collectors;

/**
 * RSSの新着だけをSlackに投稿する最小実装
 * 環境変数:
 *   FEED_URLS        カンマ区切りRSS (例: https://rss.beehiiv.com/feeds/XXXX.xml)
 *   SLACK_WEBHOOK_URL SlackのIncoming Webhook URL
 *   DEDUP_FILE        既読ID保存ファイル (省略可、デフォルト .seen.db)
 */
public class App {
  private static final Gson GSON = new Gson();

  public static void main(String[] args) throws Exception {
    String feedUrlsEnv = System.getenv("FEED_URLS");
    String webhook = System.getenv("SLACK_WEBHOOK_URL");
    String dedupFile = Optional.ofNullable(System.getenv("DEDUP_FILE")).orElse(".seen.db");

    if (feedUrlsEnv == null || webhook == null) {
      System.err.println("FEED_URLS と SLACK_WEBHOOK_URL を設定してください。");
      System.exit(1);
    }

    Set<String> seen = loadSeen(dedupFile);
    OkHttpClient http = new OkHttpClient();

    List<String> feeds = Arrays.stream(feedUrlsEnv.split(","))
                               .map(String::trim).filter(s -> !s.isEmpty())
                               .collect(Collectors.toList());

    int posted = 0;
    for (String feedUrl : feeds) {
      try (XmlReader reader = new XmlReader(new URL(feedUrl))) {
        var feed = new SyndFeedInput().build(reader);
        for (SyndEntry e : feed.getEntries()) {
          String id = e.getUri() != null ? e.getUri() :
                      e.getLink() != null ? e.getLink() : e.getTitle();

          if (id == null || seen.contains(id)) continue;

          // 投稿本文
          String title = Optional.ofNullable(e.getTitle()).orElse("(no title)");
          String link = Optional.ofNullable(e.getLink()).orElse("");
          String summary = e.getDescription() != null ? e.getDescription().getValue() : "";

          String text = "*New:* " + title + "\n" + link;
          if (!summary.isBlank()) {
            text += "\n" + truncate(strip(summary), 280);
          }

          // SlackへPOST
          SlackPayload payload = SlackPayload.simple(text);
          Request req = new Request.Builder()
              .url(webhook)
              .post(RequestBody.create(GSON.toJson(payload),
                    MediaType.parse("application/json; charset=utf-8")))
              .build();
          try (Response res = http.newCall(req).execute()) {
            if (!res.isSuccessful()) {
              System.err.println("Slack post failed: " + res.code() + " " + res.message());
            } else {
              seen.add(id);
              posted++;
            }
          }
        }
      }
    }

    saveSeen(dedupFile, seen);
    System.out.println("Posted: " + posted);
  }

  static class SlackPayload {
    @SerializedName("text") String text;
    SlackPayload(String t) { this.text = t; }
    static SlackPayload simple(String t) { return new SlackPayload(t); }
  }

  private static String strip(String html) {
    return html.replaceAll("<[^>]*>", "").replaceAll("&nbsp;", " ").trim();
  }

  private static String truncate(String s, int max) {
    return s.length() <= max ? s : s.substring(0, max - 1) + "…";
  }

  private static Set<String> loadSeen(String path) {
    try {
      return new HashSet<>(Files.readAllLines(Path.of(path)));
    } catch (IOException e) {
      return new HashSet<>();
    }
  }

  private static void saveSeen(String path, Set<String> seen) {
    try {
      Files.write(Path.of(path), seen);
    } catch (IOException e) {
      System.err.println("Failed to save seen: " + e.getMessage());
    }
  }
}
