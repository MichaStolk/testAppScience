"""
FitScience – offline trainings- en voedingscoach (Python + Flet 1.x)

Functies (vergelijkbaar met moderne 'science-based' fitness-apps):
  * Profiel-vragenlijst: lichaam, vet%, doel + tempo, activiteitsniveau, stapdoel,
    ervaring, dagen/week, duur, materiaal, prioriteitsspieren, blessures
  * Automatische programma-generator (full body / upper-lower / PPL)
  * Training loggen per set + rusttimer + oefening wisselen
  * Progressive overload: 'dubbele progressie' doelen op basis van vorige sessie
  * Voeding: calorieën via vetvrije massa + activiteit + stappen + training, eiwit per kg vetvrije massa,
    eten en stappen loggen, wekelijkse bijsturing op basis van gewichtstrend
  * Voortgang: gewicht, geschatte 1RM per oefening, trainingshistorie
Alle data staat lokaal in een JSON-bestand -> werkt 100% offline.

Starten op pc:      flet run main.py
Android-APK maken:  flet build apk
"""

import asyncio
import json
import os
import random
from datetime import date, timedelta

import flet as ft

# --------------------------------------------------------------------------
# 1. OPSLAG (lokaal JSON-bestand, werkt offline op telefoon en pc)
# --------------------------------------------------------------------------
DATA_DIR = os.getenv("FLET_APP_STORAGE_DATA") or os.path.join(os.path.expanduser("~"), ".fitscience")
os.makedirs(DATA_DIR, exist_ok=True)
DATA_FILE = os.path.join(DATA_DIR, "data.json")

DEFAULT_DATA = {
    "profile": None,
    "program": None,
    "next_day": 0,
    "sessions": [],
    "food": {},
    "weights": [],
    "activity": {},
    "last_checkin": None,
}


def load_data():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            d = json.load(f)
        d = {**json.loads(json.dumps(DEFAULT_DATA)), **d}
        for k, v in d.pop("steps", {}).items():  # migratie oude versie
            d["activity"].setdefault(k, {})["steps"] = v
        return d
    except (FileNotFoundError, json.JSONDecodeError):
        return json.loads(json.dumps(DEFAULT_DATA))


def save_data(d):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DATA_FILE)


# --------------------------------------------------------------------------
# 2. OEFENINGEN-DATABASE
#    eq: welk materiaal nodig is  (gym ⊃ dumbbell ⊃ bodyweight)
# --------------------------------------------------------------------------
EX = [
    # naam, spiergroep, materiaal, rep-range, compound
    ("Bankdrukken (barbell)", "borst", "gym", (6, 10), True),
    ("Incline dumbbell press", "borst", "dumbbell", (8, 12), True),
    ("Machine chest press", "borst", "gym", (8, 12), True),
    ("Cable fly", "borst", "gym", (10, 15), False),
    ("Dumbbell fly", "borst", "dumbbell", (10, 15), False),
    ("Push-ups", "borst", "bodyweight", (8, 20), True),
    ("Lat pulldown", "rug", "gym", (8, 12), True),
    ("Seated cable row", "rug", "gym", (8, 12), True),
    ("Barbell row", "rug", "gym", (6, 10), True),
    ("Dumbbell row (1 arm)", "rug", "dumbbell", (8, 12), True),
    ("Pull-ups", "rug", "bodyweight", (5, 12), True),
    ("Inverted row (tafel)", "rug", "bodyweight", (8, 15), True),
    ("Overhead press (dumbbell)", "schouders", "dumbbell", (8, 12), True),
    ("Lateral raise", "schouders", "dumbbell", (12, 20), False),
    ("Cable lateral raise", "schouders", "gym", (12, 20), False),
    ("Reverse fly", "schouders", "dumbbell", (12, 20), False),
    ("Pike push-ups", "schouders", "bodyweight", (6, 15), True),
    ("Dumbbell curl", "biceps", "dumbbell", (8, 15), False),
    ("Incline dumbbell curl", "biceps", "dumbbell", (10, 15), False),
    ("Cable curl", "biceps", "gym", (10, 15), False),
    ("Chin-ups", "biceps", "bodyweight", (5, 12), True),
    ("Triceps pushdown", "triceps", "gym", (10, 15), False),
    ("Overhead triceps extension", "triceps", "dumbbell", (10, 15), False),
    ("Close-grip push-ups", "triceps", "bodyweight", (8, 20), False),
    ("Bench dips", "triceps", "bodyweight", (8, 20), False),
    ("Back squat", "quadriceps", "gym", (6, 10), True),
    ("Leg press", "quadriceps", "gym", (8, 15), True),
    ("Goblet squat", "quadriceps", "dumbbell", (8, 15), True),
    ("Bulgarian split squat", "quadriceps", "dumbbell", (8, 12), True),
    ("Leg extension", "quadriceps", "gym", (10, 15), False),
    ("Bodyweight split squat", "quadriceps", "bodyweight", (10, 20), True),
    ("Romanian deadlift", "hamstrings", "gym", (6, 10), True),
    ("Dumbbell RDL", "hamstrings", "dumbbell", (8, 12), True),
    ("Lying leg curl", "hamstrings", "gym", (10, 15), False),
    ("Single-leg hip hinge", "hamstrings", "bodyweight", (10, 15), True),
    ("Hip thrust", "billen", "gym", (8, 12), True),
    ("Dumbbell hip thrust", "billen", "dumbbell", (10, 15), True),
    ("Glute bridge", "billen", "bodyweight", (12, 20), False),
    ("Standing calf raise", "kuiten", "gym", (8, 15), False),
    ("Single-leg calf raise", "kuiten", "bodyweight", (10, 20), False),
    ("Cable crunch", "buik", "gym", (10, 15), False),
    ("Hanging knee raise", "buik", "bodyweight", (8, 15), False),
    ("Dead bug", "buik", "bodyweight", (8, 15), False),
]
EXERCISES = [dict(name=n, muscle=m, eq=e, lo=r[0], hi=r[1], compound=c) for n, m, e, r, c in EX]
MUSCLES = ["borst", "rug", "schouders", "biceps", "triceps", "quadriceps", "hamstrings", "billen", "kuiten", "buik"]
EQ_LEVEL = {"bodyweight": 0, "dumbbell": 1, "gym": 2}

# Dag-sjablonen: volgorde = belangrijkste oefeningen eerst
TEMPLATES = {
    "Full body": ["quadriceps", "borst", "rug", "hamstrings", "schouders", "biceps", "triceps", "buik"],
    "Upper": ["borst", "rug", "schouders", "rug", "borst", "biceps", "triceps", "schouders"],
    "Lower": ["quadriceps", "hamstrings", "billen", "quadriceps", "kuiten", "buik", "hamstrings"],
    "Push": ["borst", "schouders", "borst", "schouders", "triceps", "triceps", "borst"],
    "Pull": ["rug", "rug", "biceps", "schouders", "biceps", "rug", "buik"],
    "Legs": ["quadriceps", "hamstrings", "billen", "quadriceps", "kuiten", "buik", "hamstrings"],
}
SPLITS = {
    2: ["Full body", "Full body"],
    3: ["Full body", "Full body", "Full body"],
    4: ["Upper", "Lower", "Upper", "Lower"],
    5: ["Upper", "Lower", "Push", "Pull", "Legs"],
    6: ["Push", "Pull", "Legs", "Push", "Pull", "Legs"],
}


# Blessures: deze oefeningen worden niet ingepland
INJURY_EXCLUDE = {
    "knie": {"Back squat", "Bulgarian split squat", "Leg extension", "Bodyweight split squat"},
    "schouder": {"Bankdrukken (barbell)", "Overhead press (dumbbell)", "Pike push-ups", "Bench dips", "Pull-ups"},
    "onderrug": {"Back squat", "Barbell row", "Romanian deadlift", "Single-leg hip hinge"},
}


def available(muscle, equipment, injuries=()):
    lvl = EQ_LEVEL[equipment]
    banned = set().union(*(INJURY_EXCLUDE.get(i, set()) for i in injuries)) if injuries else set()
    opts = [e for e in EXERCISES if e["muscle"] == muscle and EQ_LEVEL[e["eq"]] <= lvl]
    safe = [e for e in opts if e["name"] not in banned]
    return safe or opts


