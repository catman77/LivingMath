"""Readable conditional conclusions, never a source/world certification."""
import json


def readable(result: dict) -> list[str]:
    lines=['','Условные отношения наблюдателей013. Источниковые реплики, допущения, выводы модели и поддержка источником разделены.',
        'Внешняя источниковая проверка: 0. Истинность в мире: UNKNOWN. Это не физическое исполнение.']
    for q in result['consequences']:
        lines.append(q['kind']+': '+q['verdict']+'; наблюдатели '+', '.join(q.get('observers',q.get('reports',[]))))
        lines.append('Допущения: '+', '.join(q.get('assumptions',[])))
        if q.get('necessity_check_status')=='RESOURCE_BOUND':lines.append('Проверка необходимости предпосылок: RESOURCE_BOUND; неизбыточность не установлена.')
        if q.get('counterexample'):lines.append('Контрмодель в выбранной конечной области: '+json.dumps(q['counterexample'],ensure_ascii=False))
        if q.get('missing_observations'):lines.append('Минимально недостающие наблюдения: '+json.dumps(q['missing_observations'],ensure_ascii=False))
        if q.get('missing_bindings'):lines.append('Не хватает области/времени/референции: '+json.dumps(q['missing_bindings'],ensure_ascii=False))
        if q.get('counterexample_without_assumption'):lines.append('Без принятого общего смысла совместимость возможна: '+json.dumps(q['counterexample_without_assumption'],ensure_ascii=False))
    return lines
