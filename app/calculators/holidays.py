from datetime import date, timedelta


def easter_date(year: int) -> date:
    """Beregn påskedag via anonym Gregoriansk Computus."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day   = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def get_holidays_for_year(year: int) -> list:
    """Returnér liste af helligdage for ét år (14 rækker)."""
    easter = easter_date(year)

    fixed = [
        (date(year,  1,  1), "Nytårsdag",            None),
        (date(year,  5,  1), "1. maj",                "12:00"),
        (date(year,  6,  5), "Grundlovsdag",          "12:00"),
        (date(year, 12, 24), "Juleaftensdag",         None),
        (date(year, 12, 25), "1. juledag",            None),
        (date(year, 12, 26), "2. juledag",            None),
        (date(year, 12, 31), "Nytårsaftensdag",       None),
    ]

    moving = [
        (easter - timedelta(days=3),  "Skærtorsdag",           None),
        (easter - timedelta(days=2),  "Langfredag",             None),
        (easter,                      "Påskedag",               None),
        (easter + timedelta(days=1),  "2. påskedag",            None),
        (easter + timedelta(days=39), "Kristi Himmelfartsdag",  None),
        (easter + timedelta(days=49), "Pinsedag",               None),
        (easter + timedelta(days=50), "2. pinsedag",            None),
    ]

    seen = set()
    result = []
    for d, n, hf in fixed + moving:
        if d not in seen:
            seen.add(d)
            result.append({"date": d, "name": n, "half_day_from": hf, "is_auto_generated": True})
    return result
