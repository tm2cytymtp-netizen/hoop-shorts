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

### Photos and clips in every video (owner request, from 2026-11-29)
Every video uses licensed media when Wikimedia Commons is reachable (the runner checks automatically,
`HOOP_PHOTOS=auto`; it prints "licensed photos/clips: ON"):
* Player photos appear automatically on `big_number` (when its source is a player), `all_time_rank` rows,
  `head_to_head`, `comeback_card`.
* Every `hype_text` scene gets `chart.players` (2–4 names whose faces pop in) and `chart.broll` (a Commons
  search like "basketball game", "basketball dunk", "basketball arena crowd"). The clip is blurred background
  motion only. Never present it as a specific player or game.
* The runner adds every photo/clip credit to the YouTube description (CC BY / BY-SA licences require it).
* After rendering, open 2–3 frames with photos and check each face is plausibly the named player. Look up the
  Commons file title in the run log. If a photo looks wrong (a different person, a logo or a crowd), set
  `HOOP_PHOTOS=off` for that video rather than risk the wrong face.
* **No NBA game footage or highlight clips, ever**: broadcast footage is copyrighted (Content ID claims,
  strikes). The licensed Commons b-roll is the "clips" part.

Sunday is the flashiest video of the week: 7–9 scenes, mostly motion charts, all with photos.

## 3. Research rules (hard)
* Every number on screen or in narration comes from a source fetched **today**: Basketball-Reference first
  (player pages, league per-game page, leaders pages), Wikipedia/AP/ESPN for news facts. Cross-check
  anything surprising against a second source.
* Season stats are live: label them "through <date>" and say "so far" when the season is in progress.
* No fabricated quotes, no predictions stated as fact, no rumours as fact.
* No NBA game footage, broadcast clips, logos, or music (copyright, Content ID strikes). No AI images or
  likenesses of real players. Player visuals = team-colour badges (or Wikimedia Commons photos with
  attribution if that domain is reachable). No impersonating real broadcasters.

## 3b. The first 2 seconds (owner rule, every video)
Viewers decide to swipe in about 2 seconds, so **don't open on a bare number** ("Luka is averaging 36.6...").
Open with a high-stakes hook or a visual question that makes them need the answer, and keep it true:
* "Only TWO players in NBA history have scored like this..."
* "Luka is doing something even Kobe never did."
* "This hasn't happened since 1974."
The number comes in the next sentence as the payoff. The scene 1 `hype_text` should be a short question or
claim (≤6 words), with faces (`players`) and b-roll, so the very first frame already has a face and motion.
Every hook still has to be backed by a claim in SRC (check "only", "never" and "first" especially hard).

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
