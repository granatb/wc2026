# evmax v2 — Editorial article engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`. Visual target is the approved concept at `dist/design/v2.html` — open it; the generated pages must match that look.

**Goal:** Turn the evmax static site into a feed of auto-generated, reasoning-rich articles (LLM-written prose grounded in engine numbers) in a modern-editorial design, with a featured-article landing + article feed, richer stats (incl. EV/$), and a hero pitch viz — keeping all JSON/`llms.txt`/schema plumbing.

**Architecture:** Builds on the existing `evmax/{articles,render,build}.py`. New `evmax/writer.py` generates prose (cached file → Claude API → templated fallback). `render.py` is restyled to the v2 editorial system and gains an article page (prose + viz + table), a pitch SVG, and a landing (featured + feed). `build.py` orchestrates prose generation, the richer stat columns, the EV/$ article, and the landing.

**Tech Stack:** Python 3 stdlib + `anthropic` SDK (optional, only for live prose; guarded import). Tests `unittest`. Visual reference: `dist/design/v2.html`.

---

## File structure
- Create `evmax/writer.py` — prose generation + caching + prompt. Pure-ish (network only in the API tier).
- Create `evmax/prompts.py` — the article prompt template (kept separate so it's easy to tune).
- Modify `evmax/render.py` — v2 design system, `article_page` (prose), `pitch_svg`, `ev_bar`, `landing_page` (replaces `hub_page` usage; keep `hub_page` deleted or aliased), `feed_card`, Article schema.
- Modify `evmax/build.py` — generate prose per article, richer columns incl. `value`/EV$, dedicated `efficiency` article, featured + feed landing, Article schema wiring.
- Modify `evmax/articles.py` — add `EFFICIENCY` article (EV/$), ensure all stat fields exposed; add `formation_of(xi)` helper for the pitch.
- Create `data/articles/round-3/*.md` — seeded launch prose (hand-authored, same style as `dist/design/v2.html`).
- Tests: `tests/test_site_writer.py`, extend `tests/test_site_render.py`, `tests/test_site_articles.py`.

Article slugs (v2): `captains` (featured), `best-xi`, `differentials`, `efficiency` (EV/$), `high-ceiling-xi`, `blowout-transfers`.

---

## Task 1: writer.py — prose generation, tiered + cached

**Files:** Create `evmax/writer.py`, `evmax/prompts.py`; Test `tests/test_site_writer.py`.

Prose object shape (the contract render.py consumes):
```python
{"headline": str, "standfirst": str, "body_html": str, "bottom_line": str, "source": "cache|llm|template"}
```

- [ ] **Step 1 — failing test (cache + template tiers, no network):**
```python
import os, tempfile, unittest
from evmax import writer

ENTRIES = [{"rank":1,"name":"Kane","team":"England","position":"FWD","x_points":9.16,
            "captain_ev":18.31,"ceiling":13.55,"price":10.5,"value":0.872,"ownership_pct":38.6}]

class WriterTest(unittest.TestCase):
    def test_template_fallback_is_grounded_and_safe(self):
        p = writer.article_prose("captains", 3, ENTRIES, ["captain_ev","x_points","ownership_pct"],
                                 cache_dir="/nonexistent", use_llm=False)
        self.assertEqual(p["source"], "template")
        self.assertIn("Kane", p["headline"] + p["standfirst"] + p["body_html"])
        self.assertIn("18.3", p["body_html"])               # real number woven in
        self.assertTrue(p["bottom_line"])

    def test_cache_tier_wins_when_present(self):
        d = tempfile.mkdtemp()
        os.makedirs(f"{d}/round-3", exist_ok=True)
        open(f"{d}/round-3/captains.md","w").write(
            "# Back Kane\n\n> Safe armband.\n\nKane leads at 18.31.\n\n**Bottom line:** hold Kane.\n")
        p = writer.article_prose("captains", 3, ENTRIES, ["captain_ev"], cache_dir=d, use_llm=False)
        self.assertEqual(p["source"], "cache")
        self.assertEqual(p["headline"], "Back Kane")
        self.assertIn("Bottom line", p["body_html"] + p["bottom_line"])
```
- [ ] **Step 2 — run, expect fail** (`writer` missing): `python3 -m unittest tests.test_site_writer -v`
- [ ] **Step 3 — implement** `evmax/writer.py`:
  - `article_prose(article, round_no, entries, columns, cache_dir="data/articles", use_llm=True)`:
    1. If `cache_dir/round-<n>/<article>.md` exists → parse it (`# H1` → headline; `> ` line → standfirst; `**Bottom line:** …` → bottom_line; remaining markdown → `body_html` via a tiny md→p/h2/blockquote converter) → `source="cache"`.
    2. Elif `use_llm` and `ANTHROPIC_API_KEY` set and `anthropic` importable → call the API (Task 1b), write result to cache, `source="llm"`.
    3. Else → `_template(article, entries, columns)` deterministic prose (per-article sentence templates weaving in `entries[0]` + a couple of runners-up, all numbers via the same `_fmt` rules) → `source="template"`.
  - Keep the md→html converter tiny and escape data values.
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit:** `feat(site): writer.py — tiered (cache/llm/template) article prose`

### Task 1b: the Claude API tier
- [ ] In `evmax/prompts.py`, define `ARTICLE_PROMPT` — a template that receives the article slug, round, and a JSON block of the *exact* entries, and instructs: write a tight analytical article (headline, one-line standfirst, 3–5 short paragraphs with a pull-quote and a "Bottom line"); **use only the supplied numbers, cite them, invent no stats, no players not in the list**; return strict JSON `{headline, standfirst, body_markdown, bottom_line}`.
- [ ] In `writer.py`, `_llm_prose(...)`: `import anthropic` (guarded), model `claude-haiku-4-5-20251001` (cheap; fast — fine for short grounded prose), `max_tokens` ~900, temperature 0.4; parse the JSON; **validate grounding**: every number token in the output must appear in the input entries (reject + fall back to template if a fabricated figure or off-list player name is detected). Cache on success.
- [ ] Test (skipped if no key): assert that when `use_llm=True` but no key, it cleanly falls to template (no crash).

---

## Task 2: articles.py — EV/$ efficiency article + formation helper
**Files:** Modify `evmax/articles.py`; Test `tests/test_site_articles.py`.
- [ ] Test: `efficiency(rows)` returns rows ranked by `value` (xPts ÷ price) desc with `rank`, only `price`-bearing rows (reuse `rank_value` semantics; this is the public name for the EV/$ article). `formation_of(xi)` returns a string like `"3-4-3"` from a list of rows by counting DEF/MID/FWD.
- [ ] Implement `efficiency = rank_value` alias plus `formation_of(xi)`. Commit.

---

## Task 3: render.py v2 — design system + pitch + bar
**Files:** Modify `evmax/render.py`; Test `tests/test_site_render.py`.
Visual target: `dist/design/v2.html` (reproduce its CSS variables, fonts, and component styles — Hanken Grotesk + Newsreader, light surfaces, green accent, red differential).
- [ ] Replace `_STYLE`/`_FONTS` with the v2 system from `dist/design/v2.html`.
- [ ] `pitch_svg(xi_entries)` — SVG football pitch placing the XI by position (GK/DEF/MID/FWD lines), each node showing surname + xPts, captain flagged; formation auto-derived. Test: returns `<svg`, contains 11 player surnames, marks the top entry captain.
- [ ] `ev_bar(entries, metric)` — horizontal bars (reuse/replace `svg_bar_chart`) styled to v2; top entry in green, differentials in red. Keep `svg_bar_chart` name/signature for back-compat OR update its tests.
- [ ] Test the design system is applied: generated `article_page` contains `Hanken+Grotesk` (font link) and the v2 class names.
- [ ] Commit.

---

## Task 4: render.py v2 — article page (prose) + landing (featured + feed)
**Files:** Modify `evmax/render.py`; Test `tests/test_site_render.py`.
- [ ] `article_page(round_no, article, title, prose, entries, columns, nav, json_url, viz_html)`:
  - Header (logo + nav with `soon` Tools items), kicker, `prose["headline"]`, `prose["standfirst"]`, byline, `viz_html`, `prose["body_html"]`, pull-quote (from prose), the ranked table (richer columns), bottom-line, method + JSON link.
  - `<head>`: keep `rel="alternate"` JSON link + `Dataset` JSON-LD; ADD `Article` JSON-LD (`headline`, `datePublished`=generated_at, `author`/`publisher` = evmax, `articleBody` summary). Tests must still find: `<!doctype html>`, `application/ld+json`, the top player name, a real number, `rel="alternate"`, a nav title, `Monte-Carlo`.
- [ ] `landing_page(round_no, featured, feed, nav)` — featured block (kicker, headline, standfirst, byline, featured viz) + a feed grid of `feed_card`s (kicker, headline, teaser, key stat, link). Replaces `hub_page`. Test: contains the featured headline, at least 3 feed headlines, and links `/round/<n>/<slug>/`.
- [ ] `feed_card(slug, round_no, headline, teaser, stat_value, stat_label)`.
- [ ] Commit.

---

## Task 5: build.py v2 — orchestrate prose, richer columns, landing, schema
**Files:** Modify `evmax/build.py`.
- [ ] Add `efficiency` to the article map (columns `["value","x_points","price","captain_ev"]`); enrich every article's `columns` to the richer stat set where sensible (primary metric first).
- [ ] For each article: `prose = writer.article_prose(slug, round, entries, columns, use_llm=…)`; choose `viz_html = render.pitch_svg(entries)` for XI articles else `render.ev_bar(entries, columns[0])`; pass `prose` + `viz_html` into `render.article_page`.
- [ ] Featured = `captains`. Build `landing_page(round, featured=…, feed=[other articles with prose headline+standfirst+key stat])` → write to `/index.html` and `/round/<n>/index.html`.
- [ ] Add `--no-llm` flag (forces template tier; default tries cache→llm→template). Keep `/api/...`, `llms.txt`, `robots.txt`, `sitemap.xml` unchanged.
- [ ] Smoke: `python3 -m evmax.build --round 3 --sims 200 --no-llm --out /tmp/evmax_v2` → 6 articles + landing render; grep landing for featured headline + feed cards; open an article, confirm prose + pitch present.
- [ ] Commit.

---

## Task 6: seed Round-3 launch prose + production build
**Files:** Create `data/articles/round-3/*.md`.
- [ ] Author six `data/articles/round-3/<slug>.md` files in the `dist/design/v2.html` style (headline `#`, standfirst `>`, body, `**Bottom line:**`), grounded in the current 50k numbers. (These let launch ship with high-quality prose without an API key; the API automates future rounds.)
- [ ] Full suite: `python3 -m unittest discover -s tests -t .` — all green.
- [ ] Production build: `python3 -m evmax.build --round 3 --sims 50000 --out dist` (uses the seeded cache). Verify landing + 6 articles + JSON + agent files; strip any `dist/design` before deploy.
- [ ] Commit.

---

## Self-review checklist
- Prose is **grounded**: template tier only uses supplied numbers; LLM tier validates numbers/names against entries and falls back on violation. No fabricated stats can reach a page.
- Build never hard-fails without a key (cache → template).
- Stat richness incl. EV/$ present on every article + dedicated efficiency article (user request).
- Tools tab is `soon` only (phase 2), not built.
- All v1 agent plumbing (JSON endpoints, `llms.txt`, robots, sitemap, Dataset schema) preserved; Article schema added.
