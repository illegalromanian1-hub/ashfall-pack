#!/usr/bin/env python3
"""Builds the AshFall resource pack.

Design rules:
  * NEVER ship assets/minecraft/font/default.json - overriding the vanilla default
    font is what broke normal text in the old pack.
  * Every custom glyph lives in its own font file and is referenced explicitly
    from the plugin with <font:minecraft:ashfall/rank> / <font:minecraft:ashfall/title>.
  * Each custom font ends with a reference to minecraft:default, so a component using
    that font still renders ordinary text even if the glyph is missing.
  * Rank glyphs use Private Use Area codepoints (U+E000..) so they can never be
    shadowed by a vanilla/unifont glyph.
"""
import json
import os
import shutil
import zipfile
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = f"{ROOT}/pack"
LEGACY = "/tmp/opencode/packx/assets/minecraft/textures/ashfall_flag"

RANKS = [
    # id,        pips, body colour,          high tier
    ("UNRANKED", 0, (0x6B, 0x72, 0x80), False),
    ("LT5", 1, (0x8A, 0x94, 0xA6), False),
    ("HT5", 1, (0x8A, 0x94, 0xA6), True),
    ("LT4", 2, (0x4A, 0xDE, 0x80), False),
    ("HT4", 2, (0x4A, 0xDE, 0x80), True),
    ("LT3", 3, (0xE2, 0xE8, 0xF0), False),
    ("HT3", 3, (0xE2, 0xE8, 0xF0), True),
    ("LT2", 4, (0xC0, 0x84, 0xFC), False),
    ("HT2", 4, (0xC0, 0x84, 0xFC), True),
    ("LT1", 5, (0xFB, 0xBF, 0x24), False),
    ("HT1", 5, (0xF5, 0x9E, 0x0B), True),
]

TITLE_LETTERS = "ASHFLMP"
PIXEL_FONT = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
}


def scale(rows, px):
    """Expands a 1-bit pixel-font bitmap into a list of solid (x, y) pixels."""
    points = []
    for row_index, row in enumerate(rows):
        for col_index, cell in enumerate(row):
            if cell != "1":
                continue
            for dy in range(px):
                for dx in range(px):
                    points.append((col_index * px + dx, row_index * px + dy))
    return points


GOLD_RING = (0xF5, 0xB3, 0x01)
PIP_DARK = (0x11, 0x18, 0x27)
PIP_LIGHT = (0xF8, 0xFA, 0xFC)

# The 3D logo's four colours, bright edge to deepest shadow. These are the exact same
# four hex values MenuCommand and TAB use as a gradient fallback, so the extruded logo
# and the plain gradient one read as the same branding.
LOGO_HI = (0xFF, 0xF3, 0xC4)      # #fff3c4 - lit top edge of each block
LOGO_FACE = (0xFF, 0xD2, 0x3F)    # #ffd23f - the front face
LOGO_MID = (0xFF, 0x8C, 0x1A)     # #ff8c1a - first layer of extrusion
LOGO_DEEP = (0xFF, 0x4D, 0x00)    # #ff4d00 - the far side, where the light does not reach


def luminance(colour):
    r, g, b = colour
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def rank_glyph(pips, body, high_tier):
    """16x16 badge: bevelled diamond, 1..5 pips, gold ring for high tier."""
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    shade = tuple(max(0, c - 70) for c in body)
    ring = GOLD_RING if high_tier else shade
    pip = PIP_DARK if luminance(body) > 140 else PIP_LIGHT

    def diamond(inset, fill):
        d.polygon(
            [(8, inset), (15 - inset, 8), (8, 15 - inset), (inset, 8)], fill=fill
        )

    diamond(0, ring + (255,))          # outer ring: gold for HT, dark for LT
    diamond(1, body + (255,))          # face
    d.line([(8, 1), (14, 8)], fill=tuple(min(255, c + 45) for c in body) + (255,))
    d.line([(2, 8), (8, 14)], fill=shade + (255,))

    if pips == 0:
        d.rectangle([5, 7, 10, 8], fill=pip + (255,))
        return img

    # up to 5 pips in one row of 2px blocks, 1px gap, centred
    width = pips * 2 + (pips - 1)
    x0 = 8 - width // 2
    for i in range(pips):
        x = x0 + i * 3
        d.rectangle([x, 7, x + 1, 8], fill=pip + (255,))
    return img


def build_rank_atlas(path):
    atlas = Image.new("RGBA", (16 * len(RANKS), 16), (0, 0, 0, 0))
    for i, (_id, pips, body, high_tier) in enumerate(RANKS):
        atlas.paste(rank_glyph(pips, body, high_tier), (i * 16, 0))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atlas.save(path)


