"""
Custom parser for EU digital tachograph .ddd driver card files.
No external dependencies.

Format: EU Regulation 165/2014 / Commission Regulation 2016/799 Annex II.

Daily record structure (consecutive, variable length):
  2 bytes: previousRecordLength
  2 bytes: recordLength (total bytes incl. this 4-byte header)
  4 bytes: date (Unix timestamp, midnight UTC)
  2 bytes: dailyPresenceCounter
  2 bytes: activityDayDistance (km)
  N*2 bytes: ActivityChangeInfo records

ActivityChangeInfo (2 bytes, big-endian):
  bit 15:     slot (0=driver/chauffør, 1=co-driver/medchauffør)
  bit 14:     driverStatus (0=single, 1=crew)
  bit 13:     cardPresent
  bits 12-11: activity (00=rest, 01=availability, 10=work, 11=driving)
  bits 10-0:  minutes from midnight (0-1439), also relative to UTC midnight

Alle klokkeslæt i filen (dato og minutter) er UTC. Outputtet fra denne parser
konverteres til dansk lokal tid (Europe/Copenhagen, DST-korrekt) i _build_activities.
"""

import re
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ACTIVITY_REST = 0
ACTIVITY_AVAILABILITY = 1
ACTIVITY_WORK = 2
ACTIVITY_DRIVING = 3

# Minimum record size: 4-byte header + date(4) + counter(2) + distance(2) = 12
MIN_RECORD_SIZE = 12
# Plausible timestamp range: 2020-01-01 to 2035-01-01
TS_MIN = 1577836800
TS_MAX = 2051222400

_UTC = ZoneInfo("UTC")
_COPENHAGEN = ZoneInfo("Europe/Copenhagen")


def _utc_to_local(dt: datetime) -> datetime:
    """Konverter en naiv UTC-datetime (fra filens rå tidsstempler) til naiv dansk lokal tid."""
    return dt.replace(tzinfo=_UTC).astimezone(_COPENHAGEN).replace(tzinfo=None)


@dataclass
class ParsedActivity:
    tachograph_card_number: str
    start_time: datetime
    end_time: datetime
    availability_time_pct: Decimal | None
    rest_pause_pct: Decimal | None
    other_work_pct: Decimal | None
    driving_pct: Decimal | None
    source_file: str
    vehicle_registration: str | None = None
    km_start: int | None = None
    km_end: int | None = None
    # Faktiske pauseintervaller (hvil/pause) mellem start og slut,
    # så pauser kan fratrækkes i det tidsrum de afholdes
    pause_intervals: list[tuple[datetime, datetime]] = None
    # Alle hændelsessegmenter: (start, slut, aktivitet) hvor aktivitet er
    # "rest" | "availability" | "work" | "driving"
    segments: list[tuple[datetime, datetime, str]] = None
    # Filen ser ud til at være hentet midt i vagten (0 km registreret den dag,
    # og dagen slutter ikke i hvil) – resten af dagen mangler formentlig
    is_likely_incomplete: bool = False