def generate_program(p):
    """Bouwt een programma op basis van het profiel."""
    days = int(p["days"])
    slots = {45: 5, 60: 6, 75: 7, 90: 8}[int(p["duration"])]
    base_sets = {"beginner": 2, "gemiddeld": 3, "gevorderd": 3}[p["experience"]]
    prio = set(p.get("priority", []))
    rotation = {m: 0 for m in MUSCLES}  # zorgt voor variatie tussen dagen
    out = []
    for i, tpl in enumerate(SPLITS[days]):
        muscles = TEMPLATES[tpl][:slots]
        # prioriteitsspieren die op deze dag thuishoren krijgen een extra oefening
        for m in prio:
            if m in TEMPLATES[tpl] and muscles.count(m) < 2 and len(muscles) < slots + 1:
                muscles.append(m)
        chosen, used = [], set()
        for m in muscles:
            opts = [e for e in available(m, p["equipment"], p.get("injuries", [])) if e["name"] not in used]
            if not opts:
                continue
            ex = opts[rotation[m] % len(opts)]
            rotation[m] += 1
            used.add(ex["name"])
            sets = base_sets + (1 if ex["compound"] and p["experience"] != "beginner" else 0)
            if m in prio:
                sets += 1
            chosen.append(dict(name=ex["name"], muscle=m, sets=min(sets, 5), lo=ex["lo"], hi=ex["hi"],
                               rest=150 if ex["compound"] else 90,
                               inc=2.5 if ex["eq"] == "gym" else (2.0 if ex["eq"] == "dumbbell" else 0)))
        letter = "AB"[sum(1 for d in out if d["type"] == tpl) % 2]
        out.append(dict(name=f"Dag {i + 1}: {tpl} {letter}", type=tpl, exercises=chosen))
    return {"split": f"{days} dagen", "days": out, "created": str(date.today())}


# --------------------------------------------------------------------------
# 3. PROGRESSIVE OVERLOAD (dubbele progressie) + 1RM
# --------------------------------------------------------------------------
def last_performance(data, ex_name):
    for s in reversed(data["sessions"]):
        for e in s["entries"]:
            if e["name"] == ex_name and e["sets"]:
                return e["sets"]
    return None


def suggestion(data, ex):
    prev = last_performance(data, ex["name"])
    if not prev:
        return f"Eerste keer: kies een gewicht waarmee je {ex['lo']}-{ex['hi']} reps haalt met 1-2 reps in reserve."
    w = max(s[0] for s in prev)
    reps = [s[1] for s in prev]
    prev_txt = f"Vorige: {fmt(w)} kg × {', '.join(str(r) for r in reps)}"
    if all(r >= ex["hi"] for r in reps):
        if ex["inc"]:
            return f"{prev_txt}\nDoel: gewicht omhoog → {fmt(w + ex['inc'])} kg × {ex['lo']}+"
        return f"{prev_txt}\nDoel: moeilijkere variant of tempo vertragen (3 sec omlaag)"
    target = [min(r + 1, ex["hi"]) for r in reps]
    return f"{prev_txt}\nDoel: {fmt(w)} kg × {', '.join(str(r) for r in target)} (+1 rep per set)"


def e1rm(w, r):
    return w * (1 + r / 30) if r > 1 else w  # Epley


def fmt(x):
    return f"{x:.1f}".rstrip("0").rstrip(".")


def num(v, default=0.0):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# 4. VOEDING – adaptieve coach
#    Dagdoel = (berekend verbruik vandaag + coach-correctie) ± doel-tempo
#
#    a) Berekend verbruik
#       - Vetvrije massa (FFM) uit vet% (of schatting via BMI)
#       - Ruststofwisseling: Katch-McArdle  BMR = 370 + 21.6 × FFM
#       - + 10% vertering (TEF)
#       - + activiteit: Garmin 'actieve calorieën' (×0.8, horloges overschatten)
#         óf: leefstijl + stappen + gelogde training
#         Zonder data van vandaag: je plan (stapdoel + gemiddelde training)
#    b) Coach-correctie (past zich continu aan)
#       Uit de laatste 28 dagen: gemiddelde inname − verandering trendgewicht × 7700
#       = je ECHTE verbruik. Het verschil met de formule wordt (afgezwakt bij weinig data)
#       elke dag meegenomen. Hoe meer je logt, hoe nauwkeuriger.
#    c) Eiwit 1.65–2.8 g/kg FFM, vet ±25% (min 0.5 g/kg), rest koolhydraten
# --------------------------------------------------------------------------
ACTIVITY = {  # leefstijl ZONDER training en zonder extra stappen
    "zittend": (1.20, "Kantoorbaan, weinig bewegen"),
    "licht actief": (1.30, "Veel staan, bv. leraar/winkel"),
    "actief": (1.40, "Veel lopen/tillen, bv. horeca/verpleging"),
    "zeer actief": (1.55, "Zwaar fysiek werk, bv. bouw"),
}
LOSS_RATES = [0.25, 0.5, 0.75, 1.0]   # % lichaamsgewicht per week
GAIN_RATES = [0.25, 0.5, 1.0]         # kg per maand
KCAL_PER_KG = 7700
WATCH_FACTOR = 0.8                    # correctie op horloge-calorieën
COACH_WINDOW = 28                     # dagen
MIN_FOOD_DAYS = 7                     # minimaal gelogde eetdagen voor correctie


def estimate_bodyfat(p):
    """Schatting (Deurenberg) als de gebruiker geen vetpercentage weet."""
    w, h, a = num(p["weight"]), num(p["height"]) / 100, num(p["age"])
    bmi = w / (h * h)
    return max(5.0, 1.2 * bmi + 0.23 * a - 10.8 * (1 if p["sex"] == "man" else 0) - 5.4)


def recommended_rate(p, bf):
    """Advies-tempo op basis van doel, vetpercentage en ervaring."""
    lean = bf < (15 if p["sex"] == "man" else 23)
    if p["goal"] == "afvallen":
        return 0.5 if lean else (1.0 if bf > (25 if p["sex"] == "man" else 33) else 0.75)
    if p["goal"] == "spieropbouw":
        return {"beginner": 1.0, "gemiddeld": 0.5, "gevorderd": 0.25}[p["experience"]]
    return 0


def body_basics(p):
    w = num(p["weight"])
    bf = num(p.get("bodyfat")) or estimate_bodyfat(p)
    ffm = w * (1 - bf / 100)
    bmr = 370 + 21.6 * ffm
    return w, bf, ffm, bmr


def steps_kcal(steps, w):
    return max(0, steps - 4000) * 0.0005 * w      # ±0.04 kcal/stap bij 80 kg


def session_kcal(p, w):
    return int(p["duration"]) / 60 * 4 * w         # netto ±4 kcal/kg/uur krachttraining


def planned_activity(p):
    """Verwachte activiteit (boven BMR + vertering) op een gemiddelde dag volgens je plan."""
    w, _, _, bmr = body_basics(p)
    factor = ACTIVITY.get(p.get("activity", "zittend"), ACTIVITY["zittend"])[0]
    lifestyle = bmr * max(0, factor - 1.1)
    return dict(lifestyle=lifestyle, steps=steps_kcal(int(num(p.get("steps", 7000))), w),
                training=session_kcal(p, w) * int(p["days"]) / 7, source="plan (stapdoel)")


def actual_activity(data, day):
    """Werkelijke activiteit op een dag uit Garmin-calorieën of stappen. None als niets gelogd."""
    p = data["profile"]
    a = data.get("activity", {}).get(day)
    if not a:
        return None
    w, _, _, bmr = body_basics(p)
    if num(a.get("active_kcal")) > 0:
        return dict(lifestyle=0, steps=0, training=num(a["active_kcal"]) * WATCH_FACTOR,
                    source=f"Garmin actief {round(num(a['active_kcal']))} kcal × {WATCH_FACTOR}")
    if num(a.get("steps")) > 0:
        plan = planned_activity(p)
        trained = any(s["date"] == day for s in data["sessions"])
        return dict(lifestyle=plan["lifestyle"], steps=steps_kcal(int(num(a["steps"])), w),
                    training=session_kcal(p, w) if trained else 0,
                    source=f"{int(num(a['steps']))} stappen{' + training' if trained else ''}")
    return None


