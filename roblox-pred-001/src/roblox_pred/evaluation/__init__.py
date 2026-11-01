"""Fixed train-only labels, chronological folds, explicit undefined metrics."""
from datetime import datetime, timedelta
import math

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

from roblox_pred.features import validate_as_of
from roblox_pred.schemas import Sample


def train_threshold(train_outcomes: list[float], top_fraction: float) -> float:
    values = np.asarray(train_outcomes, dtype=float)
    if not 0 < top_fraction < 1 or len(values) < 2 or not np.isfinite(values).all():
        raise ValueError('INVALID_TRAIN_THRESHOLD_INPUT')
    threshold = float(np.quantile(values, 1-top_fraction, method='linear'))
    if len(set(values >= threshold)) < 2:
        raise ValueError('NO_OUTCOME_CONTRAST')
    return threshold


def temporal_split(samples: list[Sample], origin: datetime, train: list[int], validation: list[int],
                   test: list[int], embargo_days: int) -> dict[str, list[Sample]]:
    ranges = {'train': train, 'validation': validation, 'test': test}
    if (embargo_days < 91 or not (0 <= train[0] < train[1] <= validation[0] < validation[1] <= test[0] < test[1])
            or validation[0]-train[1] < embargo_days or test[0]-validation[1] < embargo_days):
        raise ValueError('TEMPORAL_EMBARGO_REQUIRED')
    folds: dict[str, list[Sample]] = {k: [] for k in ranges}
    seen = set()
    for sample in samples:
        validate_as_of(sample)
        if sample.sample_id in seen:
            raise ValueError('DUPLICATE_SAMPLE_ID')
        seen.add(sample.sample_id)
        admitted = False
        for name, (left, right) in ranges.items():
            if origin+timedelta(days=left) <= sample.as_of < origin+timedelta(days=right):
                folds[name].append(sample); admitted = True
        if not admitted:
            raise ValueError('SAMPLE_OUTSIDE_PREREGISTERED_FOLDS:' + sample.sample_id)
    for name in ['train', 'validation', 'test']:
        if not folds[name]:
            raise ValueError('EMPTY_TEMPORAL_FOLD:' + name)
        for sample in folds[name]:
            if not sample.creator_key:
                raise ValueError('UNKNOWN_CREATOR_GROUP')
    for left, right in [('train', 'validation'), ('train', 'test'), ('validation', 'test')]:
        boundary = min(s.as_of for s in folds[right])
        for sample in folds[left]:
            if sample.horizon_end > boundary or sample.outcome_available_at is None or sample.outcome_available_at > boundary:
                raise ValueError('LABEL_NOT_AVAILABLE_BEFORE_NEXT_FOLD')
        for field in ['creator_key', 'clone_group_id']:
            a = {getattr(s, field) for s in folds[left]} - {None}
            b = {getattr(s, field) for s in folds[right]} - {None}
            if a & b:
                raise ValueError('GROUP_OVERLAP:' + field)
        if {s.universe_id for s in folds[left]} & {s.universe_id for s in folds[right]}:
            raise ValueError('GROUP_OVERLAP:universe_id')
    return folds


def metrics(labels, scores, sample_ids, top_fraction: float = .1) -> dict:
    original = np.asarray(labels)
    if not np.isin(original, [0, 1]).all():
        raise ValueError('INVALID_PROBABILITY_OR_LABEL')
    y = original.astype(int); p = np.asarray(scores, dtype=float)
    if len(y) == 0 or len(y) != len(p) or len(sample_ids) != len(y) or len(set(sample_ids)) != len(y):
        raise ValueError('METRIC_SAMPLE_BINDING_REQUIRED')
    if not set(y) <= {0, 1} or not np.isfinite(p).all() or (p < 0).any() or (p > 1).any():
        raise ValueError('INVALID_PROBABILITY_OR_LABEL')
    if not 0 < top_fraction <= 1:
        raise ValueError('INVALID_TOP_FRACTION')
    indices = sorted(range(len(y)), key=lambda i: (-p[i], sample_ids[i]))
    k = max(1, math.ceil(len(y)*top_fraction)); chosen = indices[:k]
    base = float(np.mean(y)); precision = float(np.mean(y[chosen]))
    both = len(set(y)) == 2
    return {'n': len(y), 'positive': int(y.sum()), 'top_k': k, 'top_fraction': top_fraction,
        'test_prevalence': base, 'precision_at_fraction': precision,
        'lift_at_fraction': precision/base if base else None,
        'pr_auc': float(average_precision_score(y, p)) if both else None,
        'roc_auc': float(roc_auc_score(y, p)) if both else None,
        'log_loss': float(log_loss(y, np.clip(p, 1e-15, 1-1e-15), labels=[0, 1])),
        'brier': float(brier_score_loss(y, p)), 'selected_sample_ids': [sample_ids[i] for i in chosen],
        'calibration_status': 'NOT_VALIDATED', 'confidence_intervals': None}
