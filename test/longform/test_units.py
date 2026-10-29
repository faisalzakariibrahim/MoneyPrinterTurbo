import pytest

from app.longform import align, captions, footage, niche, script, voice
from app.longform.captions import CaptionStyle, Word


def W(text, s, e):
    return Word(text, s, e)


def test_phrases_break_on_sentence_and_limits():
    words = [W("Hello", 0, .3), W("world.", .35, .7), W("This", 1, 1.2), W("is", 1.25, 1.3),
             W("a", 1.35, 1.4), W("long", 1.45, 1.6), W("phrase", 1.65, 1.9), W("today", 1.95, 2.2)]
    phrases = captions.build_phrases(words, CaptionStyle(max_words=4))
    assert [len(p.words) for p in phrases] == [2, 4, 2]


def test_karaoke_events_are_contiguous_and_highlight_one_word():
    words = [W("one", 0, .4), W("two", .5, .9), W("three", 1.0, 1.4)]
    style = CaptionStyle()
    ev = captions.events(captions.build_phrases(words, style), style)
    assert len(ev) == 3
    assert ev[0][1] == ev[1][0]  # no flicker gap between words
    assert all(e[2].count("\\1c") == 1 for e in ev)


def test_ass_injection_is_neutralised():
    assert "{" not in captions.escape_text("{\\pos(0,0)}hacked")
    assert "\\" not in captions.escape_text("{\\pos(0,0)}hacked")


def test_ass_window_shifts_times():
    ev = [(10.0, 12.0, "a"), (59.0, 61.0, "b"), (70.0, 71.0, "c")]
    doc = captions.render_ass(ev, CaptionStyle(), 1920, 1080, window=(60.0, 120.0))
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,Cap,,0,0,0,,b" in doc
    assert "0:00:10.00,0:00:11.00" in doc and ",a\n" not in doc


def test_hex_to_ass():
    assert captions.hex_to_ass("#FFD84D") == "&H004DD8FF"


def test_timeline_fills_exactly_and_respects_clip_bounds():
    clips = [footage.Clip("a", 20), footage.Clip("b", 8), footage.Clip("c", 3)]
    segs = footage.plan_timeline(clips, 600, seed="x")
    assert abs(sum(s.duration for s in segs) - 600) < 1e-6
    for s in segs:
        assert s.inpoint >= 0 and s.inpoint + s.duration <= clips[s.clip].duration + 1e-6
    chunks = footage.split_chunks(segs, 600, 300)
    assert [round(c.duration, 6) for c in chunks] == [300, 300]
    for c in chunks:
        assert abs(sum(s.duration for s in c.segments) - c.duration) < 1e-6


def test_snap_to_script_keeps_script_spelling():
    rec = [W("the", 0, .2), W("dragon's", .3, .6), W("hoard", .7, 1.0), W("was", 1.1, 1.2), W("gold", 1.3, 1.6)]
    out = align.snap_to_script(rec, "The dragon's hoard was GOLD!")
    assert [w.text for w in out] == ["The", "dragon's", "hoard", "was", "GOLD!"]
    assert out[1].start == .3


def test_snap_interpolates_unmatched():
    rec = [W("a", 0, .2), W("d", 1.0, 1.2)]
    out = align.snap_to_script(rec, "a b c d")
    assert [w.text for w in out] == ["a", "b", "c", "d"]
    assert out[0].end <= out[1].start < out[2].start < out[3].start


def test_split_text_respects_limit():
    text = ("Sentence number one is here. " * 200) + "\n\n" + "Short para."
    chunks = voice.split_text(text, 500)
    assert all(len(c) <= 500 for c in chunks)
    assert "".join(chunks).replace(" ", "").replace("\n", "") == text.replace(" ", "").replace("\n", "")


@pytest.mark.parametrize("url,vid", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
])
def test_parse_video_id(url, vid):
    assert niche.parse_video_id(url) == vid


@pytest.mark.parametrize("url", [
    "https://evil.com/watch?v=dQw4w9WgXcQ",
    "http://169.254.169.254/latest/meta-data",
    "https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=short",
])
def test_parse_video_id_rejects(url):
    with pytest.raises(niche.NicheError):
        niche.parse_video_id(url)


def test_clean_narration_strips_markdown_and_directions():
    raw = "## Chapter 1: The Start\n**Bold** words here.\n[MUSIC SWELLS]\n(pause)\nPlain line."
    assert script.clean_narration(raw) == "Bold words here.\nPlain line."