def activity_for_target(data, day):
    """Welke activiteit telt mee voor het dagdoel (afhankelijk van de gekozen modus)."""
    p = data["profile"]
    plan = planned_activity(p)
    plan_total = plan["lifestyle"] + plan["steps"] + plan["training"]
    if p.get("calorie_mode", "per dag") == "weekgemiddelde":
        d0 = date.fromisoformat(day)
        vals = [actual_activity(data, str(d0 - timedelta(days=i))) for i in range(1, 8)]
        vals = [v["lifestyle"] + v["steps"] + v["training"] for v in vals if v]
        if len(vals) >= 3:
            avg = sum(vals) / len(vals)
            return dict(lifestyle=0, steps=0, training=avg, source=f"gemiddelde laatste {len(vals)} dagen"), avg
        return plan, plan_total
    act = actual_activity(data, day)
    if act and act["lifestyle"] + act["steps"] + act["training"] > plan_total:
        return act, act["lifestyle"] + act["steps"] + act["training"]  # meer bewogen = meer eten
    return plan, plan_total  # plan is de ondergrens (ochtend: nog weinig stappen)


def formula_tdee(data, day, use_actual=True):
    p = data["profile"]
    _, _, _, bmr = body_basics(p)
    if use_actual:
        act = actual_activity(data, day)
        if act:
            return bmr * 1.1 + act["lifestyle"] + act["steps"] + act["training"]
    pl = planned_activity(p)
    return bmr * 1.1 + pl["lifestyle"] + pl["steps"] + pl["training"]


def weight_trend(data):
    """Exponentieel gewogen trendgewicht per dag (dempt water/zout-schommelingen)."""
    ws = sorted(data["weights"], key=lambda x: x["date"])
    if not ws:
        return {}
    by_day = {x["date"]: x["kg"] for x in ws}
    d, end = date.fromisoformat(ws[0]["date"]), date.today()
    trend, t = {}, ws[0]["kg"]
    while d <= end:
        k = str(d)
        if k in by_day:
            t = t + 0.1 * (by_day[k] - t)
        trend[k] = t
        d += timedelta(days=1)
    return trend


def coach_correction(data):
    """Werkelijk verbruik (uit eten + gewichtstrend) minus berekend verbruik."""
    today = date.today()
    days = [str(today - timedelta(days=i)) for i in range(1, COACH_WINDOW + 1)]
    food_days = [d for d in days if sum(num(x["kcal"]) for x in data["food"].get(d, [])) >= 800]  # alleen complete dagen
    trend = weight_trend(data)
    tdays = [d for d in days if d in trend]
    info = dict(correction=0, observed=None, predicted=None, food_days=len(food_days), confidence=0.0,
                msg="")
    if len(food_days) < MIN_FOOD_DAYS or len(tdays) < 14:
        info["msg"] = (f"Coach leert nog: {len(food_days)}/{MIN_FOOD_DAYS} dagen eten gelogd, "
                       f"{len(tdays)}/14 dagen gewichtsdata. Weeg je dagelijks en log je eten.")
        return info
    first, last = min(tdays), max(tdays)
    span = (date.fromisoformat(last) - date.fromisoformat(first)).days or 1
    intake = sum(sum(num(x["kcal"]) for x in data["food"][d]) for d in food_days) / len(food_days)
    observed = intake - (trend[last] - trend[first]) * KCAL_PER_KG / span
    predicted = sum(formula_tdee(data, d) for d in food_days) / len(food_days)
    confidence = min(1.0, len(food_days) / 21)
    corr = max(-600, min(600, (observed - predicted) * confidence))
    info.update(correction=round(corr), observed=round(observed), predicted=round(predicted),
                confidence=confidence)
    richting = "hoger" if corr > 0 else "lager"
    info["msg"] = (f"Je werkelijke verbruik is ±{round(observed)} kcal, {abs(round(observed - predicted))} kcal {richting} "
                   f"dan de formule. Zekerheid {round(confidence * 100)}% → correctie {round(corr):+d} kcal.")
    return info


def nutrition_targets(p, data=None, day=None):
    data = data or {"profile": p, "activity": {}, "sessions": [], "food": {}, "weights": []}
    day = day or str(date.today())
    w, bf, ffm, bmr = body_basics(p)
    act, act_kcal = activity_for_target(data, day)
    coach = coach_correction(data)
    tdee = bmr * 1.1 + act_kcal + coach["correction"]

    rate = num(p.get("rate")) if p.get("rate") not in (None, "") else recommended_rate(p, bf)
    if p["goal"] == "afvallen":
        delta = -(rate / 100 * w) * KCAL_PER_KG / 7
        rate_txt = f"-{rate:g}% gewicht/week (≈{fmt(rate / 100 * w)} kg)"
    elif p["goal"] == "spieropbouw":
        delta = rate * KCAL_PER_KG / 30
        rate_txt = f"+{rate:g} kg/maand"
    else:
        delta, rate_txt = -0.05 * tdee, "recomp (licht tekort)"
    if delta < -0.25 * tdee:  # tekort nooit groter dan 25% (spierbehoud)
        delta = -0.25 * tdee
        rate_txt += " → begrensd op 25% tekort"
    floor = 1500 if p["sex"] == "man" else 1200
    kcal = max(floor, tdee + delta)

    protein = (2.5 if p["goal"] == "afvallen" else 2.2) * ffm
    fat = max(kcal * 0.25 / 9, 0.5 * w)  # minimaal 0.5 g/kg voor hormonen
    carbs = max(0, (kcal - protein * 4 - fat * 9) / 4)
    return dict(kcal=round(kcal), protein=round(protein), fat=round(fat), carbs=round(carbs),
                tdee=round(tdee), bmr=round(bmr), tef=round(bmr * 0.1),
                act_lifestyle=round(act["lifestyle"]), act_steps=round(act["steps"]),
                act_training=round(act["training"]), act_source=act["source"],
                coach=coach, delta=round(delta), steps=int(num(p.get("steps", 7000))),
                bf=round(bf, 1), ffm=round(ffm, 1), p_lo=round(1.65 * ffm), p_hi=round(2.8 * ffm),
                rate_txt=rate_txt, bf_estimated=not num(p.get("bodyfat")))


# --------------------------------------------------------------------------
# 4b. VOEDINGSSCHEMA
#     Kiest per maaltijd een recept dat past bij je eiwit/calorie-verhouding,
#     schaalt de porties naar je dagdoel en herberekent de rest van de dag
#     zodra je iets eet (ook eten buiten het schema).
# --------------------------------------------------------------------------
# per 100 g (of ml): kcal, eiwit, koolhydraten, vet, categorie, allergenen, eenheid (g per stuk) of None
FOODS = {
    "havermout": (370, 13, 59, 7, "plant", {"gluten"}, None),
    "magere kwark": (58, 10, 4, 0.2, "zuivel", {"lactose"}, None),
    "skyr": (63, 11, 4, 0.2, "zuivel", {"lactose"}, None),
    "hüttenkäse": (98, 12, 3, 4, "zuivel", {"lactose"}, None),
    "halfvolle melk": (46, 3.5, 4.8, 1.5, "zuivel", {"lactose"}, None),
    "kaas 30+": (290, 30, 0, 17, "zuivel", {"lactose"}, None),
    "whey eiwitpoeder": (380, 78, 6, 5, "zuivel", {"lactose"}, None),
    "ei": (140, 12.5, 0.7, 10, "ei", set(), 55),
    "kipfilet (rauw)": (110, 23, 0, 1.5, "vlees", set(), None),
    "kipfilet beleg": (105, 22, 1, 1.5, "vlees", set(), None),
    "rundergehakt 5%": (125, 21, 0, 5, "vlees", set(), None),
    "zalmfilet": (200, 20, 0, 13, "vis", set(), None),
    "tonijn in water": (110, 25, 0, 1, "vis", set(), None),
    "tofu": (125, 13, 2, 7, "plant", {"soja"}, None),
    "tempeh": (190, 19, 9, 11, "plant", {"soja"}, None),
    "sojamelk": (40, 3.3, 2.5, 1.8, "plant", {"soja"}, None),
    "soja-yoghurt": (55, 4, 3, 2.5, "plant", {"soja"}, None),
    "vegan eiwitpoeder": (380, 75, 5, 7, "plant", set(), None),
    "linzen (blik)": (100, 8, 14, 0.5, "plant", set(), None),
    "kikkererwten (blik)": (120, 7, 16, 2.5, "plant", set(), None),
    "volkorenbrood": (240, 10, 41, 3, "plant", {"gluten"}, 35),
    "volkoren wrap": (300, 9, 50, 7, "plant", {"gluten"}, 60),
    "rijstwafel": (380, 8, 80, 3, "plant", set(), 8),
    "zilvervliesrijst (droog)": (355, 7.5, 76, 2.5, "plant", set(), None),
    "volkoren pasta (droog)": (350, 13, 65, 2.5, "plant", {"gluten"}, None),
    "aardappelen": (77, 2, 17, 0.1, "plant", set(), None),
    "zoete aardappel": (86, 1.6, 20, 0.1, "plant", set(), None),
    "banaan": (89, 1.1, 23, 0.3, "plant", set(), None),
    "appel": (52, 0.3, 14, 0.2, "plant", set(), None),
    "blauwe bessen": (57, 0.7, 14, 0.3, "plant", set(), None),
    "broccoli": (34, 2.8, 7, 0.4, "plant", set(), None),
    "spinazie": (23, 2.9, 3.6, 0.4, "plant", set(), None),
    "gemengde groente": (30, 2, 5, 0.3, "plant", set(), None),
    "sla/tomaat/komkommer": (18, 1, 3, 0.2, "plant", set(), None),
    "olijfolie": (884, 0, 0, 100, "plant", set(), None),
    "pindakaas": (600, 25, 15, 50, "plant", {"noten"}, None),
    "gemengde noten": (610, 20, 15, 53, "plant", {"noten"}, None),
    "hummus": (280, 7, 12, 23, "plant", set(), None),
}

