# Hoops Shorts: automated basketball meme & Shorts studio (free stack)

Every day this app finds trending basketball topics and writes original memes and Shorts. It renders them as fast-paced vertical videos with big captions, punch zooms, sound-effect hits and music, quality-checks them, and posts them publicly to YouTube on a schedule. You get a dashboard to watch, approve or tweak everything.

**Default schedule:** 3 Shorts a day (11:00, 15:00, 19:00). Automatic mode publishes only Shorts that pass every check.

## What it makes (formats A–G)

| Format | What you get | Where the facts come from |
|---|---|---|
| **meme** | Top/bottom-text memes, "POV:" reaction memes, punchline cards; usually text-only with music + SFX | Jokes about situations; no facts claimed |
| **comparison** | Player-vs-player animated stat card (numbers count up, winners turn green) + commentary | Cited sources, shown on screen |
| **fact** | One wild stat or record, built up and paid off | Cited sources |
| **storyline** | "Nobody's talking about…" with real scores and numbers | BALLDONTLIE game data + sources |
| **ranking** | "#3 … #2 … #1" countdown reveals | Real if it claims to be real |
| **hypothetical** | "What if…" clearly framed as imagination | None needed |
| **news_reaction** | Real news, then the funny take | Verified sources, dated |

The **Meme Studio** lets you generate meme ideas, render them as images, and turn any of them into a Short with one click.

## The rules it follows (and why)

- **No ripped footage, no copyrighted songs.** NBA broadcasts and other creators' videos get matched by Content ID (claims, blocks, strikes), and reposted clips count as "reused content", which can't be monetized. Real footage comes from **My Clips**, where you upload footage you shot or licensed. The upload form refuses anything labelled as broadcast footage.
- **No AI images of real players.** AI art shows fictional cartoon hoopers. Real players appear only through **freely licensed Wikimedia Commons photos** (credited on screen) or stat cards.
- **No made-up stats, scores or quotes.**
  - Every factual claim must cite a source, and the fact-checker verifies it.
  - Scoreboard numbers come straight from the data API, never from the AI. A scoreboard pointing at a game that isn't in the data is refused.
  - Quotes must appear word-for-word in a source.
- **No impersonation or harassment.** Jokes target plays and situations. The QC editor flags anything that puts words in a real player's mouth.
- **Trending songs:** these can only be added legally inside the YouTube app, from its licensed Shorts library. When a Short would suit one, the dashboard says so. Use the weekly pack for that Short and add the song when you upload it from your phone. Everything else uses the built-in original beat, original synthesised SFX (whoosh, boom, buzzer, airhorn…), or tracks you add from the YouTube Audio Library.
- **Real NBA footage later:** the NBA runs a creator program that gives select creators licensed game footage. Apply once the channel has traction.

## The free stack ($0/month)

| Job | Service | Notes |
|---|---|---|
| Ideas, scripts, jokes, fact-check | Google **Gemini** free tier | Key: aistudio.google.com/apikey |
| Facts & stats | Wikipedia (free) | Paid upgrade: Claude + live web search |
| Scores & games | **BALLDONTLIE** free account | 5 requests/min; the free tier has no per-player box scores |
| Trend signals | ESPN + Google News RSS; YouTube search (optional free API key) | Headlines are leads, never facts |
| Cartoon images | **Cloudflare Workers AI** (FLUX schnell), 10,000 neurons/day free | About 60 neurons per image |
| Player photos | Wikimedia Commons (CC0 / CC BY / CC BY-SA) | Attribution added automatically |
| Voices | **Kokoro**, running on your computer | 5 styles: commentator, meme narrator, Gen Z, analyst, documentary |
| Music & SFX | Original generated beat + SFX; add your own licensed tracks | — |
| Posting | **Zapier free plan**: 100 posts/month (each post = 1 task) | 3/day fits; 4–5/day needs a paid Zapier plan or the weekly pack |
| Hosting | Your computer + free Cloudflare Tunnel | The computer must stay on |

## Setup (about 30 minutes)

1. `cp .env.example .env` and fill in the following:
   - `GEMINI_API_KEY`
   - `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` (use the token template **"Workers AI"**)
   - `BALLDONTLIE_API_KEY`
   - `DASHBOARD_PASSWORD`
2. Run `docker compose up -d --build`, then open http://localhost:8000 and sign in.
3. Run `cloudflared tunnel --url http://localhost:8000`, put the `https://…` address it prints into `PUBLIC_BASE_URL`, and restart.
4. In Zapier, create a Zap: **RSS by Zapier → New Item in Feed** (the feed URL is shown in Settings) → **YouTube → Upload Video**. Map Link → Video, Title, Description; set Privacy to Public, Category to Sports, Made for kids to No.
5. Settings → Channel → paste your `youtube_channel_id` (it starts with `UC`). This confirms each post and tracks views.
6. `cd backend && python check_connections.py` tests every service. It creates a sample narrator clip, a test image and a test photo lookup.

**Other platforms:** every Short also gets ready-made TikTok, Instagram and Facebook captions. Copy them from the Short's Metadata tab, or find them in the weekly pack. Posting automatically to TikTok or Instagram needs each platform's approved developer access: TikTok's Content Posting API audit, and an Instagram Business account with Meta app review. Until you have that, post them manually.

## Dashboard

| Page | What it's for |
|---|---|
| Overview | Today's top ideas, ready Shorts, schedule, spend |
| Idea Generator | Ideas scored on popularity, interest, entertainment, relevance, originality and timeliness |
| Meme Studio | Generate, render and convert memes |
| Video Production | The live pipeline and job queue |
| Video Library | Each Short with its script, sources, scenes, licence ledger, 3 titles, platform captions and covers |
| My Clips | Upload footage you have rights to |
| Content Calendar | The schedule, plus a weekly pack download |
| Analytics | Public views and likes, or full YouTube Analytics via the `youtube_api` method |
| Settings | Everything else |

## Tests

```bash
cd backend
python -m pytest -q tests/test_logic.py   # research → script → fact-check/revision, budget pause, publish guards
python -m pytest -s tests/test_hoops.py   # renders a text-only meme Short + a narrated storyline Short with a
                                          # real-data scoreboard (real Kokoro voice), full QC; rejects fake scores
```

## Known limitations

- **Comedy quality depends on the model.** Gemini's free tier is decent, Claude is funnier. Review the first week manually (`approval_mode: manual`) and use the Meme Studio to steer it.
- **Basic stats only for free.** BALLDONTLIE's free tier covers games and scores; per-player stats come from Wikipedia. BALLDONTLIE's paid tier adds box scores and season averages.
- **Caption timing is estimated.** Kokoro doesn't return word timings, so karaoke captions are timed per sentence. ElevenLabs gives exact timing.
- **Shorts covers can't be uploaded through Zapier.** The app makes cover options; YouTube picks a frame unless you set one in the YouTube app.
