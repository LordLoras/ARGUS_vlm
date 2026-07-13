"""Browser-DOM extraction helpers for the Meta Ad Library probe."""

from __future__ import annotations

from typing import Any


def mark_candidate_cards(page: Any, *, max_cards: int) -> list[dict[str, Any]]:
    return page.evaluate(
        """
        (maxCards) => {
          const textOf = (el) => (el.innerText || el.textContent || "")
            .replace(/\\s+/g, " ")
            .trim();
          const rectOf = (el) => {
            const r = el.getBoundingClientRect();
            return {
              x: r.x + window.scrollX,
              y: r.y + window.scrollY,
              width: r.width,
              height: r.height
            };
          };
          const normalizeUrl = (value) => {
            if (!value) return "";
            try {
              return new URL(value, document.baseURI).toString();
            } catch {
              return String(value);
            }
          };
          const cssUrls = (value) =>
            Array.from(String(value || "").matchAll(/url\\(["']?([^"')]+)["']?\\)/g))
              .map((match) => normalizeUrl(match[1]))
              .filter(Boolean);
          const hasCardSignals = (text) =>
            /Library\\s+ID/i.test(text) &&
            /(Active|Inactive|Started running|Platforms)/i.test(text);
          const libraryIdCount = (text) =>
            (text.match(/Library\\s+ID/gi) || []).length;
          const leaves = Array.from(document.querySelectorAll("span, div"))
            .filter((el) => /Library\\s+ID/i.test(textOf(el)));
          const selected = [];
          const platformNames = ["Facebook", "Instagram", "Messenger", "Audience Network", "Threads"];

          for (const leaf of leaves) {
            let el = leaf;
            let best = null;
            for (let depth = 0; depth < 12 && el; depth += 1, el = el.parentElement) {
              const text = textOf(el);
              const rect = el.getBoundingClientRect();
              if (
                hasCardSignals(text) &&
                libraryIdCount(text) === 1 &&
                rect.width >= 280 &&
                rect.height >= 110 &&
                rect.height <= 1800
              ) {
                best = el;
              }
            }
            if (!best) continue;

            let duplicate = false;
            for (let i = selected.length - 1; i >= 0; i -= 1) {
              const existing = selected[i];
              if (existing === best || existing.contains(best)) {
                duplicate = true;
                break;
              }
              if (best.contains(existing)) selected.splice(i, 1);
            }
            if (!duplicate) selected.push(best);
            if (selected.length >= maxCards) break;
          }

          return selected.map((card, index) => {
            card.setAttribute("data-argus-meta-ad-card", String(index));
            const links = Array.from(card.querySelectorAll("a"))
              .map((a) => ({ text: textOf(a), href: a.href || "" }))
              .filter((a) => a.href || a.text);
            const imageSources = Array.from(card.querySelectorAll("img"))
              .map((img) => {
                const rect = img.getBoundingClientRect();
                return {
                  src: normalizeUrl(img.currentSrc || img.src || ""),
                  area: Math.max(
                    (img.naturalWidth || 0) * (img.naturalHeight || 0),
                    (img.width || 0) * (img.height || 0),
                    rect.width * rect.height
                  )
                };
              })
              .filter((item) => item.src)
              .sort((left, right) => right.area - left.area)
              .map((item) => item.src);
            const videos = Array.from(card.querySelectorAll("video"));
            const videoSources = videos
              .flatMap((video) => [
                video.currentSrc || "",
                video.src || "",
                ...Array.from(video.querySelectorAll("source")).map((source) => source.src || "")
              ])
              .map(normalizeUrl)
              .filter(Boolean);
            const videoPosters = videos
              .map((video) => video.poster || "")
              .map(normalizeUrl)
              .filter(Boolean);
            const backgroundImageSources = Array.from(card.querySelectorAll("*"))
              .flatMap((el) => cssUrls(window.getComputedStyle(el).backgroundImage));
            const platformLabels = Array.from(card.querySelectorAll("[aria-label], [title], img[alt]"))
              .flatMap((el) => [el.getAttribute("aria-label"), el.getAttribute("title"), el.getAttribute("alt")])
              .filter(Boolean)
              .filter((value) => platformNames.some((name) => value.toLowerCase().includes(name.toLowerCase())));
            return {
              index,
              text: textOf(card),
              links,
              image_sources: imageSources,
              video_sources: videoSources,
              video_posters: videoPosters,
              background_image_sources: backgroundImageSources,
              platform_labels: platformLabels,
              video_count: videos.length,
              rect: rectOf(card)
            };
          });
        }
        """,
        max_cards,
    )


def visible_library_ids(page: Any) -> list[str]:
    return page.evaluate("""
        () => Array.from(document.body.innerText.matchAll(/Library\\s+ID[:\\s]*([0-9]+)/gi))
          .map((match) => match[1])
        """)
