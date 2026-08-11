#!/usr/bin/env python3
"""Build one PPSSPP CWCheat INI per game from forum thread 26189, pages 1-6.

The downloaded HTML pages are supplied explicitly so the forum remains the
source of truth.  The script keeps the posted cheats, normalizes game IDs, and
adds disabled 4:3 and 3:2 variants.  Added values are exact ratio constants
when the patch stores an aspect ratio directly; otherwise they are calculated
from the closest posted narrow/default pair.
"""

from __future__ import annotations

import argparse
import math
import re
import struct
from pathlib import Path

from bs4 import BeautifulSoup


RATIO_BITS = {
    (4, 3): 0x3FAAAAAB,
    (3, 2): 0x3FC00000,
}

INFERRED_IDS = {
    "Gladiator Begins": "ULUS10528",
    "Nayuta no Kiseki": "ULJM06113",
    "LEGO Star Wars III The Clone Wars": "ULUS10531",
}


def f32(bits: int) -> float:
    return struct.unpack(">f", bits.to_bytes(4, "big"))[0]


def bits(value: float) -> int:
    return int.from_bytes(struct.pack(">f", value), "big")


def clean_text(node) -> str:
    return node.get_text("\n", strip=True).replace("\xa0", " ")


def game_chunks(text: str) -> list[str]:
    chunks: list[list[str]] = []
    current: list[str] = []
    seen_g = seen_s = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if (line.startswith("_G ") and seen_g) or (line.startswith("_S ") and seen_s):
            chunks.append(current)
            current, seen_g, seen_s = [], False, False
        current.append(line)
        seen_g |= line.startswith("_G ")
        seen_s |= line.startswith("_S ")
    if current:
        chunks.append(current)
    return ["\n".join(x) for x in chunks]


def serial_and_name(text: str) -> tuple[str | None, str | None]:
    sm = re.search(r"(?m)^_S\s+([A-Z]{4})-?(\d{5})\s*$", text)
    gm = re.search(r"(?m)^_G\s+(.+?)\s*$", text)
    name = gm.group(1).strip() if gm else None
    serial = "".join(sm.groups()) if sm else INFERRED_IDS.get(name or "")
    return serial, name


def normalize(text: str, serial: str, name: str) -> str:
    lines = text.splitlines()
    # Two forum entries have a missing/mistyped serial directive.
    lines = [x for x in lines if not re.fullmatch(r"_L\s+[A-Z]{4}-?\d{5}", x)]
    lines = [re.sub(r"^_S\s+[A-Z]{4}-?\d{5}$", f"_S {serial}", x) for x in lines]
    if not any(x.startswith("_G ") for x in lines):
        lines.insert(0, f"_G {name}")
    if not any(x.startswith("_S ") for x in lines):
        insert = 1 if lines and lines[0].startswith("_G ") else 0
        lines.insert(insert, f"_S {serial}")
    # Files should load with no ratio forced on by default.
    lines = [re.sub(r"^_C1\b", "_C0", x) for x in lines]
    lines = ["_L 0x00000000 0x00000000" if x == "_L 0x00 0x00" else x for x in lines]
    return "\n".join(lines)


def parse_blocks(lines: list[str]):
    blocks = []
    for i, line in enumerate(lines):
        if not re.match(r"^_C[01]\b", line):
            continue
        end = i + 1
        while end < len(lines) and not re.match(r"^_C[01]\b", lines[end]):
            end += 1
        label = re.sub(r"^_C[01]\s*", "", line).strip()
        blocks.append((i, end, label, lines[i + 1 : end]))
    return blocks


def label_ratio(label: str) -> tuple[int, int] | None:
    m = re.search(r"(\d+(?:\.\d+)?):(\d+)", label)
    if m:
        a, b = float(m.group(1)), int(m.group(2))
        if a == 32 and b == 1 and "wide" in label.lower():
            return (32, 9)
        return (int(a * 10), b * 10) if not a.is_integer() else (int(a), b)
    low = label.lower()
    if "ultrawide" in low:
        return (21, 9)
    if "superwide" in low or "super ultrawide" in low:
        return (32, 9)
    if "handheld" in low or "hanheld" in low:
        return (3, 2)
    return None