# naam, type, [(product, gram)]
RECIPES = [
    ("Overnight oats met skyr", "ontbijt", [("havermout", 60), ("skyr", 200), ("blauwe bessen", 75), ("whey eiwitpoeder", 15)]),
    ("Brood met ei en kaas", "ontbijt", [("volkorenbrood", 105), ("ei", 110), ("kaas 30+", 20), ("sla/tomaat/komkommer", 50)]),
    ("Kwarkbowl met banaan", "ontbijt", [("magere kwark", 300), ("banaan", 100), ("havermout", 30), ("gemengde noten", 15)]),
    ("Vegan proteïne-oats", "ontbijt", [("havermout", 60), ("sojamelk", 250), ("vegan eiwitpoeder", 25), ("banaan", 100), ("pindakaas", 10)]),
    ("Omelet met spinazie en aardappel", "ontbijt", [("ei", 165), ("spinazie", 100), ("aardappelen", 150), ("olijfolie", 5)]),
    ("Rijstwafels met hummus + eiwitshake", "ontbijt", [("rijstwafel", 32), ("hummus", 40), ("vegan eiwitpoeder", 30), ("appel", 150)]),
    ("Tofu-scramble wrap", "ontbijt", [("tofu", 150), ("volkoren wrap", 60), ("spinazie", 50), ("olijfolie", 5)]),
    ("Brood met kip en hüttenkäse", "lunch", [("volkorenbrood", 105), ("kipfilet beleg", 60), ("hüttenkäse", 75), ("sla/tomaat/komkommer", 100)]),
    ("Tonijnwraps", "lunch", [("volkoren wrap", 120), ("tonijn in water", 120), ("sla/tomaat/komkommer", 100), ("hummus", 30)]),
    ("Kikkererwtensalade met ei", "lunch", [("kikkererwten (blik)", 150), ("ei", 110), ("sla/tomaat/komkommer", 150), ("olijfolie", 10), ("volkorenbrood", 35)]),
    ("Hummus-tempeh wrap", "lunch", [("volkoren wrap", 120), ("hummus", 40), ("tempeh", 100), ("sla/tomaat/komkommer", 100)]),
    ("Linzensalade met rijst", "lunch", [("linzen (blik)", 200), ("zilvervliesrijst (droog)", 60), ("sla/tomaat/komkommer", 150), ("olijfolie", 10)]),
    ("Aardappelsalade met tonijn", "lunch", [("tonijn in water", 120), ("aardappelen", 250), ("sla/tomaat/komkommer", 150), ("olijfolie", 10)]),
    ("Kip-rijstbak (meal prep)", "lunch", [("kipfilet (rauw)", 150), ("zilvervliesrijst (droog)", 70), ("broccoli", 150), ("olijfolie", 5)]),
    ("Kip met rijst en broccoli", "diner", [("kipfilet (rauw)", 180), ("zilvervliesrijst (droog)", 80), ("broccoli", 200), ("olijfolie", 10)]),
    ("Zalm met aardappelen en groente", "diner", [("zalmfilet", 150), ("aardappelen", 300), ("gemengde groente", 200)]),
    ("Volkoren pasta bolognese", "diner", [("rundergehakt 5%", 150), ("volkoren pasta (droog)", 90), ("gemengde groente", 200), ("olijfolie", 5)]),
    ("Tofu met zoete aardappel", "diner", [("tofu", 200), ("zoete aardappel", 250), ("spinazie", 150), ("olijfolie", 10)]),
    ("Linzencurry met rijst", "diner", [("linzen (blik)", 250), ("zilvervliesrijst (droog)", 70), ("gemengde groente", 200), ("olijfolie", 10)]),
    ("Groente-omelet met aardappel", "diner", [("ei", 165), ("kaas 30+", 30), ("gemengde groente", 200), ("aardappelen", 250)]),
    ("Skyr met blauwe bessen", "snack", [("skyr", 250), ("blauwe bessen", 100)]),
    ("Eiwitshake met banaan", "snack", [("whey eiwitpoeder", 30), ("halfvolle melk", 300), ("banaan", 100)]),
    ("Rijstwafels met pindakaas", "snack", [("rijstwafel", 24), ("pindakaas", 20), ("appel", 150)]),
    ("Hüttenkäse met noten", "snack", [("hüttenkäse", 200), ("gemengde noten", 20)]),
    ("Vegan shake", "snack", [("vegan eiwitpoeder", 30), ("sojamelk", 300)]),
    ("Eiwitshake (water) met banaan", "snack", [("vegan eiwitpoeder", 30), ("banaan", 100)]),
    ("Gekookte eieren met appel", "snack", [("ei", 110), ("appel", 150)]),
    ("Rijstwafels met kipfilet", "snack", [("rijstwafel", 24), ("kipfilet beleg", 75), ("sla/tomaat/komkommer", 50)]),
    ("Soja-yoghurt met fruit", "snack", [("soja-yoghurt", 250), ("blauwe bessen", 100), ("gemengde noten", 10)]),
]

DIETS = {
    "alles": {"vlees", "vis", "zuivel", "ei", "plant"},
    "pescotarisch": {"vis", "zuivel", "ei", "plant"},
    "vegetarisch": {"zuivel", "ei", "plant"},
    "vegan": {"plant"},
}
ALLERGENS = ["lactose", "gluten", "noten", "soja"]
MEAL_SLOTS = {  # maaltijden per dag → (naam, type, aandeel van de dag)
    3: [("Ontbijt", "ontbijt", .25), ("Lunch", "lunch", .35), ("Diner", "diner", .40)],
    4: [("Ontbijt", "ontbijt", .25), ("Lunch", "lunch", .30), ("Tussendoor", "snack", .12), ("Diner", "diner", .33)],
    5: [("Ontbijt", "ontbijt", .20), ("Tussendoor", "snack", .10), ("Lunch", "lunch", .28),
        ("Tussendoor", "snack", .12), ("Diner", "diner", .30)],
}


def recipe_violations(recipe, p):
    allowed = DIETS.get(p.get("diet", "alles"), DIETS["alles"])
    avoid = set(p.get("avoid", []))
    return sum(1 for f, _ in recipe[2] if FOODS[f][4] not in allowed or FOODS[f][5] & avoid)


def recipe_ok(recipe, p):
    return recipe_violations(recipe, p) == 0


