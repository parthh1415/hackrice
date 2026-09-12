# Firebreak — 3:30 shooting script

The long script (`video-script.md`) stays as the reference: every number in it has been checked
against a live run, and it carries the shot-by-shot notes and the warnings about which figures have
moved. **This file is what you read aloud.** It is that script cut from 1,143 narration words to
fit 3:42, because at 150 wpm the full text runs **7:37** and no amount of talking faster fixes that.

What got cut, so you can put it back if you have room: the crowding statistics, the Caccioli and
Greenwood–Landier–Thesmar citations, the boundary's axis explanation, and most of the assumptions
panel. What did NOT get cut: the inverse-question framing, the fix being non-obvious, and the
admission that the fix does not move the break point. Those three are the argument.

Numbers verified live at commit time. If you re-record after changing anything, re-check them —
`docs/video-script.md` §"recording notes" lists where each one comes from.

---

## ACT 1 — FRAME (0:00 – 0:24)

**Shot 1** · 0:00 – 0:10 · Title card, then the live app.

> "This is Firebreak. Every stress test asks the same question — what if the market drops twenty
> percent? The scenario is an assumption, and the assumption is the part nobody checks."

**Shot 2** · 0:10 – 0:24 · The network, already run. Hero reads `5.27%`.

> "Firebreak asks the inverse. What is the smallest shock that breaks this system — and what is the
> cheapest change that prevents it. Real holdings, five hedge funds, their filed 13Fs for Q2 2026.
> Forty point nine billion dollars."

---

## ACT 2 — DEMO (0:24 – 2:50)

**Shot 3 · ATTACK** · 0:24 – 0:50 · Point at the three sliders, then click **Find weakest shock**.

> "Leverage and price impact aren't in a 13F, so they're ours, and they're on screen the whole time.
> Now — don't pick a scenario. Solve for it."

*(let the search land)*

> "Negative five point two seven percent on NVIDIA. That's the smallest single-name move that forces
> three or more of these funds to sell. Nobody guessed that number."

**Shot 4 · CASCADE** · 0:50 – 1:30 · Let it play. Point at the metrics band as it fills.

> "Watch what the shock does that the shock alone doesn't explain. Two funds breach their leverage
> limit. They're forced to sell. They sell into a market where everyone holds the same ten names, so
> the price falls for everyone — and that pushes the next fund over."

> "Four point nine percent of direct loss becomes nine point one percent after three rounds. One
> point eight seven times amplification. The damage isn't the shock. It's the feedback."

**Shot 5 · BOUNDARY** · 1:30 – 2:00 · Click **Map the boundary**.

> "Two hundred and fifty-six scenarios, swept over leverage and crowding. The contour is where
> amplification hits one and a half times — the line where contagion takes over from arithmetic. The
> marker is where this system actually sits. That's the map you'd hand a risk committee."

**Shot 6 · STABILISE** · 2:00 – 2:50 · Click **Stabilise**. Let the split render.

> "Now the part that's actually useful. What's the cheapest change that survives the identical
> shock?"

> "Citadel sells one point seven million dollars of NVIDIA. That's seventy-three thousandths of one
> percent of a two point four billion dollar position — four ten-thousandths of a percent of the
> system. Same shock, same books otherwise: four funds breaching becomes two, three rounds becomes
> one."

> "And notice who it is. Citadel doesn't breach until round two. It's the shocked name, in a fund
> that isn't first to fail. Nobody would guess that either. That's why you solve it instead."

---

## ACT 3 — HONESTY & CLOSE (2:50 – 3:30)

**Shot 7** · 2:50 – 3:10 · Point at the bought line, already on screen.

> "Here's what we'd rather tell you than have you find. We re-ran the search on the fixed books. The
> break point doesn't measurably move. A cheapest single-position cut defends against this shock,
> not the next one — and the app says so itself, on screen, every time."

**Shot 8** · 3:10 – 3:30 · Open **Assumptions**, then land on the network.

> "Holdings are real and the source is on screen. Leverage and impact are ours, declared, every row
> labelled. This is a mechanism, not a prediction. Find the failure before it finds you."

---

## Timing

**420 narration words. At 150 wpm that is 2:48 of speech inside a 3:42 limit — 54 seconds of
headroom** for the cascade to play, the sweep to render, and you to breathe.

That headroom is the deliverable, not a rounding error. The full script is 1,143 words — **7:37 of
speech against a 3:42 cap**, before anyone pauses. A script with no silence in it does not become
shorter when you read it faster; it becomes a script nobody can follow, delivered by someone
visibly rushing.

(Counted with the same block-parser used on the long script: consecutive `> ` lines whose first
line opens with a quote. Annotation lines in italics are not spoken and are not counted.)

## If you are still over

Cut Shot 5 entirely (30s, 52 words). The boundary is the most impressive thing on screen and the
least necessary to the argument: beats 1, 2 and 4 carry the inverse question, the mechanism and the
actionable fix without it. Do not cut Shot 7 to make room — an unprompted limitation is worth more
to a judge than a fourth visualisation.