def find_ratio_blocks(lines: list[str]):
    result: dict[tuple[int, int], list[tuple[str, list[str]]]] = {}
    for _, _, label, body in parse_blocks(lines):
        ratio = label_ratio(label)
        if ratio:
            result.setdefault(ratio, []).append((label, body))
    return result


def l_lines(body: list[str]):
    result = []
    for line in body:
        m = re.match(r"^_L\s+(0x[0-9A-Fa-f]+)\s+(?:0x)?([0-9A-Fa-f]{8})(.*)$", line)
        if m:
            result.append((m.group(1), int(m.group(2), 16), m.group(3).strip()))
    return result


def select_block(blocks, ratio):
    options = blocks.get(ratio, [])
    if not options:
        return None
    # Naruto has several 21:9 choices; use the explicit 2.33 variant.
    for label, body in options:
        if "2.33" in label:
            return label, body
    return options[0]


def transform_body(
    source_body: list[str], source_ratio: tuple[int, int], target: tuple[int, int],
    baseline_body: list[str] | None = None, baseline_ratio: tuple[int, int] | None = None,
) -> list[str]:
    source = l_lines(source_body)
    baseline = {addr: value for addr, value, _ in l_lines(baseline_body or [])}
    src_ar = source_ratio[0] / source_ratio[1]
    dst_ar = target[0] / target[1]
    base_ar = baseline_ratio[0] / baseline_ratio[1] if baseline_ratio else None
    out = []
    i = 0
    while i < len(source):
        addr, value, _comment = source[i]
        # MIPS lui/ori pairs loading a direct float aspect-ratio constant.
        if i + 1 < len(source):
            a2, v2, _ = source[i + 1]
            if (value >> 16) in (0x3C02, 0x3C04) and (v2 >> 16) in (0x3442, 0x3484):
                target_bits = RATIO_BITS[target]
                out.append(f"_L {addr} 0x{value & 0xFFFF0000 | target_bits >> 16:08X}")
                out.append(f"_L {a2} 0x{v2 & 0xFFFF0000 | target_bits & 0xFFFF:08X}")
                i += 2
                continue

        value_f = f32(value)
        # Common forum constant 0x4017B426 means 64:27 (about 2.37037),
        # but these entries use it as a direct aspect ratio.  Narrow targets
        # should use exact 4:3 and 3:2 constants.
        if value in (0x4017B426, 0x40155555, 0x401851EC, 0x401E147B, 0x401D70A4, 0x401EB852):
            new_value = RATIO_BITS[target]
        elif (
            addr in baseline
            and base_ar
            and abs(value_f - src_ar) / src_ar < 0.03
            and abs(f32(baseline[addr]) - base_ar) / base_ar < 0.03
        ):
            new_value = RATIO_BITS[target]
        elif addr in baseline and base_ar and value_f > 1e-8:
            base_f = f32(baseline[addr])
            if abs(value_f - base_f) / max(abs(base_f), 1e-8) < 0.015:
                new_value = value
            else:
                exponent = math.log(abs(value_f / base_f)) / math.log(src_ar / base_ar)
                calculated = base_f * (dst_ar / base_ar) ** exponent
                new_value = bits(calculated)
        elif abs(value_f - src_ar) / src_ar < 0.08:
            new_value = RATIO_BITS[target]
        else:
            # A lone non-ratio value cannot be safely inferred; retain it so
            # all addresses in multi-line patches remain represented.
            new_value = value
        out.append(f"_L {addr} 0x{new_value:08X}")
        i += 1
    return out


