# SOX预测: lessons

Read before every forecast (SOX_TASK.md step 2). Keep at most 15 standing
rules and the latest 40 log entries.

## Standing rules

1. Start from the pre-market gap: over 5 years the opening gap's correlation
   with the day's close-to-close move is 0.64. Most of the day's move is
   usually already in the pre-market.
2. After the open, the session averages about zero whatever the gap size
   (open→close continues the gap's direction only ~45–58% of the time).
   Don't forecast a large move after the open without a concrete catalyst.
3. Very large gaps (beyond ±3%) have tended to fade a little after the open
   (about −0.4% on average for both up and down gaps).
4. After a SOX drop of more than 2%, the next session has leaned positive
   (about +0.4% on average, up ~57% of the time): a mild bounce tendency,
   not a rule to bet big on.
5. Pre-market quotes move a lot before the open: on 2026-10-23 SOXX went
   from +0.2% at 9:10 to −0.2% at 9:30 while Europe's semis were down 2–7%.
   Weigh Europe's chip stocks and the futures trend, not just one SOXX print.

## Log

### 2026-10-29 · forecast -2.2 / model n/a / pre-market ~-2 / actual -1.42
- What drove the day: Alphabet's 12% plunge on AI capex/free-cash-flow worries hit AI hardware; SOXX closed -1.55% before Intel's weak guidance after the close.
- What I missed or misjudged: forecast a slightly deeper fall than realized; direction right, error ~0.8.
- Lesson: after-hours earnings from a big sector name (Intel) can swamp the next gap; check the evening headlines before trusting the prior close as a base.

### 2026-10-28 · forecast +0.8 / model n/a / pre-market ~+0.9 / actual +1.75
- What drove the day: SK Hynix's record results lifted memory (Micron +4.8%); chips led a flat market into the Fed hold, which was a non-event.
- What I missed or misjudged: forecast a small fade (-0.2) but the session added ~+0.9 after the open; third straight underestimate.
- Lesson: with a strong sector catalyst, do not forecast a fade after the open; the last three days all ran past the gap.

### 2026-10-27 · forecast +2.0 / model n/a / pre-market ~+1.8 / actual +3.60
- What drove the day: Broadcom +4% on a $63B bank/Blackstone financing for Anthropic's chip purchases; halo on AMD (+5.5%), Intel (+3.6%), Micron (+2.8%); oil slid on Middle East talks.
- What I missed or misjudged: the session added ~1.8 points after the open; I again used a near-zero drift on a headline-driven rebound from oversold levels.
- Lesson: in an oversold rebound (RSI near 30, SOX −20% from high) with a fresh sector-wide AI-financing headline, the gap understates the day; two misses in a row (+1.4, +1.8) suggest drift +0.3 to +0.5.

### 2026-10-26 · forecast +1.4 / model +1.37 / pre-market +1.30 / actual +2.82 (replay, mechanical)
- What drove the day: Anthropic's IPO filing revived the AI trade; broad chip gains (Micron ~+3%, AMD ~+2.8%, Nvidia ~+2.4%, Broadcom ~+2.3%) after an eight-session selloff.
- What I missed or misjudged: the session added another ~1.4 points after the open; a mechanical drift near zero missed a headline-driven oversold rebound.
- Lesson: when RSI(14) is near 20 and a sector-wide positive headline lands, allow a small positive drift (+0.2 to +0.5) rather than zero.

### 2026-10-23 · forecast +0.6 / model +0.82 / pre-market +0.13 / actual +0.44 (made by hand at 9:10)
- What drove the day: a modest bounce after Thursday's 6.7% plunge, led by memory (Micron +2.5%); sources called it a bounce, not a reversal (SOX still −3.2% on the week).
- What I missed or misjudged: the SOX ran up to +1.8% by late morning, then faded to +0.4% into the weekend; I didn't check Europe's chip stocks (down 2–7%), though it didn't decide the day.
- Lesson: after a capitulation day the next-day bounce can come early and fade by the close, so keep `drift_est` modest.
