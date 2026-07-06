"""Calibrate the FIFA MID tackles/chances credit against realized round points.

Joins Holdet per-round events (data/holdet/stats_rN.json) to official FIFA fantasy
round points (data/fifa/players.json + rounds.json), isolates each MID's realized
non-goal stat credit as a residual:

    credit = roundPoints - goals*6 - assists*3 - appearance(2/1) - CS(1)
             + yellows(222) + 2*red_or_own_goal(219, 223)

and reports the per-90 level plus its correlation with the engine's goal/assist-share
priors. This produced the 2026-07-06 recalibration (flat 0.84 pts/90, shaping removed
— see games/fifa/model.py constants and CHANGELOG). Re-run after new rounds complete
(refresh the FIFA cache first: `python -c "from core import fifa_api; fifa_api.refresh()"`)
to check whether the anchor or the no-signal conclusion has moved.

Usage: python3 scripts/calibrate_mid_credit.py [max_round]
"""
import collections
import json
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOLDET = os.path.join(ROOT, "data", "holdet")
FIFA = os.path.join(ROOT, "data", "fifa")

STARTED, SUB_ON, SUB_OFF = {224, 562}, 225, 226
GOAL, ASSIST = 218, 220
YELLOW, RED_OR_OG = 222, (219, 223)   # decoded vs FIFA points, see core/realized.py

ALIAS = {"south korea": "korea republic", "united states": "usa",
         "ivory coast": "cote d ivoire", "czech republic": "czechia", "ir iran": "iran"}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalpha() or c == " " else " " for c in s).split())


def ckey(nm):
    n = norm(nm)
    return ALIAS.get(n, n)


def main(max_round: int) -> None:
    t = json.load(open(f"{HOLDET}/tournament.json", encoding="utf-8"))
    persons = {p["id"]: (p.get("firstname") or "", p.get("lastname") or "")
               for p in t["persons"]}
    teams = {tm["id"]: tm["name"] for tm in t["teams"]}
    hplayers = {p["id"]: p for p in t["players"]}

    fp = json.load(open(f"{FIFA}/players.json", encoding="utf-8"))
    rounds = json.load(open(f"{FIFA}/rounds.json", encoding="utf-8"))
    squad_name, team_ga = {}, {}
    for rd in rounds:
        for m in rd.get("tournaments", []):
            squad_name[m["homeSquadId"]] = m["homeSquadName"]
            squad_name[m["awaySquadId"]] = m["awaySquadName"]
            if m.get("homeScore") is not None:
                team_ga[(ckey(m["homeSquadName"]), rd["id"])] = m["awayScore"]
                team_ga[(ckey(m["awaySquadName"]), rd["id"])] = m["homeScore"]

    def fifa_match(first, last, team):
        tkey, fn, ln = ckey(team), norm(first), norm(last)
        cands = []
        for p in fp:
            if ckey(squad_name.get(p["squadId"], "")) != tkey:
                continue
            f2, l2 = norm(p.get("firstName") or ""), norm(p.get("lastName") or "")
            kn = norm(p.get("knownName") or "")
            full_h, full_f = f"{fn} {ln}".strip(), f"{f2} {l2}".strip()
            score = 0
            if full_h and full_h == full_f:
                score = 4
            elif kn and kn in (full_h, ln, fn):
                score = 3
            elif ln and ln == l2 and fn and f2 and fn[:1] == f2[:1]:
                score = 3
            elif ln and ln == l2:
                score = 2
            elif ln and l2 and (ln in l2.split() or l2 in ln.split()):
                score = 1
            if score:
                cands.append((score, p))
        cands.sort(key=lambda c: -c[0])
        if not cands or (len(cands) > 1 and cands[0][0] == cands[1][0]):
            return None
        return cands[0][1]

    creds, cache = [], {}
    for r in range(1, max_round + 1):
        path = f"{HOLDET}/stats_r{r}.json"
        if not os.path.exists(path):
            continue
        for e in json.load(open(path, encoding="utf-8")):
            pp = hplayers.get(e["player"]["id"])
            if not pp:
                continue
            ids = collections.Counter()
            for ev in e.get("events", {}).get("round", []):
                ids[ev["type"]["id"]] += ev.get("amount", 0)
            # full-90 starters only: started and not subbed off (clean appearance/CS terms)
            if not (any(i in ids for i in STARTED) and SUB_OFF not in ids):
                continue
            first, last = persons[pp["person"]["id"]]
            team = teams.get(pp["team"]["id"], "?")
            key = (first, last, team)
            if key not in cache:
                cache[key] = fifa_match(first, last, team)
            p = cache[key]
            if p is None or p["position"] != "MID":
                continue
            rp = (p.get("stats") or {}).get("roundPoints")
            pts = rp.get(str(r)) if isinstance(rp, dict) else None
            ga = team_ga.get((ckey(team), r))
            if pts is None or ga is None:
                continue
            credit = pts - ids.get(GOAL, 0) * 6 - ids.get(ASSIST, 0) * 3 - 2
            credit -= 1 if ga == 0 else 0
            credit += ids.get(YELLOW, 0) + 2 * sum(ids.get(i, 0) for i in RED_OR_OG)
            creds.append((p, r, credit))

    n = len(creds)
    if not n:
        print("no matched full-90 MID player-rounds — refresh data/fifa + data/holdet caches")
        return
    vals = [c for _, _, c in creds]
    mean = sum(vals) / n
    sd = (sum((v - mean) ** 2 for v in vals) / max(1, n - 1)) ** 0.5
    print(f"full-90 MID player-rounds: n={n}")
    print(f"realized stat credit: mean={mean:.3f} pts/90  (sd={sd:.2f}, se={sd/n**0.5:.3f})")
    byr = collections.defaultdict(list)
    for _, r, c in creds:
        byr[r].append(c)
    print("per round:", {r: round(sum(v) / len(v), 2) for r, v in sorted(byr.items())})

    from core import players as pdb, ratings
    xs, ys, prior_by_team = [], [], {}
    for p, _, c in creds:
        team = squad_name.get(p["squadId"], "")
        if team not in prior_by_team:
            try:
                prior_by_team[team] = ratings.players_for_team(team)
            except Exception:
                prior_by_team[team] = []
        nm = f'{p.get("firstName") or ""} {p.get("lastName") or ""}'.strip()
        for pr in prior_by_team[team]:
            if pr.position == "MID" and (pdb.name_match(pr.name, nm) or
                                         (p.get("knownName") and pdb.name_match(pr.name, p["knownName"]))):
                xs.append(pr.goal_share + pr.assist_share)
                ys.append(c)
                break
    if len(xs) > 20:
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
        print(f"corr(prior gs+ash, realized credit) = {num/den:+.3f}  (n={len(xs)}; "
              f"shaping is only justified if this becomes clearly positive... or negative)")

    from games.fifa import model
    cur = model.MID_TACKLES_MAX / 3.0 + model.MID_CHANCES_BASE / 2.0
    print(f"\ncurrent model flat credit: {cur:.3f} pts/90 "
          f"({'OK' if abs(cur - mean) < 2 * sd / n ** 0.5 + 0.05 else 'DRIFTED — consider re-anchoring'})")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