SPECIAL = {
    "ULUS10487": {
        (4, 3): ["_L 0x20460464 0x3FAAAAAB"],
    },
    "ULES01597": {
        (3, 2): ["_L 0x202E0074 0x00000198 // DWORD 408 (272 * 3/2)"],
        (4, 3): ["_L 0x202E0074 0x0000016B // DWORD 363 (rounded 272 * 4/3)"],
    },
    "ULUS10157": {
        (3, 2): ["_L 0x2015D214 0x00000195 // X resolution 405"],
        (4, 3): ["_L 0x2015D214 0x00000168 // X resolution 360"],
    },
    # These two posts only provide 21:9 values.  The narrow variants scale
    # each field in the direction implied by its 21:9 value and are marked as
    # calculated because the forum author did not test narrow displays.
    "ULJM05775": {
        (3, 2): ["_L 0x213ED410 0x00000230 // DWORD 560 (calculated)", "_L 0x211650B0 0x3F76DB6E // float 0.964286 (calculated)"],
        (4, 3): ["_L 0x213ED410 0x00000276 // DWORD 630 (calculated)", "_L 0x211650B0 0x3F5B6DB7 // float 0.857143 (calculated)"],
    },
    "ULUS10015": {
        (3, 2): ["_L 0x203C4260 0x3FB62FC9 // float 1.423333 (calculated)", "_L 0x203C4274 0x3FC00000 // float 1.5"],
        (4, 3): ["_L 0x203C4260 0x3FCCCCCC // float 1.6 (calculated)", "_L 0x203C4274 0x3FAAAAAB // float 1.333333"],
    },
    "ULUS10512": {
        (3, 2): [
            "_L 0x203B2340 0x3FC00000 // 3D Battles",
            "_L 0x206D94B0 0x3EF05BB3 // Tartarus X Ratio (calculated)",
            "_L 0x203B2084 0x3F132629 // Tartarus Y Ratio (calculated; use only if X Ratio glitches)",
        ],
        (4, 3): [
            "_L 0x203B2340 0x3FAAAAAB // 3D Battles",
            "_L 0x206D94B0 0x3ED5A6D8 // Tartarus X Ratio (calculated)",
            "_L 0x203B2084 0x3F2214C1 // Tartarus Y Ratio (calculated; use only if X Ratio glitches)",
        ],
    },
}


def add_target(lines: list[str], serial: str, target: tuple[int, int]) -> list[str]:
    blocks = find_ratio_blocks(lines)
    if target in blocks:
        return lines
    label = "3:2" if target == (3, 2) else "4:3"
    if serial == "NPJH50352":
        value = "0x3FC00000" if target == (3, 2) else "0x3FAAAAAB"
        return lines + [
            f"_C0 v1.0 {label}",
            f"_L 0x2028AF48 {value}",
            f"_C0 v1.01 {label}",
            f"_L 0x2028A888 {value}",
        ]
    if serial in SPECIAL and target in SPECIAL[serial]:
        body = SPECIAL[serial][target]
    else:
        choices = (
            [((3, 2), (16, 9)), ((4, 3), (16, 9)), ((21, 9), (16, 9)), ((21, 9), None)]
            if target == (4, 3)
            else [((4, 3), (16, 9)), ((21, 9), (16, 9)), ((21, 9), None)]
        )
        selected = None
        for source_ratio, base_ratio in choices:
            source = select_block(blocks, source_ratio)
            base = select_block(blocks, base_ratio) if base_ratio else None
            if source and (base_ratio is None or base):
                selected = (source_ratio, source[1], base_ratio, base[1] if base else None)
                break
        if not selected:
            return lines
        source_ratio, source_body, base_ratio, base_body = selected
        body = transform_body(source_body, source_ratio, target, base_body, base_ratio)
    if not body:
        return lines
    return lines + [f"_C0 {label}"] + body