def build_title_atlas(path):
    px, cell_w, cell_h, depth = 4, 30, 40, 5
    pad_x, pad_y = 3, 5
    atlas = Image.new("RGBA", (cell_w * len(TITLE_LETTERS), cell_h), (0, 0, 0, 0))
    for i, ch in enumerate(TITLE_LETTERS):
        glyph = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
        pen = ImageDraw.Draw(glyph)
        pixels = scale(PIXEL_FONT[ch], px)
        # 3D stack: far layers first so the face ends up on top. The extrusion
        # fades from the deepest orange at the back to the mid orange nearest
        # the face, which reads as light falling off toward the lower right.
        for d in range(depth, -1, -1):
            colour = LOGO_DEEP if d >= depth - 1 else LOGO_MID
            for (x, y) in pixels:
                pen.point((x + pad_x + d, y + pad_y + d), fill=colour + (255,))
        # face: top row of every block is the pale highlight, the rest gold.
        for (x, y) in pixels:
            pen.point((x + pad_x, y + pad_y),
                      fill=(LOGO_HI if y % px == 0 else LOGO_FACE) + (255,))
        atlas.paste(glyph, (i * cell_w, 0))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atlas.save(path)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")


# -- Warden Spear ---------------------------------------------------------
# Vanilla has wooden/stone/copper/iron/golden/diamond/netherite spears and nothing
# black, so the spear ships as an iron spear whose model is swapped through the
# minecraft:item_model component. A client without the pack, or Bedrock, just sees the
# plain iron spear, which is why the base material is a real spear.
#
# The sprite itself is the vanilla iron spear (vanilla/iron_spear*.png, pulled from the
# official client jar) with its palette crushed down to near-black. Recolouring the real
# sprite keeps the silhouette, the in-hand pose and the swap animation identical to a
# genuine spear instead of hand-drawing something that only roughly reads as one.
VANILLA = f"{ROOT}/vanilla"

SPEAR_MODEL_ID = "minecraft:ashfall/warden_spear"


def darken_sprite(img):
    """Crush a vanilla spear sprite towards black, keeping enough contrast to read.

    Iron pixels go to dark gunmetal with a faint cool tint, the wooden shaft to a dark
    brown-black. Alpha is untouched, so the sprite keeps its exact outline.
    """
    out = img.convert("RGBA")
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if not a:
                continue
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            if r > b + 12:                                    # wooden shaft
                px[x, y] = (int(4 + lum * 0.20), int(3 + lum * 0.14),
                            int(2 + lum * 0.10), a)
            else:                                            # iron head / fittings
                px[x, y] = (int(6 + lum * 0.26), int(6 + lum * 0.27),
                            int(9 + lum * 0.32), a)
    return out


