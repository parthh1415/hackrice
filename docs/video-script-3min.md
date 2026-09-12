# Firebreak — 3:30 shooting script

**This is what you read aloud.** `video-script.md` is the long reference, and it is now largely
STALE — it was written against a single-page app and 12 of its 21 shots point at UI that no
longer exists. `docs/video-shooting-guide.md` says which. This file has been corrected against
the running app; the long script has not, beyond a banner.

Numbers verified live against the running app. If you change anything, re-check them before
recording.

**Keyboard:** `1`–`6` jump between pages, `←` `→` step the cascade, `space` plays it, `?` lists
them. Pressing a number is cleaner on camera than hunting for a nav link, and `?` for two
seconds makes the thing read as a tool rather than a web page.

---

## ACT 1 — THE QUESTION (0:00 – 0:22)

**Shot 1** · Title, then the landing screen: *Find the market move your portfolio can't survive.*

> "Every stress test asks the same question. What if the market drops twenty percent? The
> scenario is an assumption — and the assumption is the part nobody checks."

**Shot 2** · Click **Use demo portfolio**. Holdings table fills — and the last column shows
how much of each name the five modelled books hold, in days of its own volume.

> "Firebreak asks the inverse. Here's a portfolio. Twelve thousand three hundred dollars,
> five names."

---

## ACT 2 — THE BREAK (0:22 – 1:20)

**Shot 3** · Click **10%** in the limit row. (There is no Continue step — the limit buttons
sit on the same page, under the holdings.)

> "How much loss would you refuse to tolerate? Ten percent. That's the whole configuration —
> no leverage, no gamma, no jargon."

**Shot 4** · Click **Run reverse stress test**. Let the search land.

> "NVIDIA, down twenty-four point seven percent. That's the smallest single-name move that
> pushes this portfolio past a ten percent loss. Nobody guessed it. It was solved for."

**Shot 5** · Point at the four tiles, then at the table below them.

> "And here's the thing. NVIDIA falling only costs this portfolio seven point two directly.
> The loss is ten. Where did the other three points come from?"

*(the table answers it on screen: Microsoft, Amazon and Alphabet were never shocked, and each
falls several percent anyway)*

---

## ACT 3 — WHY (1:20 – 2:05)

**Shot 6** · Click **See why the loss grows**, then press **space** to play the cascade.

> "From everyone else. Crowded institutions hold the same names. NVIDIA falls, they breach
> their leverage limits, they're forced to sell — and they sell into a market where their
> positions are also *your* positions. That's the feedback. That's what turns seven into ten."

*(let a round land in silence)*

> "This is real filed data. Five hedge funds, their actual 13F holdings, forty billion dollars."

---

## ACT 4 — THE FIX AND THE PROOF (2:05 – 3:20)

**Shot 7** · Click **Find the cheapest single-position fix**.

> "Now the useful part. Reduce NVIDIA by four hundred and seventy-eight dollars. That's the
> smallest change we found that survives this exact shock — and it moves to cash, so the
> portfolio is worth the same."

**Shot 8** · Click **Check it actually helped**.

> "But a recommendation isn't the end. How do you know it helped?"

> "Same shock, same assumptions, only the portfolio changed: ten percent becomes nine. Then we
> re-run the whole search on the new portfolio — the break point moves from twenty-four seven
> to twenty-seven eight. Three points further away."

**Shot 9** · Scroll to section 3, then section 4. (They are stacked on one page, not tabs.)

> "Four hundred simulated scenarios, both portfolios on identical draws. Worst case improves.
> And the historical section says *not available* — we don't ship price history, so we won't show
> you a number we made up."

---

## ACT 5 — CLOSE (3:20 – 3:30)

**Shot 10** · Press **6** for the Model page, and point at *What computed the institutional patch*.

> "Same engine, institutional question: which single position, cut by how much, stops the
> funds themselves from breaching? That's the prime brokerage version of the same search.
> Find the failure before it finds you."

---

## Timing

321 narration words. **2:08 at 150 wpm inside 3:42** — 94 seconds of headroom for the cascade to
play, the search to land, and you to breathe.

The headroom is the deliverable, not slack. A script with none doesn't get shorter when you read
it faster; it just gets delivered by someone visibly rushing. If the demo runs slower on the day
than it does here, this is what absorbs it.

(Counted with the same parser used on the long script. My first draft of this line said 430 — I
had estimated rather than counted, which on a page about not saying unverified numbers is the
wrong way round.)

## If you're long

Cut Act 5 (10s). Then Shot 9's second half. **Do not cut Shot 8** — the validation is the thing
that separates this from a visualisation, and the "not available" line is worth more to a judge
than any chart on the screen.

## If a number looks wrong on the day

Run `curl -s localhost:8765/api/portfolio/full?limit=0.10` and read the real ones. Do not say a
figure from this page that the screen is not showing.
