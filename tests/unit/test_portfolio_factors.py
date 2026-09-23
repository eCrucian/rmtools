from __future__ import annotations

import numpy as np

from src.portfolio import factors as f


def test_factor_names_are_unique_and_cover_all_categories():
    assert len(f.FACTOR_NAMES) == len(set(f.FACTOR_NAMES))
    assert len(f.FACTOR_NAMES) == len(f.CURVES) + len(f.SPOTS) + len(f.VOLS) + len(f.SPREADS) + len(f.BEHAVIORAL)


def test_build_correlation_matrix_is_symmetric_psd_unit_diagonal():
    corr = f.build_correlation_matrix()
    assert corr.shape == (len(f.FACTOR_NAMES), len(f.FACTOR_NAMES))
    assert np.allclose(corr, corr.T)
    assert np.allclose(np.diag(corr), 1.0)
    eigvals = np.linalg.eigvalsh(corr)
    assert eigvals.min() >= -1e-8


def test_raw_correlation_pairs_reference_known_factors():
    names = set(f.FACTOR_NAMES)
    for a, b, rho in f._RAW_CORRELATIONS:
        assert a in names
        assert b in names
        assert -1.0 <= rho <= 1.0


def test_nearest_psd_repairs_invalid_matrix():
    # matriz simétrica mas NÃO-PSD deliberada (três correlações fortes
    # inconsistentes entre si não podem coexistir numa matriz de correlação válida)
    broken = np.array(
        [
            [1.0, 0.9, -0.9],
            [0.9, 1.0, 0.9],
            [-0.9, 0.9, 1.0],
        ]
    )
    assert np.linalg.eigvalsh(broken).min() < 0

    repaired = f.nearest_psd(broken)
    assert np.allclose(np.diag(repaired), 1.0)
    assert np.linalg.eigvalsh(repaired).min() >= -1e-8
    assert np.allclose(repaired, repaired.T)


def test_nearest_psd_leaves_already_psd_matrix_close_to_identity():
    identity = np.eye(4)
    repaired = f.nearest_psd(identity)
    assert np.allclose(repaired, identity, atol=1e-8)
