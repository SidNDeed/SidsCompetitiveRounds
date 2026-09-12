"""Canonicalise Player Cards art and build the temporary procedural layer set.

Artist deliveries are rebuilt from decoded pixels, never copied byte-for-byte.
With no paths this script generates the v1 placeholder layers and card back;
passing paths canonicalises those deliveries in place after class validation.
"""

from __future__ import annotations

import argparse
import io
import math
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


HERE = Path(__file__).resolve().parent
API_DIR = HERE.parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import pc_face  # noqa: E402


ONE_X_CAP = 4 << 20
MASTER_CAP = 16 << 20
RETRY_CAP = 64 << 10

RGBA_LAYERS = {
    *(f"Base_{band}.png" for band in pc_face.BANDS),
    *(f"Frame_{band}.png" for band in pc_face.BANDS),
    *(f"Plates_{band}.png" for band in pc_face.BANDS),
    "BadgeFrame.png",
    "SignedSeal.png",
    "FoilOverlay.png",
    "Back.png",
}
EXPECTED_1X = RGBA_LAYERS | {"FoilMask.png", "RetryGlyph.png"}


def _base_name(path: Path) -> tuple[str, bool]:
    master = path.stem.endswith("@2x")
    return (path.stem[:-3] + path.suffix if master else path.name), master


def _asset_class(path: Path) -> tuple[tuple[int, int], str, int]:
    name = path.name
    base_name, master = _base_name(path)
    if base_name not in EXPECTED_1X:
        raise ValueError(f"unknown_asset:{name}")
    if base_name == "RetryGlyph.png":
        if master:
            raise ValueError(f"unknown_asset:{name}")
        return (96, 96), "RGBA", RETRY_CAP
    mode = "L" if base_name == "FoilMask.png" else "RGBA"
    return ((1500, 2100), mode, MASTER_CAP) if master else ((750, 1050), mode, ONE_X_CAP)


def _contract_mask(size: tuple[int, int], scale: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1), radius=40 * scale, fill=255
    )
    return mask


def _validate_contract_pixels(image: Image.Image, name: str) -> None:
    base_name, master = _base_name(Path(name))
    if base_name == "RetryGlyph.png":
        return
    scale = 2 if master else 1
    card_mask = _contract_mask(image.size, scale)
    outside = ImageChops.invert(card_mask)
    surface = image if image.mode == "L" else image.getchannel("A")
    if ImageChops.multiply(surface, outside).getbbox() is not None:
        raise ValueError(f"asset_exterior:{name}")
    if base_name == "Back.png" or base_name.startswith("Base_"):
        if ImageChops.difference(surface, card_mask).getbbox() is not None:
            raise ValueError(f"asset_opacity:{name}")
    if base_name == "FoilMask.png":
        expected = card_mask.copy()
        draw = ImageDraw.Draw(expected)
        draw.rounded_rectangle(tuple(value * scale for value in (54, 758, 696, 972)),
                               radius=18 * scale, fill=0)
        draw.rectangle(tuple(value * scale for value in (54, 978, 696, 1010)), fill=0)
        if ImageChops.difference(image, expected).getbbox() is not None:
            raise ValueError(f"asset_mask:{name}")
    contained_rect = None
    if base_name.startswith("Plates_"):
        contained_rect = (54, 758, 696, 972)
    elif base_name == "BadgeFrame.png":
        contained_rect = (58, 642, 178, 754)
    elif base_name == "SignedSeal.png":
        contained_rect = (540, 630, 660, 750)
    if contained_rect is not None:
        allowed = Image.new("L", image.size, 0)
        ImageDraw.Draw(allowed).rectangle(
            tuple(value * scale for value in contained_rect), fill=255
        )
        if ImageChops.multiply(surface, ImageChops.invert(allowed)).getbbox() is not None:
            raise ValueError(f"asset_registration:{name}")
    if base_name == "BadgeFrame.png":
        inside = Image.new("L", image.size, 0)
        ImageDraw.Draw(inside).rounded_rectangle(
            tuple(value * scale for value in (63, 647, 173, 749)),
            radius=15 * scale,
            fill=255,
        )
        if ImageChops.multiply(surface, inside).getbbox() is not None:
            raise ValueError(f"asset_interior:{name}")
    if base_name.startswith("Frame_"):
        # The five-pixel portrait rim and its rasterised edge may occupy the
        # boundary; everything eight pixels inside remains portrait-only.
        inner = Image.new("L", image.size, 0)
        ImageDraw.Draw(inner).rounded_rectangle(
            tuple(value * scale for value in (88, 158, 662, 732)),
            radius=20 * scale,
            fill=255,
        )
        if ImageChops.multiply(image.getchannel("A"), inner).getbbox() is not None:
            raise ValueError(f"asset_portrait_window:{name}")


