# Weibo seed investigation

`weibo-investigate` turns one known public Weibo post into a small, auditable research corpus with contextual metrics.

This workflow is intentionally different from keyword search. Search is useful for discovery; seed investigation is useful after an analyst has identified a post worth understanding in context.

## What it does

Given a numeric Weibo `mid`, an alphanumeric `bid`, or a public URL such as:

```text
https://m.weibo.cn/status/5320265912291527
https://m.weibo.cn/detail/5320265912291527
https://weibo.com/<uid>/<bid>
```

SUGAR attempts, in order:

1. canonical public status retrieval through the anonymous mobile-PWA JSON status surface;
2. if that public JSON status surface is unavailable, ordinary public `m.weibo.cn/detail/<id>` HTML retrieval and decoding of its embedded `status` object;
3. a bounded public comment sample;
4. a bounded public repost sample where Weibo exposes one;
5. a bounded recent public timeline sample for the seed author's account;
6. the original status when the seed itself is a repost and a stable original ID is exposed.

Every optional surface fails closed. A gated comment/repost/timeline route does not trigger synthetic cookies, browser credential extraction, CAPTCHA handling, device spoofing, proxy/account rotation, or risk-control bypass. The canonical seed is required; contextual surfaces are allowed to be unavailable and their status is recorded explicitly.

## Example

```bash
sugar weibo-investigate \
  'https://m.weibo.cn/status/5320265912291527' \
  --comments 100 \
  --comment-pages 5 \
  --reposts 100 \
  --repost-pages 5 \
  --author-posts 40 \
  --author-pages 2 \
  --name kai3 \
  --output ./runs/kai3
```

Outputs:

- `kai3.csv` — normalized seed, public responses, and contextual account posts
- `kai3.xlsx` — spreadsheet form of the same normalized corpus
- `kai3.metadata.json` — source/surface metadata
- `kai3.insights.json` — structured descriptive analysis
- `kai3.brief.md` — compact human-readable research brief

## What the analysis means

The structured insight layer reports:

- seed identity, text, date, author, and reported likes/comments/reposts;
- how many public comments/reposts SUGAR actually retrieved;
- retrieved-to-reported ratios, explicitly as coverage of the observable public surface rather than completeness;
- unique visible responders and available response-region counts;
- the most-engaged visible response records;
- hashtags and @mentions recurring in the retrieved seed/response/account corpus;
- recent-account baseline medians and the seed's percentile within the bounded retrieved timeline sample.

The account baseline is useful for questions such as: is this specific cultural/commercial message unusually engaging for this account compared with its recent public output? It is not a causal estimate.

## Interpretation guardrails

A Weibo comment or repost endpoint can expose only a partial public sample. Deleted/private/gated responses can be absent, pagination can be limited, and reported aggregate counts can exceed retrievable records. Therefore:

- `5 retrieved / 49 reported comments` means exactly that; it does **not** mean the five are a representative 10.2% sample;
- a high like/comment/repost percentile relative to an account's recent retrieved timeline indicates unusual observable engagement, not persuasion or influence;
- SUGAR does not infer sentiment from a handful of comments;
- region strings are user/platform metadata and should be treated as descriptive, not verified residence;
- repost lists are treated as flat public response samples unless Weibo supplies an explicit relationship. SUGAR does not invent a diffusion tree.

## Live validation contract

The repository includes an opt-in live smoke test using the public 2026-07-13 Weibo status `5320265912291527`, a post about ANTA KAI 3 that explicitly discusses blending Chinese kite imagery with other cultural motifs. The test performs only a bounded handful of anonymous public requests and verifies that the live seed text and engagement normalize into the investigation pipeline.

Normal unit/CI tests use deterministic captured response shapes. The separate live smoke exists to detect when Weibo changes a public surface without turning the entire ordinary unit-test matrix into a network-dependent test suite.
