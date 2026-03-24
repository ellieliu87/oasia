"""
Tests for ui/watchlist.py helper functions.

These test pure-logic functions that do not require a running Gradio app.
"""
import pandas as pd
import pytest

from ui.watchlist import _cusip_from_choice, _watchlist_df, _search_results


# ---------------------------------------------------------------------------
# _cusip_from_choice
# ---------------------------------------------------------------------------

class TestCusipFromChoice:

    def test_parses_standard_format(self):
        choice = "ABCD123456 — CC30 6.00%"
        assert _cusip_from_choice(choice) == "ABCD123456"

    def test_parses_with_spaces_around_separator(self):
        choice = "XYZ9876543 — GN30 5.50%"
        assert _cusip_from_choice(choice) == "XYZ9876543"

    def test_returns_empty_for_none(self):
        assert _cusip_from_choice(None) == ""

    def test_returns_empty_for_empty_string(self):
        assert _cusip_from_choice("") == ""

    def test_strips_whitespace(self):
        choice = "  CUSIP001  — CC15 4.50%"
        assert _cusip_from_choice(choice) == "CUSIP001"

    def test_no_separator_returns_whole_string(self):
        """If the choice has no '—' separator, return the whole stripped string."""
        choice = "PLAINID"
        assert _cusip_from_choice(choice) == "PLAINID"

    def test_multiple_separators_takes_first(self):
        """Only the part before the first separator is the CUSIP."""
        choice = "CUSIP123 — CC30 — extra"
        assert _cusip_from_choice(choice) == "CUSIP123"


# ---------------------------------------------------------------------------
# _watchlist_df
# ---------------------------------------------------------------------------

class TestWatchlistDf:

    def test_returns_dataframe(self):
        result = _watchlist_df(username="nonexistent_user_xyz")
        assert isinstance(result, pd.DataFrame)

    def test_empty_watchlist_has_correct_columns(self):
        df = _watchlist_df(username="nonexistent_user_xyz")
        expected_cols = {"CUSIP", "Pool ID", "Notes", "Added"}
        assert set(df.columns) == expected_cols, (
            f"Unexpected columns: {set(df.columns)}"
        )

    def test_empty_watchlist_has_no_rows(self):
        df = _watchlist_df(username="nonexistent_user_xyz")
        assert len(df) == 0


# ---------------------------------------------------------------------------
# _search_results
# ---------------------------------------------------------------------------

class TestSearchResults:

    def test_returns_tuple(self):
        result = _search_results()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_first_element_is_dataframe(self):
        df, choices = _search_results()
        assert isinstance(df, pd.DataFrame)

    def test_second_element_is_list(self):
        df, choices = _search_results()
        assert isinstance(choices, list)

    def test_choices_are_strings(self):
        df, choices = _search_results()
        for c in choices:
            assert isinstance(c, str), f"Choice is not a string: {c!r}"

    def test_choices_contain_cusip_separator(self):
        df, choices = _search_results()
        if choices:  # only check if there are results
            for c in choices:
                assert " — " in c, (
                    f"Choice does not contain ' — ' separator: {c!r}"
                )

    def test_df_has_required_columns(self):
        df, _ = _search_results()
        if not df.empty:
            required = {"CUSIP", "Type", "Coupon %", "FICO", "LTV %"}
            assert required.issubset(set(df.columns)), (
                f"Missing columns: {required - set(df.columns)}"
            )

    def test_product_filter_returns_subset(self):
        df_all, choices_all = _search_results(product="All")
        df_cc30, choices_cc30 = _search_results(product="CC30")
        # Filtered result should have <= total results
        assert len(df_cc30) <= len(df_all)

    def test_invalid_product_returns_empty_or_partial(self):
        df, choices = _search_results(product="INVALIDTYPE999")
        assert isinstance(df, pd.DataFrame)
        assert isinstance(choices, list)

    def test_df_row_count_matches_choices(self):
        df, choices = _search_results()
        assert len(df) == len(choices), (
            f"DataFrame rows ({len(df)}) != choices count ({len(choices)})"
        )

    def test_choices_cusip_matches_df(self):
        """Each choice CUSIP should appear in the DataFrame CUSIP column."""
        df, choices = _search_results()
        if df.empty or not choices:
            return
        df_cusips = set(df["CUSIP"].astype(str))
        for choice in choices:
            cusip = _cusip_from_choice(choice)
            assert cusip in df_cusips, (
                f"Choice CUSIP '{cusip}' not found in DataFrame"
            )