def _encode_pixels(image: Image.Image, mode: str) -> bytes:
    converted = image if image.mode == mode else image.convert(mode)
    fresh = Image.frombytes(mode, converted.size, converted.tobytes())
    output = io.BytesIO()
    fresh.save(output, format="PNG", compress_level=6, optimize=False)
    data = output.getvalue()
    if any(kind not in {b"IHDR", b"IDAT", b"IEND"} for kind, _ in pc_face.png_chunks(data)):
        raise ValueError("canonical_chunks")
    return data


def canonicalise_bytes(data: bytes, name: str) -> bytes:
    """Return canonical bytes for a named layer, master, back, or retry glyph."""
    expected_size, expected_mode, cap = _asset_class(Path(name))
    if len(data) > cap:
        raise ValueError(f"asset_too_large:{name}")
    pc_face.png_chunks(data)
    width, height, depth, colour_type, interlace = pc_face.png_ihdr(data)
    expected_colour_type = 6 if expected_mode == "RGBA" else 0
    if ((width, height) != expected_size or depth != 8
            or colour_type != expected_colour_type or interlace != 0):
        raise ValueError(f"asset_shape:{name}")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if (source.format or "").upper() != "PNG":
                raise ValueError("not_png")
            if getattr(source, "n_frames", 1) != 1:
                raise ValueError(f"asset_animated:{name}")
            source.load()
            if source.size != expected_size or source.mode != expected_mode:
                raise ValueError(f"asset_shape:{name}")
            pixels = source.tobytes()
        fresh = Image.frombytes(expected_mode, expected_size, pixels)
        _validate_contract_pixels(fresh, name)
        canonical = (pc_face.canonical_png(_encode_pixels(fresh, "RGBA"), expected_size)
                     if expected_mode == "RGBA" else _encode_pixels(fresh, "L"))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"asset_invalid:{name}") from exc
    if len(canonical) > cap:
        raise ValueError(f"asset_too_large:{name}")
    if _encode_pixels(fresh, expected_mode) != canonical:
        raise ValueError(f"asset_not_idempotent:{name}")
    return canonical


def canonicalise_file(path: str | Path) -> bytes:
    """Canonicalise one delivery in place and return the bytes written."""
    target = Path(path)
    canonical = canonicalise_bytes(target.read_bytes(), target.name)
    target.write_bytes(canonical)
    return canonical


def _save_generated(name: str, image: Image.Image) -> None:
    raw = _encode_pixels(image, image.mode)
    canonical = canonicalise_bytes(raw, name)
    (HERE / name).write_bytes(canonical)


def _card_mask() -> Image.Image:
    return pc_face._rounded_mask(pc_face.CARD_W, pc_face.CARD_H, 40)


def _masked_rgba(image: Image.Image) -> Image.Image:
    output = Image.new("RGBA", image.size, (0, 0, 0, 0))
    output.paste(image.convert("RGBA"), (0, 0), _card_mask())
    return output


def _base_layer(band: str) -> Image.Image:
    colour = pc_face.LAYOUT["colours"]["bands"][band]
    card = pc_face.LAYOUT["colours"]["card"]
    image = pc_face._vertical_gradient(
        (pc_face.CARD_W, pc_face.CARD_H),
        pc_face._mix(colour, card, 0.72),
        (14, 15, 20),
    )
    seed = zlib_crc32_ascii(band)
    image = Image.alpha_composite(image, pc_face._grain_layer(750, 1050, 22, seed))
    return _masked_rgba(image)


def zlib_crc32_ascii(value: str) -> int:
    import zlib
    return zlib.crc32(value.encode("ascii")) & 0xFFFFFFFF


def _frame_layer(band: str) -> Image.Image:
    colour = tuple(pc_face.LAYOUT["colours"]["bands"][band])
    image = Image.new("RGBA", (750, 1050), (0, 0, 0, 0))
    if band in ("epic", "legendary"):
        halo = Image.new("RGBA", image.size, (0, 0, 0, 0))
        ImageDraw.Draw(halo).rounded_rectangle(
            (60, 130, 690, 760),
            radius=48,
            fill=pc_face._rgba(colour, 120 if band == "legendary" else 90),
        )
        image = Image.alpha_composite(image, halo.filter(ImageFilter.GaussianBlur(34)))
    draw = ImageDraw.Draw(image)
    rim_width = int(pc_face.LAYOUT["materials"]["rim_width"][band])
    draw.rounded_rectangle((0, 0, 749, 1049), radius=40,
                           outline=pc_face._rgba(colour), width=rim_width)
    draw.rounded_rectangle((rim_width, rim_width, 749 - rim_width, 1049 - rim_width),
                           radius=32, outline=(0, 0, 0, 110), width=3)
    if band == "epic":
        draw.rounded_rectangle((26, 26, 723, 1023), radius=24,
                               outline=pc_face._rgba(pc_face._mix(colour, (255, 255, 255), 0.25), 200),
                               width=2)
    if band == "legendary":
        draw.rounded_rectangle((22, 22, 727, 1027), radius=26,
                               outline=(255, 232, 180, 230), width=3)
    # The reference halo was drawn before the portrait.  Clearing the window
    # here makes the post-portrait asset stack pixel-equivalent in its interior.
    window = pc_face._rounded_mask(590, 590, 28)
    image.paste((0, 0, 0, 0), (80, 150, 670, 740), window)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((80, 150, 669, 739), radius=28,
                           outline=pc_face._rgba(colour, 230), width=5)
    return _masked_rgba(image)


