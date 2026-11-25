# Daily run: one fact-checked NBA stats Short a day for umbr3off

This file is the standing instruction for the scheduled daily run. The owner asked for one Short every day,
made and posted automatically and **public** (owner's choice, 2026-11-25). Posting is done by the owner's own
Zap ("Hoop Shorts: feed → YouTube"), which uploads every new `feed.xml` item publicly. **Adding an item to
`feed.xml` and pushing therefore publishes the video.** Only do that when every check below has passed.

## 0. Setup (fresh session)
```bash
git clone https://github.com/tm2cytymtp-netizen/hoop-shorts /home/claude/hoop-shorts   # or use the attached repo
cd /home/claude/hoop-shorts
pip install -r backend/requirements.txt --break-system-packages -q
which ffmpeg || (apt-get update -qq && apt-get install -y -qq ffmpeg)
```
The runner downloads the Kokoro voice model from GitHub on first use.

## 1. Should today run?
* Date in America/Rankin_Inlet (Central). **Skip** these dates (videos already scheduled by hand):
  2026-11-26, 2026-11-27, 2026-11-28.
* Skip if `feed.xml` already has an item whose guid starts with today's date.

### Prepared episodes
If `daily/episodes/<today's date>-*.py` already exists, it was prepared in advance with older data (its
docstring says what to refresh). Use it as the plan, but **re-fetch every number and claim today**: update
SRC, the narration, claims, `THRU` date and description to match today's sources (add anything new, e.g.
another 50-point game, and keep the video 30–55 s). Then continue at step 5. Never publish it unrefreshed.

## 2. Today's format (weekly rhythm)
| Day | Format | Slot (Central) |
|---|---|---|
| Mon | Weekend standouts in the numbers | 3:00 pm |
| Tue | Head-to-head comparison (2–3 players, one question) | 3:00 pm |
| Wed | Breakout or slump: this season vs last season | 3:00 pm |
| Thu | History / GOAT-style debate by the numbers | 3:00 pm |
| Fri | Storyline: injury, trade, streak, milestone in the news | 3:00 pm |
| Sat | Top-5 ranking (with an all-time or league context) | 12:00 pm |
| Sun | Week in numbers: the week's biggest stat lines and leaders, extra-flashy | 12:00 pm |

Pick the most timely topic that fits the format (search today's NBA news). Avoid repeating a player who led
one of the last 3 videos unless the news demands it.

### Sunday extras (owner request)
Sunday's "week in numbers" should be the flashiest video of the week: 8–9 scenes, mostly motion charts
(`hype_text`, `all_time_rank`, `head_to_head`, `season_bars`), a `look` with the week's top team colours.
Real player **photos**: test `curl -sI https://upload.wikimedia.org` first. If it answers, run the renderer with
`HOOP_NO_PHOTOS=0` so licensed Wikimedia Commons photos are used (credit them in the description as
"Photos: Wikimedia Commons (<licence>)"). If it doesn't answer, team badges are used; say nothing about it.
**No game footage or highlight clips**: NBA broadcast footage is copyrighted and would get Content ID claims
or strikes on the channel. Never download or include it, even short clips.

## 3. Research rules (hard)
* Every number on screen or in narration comes from a source fetched **today**: Basketball-Reference first
  (player pages, league per-game page, leaders pages), Wikipedia/AP/ESPN for news facts. Cross-check
  anything surprising against a second source.
* Season stats are live: label them "through <date>" and say "so far" when the season is in progress.
* No fabricated quotes, no predictions stated as fact, no rumours as fact.
* No NBA game footage, broadcast clips, logos, or music (copyright, Content ID strikes). No AI images or
  likenesses of real players. Player visuals = team-colour badges (or Wikimedia Commons photos with
  attribution if that domain is reachable). No impersonating real broadcasters.

## 4. Write the episode
Create `daily/episodes/YYYY-MM-DD-<slug>.py` with the same shape as `daily/episodes/_example_luka.py`:
`SRC` (every number the video shows), `SCRIPT` (scenes with narration, visual, claims), `META`
(title, description, tags), `FORMAT`, `PLAYERS`.
* 30–55 s of narration, 6–9 scenes, hook first, one clear question at the end (either/or questions get more
  comments, e.g. "Luka or Jordan? Pick one 👇").
* Chart types (data-linked; renderer reads numbers from SRC): `hype_text`, `all_time_rank` (L# source),
  `head_to_head` (2–5 players, career or `season`), `tally`, `comeback_card` (tone positive/injury,
  before_head/after_head), `season_bars`, `line_compare`, `big_number`, `slope`, `leaderboard`.
* `SCRIPT["look"] = {"team": "<main team>", "watermark": "<jersey number>"}` tints the animated background.
* Description: 1–2 sentence summary, the question, "Stats: Basketball-Reference, through <date>.", 3–5 hashtags
  including #NBA and #Shorts. Title ≤ 70 chars, no clickbait that the video doesn't pay off.
* Names: check pronunciation with `kokoro_onnx.tokenizer.Tokenizer().phonemize(name, "en-us")`; add
  respellings or `/ipa/` to `SCRIPT["pronunciations"]` (global defaults live in backend/app/settings_store.py).

## 5. Render and check
```bash
python daily/runner.py daily/episodes/<file>.py --no-publish
```
Must print `FACT CHECK: n / n` and `QC PASSED 22/22`. Then pull 6–8 frames with ffmpeg into a contact sheet
and **look at it**: no text overlapping captions, numbers readable, nothing cut off. Fix and re-render if not.

## 6. Publish (only if everything passed)
```bash
rm videos/<file>.mp4      # the --no-publish copy
python daily/runner.py daily/episodes/<file>.py   # renders again and adds the feed item
git add videos feed.xml daily/episodes && git commit -m "Daily Short: <title>" && git push
```
Time it so the push lands within ~15 minutes before the slot (the Zap checks the feed every ~15 min).
Verify `https://raw.githubusercontent.com/tm2cytymtp-netizen/hoop-shorts/main/feed.xml` shows the new item.

## 7. If anything fails
Do **not** publish. Tell the owner in one or two sentences what failed and why (failed check, a number
you couldn't verify, render error). A skipped day is better than a wrong stat.