def macros(items):
    t = {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    for f, g in items:
        k, pr, c, fa = FOODS[f][:4]
        t["kcal"] += k * g / 100
        t["protein"] += pr * g / 100
        t["carbs"] += c * g / 100
        t["fat"] += fa * g / 100
    return t


def round_portion(food, grams):
    unit = FOODS[food][6]
    if unit:
        n = max(1, round(grams / unit))
        return n * unit, f"{n}×"
    return max(5, round(grams / 5) * 5), ""


def scale_recipe(recipe, kcal_target):
    base = macros(recipe[2])
    s = max(0.4, min(2.2, kcal_target / base["kcal"]))
    items = [(f, round_portion(f, g * s)[0]) for f, g in recipe[2]]
    return items, macros(items)


def day_plan(data, day, targets):
    """Maakt (of herberekent) het schema voor een dag."""
    p = data["profile"]
    slots = MEAL_SLOTS[int(p.get("meals", 4))]
    swaps = data.setdefault("plan_swaps", {}).get(day, {})
    log = data["food"].get(day, [])
    eaten_slots = {x.get("slot") for x in log if x.get("slot") is not None}
    eaten = {k: sum(num(x[k]) for x in log) for k in ("kcal", "protein", "carbs", "fat")}
    open_share = sum(sh for i, (_, _, sh) in enumerate(slots) if i not in eaten_slots) or 1
    kcal_left = max(0, targets["kcal"] - eaten["kcal"])
    prot_left = max(0, targets["protein"] - eaten["protein"])
    want_ratio = (prot_left * 4 / kcal_left) if kcal_left else 0.3

    plan = []
    for i, (label, mtype, share) in enumerate(slots):
        cands = [r for r in RECIPES if r[1] == mtype and recipe_ok(r, p)]
        if not cands:  # niets past perfect: neem de minst afwijkende
            same = [r for r in RECIPES if r[1] == mtype]
            best = min(recipe_violations(r, p) for r in same)
            cands = [r for r in same if recipe_violations(r, p) == best]
        rng = random.Random(f"{day}-{i}-{swaps.get(str(i), 0)}")
        rng.shuffle(cands)

        def ratio(r):
            m = macros(r[2])
            return abs(m["protein"] * 4 / m["kcal"] - want_ratio)

        if swaps.get(str(i), 0) == 0:  # standaard: beste eiwit-match uit 3 willekeurige
            recipe = min(cands[:3], key=ratio)
        else:  # bij 'wissel' gewoon de volgende in de geschudde lijst
            recipe = cands[swaps[str(i)] % len(cands)]
        done = i in eaten_slots
        kcal_slot = kcal_left * share / open_share
        items, m = scale_recipe(recipe, kcal_slot) if not done else ([], None)
        plan.append(dict(slot=i, label=label, name=recipe[0], items=items, macros=m, eaten=done))

    # eiwit-check: tekort aanvullen met de meest eiwitrijke snack-optie
    planned_prot = sum(x["macros"]["protein"] for x in plan if x["macros"])
    gap = prot_left - planned_prot
    if gap > 15 and any(not x["eaten"] for x in plan):
        allowed = DIETS.get(p.get("diet", "alles"), DIETS["alles"])
        avoid = set(p.get("avoid", []))
        for src in ("skyr", "magere kwark", "whey eiwitpoeder", "vegan eiwitpoeder", "tofu"):
            if FOODS[src][4] in allowed and not (FOODS[src][5] & avoid):
                g = round(gap / FOODS[src][1] * 100 / 5) * 5
                extra = [(src, g)]
                # zelfde calorieën: overige open maaltijden iets kleiner maken
                ek = macros(extra)["kcal"]
                open_meals = [x for x in plan if not x["eaten"]]
                tot = sum(x["macros"]["kcal"] for x in open_meals) or 1
                f = max(0.6, (tot - ek) / tot)
                for x in open_meals:
                    x["items"] = [(fd, round_portion(fd, gr * f)[0]) for fd, gr in x["items"]]
                    x["macros"] = macros(x["items"])
                plan.append(dict(slot=len(slots), label="Eiwit-aanvulling", name=f"Extra {src}",
                                 items=extra, macros=macros(extra), eaten=False))
                break
    return plan, eaten


def portion_text(food, grams):
    unit = FOODS[food][6]
    if unit:
        n = round(grams / unit)
        names = {"ei": "ei" if n == 1 else "eieren", "volkorenbrood": "snee" if n == 1 else "sneetjes",
                 "volkoren wrap": "wrap" if n == 1 else "wraps", "rijstwafel": "rijstwafel" + ("" if n == 1 else "s")}
        return f"{n} {names.get(food, food)} ({grams} g)"
    unit_txt = "ml" if food in ("halfvolle melk", "sojamelk") else "g"
    return f"{grams} {unit_txt} {food}"


# --------------------------------------------------------------------------
# 5. USER INTERFACE
# --------------------------------------------------------------------------
def main(page: ft.Page):
    page.title = "FitScience"
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.TEAL)
    page.padding = 0
    data = load_data()
    state = {"timer_task": None, "workout": None, "food_tab": "schema"}

    timer_text = ft.Text("", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.TEAL_200)
    body = ft.Container(expand=True, padding=12)

    def toast(msg):
        page.show_dialog(ft.SnackBar(ft.Text(msg)))

    def title(t, sub=None):
        items = [ft.Text(t, size=24, weight=ft.FontWeight.BOLD)]
        if sub:
            items.append(ft.Text(sub, size=13, color=ft.Colors.GREY_400))
        return ft.Column(items, spacing=2)

    def card(*controls):
        return ft.Card(content=ft.Container(ft.Column(list(controls), spacing=6), padding=12))

    def persist():
        save_data(data)

    # ---------------- rusttimer ----------------
    async def run_timer(seconds):
        try:
            for s in range(seconds, 0, -1):
                timer_text.value = f"⏱ Rust: {s // 60}:{s % 60:02d}"
                page.update()
                await asyncio.sleep(1)
            timer_text.value = "✅ Volgende set!"
            page.update()
        except asyncio.CancelledError:
            pass

    def start_timer(seconds):
        t = state["timer_task"]
        if t and not t.done():
            t.cancel()
        state["timer_task"] = page.run_task(run_timer, seconds)

    # ---------------- PROFIEL ----------------
    def view_profile():
        p = data["profile"] or {}
        num_kb = ft.KeyboardType.NUMBER

        def section(t):
            return ft.Text(t, size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.TEAL_200)

        # -- lichaam
        f_sex = ft.Dropdown(label="Geslacht", value=p.get("sex", "man"), expand=True,
                            options=[ft.DropdownOption("man"), ft.DropdownOption("vrouw")])
        f_age = ft.TextField(label="Leeftijd", value=str(p.get("age", "")), keyboard_type=num_kb, expand=True)
        f_h = ft.TextField(label="Lengte (cm)", value=str(p.get("height", "")), keyboard_type=num_kb, expand=True)
        f_w = ft.TextField(label="Gewicht (kg)", value=str(p.get("weight", "")), keyboard_type=num_kb, expand=True)
        f_bf = ft.TextField(label="Vetpercentage % (leeg = schatten)", value=str(p.get("bodyfat") or ""),
                            keyboard_type=num_kb)
        # -- doel & tempo
        f_goal = ft.Dropdown(label="Doel", value=p.get("goal", "spieropbouw"),
                             options=[ft.DropdownOption(x) for x in ("spieropbouw", "afvallen", "recomp")])
        def rate_options(goal):
            opts = [ft.DropdownOption("auto", "Advies (automatisch)")]
            if goal == "afvallen":
                opts += [ft.DropdownOption(str(r), f"{fmt(r)}% lichaamsgewicht per week") for r in LOSS_RATES]
            elif goal == "spieropbouw":
                opts += [ft.DropdownOption(str(r), f"{fmt(r)} kg per maand") for r in GAIN_RATES]
            return opts

        f_rate = ft.Dropdown(label="Tempo", value=str(p.get("rate") or "auto"), options=rate_options(f_goal.value))
        if f_rate.value not in [o.key for o in f_rate.options]:
            f_rate.value = "auto"

        def on_goal(_):
            f_rate.options = rate_options(f_goal.value)
            f_rate.value = "auto"
            page.update()

        f_goal.on_select = on_goal
        # -- activiteit & stappen
        f_act = ft.Dropdown(label="Dagelijkse activiteit (zonder training)", value=p.get("activity", "zittend"),
                            options=[ft.DropdownOption(k, f"{k} – {v[1]}") for k, v in ACTIVITY.items()])
        f_steps = ft.Dropdown(label="Minimaal stapdoel per dag", value=str(p.get("steps", 7000)),
                              options=[ft.DropdownOption(str(s), f"{s:,}".replace(",", ".")) for s in
                                       range(4000, 15001, 1000)])
        f_mode = ft.Dropdown(label="Hoe beweegt je caloriedoel mee?", value=p.get("calorie_mode", "per dag"),
                             options=[ft.DropdownOption("per dag", "Per dag – meer bewegen = meer eten"),
                                      ft.DropdownOption("weekgemiddelde", "Weekgemiddelde – stabiel doel")])
        # -- voeding
        f_diet = ft.Dropdown(label="Voedingsvoorkeur", value=p.get("diet", "alles"),
                             options=[ft.DropdownOption(x) for x in DIETS])
        f_meals = ft.Dropdown(label="Maaltijden per dag", value=str(p.get("meals", 4)),
                              options=[ft.DropdownOption("3", "3 (ontbijt, lunch, diner)"),
                                       ft.DropdownOption("4", "4 (+ 1 tussendoortje)"),
                                       ft.DropdownOption("5", "5 (+ 2 tussendoortjes)")])
        avoid = set(p.get("avoid", []))
        avoid_checks = [ft.Checkbox(label=a, value=a in avoid) for a in ALLERGENS]
        # -- training
        f_exp = ft.Dropdown(label="Trainingservaring", value=p.get("experience", "beginner"),
                            options=[ft.DropdownOption("beginner", "beginner (< 1 jaar)"),
                                     ft.DropdownOption("gemiddeld", "gemiddeld (1-3 jaar)"),
                                     ft.DropdownOption("gevorderd", "gevorderd (3+ jaar)")])
        f_days = ft.Dropdown(label="Trainingsdagen per week", value=str(p.get("days", 3)),
                             options=[ft.DropdownOption(str(x)) for x in range(2, 7)])
        f_dur = ft.Dropdown(label="Duur per training (min)", value=str(p.get("duration", 60)),
                            options=[ft.DropdownOption(str(x)) for x in (45, 60, 75, 90)])
        f_eq = ft.Dropdown(label="Materiaal", value=p.get("equipment", "gym"),
                           options=[ft.DropdownOption("gym", "Volledige gym"),
                                    ft.DropdownOption("dumbbell", "Thuis met dumbbells"),
                                    ft.DropdownOption("bodyweight", "Alleen lichaamsgewicht")])
        prio = set(p.get("priority", []))
        checks = [ft.Checkbox(label=m, value=m in prio) for m in MUSCLES]
        inj = set(p.get("injuries", []))
        inj_checks = [ft.Checkbox(label=k, value=k in inj) for k in INJURY_EXCLUDE]

        def save(_):
            if not all([f_age.value, f_h.value, f_w.value]):
                toast("Vul leeftijd, lengte en gewicht in.")
                return
            new = dict(sex=f_sex.value, age=num(f_age.value), height=num(f_h.value), weight=num(f_w.value),
                       bodyfat=num(f_bf.value) or None, goal=f_goal.value,
                       rate=None if f_rate.value in (None, "", "auto") else num(f_rate.value),
                       activity=f_act.value, steps=int(f_steps.value), calorie_mode=f_mode.value,
                       diet=f_diet.value, meals=int(f_meals.value), avoid=[c.label for c in avoid_checks if c.value],
                       experience=f_exp.value, days=int(f_days.value),
                       duration=int(f_dur.value), equipment=f_eq.value,
                       priority=[c.label for c in checks if c.value][:2],
                       injuries=[c.label for c in inj_checks if c.value])
            data["profile"] = new
            data["program"] = generate_program(new)
            data["next_day"] = 0
            if not data["weights"]:
                data["weights"].append({"date": str(date.today()), "kg": new["weight"]})
            persist()
            t = nutrition_targets(new, data)
            toast(f"Programma gemaakt · {t['kcal']} kcal · {t['protein']} g eiwit · {t['steps']} stappen")
            nav.selected_index = 1
            show(1)

        return ft.ListView(controls=[
            title("Profiel", "Je antwoorden bepalen programma, calorieën en eiwit"),
            section("1. Lichaam"),
            ft.Row([f_sex, f_age]), ft.Row([f_h, f_w]), f_bf,
            section("2. Doel"),
            f_goal, f_rate,
            section("3. Activiteit buiten de sportschool"),
            f_act, f_steps, f_mode,
            ft.Text("Je stapdoel is de basis. Log je stappen of Garmin-calorieën, dan past je dagdoel zich aan.",
                    size=12, color=ft.Colors.GREY_400),
            section("4. Voeding"),
            f_diet, f_meals,
            ft.Text("Vermijden (allergie/intolerantie):", weight=ft.FontWeight.W_500),
            ft.Row(avoid_checks, wrap=True, spacing=0),
            section("5. Training"),
            f_exp, f_days, f_dur, f_eq,
            ft.Text("Prioriteitsspieren (max 2) – krijgen extra volume:", weight=ft.FontWeight.W_500),
            ft.Row(checks, wrap=True, spacing=0),
            ft.Text("Blessures / klachten – zware oefeningen worden vervangen:", weight=ft.FontWeight.W_500),
            ft.Row(inj_checks, wrap=True, spacing=0),
            ft.FilledButton(content="Opslaan & plan maken", icon=ft.Icons.AUTO_AWESOME, on_click=save),
        ], spacing=10)

    # ---------------- PROGRAMMA ----------------
    def swap_exercise(day_idx, ex_idx):
        ex = data["program"]["days"][day_idx]["exercises"][ex_idx]
        opts = available(ex["muscle"], data["profile"]["equipment"], data["profile"].get("injuries", []))
        names = [o["name"] for o in opts]
        nxt = opts[(names.index(ex["name"]) + 1) % len(opts)] if ex["name"] in names else opts[0]
        ex.update(name=nxt["name"], lo=nxt["lo"], hi=nxt["hi"],
                  rest=150 if nxt["compound"] else 90,
                  inc=2.5 if nxt["eq"] == "gym" else (2.0 if nxt["eq"] == "dumbbell" else 0))
        persist()

    def view_program():
        prog = data["program"]
        if not prog:
            return title("Programma", "Vul eerst je profiel in.")
        items = [title("Jouw programma", f"{prog['split']} · gemaakt {prog['created']}")]
        for di, d in enumerate(prog["days"]):
            rows = []
            for ei, e in enumerate(d["exercises"]):
                def on_swap(_, di=di, ei=ei):
                    swap_exercise(di, ei)
                    show(1)
                rows.append(ft.Row([
                    ft.Column([ft.Text(e["name"], weight=ft.FontWeight.W_500),
                               ft.Text(f"{e['sets']} sets × {e['lo']}-{e['hi']} reps · {e['muscle']} · rust {e['rest']}s",
                                       size=12, color=ft.Colors.GREY_400)], spacing=0, expand=True),
                    ft.IconButton(ft.Icons.SWAP_HORIZ, tooltip="Alternatief", on_click=on_swap),
                ]))
            marker = "  ← volgende" if di == data["next_day"] % len(prog["days"]) else ""
            items.append(card(ft.Text(d["name"] + marker, size=16, weight=ft.FontWeight.BOLD), *rows))
        return ft.ListView(controls=items, spacing=8)

    # ---------------- TRAINING ----------------
    def view_workout():
        prog = data["program"]
        if not prog:
            return title("Training", "Vul eerst je profiel in.")
        di = data["next_day"] % len(prog["days"])
        day = prog["days"][di]
        inputs = []  # (exercise, [(w_field, r_field, check), ...])
        items = [title(day["name"], "Log elke set. Vink af om de rusttimer te starten."), timer_text]
        for ex in day["exercises"]:
            prev = last_performance(data, ex["name"]) or []
            rows, fields = [], []
            for s in range(ex["sets"]):
                pw = fmt(prev[s][0]) if s < len(prev) else ""
                wf = ft.TextField(label="kg", value=pw, width=80, dense=True, keyboard_type=ft.KeyboardType.NUMBER)
                rf = ft.TextField(label="reps", width=70, dense=True, keyboard_type=ft.KeyboardType.NUMBER,
                                  hint_text=f"{ex['lo']}-{ex['hi']}")
                cb = ft.Checkbox(on_change=lambda e, r=ex["rest"]: start_timer(r) if e.control.value else None)
                fields.append((wf, rf, cb))
                rows.append(ft.Row([ft.Text(f"Set {s + 1}", width=48), wf, rf, cb]))
            inputs.append((ex, fields))
            items.append(card(
                ft.Text(ex["name"], size=16, weight=ft.FontWeight.BOLD),
                ft.Text(suggestion(data, ex), size=12, color=ft.Colors.TEAL_100),
                *rows))

        def finish(_):
            entries = []
            for ex, fields in inputs:
                sets = [[num(w.value), int(num(r.value))] for w, r, _ in fields if num(r.value) > 0]
                if sets:
                    entries.append({"name": ex["name"], "sets": sets})
            if not entries:
                toast("Nog niets gelogd.")
                return
            data["sessions"].append({"date": str(date.today()), "day": day["name"], "entries": entries})
            data["next_day"] = di + 1
            persist()
            t = state["timer_task"]
            if t and not t.done():
                t.cancel()
            timer_text.value = ""
            toast(f"Training opgeslagen! ({len(entries)} oefeningen)")
            show(0)

        def skip(_):
            data["next_day"] = di + 1
            persist()
            show(0)

        items.append(ft.Row([
            ft.FilledButton(content="Training afronden", icon=ft.Icons.CHECK, on_click=finish),
            ft.TextButton(content="Dag overslaan", on_click=skip)]))
        return ft.ListView(controls=items, spacing=8)

    # ---------------- VOEDING ----------------
    def view_food():
        if not data["profile"]:
            return title("Voeding", "Vul eerst je profiel in.")
        key = str(date.today())
        t = nutrition_targets(data["profile"], data, key)
        log = data["food"].setdefault(key, [])
        tot = {k: sum(num(x[k]) for x in log) for k in ("kcal", "protein", "carbs", "fat")}

        def bar(label, k, unit):
            frac = min(tot[k] / t[k], 1) if t[k] else 0
            return ft.Column([ft.Text(f"{label}: {round(tot[k])} / {t[k]} {unit}", size=13),
                              ft.ProgressBar(value=frac, color=ft.Colors.TEAL_300)], spacing=2)

        # --- activiteit vandaag (Garmin / telefoon)
        act_log = data.setdefault("activity", {})
        today_act = act_log.get(key, {})
        steps_today = int(num(today_act.get("steps")))
        f_steps = ft.TextField(label="Stappen", expand=True, dense=True,
                               value=str(steps_today or ""), keyboard_type=ft.KeyboardType.NUMBER)
        f_active = ft.TextField(label="Actieve kcal (Garmin)", expand=True, dense=True,
                                value=str(int(num(today_act.get("active_kcal"))) or ""),
                                keyboard_type=ft.KeyboardType.NUMBER)

        def save_activity(_):
            act_log[key] = {"steps": int(num(f_steps.value)), "active_kcal": int(num(f_active.value))}
            persist()
            toast("Activiteit opgeslagen – dagdoel bijgewerkt")
            show(3)

        steps_card = card(
            ft.Text("Activiteit vandaag", weight=ft.FontWeight.BOLD),
            ft.Text(f"{steps_today:,} / {t['steps']:,} stappen".replace(",", "."), size=13),
            ft.ProgressBar(value=min(steps_today / t["steps"], 1) if t["steps"] else 0, color=ft.Colors.AMBER_300),
            ft.Row([f_steps, f_active, ft.IconButton(ft.Icons.SAVE, on_click=save_activity)]),
            ft.Text("Garmin Connect-app → Mijn dag → Calorieën → 'Actief'. Vul 's avonds in (of vaker): "
                    "beweeg je meer dan gepland, dan stijgt je dagdoel mee.", size=11, color=ft.Colors.GREY_400))

        # --- coach
        c = t["coach"]
        coach_card = card(
            ft.Row([ft.Icon(ft.Icons.PSYCHOLOGY, color=ft.Colors.TEAL_200),
                    ft.Text("Coach", weight=ft.FontWeight.BOLD)]),
            ft.Text(c["msg"], size=12),
            ft.ProgressBar(value=c["confidence"], color=ft.Colors.TEAL_300))

        # --- uitleg: hoe is je caloriedoel opgebouwd?
        def line(lbl, v):
            return ft.Row([ft.Text(lbl, size=13, expand=True), ft.Text(f"{v:+d}" if lbl[0] == "+" else str(v), size=13)])

        breakdown = ft.ExpansionTile(
            title=ft.Text("Hoe is mijn dagdoel berekend?", size=14),
            controls=[ft.Container(ft.Column([
                ft.Text(f"Vetpercentage {t['bf']}%{' (geschat)' if t['bf_estimated'] else ''} → vetvrije massa {t['ffm']} kg",
                        size=12, color=ft.Colors.GREY_400),
                line("Ruststofwisseling (Katch-McArdle)", t["bmr"]),
                line("+ Vertering (10%)", t["tef"]),
                ft.Text(f"Activiteit volgens: {t['act_source']}", size=12, color=ft.Colors.GREY_400),
                line("+ Leefstijl", t["act_lifestyle"]),
                line("+ Stappen", t["act_steps"]),
                line("+ Training / horloge", t["act_training"]),
                line("+ Coach-correctie", t["coach"]["correction"]),
                ft.Divider(height=4),
                line("= Verbruik vandaag", t["tdee"]),
                line(f"+ Doel: {t['rate_txt']}", t["delta"]),
                ft.Divider(height=4),
                line("= Dagdoel", t["kcal"]),
                ft.Text(f"Eiwit: {t['protein']} g (bereik {t['p_lo']}–{t['p_hi']} g = 1,65–2,8 g/kg vetvrije massa). "
                        f"Vet ±25% van je calorieën, de rest is koolhydraten.", size=12, color=ft.Colors.GREY_400),
            ], spacing=2), padding=8)])

        name = ft.TextField(label="Product", expand=True, dense=True)
        kc = ft.TextField(label="kcal", width=70, dense=True, keyboard_type=ft.KeyboardType.NUMBER)
        pr = ft.TextField(label="eiwit", width=70, dense=True, keyboard_type=ft.KeyboardType.NUMBER)
        ch = ft.TextField(label="koolh", width=70, dense=True, keyboard_type=ft.KeyboardType.NUMBER)
        ft_ = ft.TextField(label="vet", width=70, dense=True, keyboard_type=ft.KeyboardType.NUMBER)

        def add(item):
            log.append(item)
            persist()
            show(3)

        def add_click(_):
            if not name.value or not kc.value:
                toast("Vul product en kcal in.")
                return
            add({"name": name.value, "kcal": num(kc.value), "protein": num(pr.value),
                 "carbs": num(ch.value), "fat": num(ft_.value)})

        # recent gegeten producten (uit eerdere dagen) als snelknoppen
        recent, seen = [], set()
        for day_items in reversed(list(data["food"].values())):
            for it in reversed(day_items):
                if it["name"] not in seen:
                    seen.add(it["name"])
                    recent.append(it)
        quick = [ft.Chip(label=ft.Text(f"{r['name']} ({round(num(r['kcal']))})"),
                         on_click=lambda _, r=r: add(dict(r))) for r in recent[:8]]

        def remove(i):
            log.pop(i)
            persist()
            show(3)

        log_rows = [ft.Row([ft.Text(f"{x['name']} – {round(num(x['kcal']))} kcal, {round(num(x['protein']))}g eiwit",
                                    expand=True, size=13),
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, on_click=lambda _, i=i: remove(i))])
                    for i, x in enumerate(log)]

        # --- voedingsschema
        def swap_meal(slot):
            sw = data.setdefault("plan_swaps", {}).setdefault(key, {})
            sw[str(slot)] = sw.get(str(slot), 0) + 1
            persist()
            show(3)

        def eat_meal(meal):
            m = meal["macros"]
            log.append({"name": f"{meal['label']}: {meal['name']}", "slot": meal["slot"],
                        **{k: round(m[k], 1) for k in ("kcal", "protein", "carbs", "fat")}})
            persist()
            toast("Gelogd – de rest van je dag is herberekend")
            show(3)

        def plan_controls():
            plan, eaten = day_plan(data, key, t)
            open_meals = [m for m in plan if not m["eaten"]]
            pk = sum(m["macros"]["kcal"] for m in open_meals)
            pp = sum(m["macros"]["protein"] for m in open_meals)
            out = [card(
                ft.Text(f"Nog te eten vandaag: {round(max(0, t['kcal'] - eaten['kcal']))} kcal · "
                        f"{round(max(0, t['protein'] - eaten['protein']))} g eiwit", weight=ft.FontWeight.BOLD),
                ft.Text(f"Schema hieronder: {round(pk)} kcal · {round(pp)} g eiwit. Eet je iets anders? "
                        f"Log het bij 'Logboek', dan schuiven de porties automatisch mee.",
                        size=12, color=ft.Colors.GREY_400))]
            for m in plan:
                if m["eaten"]:
                    out.append(card(ft.Text(f"✓ {m['label']} – gegeten", color=ft.Colors.GREY_500)))
                    continue
                mm = m["macros"]
                out.append(card(
                    ft.Row([ft.Text(m["label"], size=12, color=ft.Colors.TEAL_200, expand=True),
                            ft.Text(f"{round(mm['kcal'])} kcal", size=12)]),
                    ft.Text(m["name"], size=16, weight=ft.FontWeight.BOLD),
                    *[ft.Text("• " + portion_text(f, g), size=13) for f, g in m["items"]],
                    ft.Text(f"E {round(mm['protein'])} g · K {round(mm['carbs'])} g · V {round(mm['fat'])} g",
                            size=12, color=ft.Colors.GREY_400),
                    ft.Row([ft.FilledButton(content="Gegeten", icon=ft.Icons.CHECK,
                                            on_click=lambda _, m=m: eat_meal(m)),
                            ft.TextButton(content="Ander gerecht", icon=ft.Icons.REFRESH,
                                          on_click=lambda _, s=m["slot"]: swap_meal(s))
                            if m["label"] != "Eiwit-aanvulling" else ft.Container()])))
            return out

        def set_tab(tab):
            state["food_tab"] = tab
            show(3)

        tab = state.get("food_tab", "schema")
        tabs = ft.Row([
            (ft.FilledButton if tab == "schema" else ft.OutlinedButton)(
                content="Schema", icon=ft.Icons.RESTAURANT_MENU, on_click=lambda _: set_tab("schema")),
            (ft.FilledButton if tab == "log" else ft.OutlinedButton)(
                content="Logboek", icon=ft.Icons.LIST, on_click=lambda _: set_tab("log"))])
        header = [
            title("Voeding vandaag", f"Dagdoel {t['kcal']} kcal · verbruik ≈ {t['tdee']} kcal · past zich dagelijks aan"),
            card(bar("Calorieën", "kcal", "kcal"), bar("Eiwit", "protein", "g"),
                 bar("Koolhydraten", "carbs", "g"), bar("Vet", "fat", "g"), breakdown),
            tabs]
        if tab == "schema":
            return ft.ListView(controls=header + plan_controls() + [steps_card, coach_card], spacing=8)

        return ft.ListView(controls=header + [
            steps_card, coach_card,
            card(ft.Text("Eten toevoegen", weight=ft.FontWeight.BOLD), name,
                 ft.Row([kc, pr, ch, ft_], wrap=True),
                 ft.FilledButton(content="Toevoegen", icon=ft.Icons.ADD, on_click=add_click),
                 *([ft.Text("Snel opnieuw toevoegen:", size=12), ft.Row(quick, wrap=True)] if quick else [])),
            card(ft.Text("Gelogd", weight=ft.FontWeight.BOLD), *(log_rows or [ft.Text("Nog niets.")])),
        ], spacing=8)

    # ---------------- VOORTGANG ----------------
    def view_progress():
        wf = ft.TextField(label="Gewicht vandaag (kg)", expand=True, dense=True, keyboard_type=ft.KeyboardType.NUMBER)

        def add_weight(_):
            if num(wf.value) <= 0:
                return
            data["weights"] = [x for x in data["weights"] if x["date"] != str(date.today())]
            data["weights"].append({"date": str(date.today()), "kg": num(wf.value)})
            if data["profile"]:  # trendgewicht gebruiken, niet de dagschommeling
                data["profile"]["weight"] = round(weight_trend(data)[str(date.today())], 1)
            persist()
            show(4)

        trend = weight_trend(data)
        ws = sorted(data["weights"], key=lambda x: x["date"])[-10:]
        weight_rows = [ft.Text(f"{x['date']}: {fmt(x['kg'])} kg  (trend {fmt(round(trend.get(x['date'], x['kg']), 1))})",
                               size=13) for x in reversed(ws)]

        # weekoverzicht
        week = [str(date.today() - timedelta(days=i)) for i in range(7)]
        summary = "Log gewicht, eten en activiteit om je weekoverzicht te zien."
        if data["profile"] and len(trend) > 7:
            t_now, t_old = trend[week[0]], trend.get(str(date.today() - timedelta(days=7)), trend[min(trend)])
            change = (t_now - t_old) / t_old * 100
            t = nutrition_targets(data["profile"], data)
            goal_pct = t["delta"] * 7 / KCAL_PER_KG / t_now * 100
            steps = [num(data["activity"].get(d, {}).get("steps")) for d in week if data["activity"].get(d)]
            kcal = [sum(num(x["kcal"]) for x in data["food"][d]) for d in week if data["food"].get(d)]
            summary = (f"Trendgewicht: {change:+.2f}%/week (doel {goal_pct:+.2f}%)\n"
                       f"Gem. stappen: {round(sum(steps) / len(steps)) if steps else '–'} (doel {t['steps']})\n"
                       f"Gem. inname: {round(sum(kcal) / len(kcal)) if kcal else '–'} kcal\n{t['coach']['msg']}")

        best = {}
        for s in data["sessions"]:
            for e in s["entries"]:
                for w, r in e["sets"]:
                    v = e1rm(w, r)
                    first, top = best.get(e["name"], (v, v))
                    best[e["name"]] = (first, max(top, v))
        pr_rows = [ft.Text(f"{n}: e1RM {fmt(top)} kg ({'+' if top >= first else ''}{fmt(top - first)})", size=13)
                   for n, (first, top) in sorted(best.items())]

        hist = [ft.Text(f"{s['date']} – {s['day']} ({len(s['entries'])} oef.)", size=13)
                for s in reversed(data["sessions"][-15:])]

        return ft.ListView(controls=[
            title("Voortgang", f"{len(data['sessions'])} trainingen gelogd"),
            card(ft.Text("Lichaamsgewicht", weight=ft.FontWeight.BOLD),
                 ft.Row([wf, ft.IconButton(ft.Icons.ADD, on_click=add_weight)]), *weight_rows,
                 ft.Text("Weeg je elke ochtend: de coach gebruikt het trendgewicht."
                         , size=11, color=ft.Colors.GREY_400)),
            card(ft.Text("Deze week", weight=ft.FontWeight.BOLD), ft.Text(summary, size=13)),
            card(ft.Text("Kracht – geschatte 1RM (sinds start)", weight=ft.FontWeight.BOLD),
                 *(pr_rows or [ft.Text("Nog geen trainingen.")])),
            card(ft.Text("Historie", weight=ft.FontWeight.BOLD), *(hist or [ft.Text("—")])),
        ], spacing=8)

    # ---------------- navigatie ----------------
    views = [view_workout, view_program, view_profile, view_food, view_progress]

    def show(i):
        body.content = views[i]()
        page.update()

    nav = ft.NavigationBar(
        selected_index=0 if data["profile"] else 2,
        on_change=lambda e: show(e.control.selected_index),
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.FITNESS_CENTER, label="Training"),
            ft.NavigationBarDestination(icon=ft.Icons.CALENDAR_MONTH, label="Programma"),
            ft.NavigationBarDestination(icon=ft.Icons.PERSON, label="Profiel"),
            ft.NavigationBarDestination(icon=ft.Icons.RESTAURANT, label="Voeding"),
            ft.NavigationBarDestination(icon=ft.Icons.SHOW_CHART, label="Voortgang"),
        ])
    page.navigation_bar = nav
    page.add(ft.SafeArea(body, expand=True))
    show(nav.selected_index)


if __name__ == "__main__":
    ft.run(main)
