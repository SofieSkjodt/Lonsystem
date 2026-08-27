import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from routers.activities import _correct_all_segments_list


def check(name, segments, expected_segments, expected_count):
    result, count = _correct_all_segments_list(segments)
    ok = result == expected_segments and count == expected_count
    status = "OK" if ok else "FEJL"
    print(f"{name}: {status} - fik {result}, {count} (forventet {expected_segments}, {expected_count})")


# Blandede segmenter: kun de to 'rest'-segmenter rettes, driving/work urørt
check(
    "Blandede segmenter",
    [
        ["2026-06-08T06:00:00", "2026-06-08T06:45:00", "driving"],
        ["2026-06-08T06:45:00", "2026-06-08T07:15:00", "rest"],
        ["2026-06-08T07:15:00", "2026-06-08T08:00:00", "work"],
        ["2026-06-08T08:00:00", "2026-06-08T08:30:00", "rest"],
    ],
    [
        ["2026-06-08T06:00:00", "2026-06-08T06:45:00", "driving"],
        ["2026-06-08T06:45:00", "2026-06-08T07:15:00", "work", "rest"],
        ["2026-06-08T07:15:00", "2026-06-08T08:00:00", "work"],
        ["2026-06-08T08:00:00", "2026-06-08T08:30:00", "work", "rest"],
    ],
    2,
)

# Et segment er allerede rettet (len==4) -> springes over, kun det andet rettes
check(
    "Allerede rettet segment springes over",
    [
        ["2026-06-08T06:00:00", "2026-06-08T06:30:00", "work", "rest"],
        ["2026-06-08T06:30:00", "2026-06-08T07:00:00", "rest"],
    ],
    [
        ["2026-06-08T06:00:00", "2026-06-08T06:30:00", "work", "rest"],
        ["2026-06-08T06:30:00", "2026-06-08T07:00:00", "work", "rest"],
    ],
    1,
)

# Ingen pause-segmenter overhovedet -> 0 rettet, listen uændret
check(
    "Ingen pauser",
    [["2026-06-08T06:00:00", "2026-06-08T06:45:00", "driving"]],
    [["2026-06-08T06:00:00", "2026-06-08T06:45:00", "driving"]],
    0,
)

# Tom liste -> 0 rettet, tom liste tilbage
check("Tom liste", [], [], 0)