def _plates_layer(_band: str) -> Image.Image:
    image = Image.new("RGBA", (750, 1050), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle((54, 758, 696, 972), radius=18,
                                            fill=pc_face._rgba(pc_face.LAYOUT["colours"]["card"], 235))
    return _masked_rgba(image)


def _badge_frame() -> Image.Image:
    image = Image.new("RGBA", (750, 1050), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle((58, 642, 178, 754), radius=20,
                                            outline=(255, 255, 255, 255), width=4)
    return _masked_rgba(image)


def _signed_seal() -> Image.Image:
    image = Image.new("RGBA", (750, 1050), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    sign = pc_face._rgba(pc_face.LAYOUT["colours"]["sign"])
    draw.ellipse((540, 630, 660, 750), fill=sign, outline=(60, 40, 10, 255), width=4)
    draw.ellipse((550, 640, 650, 740), outline=(60, 40, 10, 255), width=2)
    draw.ellipse((593, 702, 607, 716), fill=(60, 40, 10, 255))
    return _masked_rgba(image)


def _foil_overlay() -> Image.Image:
    width, height = 750, 1050
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = image.load()
    denominator = width + height * 0.6
    for y in range(height):
        for x in range(width):
            phase = ((x + y * 0.6) / denominator) * 12.0
            sine = math.sin(phase)
            pixels[x, y] = (
                int(127 + 127 * sine),
                int(127 - 127 * sine),
                int(215 + 40 * math.sin(2 * phase + 1.0)),
                75,
            )
    image = Image.alpha_composite(image, pc_face._grain_layer(width, height, 100, 7))
    sweep = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(sweep)
    for x in range(-300, width + 300, 3):
        alpha = max(0, 125 - abs(x - 260) * 5 // 8)
        if alpha:
            draw.line((x, 0, x - 420, height), fill=(255, 255, 255, alpha), width=3)
    return _masked_rgba(Image.alpha_composite(image, sweep))


def _foil_mask() -> Image.Image:
    mask = _card_mask()
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((54, 758, 696, 972), radius=18, fill=0)
    draw.rectangle((54, 978, 696, 1010), fill=0)
    return mask


def _retry_glyph() -> Image.Image:
    image = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    colour = pc_face._rgba(pc_face.LAYOUT["colours"]["label"])
    draw.arc((17, 17, 79, 79), start=35, end=315, fill=colour, width=9)
    draw.polygon(((75, 14), (90, 35), (65, 34)), fill=colour)
    return image


def generate_placeholders() -> list[Path]:
    """Generate and canonicalise every temporary v1 art layer."""
    generated: list[Path] = []
    for band in pc_face.BANDS:
        for prefix, builder in (("Base", _base_layer), ("Frame", _frame_layer),
                                ("Plates", _plates_layer)):
            name = f"{prefix}_{band}.png"
            _save_generated(name, builder(band))
            generated.append(HERE / name)
    for name, image in (
        ("BadgeFrame.png", _badge_frame()),
        ("SignedSeal.png", _signed_seal()),
        ("FoilOverlay.png", _foil_overlay()),
        ("FoilMask.png", _foil_mask()),
        ("RetryGlyph.png", _retry_glyph()),
    ):
        _save_generated(name, image)
        generated.append(HERE / name)
    (HERE / "Back.png").write_bytes(canonicalise_bytes(pc_face.render_back(), "Back.png"))
    generated.append(HERE / "Back.png")
    if {path.name for path in generated} != EXPECTED_1X:
        raise AssertionError("placeholder_manifest")
    return generated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="delivered assets to canonicalise in place")
    parser.add_argument("--generate-placeholders", action="store_true",
                        help="generate the procedural v1 placeholder set")
    args = parser.parse_args(argv)
    if args.generate_placeholders or not args.paths:
        paths = generate_placeholders()
    else:
        paths = [Path(path) for path in args.paths]
        for path in paths:
            canonicalise_file(path)
    for path in paths:
        print(f"{path.name}: {path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
