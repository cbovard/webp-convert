#!/usr/bin/env python3
"""Batch-convert images in input/ to lossy WebP in output/.

Drop .jpg/.jpeg/.png/.tif/.tiff files into input/, run the script, pick a
quality (or all of them). Each image becomes {name}-{quality}.webp in
output/, and the original moves to input/done/ once all its outputs are
written.

Usage:
    python3 webp.py              # asks for quality
    python3 webp.py -q 80        # one quality, no menu
    python3 webp.py -q all -y    # every quality, overwrite without asking
"""

import argparse
import os
import platform
import shutil
import sys
from pathlib import Path

if sys.version_info < (3, 9):
    sys.exit("webp-convert needs Python 3.9 or newer (found %d.%d)." % sys.version_info[:2])

HERE = Path(__file__).resolve().parent
INPUT_DIR = HERE / "input"
OUTPUT_DIR = HERE / "output"
DONE_DIR = INPUT_DIR / "done"

QUALITIES = [90, 80, 70, 60, 50, 40]
DEFAULT_QUALITY = 80
EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def install_hint():
    if platform.system() == "Darwin":
        return (
            "  python3 -m pip install --user Pillow\n"
            "If that fails with \"externally-managed-environment\" (Homebrew Python):\n"
            "  brew install pillow"
        )
    return (
        "Ubuntu/Debian:\n"
        "  sudo apt install python3-pil\n"
        "Other Linux:\n"
        "  python3 -m pip install --user Pillow"
    )


def load_pillow():
    try:
        from PIL import Image, features
    except ImportError:
        sys.exit("Pillow is not installed. Install it with:\n" + install_hint())
    if not features.check("webp"):
        sys.exit(
            "Pillow is installed but was built without WebP support.\n"
            "Reinstall it with:\n" + install_hint()
        )
    return Image


def human_k(size):
    k = size / 1024
    return "%.1fK" % k if k < 10 else "%dK" % round(k)


def smaller(before, after):
    if before == 0:
        return "0%"
    pct = (1 - after / before) * 100
    return "%d%% smaller" % round(pct) if pct >= 0 else "%d%% larger" % round(-pct)


def ask_quality():
    print("Quality?")
    for i, q in enumerate(QUALITIES, 1):
        print("  %d) %d" % (i, q))
    print("  %d) All of the above" % (len(QUALITIES) + 1))
    default_choice = QUALITIES.index(DEFAULT_QUALITY) + 1
    while True:
        try:
            answer = input(
                "Choose [1-%d, default %d]: " % (len(QUALITIES) + 1, default_choice)
            ).strip()
        except EOFError:
            answer = ""
        if answer == "":
            return [DEFAULT_QUALITY]
        if answer.isdigit():
            n = int(answer)
            if 1 <= n <= len(QUALITIES):
                return [QUALITIES[n - 1]]
            if n == len(QUALITIES) + 1:
                return list(QUALITIES)
        print("Please enter a number from 1 to %d." % (len(QUALITIES) + 1))


def parse_quality(value):
    if value.lower() == "all":
        return list(QUALITIES)
    if value.isdigit() and int(value) in QUALITIES:
        return [int(value)]
    raise argparse.ArgumentTypeError(
        "choose one of %s or 'all'" % ", ".join(str(q) for q in QUALITIES)
    )


def numbered_path(path):
    """path if free, else path-1, path-2, ... with the same suffix."""
    if not path.exists():
        return path
    n = 1
    while True:
        candidate = path.with_name("%s-%d%s" % (path.stem, n, path.suffix))
        if not candidate.exists():
            return candidate
        n += 1


def collect_sources():
    sources, unsupported = [], []
    for entry in sorted(INPUT_DIR.iterdir(), key=lambda p: p.name.lower()):
        if entry.name.startswith(".") or not entry.is_file():
            continue
        if entry.suffix.lower() in EXTENSIONS:
            sources.append(entry)
        else:
            unsupported.append(entry)
    return sources, unsupported


def output_stems(sources):
    """Map each source to its output stem, numbering sources that share a name."""
    groups = {}
    for src in sources:
        groups.setdefault(src.stem.lower(), []).append(src)
    stems = {}
    for group in groups.values():
        if len(group) == 1:
            stems[group[0]] = (group[0].stem, None)
        else:
            for n, src in enumerate(sorted(group, key=lambda p: p.name.lower()), 1):
                stems[src] = (src.stem, n)
    return stems


