"""Tests del detector unicode_script."""
from __future__ import annotations

from src.detectors import unicode_script as us


class TestScriptDetection:
    def test_pure_spanish_is_latin(self):
        assert us.script_of("á") == "latin"
        assert us.script_of("ñ") == "latin"
        assert us.script_of("z") == "latin"

    def test_chinese_is_han(self):
        assert us.script_of("中") == "han"
        assert us.script_of("文") == "han"

    def test_cyrillic_is_cyrillic(self):
        assert us.script_of("Д") == "cyrillic"
        assert us.script_of("я") == "cyrillic"

    def test_arabic(self):
        assert us.script_of("ع") == "arabic"

    def test_hiragana_katakana(self):
        assert us.script_of("あ") == "hiragana"
        assert us.script_of("カ") == "katakana"

    def test_hangul(self):
        assert us.script_of("안") == "hangul"

    def test_neutrals_are_none(self):
        assert us.script_of(" ") is None
        assert us.script_of("1") is None
        assert us.script_of(".") is None
        assert us.script_of("🚀") is None
        assert us.script_of("!") is None


class TestRatio:
    def test_pure_spanish_zero_ratio(self):
        r, dom = us.non_allowed_ratio("Hola amigos cómo estáis", ["latin"])
        assert r == 0.0
        assert dom == ""

    def test_pure_chinese_full_ratio(self):
        r, dom = us.non_allowed_ratio("你好世界欢迎", ["latin"])
        assert r == 1.0
        assert dom == "han"

    def test_mixed_chinese_in_spanish_above_threshold(self):
        # "Hola 你好" → 4 latin + 2 han = 33% han
        r, dom = us.non_allowed_ratio("Hola 你好", ["latin"])
        assert 0.3 <= r < 0.4
        assert dom == "han"

    def test_emojis_dont_count(self):
        r, _ = us.non_allowed_ratio("Hola 🚀🔥", ["latin"])
        assert r == 0.0

    def test_numbers_dont_count(self):
        r, _ = us.non_allowed_ratio("Tengo 25 años", ["latin"])
        assert r == 0.0

    def test_cyrillic_allowed_when_in_list(self):
        r, _ = us.non_allowed_ratio("Привет hola", ["latin", "cyrillic"])
        assert r == 0.0


class TestCheck:
    def test_no_hit_when_below_threshold(self):
        hit = us.check("Hola amigos", True, ["latin"], 0.3)
        assert not hit

    def test_hit_on_first_msg_chinese(self):
        hit = us.check("你好世界", True, ["latin"], 0.3)
        assert hit
        assert hit.score == 100
        assert hit.rule == "non_allowed_script"
        assert "han" in hit.reason

    def test_lower_score_when_not_first_msg(self):
        hit = us.check("你好世界", False, ["latin"], 0.3)
        assert hit
        assert hit.score == 30

    def test_empty_message(self):
        assert not us.check("", True, ["latin"], 0.3)
        assert not us.check(None, True, ["latin"], 0.3)
