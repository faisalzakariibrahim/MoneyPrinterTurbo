"""Word-by-word ASS caption generation.

Words (with timestamps from forced alignment) are grouped into short phrases. In
``karaoke`` mode each word gets its own event that shows the whole phrase with the
current word highlighted, which is the style that holds attention on long videos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


@dataclass
class CaptionStyle:
    enabled: bool = True
    mode: str = "karaoke"  # karaoke | phrase | word
    font: str = "Inter"
    bold: bool = True
    size_ratio: float = 0.055  # font size as a fraction of video height
    primary: str = "#FFFFFF"
    highlight: str = "#FFD84D"
    outline: str = "#000000"
    outline_ratio: float = 0.0045
    shadow_ratio: float = 0.002
    box: bool = False
    box_color: str = "#000000"
    box_opacity: float = 0.55
    position: str = "bottom"  # bottom | center | top
    margin_ratio: float = 0.09
    max_words: int = 5
    max_chars: int = 30
    max_gap: float = 0.6
    uppercase: bool = False

    @classmethod
    def from_dict(cls, data: dict | None) -> "CaptionStyle":
        if not data:
            return cls()
        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class Phrase:
    words: list[Word] = field(default_factory=list)

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end


_SENTENCE_END = re.compile(r"[.!?…]['\")\]]*$")
_CLAUSE_END = re.compile(r"[,;:—–]['\")\]]*$")


def hex_to_ass(color: str, opacity: float = 1.0) -> str:
    """#RRGGBB -> &HAABBGGRR (ASS alpha is inverted: 00 opaque, FF transparent)."""
    c = color.lstrip("#")
    if len(c) != 6 or not re.fullmatch(r"[0-9A-Fa-f]{6}", c):
        c = "FFFFFF"
    r, g, b = c[0:2], c[2:4], c[4:6]
    alpha = max(0, min(255, round((1 - opacity) * 255)))
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs = int(round(seconds * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape_text(text: str) -> str:
    # Braces start override blocks and backslashes start tags; neutralise both so
    # script text can never inject ASS commands.
    return (
        text.replace("\\", "⧵")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def clean_words(words: Iterable[Word]) -> list[Word]:
    out: list[Word] = []
    for w in words:
        text = w.text.strip()
        if not text or w.end < w.start:
            continue
        out.append(Word(text, float(w.start), float(w.end)))
    out.sort(key=lambda w: w.start)
    return out


def build_phrases(words: Sequence[Word], style: CaptionStyle) -> list[Phrase]:
    phrases: list[Phrase] = []
    current = Phrase()
    chars = 0
    limit_words = 1 if style.mode == "word" else max(1, style.max_words)
    for w in clean_words(words):
        if current.words:
            gap = w.start - current.words[-1].end
            prev = current.words[-1].text
            if (
                len(current.words) >= limit_words
                or chars + 1 + len(w.text) > style.max_chars
                or gap > style.max_gap
                or _SENTENCE_END.search(prev)
                or (_CLAUSE_END.search(prev) and len(current.words) >= 2)
            ):
                phrases.append(current)
                current = Phrase()
                chars = 0
        current.words.append(w)
        chars += len(w.text) + (1 if chars else 0)
    if current.words:
        phrases.append(current)
    return phrases


def _alignment(position: str) -> int:
    return {"top": 8, "center": 5}.get(position, 2)


def header(style: CaptionStyle, width: int, height: int) -> str:
    size = max(12, round(height * style.size_ratio))
    outline = max(0, round(height * style.outline_ratio))
    shadow = max(0, round(height * style.shadow_ratio))
    margin_v = round(height * style.margin_ratio)
    margin_h = round(width * 0.08)
    border_style = 3 if style.box else 1
    back = hex_to_ass(style.box_color, style.box_opacity) if style.box else hex_to_ass("#000000", 0.6)
    outline_colour = hex_to_ass(style.box_color, style.box_opacity) if style.box else hex_to_ass(style.outline)
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "YCbCr Matrix: TV.709\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Cap,{style.font},{size},{hex_to_ass(style.primary)},{hex_to_ass(style.highlight)},"
        f"{outline_colour},{back},{-1 if style.bold else 0},0,0,0,100,100,0,0,"
        f"{border_style},{outline},{shadow},{_alignment(style.position)},{margin_h},{margin_h},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _fmt(word: Word, style: CaptionStyle) -> str:
    text = escape_text(word.text)
    return text.upper() if style.uppercase else text


def events(phrases: Sequence[Phrase], style: CaptionStyle) -> list[tuple[float, float, str]]:
    """Return absolute-time (start, end, ass_text) caption events."""
    hl = hex_to_ass(style.highlight)
    out: list[tuple[float, float, str]] = []
    for idx, phrase in enumerate(phrases):
        next_start = phrases[idx + 1].start if idx + 1 < len(phrases) else None
        tail_end = phrase.end + 0.35
        if next_start is not None:
            tail_end = min(tail_end, next_start)
        tail_end = max(tail_end, phrase.end)
        if style.mode == "phrase" or style.mode == "word":
            text = " ".join(_fmt(w, style) for w in phrase.words)
            out.append((phrase.start, tail_end, text))
            continue
        words = phrase.words
        for i, w in enumerate(words):
            start = w.start
            end = words[i + 1].start if i + 1 < len(words) else tail_end
            if end <= start:
                end = start + 0.05
            parts = []
            for j, other in enumerate(words):
                token = _fmt(other, style)
                parts.append(f"{{\\1c{hl}}}{token}{{\\r}}" if j == i else token)
            out.append((start, end, " ".join(parts)))
    return out


def render_ass(
    evts: Sequence[tuple[float, float, str]],
    style: CaptionStyle,
    width: int,
    height: int,
    window: tuple[float, float] | None = None,
) -> str:
    """Build an ASS document. With ``window`` only overlapping events are kept and
    their times are shifted so the window start becomes 0 (used for chunk renders)."""
    lines = [header(style, width, height)]
    offset = 0.0
    lo, hi = (window if window else (float("-inf"), float("inf")))
    if window:
        offset = lo
    for start, end, text in evts:
        if end <= lo or start >= hi:
            continue
        s = max(start, lo) - offset
        e = min(end, hi) - offset
        if e - s < 0.01:
            continue
        lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Cap,,0,0,0,,{text}\n")
    return "".join(lines)


def words_to_srt(words: Sequence[Word], style: CaptionStyle | None = None) -> str:
    """Plain SRT (phrase level) for uploading as YouTube closed captions."""
    style = style or CaptionStyle(mode="phrase", max_words=10, max_chars=60)

    def t(x: float) -> str:
        ms = int(round(max(0.0, x) * 1000))
        h, rem = divmod(ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    blocks = []
    for i, p in enumerate(build_phrases(words, style), start=1):
        text = " ".join(w.text for w in p.words)
        blocks.append(f"{i}\n{t(p.start)} --> {t(p.end)}\n{text}\n")
    return "\n".join(blocks)