def build_spear(out_dir):
    """Writes both spear sprites: the flat 16x16 and the 32x32 held-in-hand one."""
    for name in ("iron_spear", "iron_spear_in_hand"):
        src = f"{VANILLA}/{name}.png"
        darken_sprite(Image.open(src)).save(f"{out_dir}/{name}.png")


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    fonts = f"{OUT}/assets/minecraft/font/ashfall"
    textures = f"{OUT}/assets/minecraft/textures/ashfall/font"

    build_rank_atlas(f"{textures}/rank.png")
    build_title_atlas(f"{textures}/title.png")
    spear_tex = f"{OUT}/assets/minecraft/textures/item/ashfall"
    os.makedirs(spear_tex, exist_ok=True)
    build_spear(spear_tex)
    os.rename(f"{spear_tex}/iron_spear.png", f"{spear_tex}/warden_spear.png")
    os.rename(f"{spear_tex}/iron_spear_in_hand.png", f"{spear_tex}/warden_spear_in_hand.png")

    # -- Warden Spear model -----------------------------------------------
    # Mirrors vanilla's own iron_spear wiring: an item definition that picks the flat
    # sprite for gui/ground/fixed/on_shelf and the held sprite for everything else,
    # plus the same swap animation scale. 26.x reads the minecraft:item_model component
    # as an item definition (assets/minecraft/items/<id>.json) which then points at the
    # model, while older clients that only know custom model data look for the model
    # file itself. Shipping the pair means the black spear resolves either way, and a
    # client that finds neither still falls back to the item's own texture.
    write_json(f"{OUT}/assets/minecraft/items/ashfall/warden_spear.json", {
        "model": {
            "type": "minecraft:select",
            "property": "minecraft:display_context",
            "cases": [{
                "when": ["gui", "ground", "fixed", "on_shelf"],
                "model": {"type": "minecraft:model",
                          "model": "minecraft:item/ashfall/warden_spear"},
            }],
            "fallback": {"type": "minecraft:model",
                         "model": "minecraft:item/ashfall/warden_spear_in_hand"},
        },
        "swap_animation_scale": 1.95,
    })
    write_json(f"{OUT}/assets/minecraft/models/item/ashfall/warden_spear.json", {
        "parent": "minecraft:item/generated",
        "textures": {"layer0": "minecraft:item/ashfall/warden_spear"},
    })
    write_json(f"{OUT}/assets/minecraft/models/item/ashfall/warden_spear_in_hand.json", {
        "parent": "minecraft:item/spear_in_hand",
        "textures": {"layer0": "minecraft:item/ashfall/warden_spear_in_hand"},
    })

    # Old flag art is kept so stray flag / icon characters still resolve.
    os.makedirs(f"{OUT}/assets/minecraft/textures/ashfall_flag", exist_ok=True)
    for name in ("atlas.png", "icons.png"):
        src = f"{LEGACY}/{name}"
        if os.path.exists(src):
            shutil.copy(src, f"{OUT}/assets/minecraft/textures/ashfall_flag/{name}")

    # -- rank font -------------------------------------------------------
    rank_providers = [
        {"type": "bitmap", "file": "ashfall/font/rank", "height": 16, "ascent": 13,
         "chars": ["".join(chr(0xE000 + i) for i in range(len(RANKS)))]},
    ]
    # Only declare the legacy icon provider when the texture actually made it
    # into the pack, otherwise the client logs a missing-texture error.
    if os.path.exists(f"{OUT}/assets/minecraft/textures/ashfall_flag/icons.png"):
        rank_providers.append(
            {"type": "bitmap", "file": "ashfall_flag/icons", "height": 8, "ascent": 6,
             "chars": ["💎💧🪓🏹🔨💜🔥🔱"]}
        )
    rank_providers.append({"type": "reference", "id": "minecraft:default"})
    write_json(f"{fonts}/rank.json", {"providers": rank_providers})

    # -- 3D title font ---------------------------------------------------
    write_json(f"{fonts}/title.json", {
        "providers": [
            {"type": "space", "advances": {" ": 6}},
            {"type": "bitmap", "file": "ashfall/font/title", "height": 40, "ascent": 32,
             "chars": [TITLE_LETTERS]},
            {"type": "reference", "id": "minecraft:default"},
        ]
    })

    # Which clients accept the pack.
    #
    # Verified against the real 26.3 client codec, not guessed. Every claim
    # below was produced by parsing candidate files through
    # PackFormat.packCodec(PackType.CLIENT_RESOURCES) out of the official
    # 26.3 client jar and asking PackCompatibility.forVersion(range, 97.1):
    #
    #   * version.json for 26.3 reports resource_major 97 / resource_minor 1,
    #     and data_major 121. 121 is the DATA pack format, not the resource one.
    #   * PackFormat.lastPreMinorVersion(CLIENT_RESOURCES) is 64, so anything
    #     from 65.0 up must carry both min_format and max_format; a bare
    #     "pack_format" there is rejected with "declares support for version
    #     newer than 64, but is missing mandatory fields min_format and
    #     max_format".
    #   * "pack_format" is also deprecated from 65.0 up, so the legacy scalar
    #     and its "supported_formats" companion are simply not shipped.
    #   * A legacy "pack_format": 15 parses but resolves to TOO_OLD against
    #     97.1, which is how the old pack failed to show its title.
    #   * min 88 / max 121 parses to the range 88.0..121.* and comes back
    #     COMPATIBLE against 97.1. 88.0 is 1.21.9, the oldest client that can
    #     read this pack's fonts and item models; the upper bound is generous
    #     so future client updates do not turn the pack incompatible.
    #
    # Getting this wrong is invisible on the server and fatal on the client: a
    # rejected pack leaves minecraft:ashfall/title undefined, every glyph in it
    # falls back to a zero-width blank, and the ASHFALLSMP title renders as
    # nothing at all instead of as an error.
    write_json(f"{OUT}/pack.mcmeta", {
        "pack": {
            "description": "AshFall 3D title",
            "min_format": 88,
            "max_format": 121,
        }
    })

    # -- legacy default font (only used by explicit <font:...> references) --
    # Optional: the original tree this was copied from lived in /tmp and is
    # long gone. Skipping it is safe, the current fonts do not reference it.
    legacy_src = "/tmp/opencode/packx/assets/minecraft/font/default.json"
    if os.path.exists(legacy_src):
        with open(legacy_src, encoding="utf-8") as handle:
            legacy = json.load(handle)
        write_json(f"{OUT}/assets/minecraft/font/ashfall/legacy.json", legacy)
    else:
        print("note: legacy flag font not found, shipping without it")

    zip_path = "/home/daniel/Documents/ashfall/ashfall-pack.zip"
    if os.path.exists(zip_path):
        os.remove(zip_path)
    files = []
    for root, _dirs, names in os.walk(OUT):
        for name in names:
            full = os.path.join(root, name)
            files.append((full, os.path.relpath(full, OUT)))
    files.sort(key=lambda item: (item[1] != "pack.mcmeta", item[1]))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for full, arc in files:
            zf.write(full, arc)
    print("built", zip_path)
    for _full, arc in files:
        print("  ", arc)


if __name__ == "__main__":
    main()
