"""Train-only preprocessing, fixed M0/M1 models; no native-system impersonation."""
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from roblox_pred.schemas import Sample


def frame(samples: list[Sample], config: dict) -> pd.DataFrame:
    names = config['models']['numeric_features'] + config['models']['categorical_features']
    rows = [{k: s.features[k].value if k in s.features else None for k in names} for s in samples]
    result = pd.DataFrame(rows, columns=names)
    for name in config['models']['numeric_features']:
        result[name] = pd.to_numeric(result[name], errors='raise').astype(float)
    for name in config['models']['categorical_features']:
        result[name] = result[name].map(lambda v: str(v) if v is not None else '__MISSING__')
    return result


def preprocessing(config: dict) -> ColumnTransformer:
    return ColumnTransformer([
        ('numeric', Pipeline([('impute', SimpleImputer(strategy='median', add_indicator=True,
            keep_empty_features=True)), ('scale', StandardScaler())]), config['models']['numeric_features']),
        ('category', OneHotEncoder(handle_unknown='ignore', sparse_output=False),
            config['models']['categorical_features'])])


def fit_models(samples: list[Sample], labels: list[int], config: dict) -> dict[str, Pipeline]:
    x = frame(samples, config)
    logistic = Pipeline([('preprocess', preprocessing(config)), ('model',
        LogisticRegression(max_iter=1000, C=1., random_state=config['seed']))])
    settings = config['models']
    if settings['tabular_backend'] == 'catboost':
        # Optional, not installed or claimed tested by the default acceptance run.
        from catboost import CatBoostClassifier
        tabular = Pipeline([('preprocess', preprocessing(config)), ('model', CatBoostClassifier(
            iterations=settings['forest_trees'], depth=settings['max_depth'], random_seed=config['seed'],
            verbose=False, thread_count=1, allow_writing_files=False))])
    elif settings['tabular_backend'] == 'sklearn':
        tabular = Pipeline([('preprocess', preprocessing(config)), ('model', RandomForestClassifier(
            n_estimators=settings['forest_trees'], max_depth=settings['max_depth'],
            min_samples_leaf=settings['min_samples_leaf'], random_state=config['seed'], n_jobs=1))])
    else:
        raise ValueError('UNREGISTERED_MODEL_BACKEND')
    return {'M0_logistic': logistic.fit(x, labels), 'M1_tabular': tabular.fit(x, labels)}


def predict(models: dict[str, Pipeline], samples: list[Sample], config: dict,
            train_base_rate: float) -> dict[str, np.ndarray]:
    x = frame(samples, config)
    # Stable per-id random sanity scores, independent of labels/order/fold population.
    from roblox_pred.config import digest
    random = [int(digest([config['seed'], s.sample_id])[:13], 16) / float(16**13) for s in samples]
    return {'M0_random': np.array(random), 'M0_base_rate': np.full(len(samples), train_base_rate),
        **{key: model.predict_proba(x)[:, 1] for key, model in models.items()}}
