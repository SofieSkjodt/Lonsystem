"""
Fælles sti-validering for DDD-import og CSV/PDF-eksport. Uden dette kunne en
bruger med den relevante rettighed angive en vilkårlig sti (fx "C:\\") som
udgangspunkt for en mappescanning eller en gem-placering, hvilket ville
udløse et unødigt tungt rekursivt filsystem-scan af hele drev, eller skrive
lønfiler til vilkårlige placeringer på serverens diske.
"""
from pathlib import Path

# I dag: kun tjeneste-kontoens/brugerens hjemmemappe. Udvid denne liste, hvis
# der er en bestemt netværksdelt mappe eller USB-drevbogstav, der reelt skal
# understøttes.
ALLOWED_ROOTS = [Path.home().resolve()]


def is_under_allowed_root(path: Path) -> bool:
    """True hvis `path` ligger under (eller er) en af de tilladte rødder."""
    resolved = Path(path).resolve()
    for root in ALLOWED_ROOTS:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False