def parse_ddd_file(file_path: Path) -> list[ParsedActivity]:
    """Parse a .ddd driver card file and return activities per working day."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "rb") as f:
        data = f.read()

    card_number = _extract_card_number(data)
    vehicle_reg = _extract_vehicle_registration(data)
    daily_odometer = _extract_daily_odometer(data)
    daily_records = _find_all_daily_records(data)

    if not daily_records:
        return []

    return _build_activities(card_number, vehicle_reg, daily_odometer, daily_records, str(file_path))


def scan_ddd_folder(folder_path: Path) -> tuple[list[tuple[Path, list[ParsedActivity]]], list[str]]:
    """
    Scan folder (inkl. alle undermapper) for .ddd-filer.
    Returns (results, errors) – ikke-parsebare filer rapporteres som fejl i
    stedet for kun at blive printet til serverkonsollen.
    """
    results = []
    errors = []
    # set(): på filsystemer uden versalfølsomhed (Windows) matcher "*.ddd" og
    # "*.DDD" de samme filer, og ville ellers behandle hver fil to gange.
    ddd_files = sorted(
        set(folder_path.rglob("*.ddd")) | set(folder_path.rglob("*.DDD"))
    )
    for f in ddd_files:
        try:
            activities = parse_ddd_file(f)
            results.append((f, activities))
        except Exception as e:
            errors.append(f"{f.name}: fejl ved import ({e})")
    return results, errors


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_vehicle_registration(data: bytes) -> str | None:
    """
    Forsøger at finde køretøjets registreringsnummer i .ddd-filen.
    I EU-tachografformatet (Reg. 165/2014) gemmes registreringsnummeret i
    CardVehiclesUsed-blokken som: 1 byte codePage (typisk 0x00) + ASCII-streng.
    Vi søger efter dette mønster heuristisk.
    """
    # Primær søgning: codePage-byte (0x00 eller 0x01) efterfulgt af pladelignenede streng
    for match in re.finditer(rb'[\x00\x01]([A-Z][A-Z0-9]{4,11})', data):
        candidate = match.group(1).decode("ascii")
        # Skal indeholde mindst ét bogstav og ét ciffer
        if re.search(r'[A-Z]', candidate) and re.search(r'\d', candidate):
            # Undgå at matche kortnummeret (2 bogstaver + 14 cifre)
            if not re.fullmatch(r'[A-Z]{2}\d{14}', candidate):
                return candidate
    return None


def _extract_card_number(data: bytes) -> str:
    """
    Find the tachograph card number in the file.

    Kortnummerfeltet (CardNumber) er ifølge EU-tachografspecifikationen 16 tegn:
    14 tegn driverIdentification + 1 ciffer udskiftningsindeks + 1 ciffer
    fornyelsesindeks. De sidste 2 cifre hører ikke til det stabile kortnummer
    (de ændrer sig når kortet fornys/udskiftes), så vi matcher det fulde
    16-tegns felt for sikker lokalisering, men returnerer kun de første 14 tegn.
    """
    match = re.search(rb'[A-Z]{2}\d{14}', data)
    if match:
        return match.group(0)[:14].decode("ascii")
    return "UNKNOWN"


def _extract_daily_odometer(data: bytes) -> dict[int, int]:
    """
    Finder tabellen med km-standen ved starten af hver køretur/dag.

    Bekræftet ved byte-analyse (2026-07-02): filen indeholder et kompakt array
    af 20-byte elementer i kronologisk rækkefølge:
      3 bytes:  km-stand (big-endian)
      4 bytes:  tidsstempel (TimeReal, UTC) – matcher dagens beregnede
                dagsstart (day_start_minute) til minuttet
      13 bytes: øvrige data (bl.a. køretøjsregistrering ved køretøjsskift)

    Der er ingen pålidelig fast start-offset eller TLV-tag at søge efter, så
    tabellen findes ved kæde-validering: det længste sammenhængende forløb af
    plausible (km, tidsstempel)-par med præcis 20 bytes' afstand. Tilfældige
    byte-sekvenser andre steder i filen danner ikke kæder af denne længde.

    OBS: Førerkort gemmer kun et begrænset antal køretøjsbrug-poster, så
    tabellen dækker typisk ikke hele kortets historik – ældre dage vil derfor
    ikke have km-data.

    Returnerer {tidsstempel: km-stand}.
    """
    STRIDE = 20
    MIN_CHAIN_LENGTH = 5

    def read_pair(pos: int) -> tuple[int, int] | None:
        if pos < 0 or pos + 7 > len(data):
            return None
        odo = struct.unpack_from(">I", b"\x00" + data[pos:pos + 3])[0]
        if not (1 <= odo <= 2_000_000):
            return None
        ts = struct.unpack_from(">I", data, pos + 3)[0]
        if not (TS_MIN <= ts <= TS_MAX):
            return None
        return odo, ts

    visited: set[int] = set()
    best_chain: list[tuple[int, int]] = []
    for start in range(0, len(data) - 7):
        if start in visited:
            continue
        pair = read_pair(start)
        if pair is None:
            continue
        chain = [pair]
        pos = start + STRIDE
        while True:
            nxt = read_pair(pos)
            if nxt is None:
                break
            chain.append(nxt)
            visited.add(pos)
            pos += STRIDE
        if len(chain) >= MIN_CHAIN_LENGTH and len(chain) > len(best_chain):
            best_chain = chain

    return {ts: odo for odo, ts in best_chain}


def _lookup_daily_km(expected_ts: int, odometer_table: dict[int, int], tolerance_sec: int = 120) -> int | None:
    """Find km-standen tættest på det forventede tidsstempel (dagens beregnede start), inden for tolerance."""
    best = None
    best_diff = None
    for ts, odo in odometer_table.items():
        diff = abs(ts - expected_ts)
        if diff <= tolerance_sec and (best_diff is None or diff < best_diff):
            best = odo
            best_diff = diff
    return best


def _is_daily_chain_start(data: bytes, pos: int) -> bool:
    """
    Tjekker om `pos` er starten på mindst 2 sammenhængende gyldige dags-records.
    Heuristik: et record (min. 12 byte header) med gyldigt tidsstempel, hvor det
    næste record starter umiddelbart derefter, dets previousRecordLength matcher
    dette records length, og dets tidsstempel er inden for 7 dage af det første.
    """
    if pos + 28 > len(data):
        return False
    rec_len = struct.unpack_from(">H", data, pos + 2)[0]
    if rec_len < MIN_RECORD_SIZE or rec_len > 4096:
        return False
    if pos + rec_len + 4 > len(data):
        return False
    ts = struct.unpack_from(">I", data, pos + 4)[0]
    if not (TS_MIN <= ts <= TS_MAX):
        return False
    next_pos = pos + rec_len
    if next_pos + 4 > len(data):
        return False
    next_prev_len = struct.unpack_from(">H", data, next_pos)[0]
    next_rec_len  = struct.unpack_from(">H", data, next_pos + 2)[0]
    if next_prev_len != rec_len:
        return False
    if next_rec_len < MIN_RECORD_SIZE or next_rec_len > 4096:
        return False
    next_ts = struct.unpack_from(">I", data, next_pos + 4)[0]
    if not (TS_MIN <= next_ts <= TS_MAX):
        return False
    if abs(int(next_ts) - int(ts)) > 7 * 86400:
        return False
    return True


def _walk_daily_chain(data: bytes, start: int) -> list[tuple[datetime, int, bytes]]:
    """Walk consecutive daily records fra `start` til kæden brydes. Returns [(date, distance_km, activity_bytes), ...]."""
    records = []
    pos = start
    while pos + MIN_RECORD_SIZE <= len(data):
        rec_len = struct.unpack_from(">H", data, pos + 2)[0]
        if rec_len < MIN_RECORD_SIZE or rec_len > 4096:
            break
        if pos + rec_len > len(data):
            break
        ts       = struct.unpack_from(">I", data, pos + 4)[0]
        distance = struct.unpack_from(">H", data, pos + 10)[0]
        if not (TS_MIN <= ts <= TS_MAX):
            break

        # Activity bytes start at offset 12 within the record
        activity_bytes = data[pos + 12 : pos + rec_len]
        dt = datetime.utcfromtimestamp(ts)
        records.append((dt, distance, activity_bytes))
        pos += rec_len

    return records


def _find_all_daily_records(data: bytes) -> list[tuple[datetime, int, bytes]]:
    """
    Find ALLE dags-records i filen, ikke kun den første sammenhængende kæde.

    Tachograf-kort gemmer aktivitetsdata i en cirkulær buffer, og .ddd-filer kan
    indeholde flere separate og/eller duplikerede blokke med dags-records – ikke
    nødvendigvis i kronologisk byte-rækkefølge (bekræftet ved byte-analyse
    2026-07-26: samme fils data for en periode lå adskilt fra data for en
    efterfølgende periode, med en helt anden byteposition). En enkelt lineær
    scanning fra byte 0 (den tidligere `_find_daily_records_start`) kan derfor
    lande på en kort, ufuldstændig kæde og stoppe alt for tidligt, selvom resten
    af dagene findes andetsteds i filen.

    Denne funktion scanner hele filen for samtlige gyldige kæde-startpunkter,
    vandrer hver kæde, og fletter resultaterne pr. dato – ved konflikt (samme
    dato fundet i flere kæder) beholdes den mest fuldstændige version (flest
    aktivitetsbytes).

    En gyldig kæde starter typisk ved hvert record i kæden (ikke kun ved
    kædens første record), så uden optimering ville samme kæde blive
    genvandret fra hver position i den (O(kædelængde²)). Allerede besøgte
    record-startpositioner markeres derfor og springes over, så hele filen
    kun gennemgås én gang (O(filstørrelse)) – samme teknik som i
    `_extract_daily_odometer`.
    """
    merged: dict = {}
    visited: set[int] = set()
    n = len(data)
    pos = 0
    while pos < n - 28:
        if pos not in visited and _is_daily_chain_start(data, pos):
            walk_pos = pos
            for dt, distance, activity_bytes in _walk_daily_chain(data, pos):
                visited.add(walk_pos)
                walk_pos += len(activity_bytes) + 12
                key = dt.date()
                existing = merged.get(key)
                if existing is None or len(activity_bytes) > len(existing[2]):
                    merged[key] = (dt, distance, activity_bytes)
        pos += 1
    return [merged[k] for k in sorted(merged)]


def _decode_activity_changes(activity_bytes: bytes) -> list[tuple[int, int]]:
    """
    Decode 2-byte ActivityChangeInfo records.
    Returns sorted list of (minutes_from_midnight, activity) for driver slot only.
    """
    changes = []
    for i in range(0, len(activity_bytes) - 1, 2):
        word = struct.unpack_from(">H", activity_bytes, i)[0]
        slot     = (word >> 15) & 0x1
        activity = (word >> 11) & 0x3   # bits 12-11
        minutes  = word & 0x7FF          # bits 10-0
        if slot != 0:
            continue
        if minutes > 1439:
            continue
        changes.append((minutes, activity))
    # Sort by time and deduplicate
    seen: set[tuple[int, int]] = set()
    result = []
    for m, a in sorted(changes):
        if (m, a) not in seen:
            seen.add((m, a))
            result.append((m, a))
    return result


def _build_activities(
    card_number: str,
    vehicle_registration: str | None,
    daily_odometer: dict[int, int],
    daily_records: list[tuple[datetime, int, bytes]],
    source_file: str,
) -> list[ParsedActivity]:
    """Convert daily records into ParsedActivity objects for working days."""
    activities = []

    for day_dt, distance, activity_bytes in daily_records:
        if distance == 0 and len(activity_bytes) <= 2:
            continue  # Rest day with no actual activity changes

        changes = _decode_activity_changes(activity_bytes)
        if not changes:
            continue

        # Find first non-rest minute (afgør om dagen overhovedet har arbejde)
        first_nonrest_minute = next(
            (m for m, a in changes if a != ACTIVITY_REST), None
        )
        if first_nonrest_minute is None:
            continue

        # changes[0] er altid en "rest"-post ved minut 0 (videreført status fra
        # forrige dag, ikke en reel pause). Er der en ekstra hvil-post lige
        # derefter, er det chaufførens faktiske dagsstart (kort pause inden
        # arbejdet begynder) – den skal indgå i den viste arbejdstid, men
        # tælles stadig som ubetalt pause (ender i pause_intervals nedenfor).
        day_start_minute = first_nonrest_minute
        if len(changes) > 1 and changes[0][0] == 0 and changes[1][1] == ACTIVITY_REST:
            day_start_minute = changes[1][0]

        last_minute = changes[-1][0]
        if last_minute <= day_start_minute:
            continue

        start_time = _utc_to_local(day_dt + timedelta(
            hours=day_start_minute // 60,
            minutes=day_start_minute % 60,
        ))
        end_time = _utc_to_local(day_dt + timedelta(
            hours=last_minute // 60,
            minutes=last_minute % 60,
        ))

        # Calculate time in each activity between day start and end
        total_minutes = last_minute - day_start_minute
        if total_minutes <= 0:
            continue

        ACTIVITY_NAMES = {
            ACTIVITY_REST: "rest",
            ACTIVITY_AVAILABILITY: "availability",
            ACTIVITY_WORK: "work",
            ACTIVITY_DRIVING: "driving",
        }
        mins = {ACTIVITY_REST: 0, ACTIVITY_AVAILABILITY: 0, ACTIVITY_WORK: 0, ACTIVITY_DRIVING: 0}
        pause_intervals: list[tuple[datetime, datetime]] = []
        segments: list[tuple[datetime, datetime, str]] = []
        for i, (minute, activity) in enumerate(changes):
            if minute < day_start_minute:
                continue
            next_minute = changes[i + 1][0] if i + 1 < len(changes) else last_minute
            seg_start = max(minute, day_start_minute)
            seg_end = min(next_minute, last_minute)
            duration = max(0, seg_end - seg_start)
            if activity in mins:
                mins[activity] += duration
            if duration > 0:
                seg = (
                    _utc_to_local(day_dt + timedelta(minutes=seg_start)),
                    _utc_to_local(day_dt + timedelta(minutes=seg_end)),
                )
                segments.append((seg[0], seg[1], ACTIVITY_NAMES.get(activity, "work")))
                if activity == ACTIVITY_REST:
                    pause_intervals.append(seg)

        def pct(m: int) -> Decimal | None:
            return Decimal(str(round(m / total_minutes * 100, 2))) if total_minutes else None

        # Bekræftet på flere reelle filer (2026-07): når kortet udlæses midt i
        # en vagt, er dagens km-distance endnu ikke skrevet (0), og dagen
        # slutter ikke tilbage i hvil – begge tegn samtidig er et pålideligt
        # signal om at resten af dagen mangler i filen.
        is_likely_incomplete = (distance == 0 and changes[-1][1] != ACTIVITY_REST)

        # km_start = km-stand fra den separate dagsstart-tabel (tættest på dagens
        # beregnede startminut). km_end udledes af dagens egen kørte distance
        # (activityDayDistance) i stedet for at antage kontinuitet til næste
        # tabelpost, så det også virker korrekt ved køretøjsskift.
        day_start_ts = int(
            (day_dt + timedelta(minutes=day_start_minute)).replace(tzinfo=timezone.utc).timestamp()
        )
        km_start = _lookup_daily_km(day_start_ts, daily_odometer)
        km_end = km_start + distance if km_start is not None and distance else None

        activities.append(
            ParsedActivity(
                tachograph_card_number=card_number,
                start_time=start_time,
                end_time=end_time,
                availability_time_pct=pct(mins[ACTIVITY_AVAILABILITY]),
                rest_pause_pct=pct(mins[ACTIVITY_REST]),
                other_work_pct=pct(mins[ACTIVITY_WORK]),
                driving_pct=pct(mins[ACTIVITY_DRIVING]),
                source_file=source_file,
                vehicle_registration=vehicle_registration,
                km_start=km_start,
                km_end=km_end,
                pause_intervals=pause_intervals,
                segments=segments,
                is_likely_incomplete=is_likely_incomplete,
            )
        )

    return activities


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path

    base = Path(__file__).resolve().parent.parent
    ddd_files = (
        list(base.glob("*.ddd"))
        + list(base.glob("*.DDD"))
        + list((base / "ddd_input").glob("*.ddd"))
        + list((base / "ddd_input").glob("*.DDD"))
    )

    if not ddd_files:
        print("Ingen .ddd filer fundet.")
    else:
        for f in ddd_files:
            print(f"\n{'='*65}")
            print(f"Fil: {f.name}")
            try:
                acts = parse_ddd_file(f)
                if acts:
                    print(f"Kortnummer : {acts[0].tachograph_card_number}")
                print(f"Arbejdsdage: {len(acts)}")
                for a in acts:
                    total_h = (a.end_time - a.start_time).seconds // 3600
                    total_m = ((a.end_time - a.start_time).seconds % 3600) // 60
                    print(
                        f"  {a.start_time.strftime('%Y-%m-%d %H:%M')} -> "
                        f"{a.end_time.strftime('%H:%M')}  "
                        f"({total_h}t{total_m:02d}m)  "
                        f"hvil={a.rest_pause_pct}%  "
                        f"rådigh={a.availability_time_pct}%  "
                        f"arb={a.other_work_pct}%  "
                        f"koersel={a.driving_pct}%"
                    )
            except Exception as e:
                import traceback
                print(f"FEJL: {e}")
                traceback.print_exc()
