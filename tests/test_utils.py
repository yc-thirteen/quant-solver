"""Unit tests for utility helpers."""

from __future__ import annotations

import pytest

from quant_solver.utils import answers_equivalent, extract_json, normalize_answer


class TestExtractJson:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_json_with_prose(self):
        text = 'Here is the answer:\n\n{"answer": "4/3"}\n\nThat is all.'
        assert extract_json(text) == {"answer": "4/3"}

    def test_fenced_json(self):
        text = 'Sure!\n```json\n{"x": 2}\n```\n'
        assert extract_json(text) == {"x": 2}

    def test_balanced_braces_with_nested(self):
        text = 'prose {"a": {"b": 1}} trailing'
        assert extract_json(text) == {"a": {"b": 1}}

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            extract_json("nothing here")


class TestNormalizeAnswer:
    def test_percentage(self):
        assert normalize_answer("2.3%") == normalize_answer("0.023")

    def test_fraction_equivalence(self):
        assert normalize_answer("1/2") == normalize_answer("0.5")

    def test_caret_treated_as_power(self):
        # 3^2 and 9 should canonicalize the same.
        assert normalize_answer("3^2") == normalize_answer("9")


class TestAnswersEquivalent:
    def test_identical_strings(self):
        assert answers_equivalent("4/3", "4/3")

    def test_fraction_and_decimal(self):
        assert answers_equivalent("1/2", "0.5")

    def test_percent_and_decimal(self):
        assert answers_equivalent("2.3%", "0.023")

    def test_equivalent_radicals(self):
        assert answers_equivalent("(9*sqrt(2)-6)/7", "3*sqrt(2)/(3+sqrt(2))")

    def test_non_equivalent(self):
        assert not answers_equivalent("1/2", "1/3")

    def test_unparseable_falls_back_to_string_compare(self):
        assert answers_equivalent("NEEDS_HUMAN_REVIEW", "NEEDS_HUMAN_REVIEW")
        assert not answers_equivalent("NEEDS_HUMAN_REVIEW", "something")
