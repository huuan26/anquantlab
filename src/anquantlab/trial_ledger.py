"""Session trial ledger with eigenvalue-based effective independent trials (N_eff)."""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field

import numpy as np

from .schemas import TrialLedgerSnapshot

MAX_STORED_TRIALS = 128


@dataclass
class _DatasetLedger:
    total_evaluations: int = 0
    holdout_peeks: int = 0
    last_holdout_locked: bool = True
    peeked_keys: set[str] = field(default_factory=set)
    trials: OrderedDict[str, tuple[np.ndarray, float]] = field(default_factory=OrderedDict)
    cached_n_eff: float = 1.0
    cached_sr_std: float = 0.5
    best_is_sharpe: float | None = None


def _normalize_unit_norm(returns: np.ndarray) -> np.ndarray | None:
    arr = np.asarray(returns, dtype=np.float64)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    if arr.size < 3:
        return None
    centered = arr - float(np.mean(arr))
    norm = float(np.linalg.norm(centered))
    if norm <= 1e-12:
        return None
    return centered / norm


def _recompute_effective_trials(
    trials: OrderedDict[str, tuple[np.ndarray, float]],
) -> tuple[float, float, float | None]:
    if not trials:
        return 1.0, 0.5, None

    sharpes = [sr for _, sr in trials.values() if np.isfinite(sr)]
    best_sr = round(max(sharpes), 4) if sharpes else None
    sr_std = (
        round(max(0.15, float(np.std(np.asarray(sharpes, dtype=np.float64), ddof=1))), 4)
        if len(sharpes) >= 2
        else 0.5
    )

    non_null_vecs = [vec for vec, _ in trials.values() if vec is not None and vec.size >= 3]
    if len(non_null_vecs) <= 1:
        return 1.0, sr_std, best_sr

    # Align on the most common In-Sample length (in case dataset reloaded)
    target_len = non_null_vecs[-1].size
    aligned = [v for v in non_null_vecs if v.size == target_len]
    m = len(aligned)
    if m <= 1:
        return 1.0, sr_std, best_sr

    mat = np.vstack(aligned)
    corr = np.clip(mat @ mat.T, -1.0, 1.0)
    np.fill_diagonal(corr, 1.0)
    frob_sq = float(np.sum(corr * corr))
    n_eff = (m * m) / max(float(m), frob_sq)
    return round(max(1.0, min(float(m), n_eff)), 2), sr_std, best_sr


class TrialLedgerRegistry:
    """Thread-safe in-memory tracker for multiple-testing p-hacking defense."""

    def __init__(self, max_trials: int = MAX_STORED_TRIALS) -> None:
        self.max_trials = max(8, max_trials)
        self._lock = threading.Lock()
        self._ledgers: dict[str, _DatasetLedger] = {}

    def record_trial(
        self,
        dataset_id: str,
        trial_key: str,
        is_net_returns: np.ndarray,
        is_sharpe: float,
        *,
        holdout_locked: bool,
    ) -> TrialLedgerSnapshot:
        """Record an IS strategy evaluation, update eigenvalue N_eff, and track OOS peeks."""
        unit_vec = _normalize_unit_norm(is_net_returns)
        clean_sr = float(is_sharpe) if np.isfinite(is_sharpe) else 0.0

        with self._lock:
            ledger = self._ledgers.setdefault(dataset_id, _DatasetLedger())
            ledger.total_evaluations += 1

            if not holdout_locked:
                if ledger.last_holdout_locked or trial_key not in ledger.peeked_keys:
                    ledger.holdout_peeks += 1
                    ledger.peeked_keys.add(trial_key)
            ledger.last_holdout_locked = holdout_locked

            is_new_or_updated = trial_key not in ledger.trials
            if unit_vec is not None:
                ledger.trials[trial_key] = (unit_vec, clean_sr)
                ledger.trials.move_to_end(trial_key)
            elif is_new_or_updated:
                ledger.trials[trial_key] = (np.zeros(0, dtype=np.float64), clean_sr)

            while len(ledger.trials) > self.max_trials:
                ledger.trials.popitem(last=False)

            if is_new_or_updated or len(ledger.trials) <= 2:
                n_eff, sr_std, best_sr = _recompute_effective_trials(ledger.trials)
                ledger.cached_n_eff = n_eff
                ledger.cached_sr_std = sr_std
                ledger.best_is_sharpe = best_sr
            elif ledger.best_is_sharpe is None or clean_sr > ledger.best_is_sharpe:
                ledger.best_is_sharpe = round(clean_sr, 4)

            return TrialLedgerSnapshot(
                dataset_id=dataset_id,
                total_evaluations=ledger.total_evaluations,
                unique_trials=len(ledger.trials),
                effective_n_trials=ledger.cached_n_eff,
                trials_sr_std=ledger.cached_sr_std,
                best_is_sharpe=ledger.best_is_sharpe,
                holdout_peeks=ledger.holdout_peeks,
            )

    def get_snapshot(self, dataset_id: str) -> TrialLedgerSnapshot:
        with self._lock:
            ledger = self._ledgers.get(dataset_id)
            if ledger is None:
                return TrialLedgerSnapshot(
                    dataset_id=dataset_id,
                    total_evaluations=0,
                    unique_trials=0,
                    effective_n_trials=1.0,
                    trials_sr_std=0.5,
                    best_is_sharpe=None,
                    holdout_peeks=0,
                )
            return TrialLedgerSnapshot(
                dataset_id=dataset_id,
                total_evaluations=ledger.total_evaluations,
                unique_trials=len(ledger.trials),
                effective_n_trials=ledger.cached_n_eff,
                trials_sr_std=ledger.cached_sr_std,
                best_is_sharpe=ledger.best_is_sharpe,
                holdout_peeks=ledger.holdout_peeks,
            )
