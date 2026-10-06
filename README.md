# webp-convert

Batch-convert JPEG, PNG and TIFF images to lossy WebP for the web. Works on
macOS and Linux.

Drop images into `input/`, run the script, pick a quality. WebP files land
in `output/`, and the originals move to `input/done/`.

## Requirements

- Python 3.9 or newer (the `python3` that comes with Apple's Command Line
  Tools is fine)
- [Pillow](https://python-pillow.org/), with WebP support

### Install Pillow

**macOS**

```bash
python3 -m pip install --user Pillow
```

If that fails with `externally-managed-environment` (Homebrew Python):

```bash
brew install pillow
```

**Ubuntu / Debian**

```bash
sudo apt install python3-pil
```

**Other Linux**

```bash
python3 -m pip install --user Pillow
```

Check that it worked (should print `True`):

```bash
python3 -c "from PIL import features; print(features.check('webp'))"
```

If Pillow is missing when you run the script, it prints the install command
for your system and exits.

## Usage

1. Copy your images into `input/`.
2. Run:

   ```bash
   python3 webp.py
   ```

   (`./webp.py` works too.)

3. Pick a quality:

   ```
   Quality?
     1) 90
     2) 80
     3) 70
     4) 60
     5) 50
     6) 40
     7) All of the above
   Choose [1-7, default 2]:
   ```

   Press Enter for 80.

### Options

| Option | What it does |
| --- | --- |
| `-q 80` / `-q all` | Skip the menu. Any of 90, 80, 70, 60, 50, 40 or `all`. |
| `-y` | Overwrite existing files in `output/` without asking. |

```bash
python3 webp.py -q all -y
```

## What it does

- **Input:** `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff` in the top level of
  `input/` (any letter case). Anything else is listed as skipped.
- **Output names:** `{name}-{quality}.webp`, e.g. `banner-steak.jpg` at 60
  becomes `output/banner-steak-60.webp`.
  - If two sources share a name (`banner-steak.jpg` and `banner-steak.png`),
    both get numbered, sorted by filename: `banner-steak-60-1.webp`,
    `banner-steak-60-2.webp`.
- **Existing output:** asks per file — `y` (yes), `N` (no, default), `a`
  (yes to all). `-y` skips the question.
- **Originals:** moved to `input/done/` once all their WebP files are
  written. A file that failed, or that you chose not to overwrite, stays in
  `input/`. If `done/` already has a file with the same name, the new one is
  numbered (`banner-steak-1.jpg`) — nothing is ever deleted.
- **Metadata:** EXIF (camera, date, GPS) is removed. The colour profile is
  kept, so colours match the original. Rotation tags are not applied —
  export images the right way up.
- **Size:** images are not resized.
- **PNGs** use the same lossy quality as photos. Transparency is kept.

At the end it prints each file's size per quality, totals per quality, and
a summary.

## License

MIT — see [LICENSE](LICENSE).
