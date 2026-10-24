"""A small statistical model for SOX预测: the SOX's move after the open.

Forecast = opening gap + expected move after the open (open -> close). The
gap is seen in the pre-market; this model estimates the second part from
things known before the bell, as a linear regression fitted on 5 years of
daily data (10 years):

  gap       SOX opening gap vs the previous close, %  (live: SOXX pre-market)
  qqq_gap   Nasdaq-100 (QQQ) opening gap, %           (live: QQQ pre-market)
  gap_big   the part of the SOX gap beyond +/-2%, to let big gaps fade
  prev      the SOX's previous-day move, %
  ret5      the SOX's 5-day move to the previous close, %
  dist20    previous close vs its 20-day average, %
  vol20     standard deviation of the last 20 daily moves, %

sox_brief.py refits it every morning and saves data/sox-model.json: the
coefficients plus an honest walk-forward test (each year predicted by a model
fitted only on the years before it). sox.py applies it at the moment of each
call. Expect little: in that test the model barely differs from "no move
after the open", which is itself worth knowing.
"""

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).parent
MODEL = ROOT / "data" / "sox-model.json"
FEATURES = ["gap", "qqq_gap", "gap_big", "prev", "ret5", "dist20", "vol20"]
RIDGE = 5.0      # shrinks the coefficients toward zero; daily moves are mostly noise
CLIP = 8.0       # caps extreme days so a few crashes don't dominate the fit


def clip(x):
    return max(-CLIP, min(CLIP, x))


def pct(a, b):
    return (a / b - 1) * 100


def history_features(closes):
    """Features known at the previous close. closes: SOX closes up to and including it (oldest first)."""
    if len(closes) < 22:
        return None
    rets = [pct(b, a) for a, b in zip(closes[-21:], closes[-20:])]
    return {
        "prev": pct(closes[-1], closes[-2]),
        "ret5": pct(closes[-1], closes[-6]),
        "dist20": pct(closes[-1], sum(closes[-20:]) / 20),
        "vol20": statistics.pstdev(rets),
    }


def features(closes, gap, qqq_gap):
    h = history_features(closes)
    if h is None:
        return None
    big = max(abs(gap) - 2, 0) * (1 if gap > 0 else -1)
    return dict(h, gap=gap, qqq_gap=qqq_gap, gap_big=big)


def dataset(sox_rows, qqq_rows):
    """sox_rows/qqq_rows: [(date, open, close)] oldest first. Returns [(date, x, y)] with y = open->close %."""
    q = {d: (o, c) for d, o, c in qqq_rows}
    qprev = {}
    for (d0, _, c0), (d1, _, _) in zip(qqq_rows, qqq_rows[1:]):
        qprev[d1] = c0
    out = []
    closes = [c for _, _, c in sox_rows]
    for i in range(22, len(sox_rows)):
        d, o, c = sox_rows[i]
        if d not in q or d not in qprev:
            continue
        x = features(closes[:i], pct(o, closes[i - 1]), pct(q[d][0], qprev[d]))
        if x:
            out.append((d, {k: clip(v) for k, v in x.items()}, clip(pct(c, o))))
    return out


def solve(a, b):
    """Solve a x = b (small dense system) by Gaussian elimination with pivoting."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r != col and m[col][col]:
                f = m[r][col] / m[col][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [m[i][n] / m[i][i] for i in range(n)]


def fit(rows):
    """Ridge regression on standardized features. Returns a model dict."""
    xs = [[x[k] for k in FEATURES] for _, x, _ in rows]
    ys = [y for _, _, y in rows]
    mu = [statistics.mean(col) for col in zip(*xs)]
    sd = [statistics.pstdev(col) or 1 for col in zip(*xs)]
    z = [[(v - m_) / s_ for v, m_, s_ in zip(row, mu, sd)] for row in xs]
    ym = statistics.mean(ys)
    k = len(FEATURES)
    a = [[sum(r[i] * r[j] for r in z) + (RIDGE if i == j else 0) for j in range(k)] for i in range(k)]
    b = [sum(r[i] * (y - ym) for r, y in zip(z, ys)) for i in range(k)]
    w = solve(a, b)
    # Back to raw units: drift = intercept + sum(coef * feature).
    coef = {f: w[i] / sd[i] for i, f in enumerate(FEATURES)}
    intercept = ym - sum(coef[f] * mu[i] for i, f in enumerate(FEATURES))
    return {"intercept": intercept, "coef": coef}


def predict(model, x):
    return model["intercept"] + sum(model["coef"][f] * clip(x[f]) for f in FEATURES)


def evaluate(train, test):
    """Fit on train, score on test against the zero-drift baseline."""
    m = fit(train)
    p = [predict(m, x) for _, x, _ in test]
    y = [v for _, _, v in test]
    sig = [(a, b) for a, b in zip(p, y) if abs(a) >= 0.1]
    return {
        "days": len(test), "from": test[0][0], "to": test[-1][0],
        # After-open move: model vs "no move after the open".
        "mae_drift_model": statistics.mean(abs(a - b) for a, b in zip(p, y)),
        "mae_drift_zero": statistics.mean(abs(b) for b in y),
        "sign_hit": sum(1 for a, b in sig if (a > 0) == (b > 0)) / len(sig) if sig else None,
        "sign_days": len(sig),
        "corr": statistics.correlation(p, y) if len(set(p)) > 1 else 0,
    }


def build(sox_rows, qqq_rows):
    """Fit on all data plus a walk-forward test by calendar year; returns the saved model."""
    rows = dataset(sox_rows, qqq_rows)
    years = sorted({d[:4] for d, _, _ in rows})
    tests = []
    for y in years:
        train = [r for r in rows if r[0] < y]
        test = [r for r in rows if r[0][:4] == y]
        if len(train) >= 500 and test:
            tests.append(dict(evaluate(train, test), year=y))
    model = fit(rows)
    hit = sum(t["sign_hit"] * t["sign_days"] for t in tests if t["sign_hit"] is not None)
    n = sum(t["sign_days"] for t in tests)
    model.update(features=FEATURES, ridge=RIDGE, trained_on=[rows[0][0], rows[-1][0]], days=len(rows),
                 walk_forward=tests,
                 summary={"years": len(tests),
                          "years_beating_zero": sum(1 for t in tests if t["mae_drift_model"] < t["mae_drift_zero"]),
                          "mae_model": statistics.mean(t["mae_drift_model"] for t in tests),
                          "mae_zero": statistics.mean(t["mae_drift_zero"] for t in tests),
                          "sign_hit": hit / n if n else None, "sign_days": n})
    return model


def load():
    try:
        return json.loads(MODEL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save(model):
    MODEL.write_text(json.dumps(model, indent=1) + "\n", encoding="utf-8")
