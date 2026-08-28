"""
Import/eksport af filer (DDD-import, CSV/PDF-eksport) accepterede hidtil en
vilkårlig sti uden reel begrænsning - en bruger kunne angive fx "C:\\" og
få systemet til at scanne/skrive til et helt drev. is_under_allowed_root()
begrænser dette til brugerens/tjeneste-kontoens hjemmemappe (Path.home()).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from pathlib import Path

from utils.safe_paths import is_under_allowed_root


def test_path_under_home_is_allowed():
    candidate = Path.home() / "Downloads" / "ddd-filer"
    assert is_under_allowed_root(candidate) is True


def test_home_itself_is_allowed():
    assert is_under_allowed_root(Path.home()) is True


def test_path_outside_home_is_rejected():
    outside = Path(Path.home().anchor) / "et-helt-andet-sted"
    assert is_under_allowed_root(outside) is False


def test_drive_root_is_rejected():
    assert is_under_allowed_root(Path(Path.home().anchor)) is False
