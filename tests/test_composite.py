from __future__ import annotations

import numpy as np
import pandas as pd

from onchain_index.composite import (
    TIER_PCT,
    epoch_for_date,
    holder_behavior_cohorts,
    holder_behavior_composite,
    pi_score,
    sizing_tier,
    valuation_composite,
)


def _sample_frame(periods: int = 900) -> pd.DataFrame:
    idx = pd.date_range("2018-01-01", periods=periods)
    x = np.linspace(1.0, 10.0, periods)
    wiggle = np.sin(np.linspace(0.0, 20.0, periods))
    return pd.DataFrame(
        {
            "sth_mvrv": x + wiggle,
            "rhodl_ratio": x * 2 + wiggle,
            "puell_multiple": x / 2 + wiggle,
            "mvrv_zscore": x / 3 + wiggle,
            "hodl_1yr_pct": 60 + np.cos(np.linspace(0.0, 12.0, periods)),
            "mstr_btc": np.where(
                np.arange(periods) < 100,
                np.nan,
                np.arange(periods) + np.sin(np.linspace(0.0, 40.0, periods)) * 10,
            ),
            "etf_net_flow_m": np.sin(np.linspace(0.0, 40.0, periods)) * 100,
        },
        index=idx,
    )


def test_pi_score_uses_dimension_composites() -> None:
    data = _sample_frame()

    expected = valuation_composite(data) + holder_behavior_composite(data)

    pd.testing.assert_series_equal(pi_score(data), expected.rename("pi_score"))


def test_sizing_tier_is_binary_mrmi_shape() -> None:
    idx = pd.date_range("2024-01-01", periods=5)
    score = pd.Series([-2.0, 0.0, 0.0001, 2.0, np.nan], index=idx)

    tiers = sizing_tier(score)

    labels = list(tiers.astype("object"))
    assert labels == ["CASH", "CASH", "STAY LONG", "STAY LONG", np.nan]
    allocations = [TIER_PCT[str(label)] if not pd.isna(label) else np.nan for label in labels]
    assert allocations[:4] == [0.0, 0.0, 100.0, 100.0]
    assert np.isnan(allocations[-1])
    assert list(tiers.cat.categories) == ["CASH", "STAY LONG"]
    assert tiers.cat.ordered


def test_pi_score_math_regression_unchanged_by_tier_simplification() -> None:
    score = pi_score(_sample_frame(periods=900)).dropna().tail(5)

    expected = pd.Series(
        [1.151482401317, 1.163384874879, 1.175071621867, 1.186547303724, 1.197816696559],
        index=pd.date_range("2020-06-14", periods=5),
        name="pi_score",
    )
    pd.testing.assert_series_equal(score, expected, check_exact=False, atol=1e-12)


def test_epoch_evolution_labels_and_available_cohorts() -> None:
    assert epoch_for_date("2019-12-31") == "2012-2020"
    assert epoch_for_date("2021-01-01") == "2020-2024"
    assert epoch_for_date("2024-01-11") == "2024-onward"

    data = _sample_frame(periods=3200)
    data.index = pd.date_range("2018-01-01", periods=len(data))
    cohorts = holder_behavior_cohorts(data)

    pre_2020 = pd.Timestamp("2019-12-31")
    post_2024 = cohorts["institutional_etf"].dropna().index[-1]

    assert pd.notna(cohorts["on_chain"].loc[pre_2020])
    assert pd.isna(cohorts["corporate_dat"].loc[pre_2020])
    assert pd.isna(cohorts["institutional_etf"].loc[pre_2020])
    assert pd.notna(cohorts["on_chain"].loc[post_2024])
    assert pd.notna(cohorts["corporate_dat"].loc[post_2024])
    assert pd.notna(cohorts["institutional_etf"].loc[post_2024])
    assert set(cohorts) == {"on_chain", "corporate_dat", "institutional_etf"}


def test_composite_has_no_same_day_lookahead() -> None:
    data = _sample_frame(periods=620)
    changed = data.copy()
    date = data.index[-1]
    changed.loc[date, ["sth_mvrv", "rhodl_ratio", "puell_multiple", "mvrv_zscore"]] = 1_000_000.0
    changed.loc[date, "hodl_1yr_pct"] = -1_000_000.0

    base_score = pi_score(data)
    changed_score = pi_score(changed)

    assert changed_score.loc[date] == base_score.loc[date]
