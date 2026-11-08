"""Shrink the site's screenshots without changing what they show.

Two sets of PNGs have to live in git for the site to build anywhere:

  * the 21 app screenshots `site/build.py` copies and publishes (8 MB);
  * the 43 e2e screenshots that prove the site itself (12 MB).

A 2880x1800 capture of a light UI is mostly flat colour, which PNG stores badly at 24 bits. An 8-bit
palette with dithering typically keeps ~40% of the bytes. The risk is text: quantising a screenshot of
small type can fringe antialiased edges.

So this script **measures its own damage** and refuses a file it would visibly hurt:

  1. quantise to 256 colours with Floyd-Steinberg dithering;
  2. decode both and compute the mean absolute error per channel, plus the 99.5th percentile;
  3. keep the quantised file only if the mean error is under `MAX_MAE` and the tail under `MAX_P999`;
  4. otherwise leave the original byte-for-byte alone and say so.

That makes the decision reproducible instead of a judgement call made once and forgotten.

    python3 site/optimize_shots.py --dry-run    # report what would change
    python3 site/optimize_shots.py              # rewrite the files that pass
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageStat
except ImportError:  # pragma: no cover
    print("optimize_shots: Pillow is needed for this tool only (pip install pillow)", file=sys.stderr)
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parent.parent
E2E = ROOT / "specs" / "008-github-page" / "e2e"

#: Mean absolute error per channel that is not visible on a screenshot of a UI. 1.5/255 is well under
#: the ~2/255 where a flat area starts to band on a good display.
MAX_MAE = 1.5
#: The tail matters more than the mean: a small number of badly wrong pixels is a fringed glyph.
MAX_P999 = 24
#: Below this saving, a rewrite is not worth the churn in the diff.
MIN_SAVING = 0.25


def quantise(data: bytes) -> tuple[bytes, float, int]:
    """Return (png bytes, mean absolute error, 99.5th percentile error) for an 8-bit version."""
    original = Image.open(io.BytesIO(data)).convert("RGB")
    palette = original.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
    buf = io.BytesIO()
    palette.save(buf, "PNG", optimize=True)
    rebuilt = palette.convert("RGB")

    diff = ImageChops.difference(original, rebuilt).convert("L")
    stat = ImageStat.Stat(diff)
    mae = stat.mean[0]
    # percentile from the histogram: walk bins until 99.5% of pixels are accounted for
    hist = diff.histogram()
    total = sum(hist)
    running, p999 = 0, 0
    for value, count in enumerate(hist):
        running += count
        if running >= total * 0.995:
            p999 = value
            break
    return buf.getvalue(), mae, p999


def targets() -> list[Path]:
    """The app screenshots the build publishes, plus every e2e capture."""
    src = (ROOT / "site" / "build.py").read_text(encoding="utf-8")
    block = re.search(r"SHOTS: dict\[str, str\] = \{(.*?)\n\}", src, re.S).group(1)
    published = [ROOT / rel for _name, rel in re.findall(r'"([\w-]+)": "([^"]+)"', block)]
    captured = sorted(E2E.rglob("*.png"))
    tutorial = sorted((ROOT / "docs" / "e2e" / "screenshots" / "tutorial").glob("*.png"))
    # de-duplicate, keep order
    seen, out = set(), []
    for p in published + captured + tutorial:
        if p not in seen and p.is_file():
            seen.add(p)
            out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = targets()
    before = sum(p.stat().st_size for p in files)
    after = 0
    kept = refused = 0
    refused_list: list[tuple[str, float, int]] = []

    for path in files:
        data = path.read_bytes()
        size = len(data)
        if path.suffix.lower() != ".png" or size < 20_000:
            after += size
            continue
        new, mae, p999 = quantise(data)
        saving = 1 - len(new) / size
        if saving < MIN_SAVING or mae > MAX_MAE or p999 > MAX_P999:
            after += size
            refused += 1
            if saving >= MIN_SAVING:
                refused_list.append((str(path.relative_to(ROOT)), mae, p999))
            continue
        after += len(new)
        kept += 1
        if not args.dry_run:
            path.write_bytes(new)

    print(f"{len(files)} images: {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB "
          f"({100 * (1 - after / before):.0f}% smaller)")
    print(f"  rewritten: {kept}{' (dry run)' if args.dry_run else ''}")
    print(f"  left alone: {refused} (would have lost visible detail)")
    for name, mae, p999 in refused_list:
        print(f"    {name}  mean {mae:.2f}, p99.5 {p999}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