def out_path(stem, clash_n, quality):
    name = "%s-%d" % (stem, quality)
    if clash_n is not None:
        name += "-%d" % clash_n
    return OUTPUT_DIR / (name + ".webp")


class OverwritePrompt:
    def __init__(self, always):
        self.always = always

    def allow(self, path):
        if self.always:
            return True
        while True:
            try:
                answer = input(
                    "%s exists. Overwrite? [y/N/a(ll)]: " % path.name
                ).strip().lower()
            except EOFError:
                answer = ""
            if answer in ("y", "yes"):
                return True
            if answer in ("", "n", "no"):
                return False
            if answer in ("a", "all"):
                self.always = True
                return True
            print("Please answer y, n or a.")


def prepare(Image, img):
    """Return (image ready for WebP, ICC profile bytes or None)."""
    icc = img.info.get("icc_profile")
    if img.mode == "CMYK":
        # A CMYK profile can't describe RGB pixels: convert through it to sRGB.
        converted = None
        if icc:
            try:
                import io
                from PIL import ImageCms

                converted = ImageCms.profileToProfile(
                    img,
                    ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                    ImageCms.createProfile("sRGB"),
                    outputMode="RGB",
                )
            except Exception:
                converted = None
        return (converted or img.convert("RGB")), None
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )
    if has_alpha:
        return (img if img.mode == "RGBA" else img.convert("RGBA")), icc
    return (img if img.mode == "RGB" else img.convert("RGB")), icc


def load_image(Image, src):
    """Open src and return (image ready for WebP, save options)."""
    with Image.open(src) as img:
        img.load()
        ready, icc = prepare(Image, img)
    options = {"exif": b"", "xmp": b""}
    if icc:
        options["icc_profile"] = icc
    return ready, options


def write_webp(image, options, dest, quality):
    tmp = dest.with_name("." + dest.name + ".tmp")
    try:
        image.save(tmp, format="WEBP", quality=quality, **options)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def main():
    parser = argparse.ArgumentParser(
        description="Convert images in input/ to WebP in output/."
    )
    parser.add_argument(
        "-q", "--quality", type=parse_quality, metavar="Q",
        help="skip the menu: %s or 'all'" % ", ".join(str(q) for q in QUALITIES),
    )
    parser.add_argument(
        "-y", "--yes", action="store_true",
        help="overwrite existing output files without asking",
    )
    args = parser.parse_args()

    Image = load_pillow()

    INPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

    sources, unsupported = collect_sources()
    for path in unsupported:
        print("skipped: unsupported format: %s" % path.name)
    if not sources:
        print("No .jpg/.jpeg/.png/.tif/.tiff images in %s" % INPUT_DIR)
        return 0

    qualities = args.quality or ask_quality()
    print()

    stems = output_stems(sources)
    prompt = OverwritePrompt(args.yes)
    totals = {q: [0, 0] for q in qualities}  # quality -> [before, after]
    images_done = written = skipped = failed = moved = 0

    for src in sources:
        stem, clash_n = stems[src]
        before = src.stat().st_size
        print("%s  (%s)" % (src.name, human_k(before)))

        try:
            image, options = load_image(Image, src)
        except Exception as exc:
            print("    FAILED: %s" % exc)
            failed += 1
            continue

        complete = True
        for q in qualities:
            dest = out_path(stem, clash_n, q)
            if dest.exists() and not prompt.allow(dest):
                print("    %d  skipped (exists)" % q)
                skipped += 1
                complete = False
                continue
            try:
                write_webp(image, options, dest, q)
            except Exception as exc:
                print("    %d  FAILED: %s" % (q, exc))
                failed += 1
                complete = False
                continue
            after = dest.stat().st_size
            totals[q][0] += before
            totals[q][1] += after
            written += 1
            print("    %d  ->  %s  (%s)" % (q, human_k(after), smaller(before, after)))

        if complete:
            DONE_DIR.mkdir(exist_ok=True)
            shutil.move(str(src), str(numbered_path(DONE_DIR / src.name)))
            moved += 1
            images_done += 1

    print()
    if written:
        print("Totals by quality:")
        for q in qualities:
            b, a = totals[q]
            if b:
                print("    %d:  %s -> %s  (%s)" % (q, human_k(b), human_k(a), smaller(b, a)))
        print()
    print(
        "Done: %d images, %d WebP files written, %d skipped, %d failed"
        % (images_done, written, skipped, failed)
    )
    print("Moved %d originals to input/done/" % moved)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)
