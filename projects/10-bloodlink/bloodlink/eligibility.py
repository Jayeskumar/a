"""Whole-blood donor eligibility as explicit, named rules (see config for sources)."""
import datetime as dt

from .config import AGE_MAX, AGE_MIN, HB_MIN_G_DL, MIN_INTERVAL_DAYS, WEIGHT_MIN_KG


class ProfileError(ValueError):
    pass


def parse_date(value, field="date"):
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ProfileError("%s must be an ISO date like 2026-07-15" % field)


def normalize_sex(sex):
    s = str(sex or "").strip().upper()[:1]
    if s not in ("M", "F", "O"):
        raise ProfileError("sex must be M, F or O")
    return s


def interval_days(sex):
    # 'O' (other / not stated) gets the longer interval: the conservative choice.
    return MIN_INTERVAL_DAYS.get(sex, max(MIN_INTERVAL_DAYS.values()))


def age_on(dob, today):
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _add_years(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year + years, day=28)


def evaluate(profile, today):
    """Apply every rule; return pass/fail per rule, reasons and the next eligible date.

    profile keys: sex, age or dob, weight_kg, last_donation (date|None), hb (optional),
    unwell (bool, optional), deferred_until (date, optional).
    """
    if not isinstance(profile, dict):
        raise ProfileError("profile must be an object")
    sex = normalize_sex(profile.get("sex"))
    dob = parse_date(profile.get("dob"), "dob")
    age = profile.get("age")
    if dob is not None:
        if dob > today:
            raise ProfileError("date of birth is in the future")
        age = age_on(dob, today)
    if age is None:
        raise ProfileError("age or dob is required")
    try:
        age = int(age)
        weight = float(profile.get("weight_kg"))
    except (TypeError, ValueError):
        raise ProfileError("age and weight_kg must be numbers")
    if not (0 < age < 120) or not (0 < weight < 300):
        raise ProfileError("age or weight out of range")
    last = parse_date(profile.get("last_donation"), "last_donation")
    if last is not None and last > today:
        raise ProfileError("last donation date is in the future")
    hb = profile.get("hb")
    if hb not in (None, ""):
        try:
            hb = float(hb)
        except (TypeError, ValueError):
            raise ProfileError("hb must be a number in g/dL")
        if not (3 <= hb <= 25):
            raise ProfileError("hb out of range (g/dL)")
    else:
        hb = None
    deferred = parse_date(profile.get("deferred_until"), "deferred_until")

    rules = []
    dates = []          # dates at which a failing temporary rule clears
    permanent = False   # a failing rule with no clearing date

    # 1. Age
    if age < AGE_MIN:
        when = _add_years(dob, AGE_MIN) if dob else None
        rules.append(_rule("age", "Age %d-%d" % (AGE_MIN, AGE_MAX), False,
                           "Age %d is below %d" % (age, AGE_MIN), when))
        if when:
            dates.append(when)
        else:
            dates.append(today + dt.timedelta(days=365 * (AGE_MIN - age)))
    elif age > AGE_MAX:
        rules.append(_rule("age", "Age %d-%d" % (AGE_MIN, AGE_MAX), False,
                           "Age %d is above %d" % (age, AGE_MAX)))
        permanent = True
    else:
        rules.append(_rule("age", "Age %d-%d" % (AGE_MIN, AGE_MAX), True, "Age %d" % age))

    # 2. Weight
    ok = weight >= WEIGHT_MIN_KG
    rules.append(_rule("weight", "Weight >= %g kg" % WEIGHT_MIN_KG, ok,
                       "%.1f kg" % weight + ("" if ok else " is below %g kg" % WEIGHT_MIN_KG)))
    if not ok:
        permanent = True

    # 3. Interval since last whole-blood donation
    need = interval_days(sex)
    label = "%d days since last donation (%s)" % (need, {"M": "men", "F": "women"}.get(sex, "conservative"))
    if last is None:
        rules.append(_rule("interval", label, True, "No previous donation recorded"))
    else:
        since = (today - last).days
        when = last + dt.timedelta(days=need)
        if since >= need:
            rules.append(_rule("interval", label, True, "Last donated %d days ago" % since))
        else:
            rules.append(_rule("interval", label, False,
                               "Donated %d days ago; wait %d more days" % (since, need - since), when))
            dates.append(when)

    # 4. Haemoglobin (only if reported)
    if hb is None:
        rules.append(_rule("hb", "Hb >= %g g/dL" % HB_MIN_G_DL, None, "Checked at the blood bank"))
    elif hb >= HB_MIN_G_DL:
        rules.append(_rule("hb", "Hb >= %g g/dL" % HB_MIN_G_DL, True, "Hb %.1f g/dL" % hb))
    else:
        rules.append(_rule("hb", "Hb >= %g g/dL" % HB_MIN_G_DL, False,
                           "Hb %.1f g/dL is low - recheck after iron-rich diet / doctor advice" % hb))
        permanent = True  # no predictable clearing date

    # 5. Feeling unwell today / temporary deferral
    if profile.get("unwell"):
        when = today + dt.timedelta(days=1)
        rules.append(_rule("health", "Feeling well today", False,
                           "Unwell today - donate only when fully recovered", when))
        dates.append(when)
    else:
        rules.append(_rule("health", "Feeling well today", True, "No illness reported"))
    if deferred and deferred > today:
        rules.append(_rule("deferral", "No temporary deferral", False,
                           "Deferred by blood bank until %s" % deferred.isoformat(), deferred))
        dates.append(deferred)

    failing = [r for r in rules if r["pass"] is False]
    eligible = not failing
    next_date = None
    if not eligible and not permanent and dates:
        next_date = max(dates)
    return {
        "eligible": eligible,
        "sex": sex,
        "age": age,
        "rules": rules,
        "reasons": [r["detail"] for r in failing],
        "codes": [r["code"] for r in failing],
        "next_eligible_date": (today if eligible else next_date).isoformat() if (eligible or next_date) else None,
        "days_until_eligible": 0 if eligible else ((next_date - today).days if next_date else None),
        "interval_days": need,
    }


def _rule(code, label, passed, detail, clears_on=None):
    return {"code": code, "label": label, "pass": passed, "detail": detail,
            "clears_on": clears_on.isoformat() if clears_on else None}


def donor_profile(donor):
    """Registry record -> eligibility profile."""
    return {
        "sex": donor["sex"],
        "dob": donor["dob"],
        "weight_kg": donor["weight_kg"],
        "last_donation": donor.get("last_donation"),
        "deferred_until": donor.get("deferred_until"),
    }