def custom_page5_games(soup) -> list[str]:
    result = []
    body = soup.select_one("#pid_142041")
    text = clean_text(body)
    posted = list(body.select("div.codeblock div.body"))
    v10 = clean_text(posted[0]).replace("_C0 ", "_C0 v1.0 ")
    v101 = clean_text(posted[1]).replace("_C0 ", "_C0 v1.01 ")
    result.extend([
        "_G God Eater Burst [JP]\n_S NPJH50352\n" + v10 + "\n" + v101,
        "_G Monster Hunter Portable 3rd [PSP]\n_S ULJM05800\n// Cheat must be enabled before launching the game.\n" + clean_text(posted[2]),
    ])
    return result


def collect(html_files: list[Path], additional_files: list[Path] | None = None):
    soups = [BeautifulSoup(p.read_text(errors="replace"), "html.parser") for p in html_files]
    games: dict[str, tuple[str, str]] = {}

    def take(text: str, only_new: bool = False):
        for chunk in game_chunks(text):
            serial, name = serial_and_name(chunk)
            if serial and name and (not only_new or serial not in games):
                games[serial] = (name, normalize(chunk, serial, name))

    # Page 1 first post is the maintained/consolidated list.
    for code in soups[0].select_one("div.post_body").select("div.codeblock div.body"):
        take(clean_text(code))

    # Page 2: corrected/full Lord of Apocalypse plus four new patches.
    for code in soups[1].select_one("#pid_137426").select("div.codeblock div.body"):
        take(clean_text(code))

    # All actual code posts on pages 3 and 4.
    for page in (soups[2], soups[3]):
        for body in page.select("div.post_body"):
            for quote in body.select("blockquote"):
                quote.decompose()
            for code in body.select("div.codeblock div.body"):
                take(clean_text(code))

    # Page 5 includes IDs in prose for three code blocks.
    for text in custom_page5_games(soups[4]):
        take(text)
    for pid in ("pid_143053", "pid_146762", "pid_146771"):
        body = soups[4].select_one(f"#{pid}")
        for code in body.select("div.codeblock div.body"):
            take(clean_text(code))

    # Page 6: use the later fixed MHP2G assembly patch, not its beta predecessor.
    for pid in ("pid_151886", "pid_159009", "pid_160651"):
        body = soups[5].select_one(f"#{pid}")
        for code in body.select("div.codeblock div.body"):
            take(clean_text(code))

    # Supplemental collection threads may repeat older or superseded codes.
    # Import only IDs not already collected from the primary six-page thread.
    for path in additional_files or []:
        soup = BeautifulSoup(path.read_text(errors="replace"), "html.parser")
        for body in soup.select("div.post_body"):
            for quote in body.select("blockquote"):
                quote.decompose()
            for code in body.select("div.codeblock div.body"):
                take(clean_text(code), only_new=True)
    return games


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", nargs=6, type=Path, help="forum pages 1 through 6")
    parser.add_argument(
        "--additional-html", action="append", type=Path, default=[],
        help="supplemental forum thread HTML; only new game IDs are imported",
    )
    parser.add_argument("--output", type=Path, default=Path("PPSSPP"))
    args = parser.parse_args()
    if not all(p.is_file() for p in args.html):
        parser.error("all six HTML page paths must exist")

    if not all(p.is_file() for p in args.additional_html):
        parser.error("all supplemental HTML paths must exist")
    games = collect(args.html, args.additional_html)
    args.output.mkdir(parents=True, exist_ok=True)
    for serial, (name, text) in sorted(games.items()):
        lines = text.splitlines()
        lines = ["_C0 Handheld 3:2" if x == "_C0 Handheld" else x for x in lines]
        lines = add_target(lines, serial, (3, 2))
        lines = add_target(lines, serial, (4, 3))
        output = "\n".join(lines).replace("\xa0", " ").rstrip() + "\n"
        (args.output / f"{serial}.ini").write_text(output)
    print(f"Wrote {len(games)} game files to {args.output}")


if __name__ == "__main__":
    main()
