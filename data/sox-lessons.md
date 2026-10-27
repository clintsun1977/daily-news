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

### 2026-10-23 · forecast +0.6 / model +0.82 / pre-market +0.13 / actual +0.44 (made by hand at 9:10)
- What drove the day: a modest bounce after Thursday's 6.7% plunge, led by memory (Micron +2.5%); sources called it a bounce, not a reversal (SOX still −3.2% on the week).
- What I missed or misjudged: the SOX ran up to +1.8% by late morning, then faded to +0.4% into the weekend; I didn't check Europe's chip stocks (down 2–7%), though it didn't decide the day.
- Lesson: after a capitulation day the next-day bounce can come early and fade by the close, so keep `drift_est` modest.
