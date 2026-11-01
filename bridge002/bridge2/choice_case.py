"""Finite source-local models of the actual SUTI.game working specification."""
from itertools import combinations

from .shared import Refusal, canonical_hash, statuses

CONTROLS = ('pause', 'skip', 'exit')
ACTION = 'chosen_reversible_trial'
ORDER = ['choose', 'trial', 'report', 'confirm_save', 'save']


def menus(model: str, action_names=(ACTION,)) -> list[list[str]]:
    if model not in ('literal_total_budget', 'separate_control_channel'):
        raise Refusal('UNKNOWN_CHOICE_MODEL')
    universe = list(CONTROLS) + list(action_names)
    result = []
    for size in range(len(universe) + 1):
        for selected in combinations(universe, size):
            if not set(CONTROLS) <= set(selected):
                continue
            counted = len(selected) if model == 'literal_total_budget' else len(set(selected) - set(CONTROLS))
            if counted <= 3:
                result.append(list(selected))
    return result


def transition(state: str, event: str, menu: list[str]) -> str:
    if event == 'silence':
        return state
    if event in CONTROLS:
        return 'closed_without_trial'
    allowed = {('waiting', ACTION): 'explicitly_selected', ('explicitly_selected', 'trial'): 'trial_token',
               ('trial_token', 'report'): 'reported', ('reported', 'confirm_save'): 'save_confirmed',
               ('save_confirmed', 'save'): 'saved'}
    if state == 'waiting' and event == ACTION and event not in menu:
        raise Refusal('ACTION_NOT_OFFERED')
    if (state, event) not in allowed:
        raise Refusal('MISSING_EXPLICIT_PRECONDITION')
    return allowed[(state, event)]


def evaluate(model: str) -> dict:
    offered = menus(model)
    reachable = [menu for menu in offered if ACTION in menu]
    traces = []
    for menu in reachable:
        state = 'waiting';trace = [{'state': state, 'event': 'initial'}]
        for event in [ACTION, 'trial', 'report', 'confirm_save', 'save']:
            state = transition(state, event, menu);trace.append({'state': state, 'event': event})
        traces.append({'menu': menu, 'states': trace})
    return {'model': model, 'universe': [*CONTROLS, ACTION], 'enumerated_subsets': 16,
            'admissible_menus': offered, 'trial_selectable': bool(reachable), 'successful_symbolic_traces': traces,
            'scope': 'Symbolic choice feasibility only; no actual person, movement, application action or LM execution.',
            'counting_scope': 'All menu entries' if model == 'literal_total_budget' else 'Actions only, with separate always-available controls'}


def project(contract: dict, model: str, title: str = '') -> dict:
    result = evaluate(model)
    ledger = []
    for section in ('D', 'R', 'T', 'O'):
        for item in contract[section]:
            state, reason = 'PRESERVED', 'Source-local declaration retained in this symbolic model.'
            if item['id'] == 'D_MENU_BUDGET' and model == 'separate_control_channel':
                state, reason = 'NARROWED', 'Limit applies to actions rather than the entire menu. This is an explicit proposed clarification, not literal preservation.'
            if item['id'] == 'O_AUTHOR_REVIEW':
                state, reason = 'UNKNOWN', 'No author judgment of the resulting explanation has been supplied.'
            ledger.append({'section': section, 'id': item['id'], 'source_address': item['source_address'],
                           'state': state, 'reason': reason, 'must_preserve': item['must_preserve']})
    return {'source_sha256': contract['source_sha256'], 'contract_sha256': canonical_hash(contract),
            'model': model, 'title': title or model, 'operation_order': ORDER,
            'structural_fingerprint': canonical_hash({'source': contract['source_sha256'], 'model': model, 'order': ORDER}),
            'formal_result': result, 'loss_ledger': ledger,
            'bindings': [{'source_item_id': row['id'], 'source_span': row['source_address'],
                          'model_element': model + ':' + row['id'],
                          'test_or_claim': ('trial_selectable_and_cardinality' if row['id'] in ('D_MENU_BUDGET','D_CONTROL_PRESENCE','D_TRIAL_BRANCH','O_SELECTABLE_TRIAL')
                                           else 'author_recognition_NOT_TESTED' if row['id']=='O_AUTHOR_REVIEW'
                                           else 'explicit_guarded_transition_order')}
                         for section in ('D','R','T','O') for row in contract[section]],
            'semantic_status': 'UNREACHABLE_TRIAL_UNDER_LITERAL_READING' if not result['trial_selectable'] else 'REQUIRES_COUNTING_SCOPE_REVIEW',
            **{k:v for k,v in statuses(mathematical='FINITE_CONSTRAINTS_ENUMERATED', execution='LOCAL_SYMBOLIC_MODEL_ONLY').items() if k!='semantic_status'}}


def audit(contract: dict, projection: dict) -> dict:
    expected = project(contract, projection['model'], projection.get('title', ''))
    if projection != expected:
        raise Refusal('SOURCE_MODEL_ORDER_LOSS_OR_RESULT_DRIFT')
    return {'status': 'LOCAL_MODEL_CHECKED', 'source_sha256': contract['source_sha256'],
            'semantic_status': projection['semantic_status'], 'author_review_status': 'NO_REVIEW',
            'counting_scope_changed': any(x['state'] == 'NARROWED' for x in projection['loss_ledger']),
            'full_source_semantics_preserved': False, 'proof_status': 'unverified',
            'execution_permission': {'allowed': False}}


def reverse_explanation(contract: dict, projections: list[dict]) -> str:
    return '''# Разбор рабочего SUTI.game: лимит выбора

Исследован исходный `algorithm-contour.v1.md` из присланного автором архива.
Снимок исходных байтов: `''' + contract['source_sha256'] + '''`.

В псевдокоде задано `make_options(max_count=3, include=["pause", "skip", "exit"])`.
Если три обязательных управления входят в общий лимит три, они заполняют меню.
Любой вариант обратимой пробы был бы четвёртым. При буквальной трактовке условие
выбора действия несовместимо с этим меню: ветка `execute_reversible_trial` недостижима.
Проверка перебрала все16 подмножеств трёх управлений и одного символического действия.
Это конечное следствие условий черновика, не результат испытания самой игры.

Вторая трактовка разделяет каналы: до трёх действий и отдельные постоянные
`pause/skip/exit`. Тогда пробу можно выбрать; без явного выбора она не выполняется.
Но область лимита изменилась: это предлагаемое уточнение D_MENU_BUDGET (NARROWED).
Я не выдаю его за уже подтверждённый авторский смысл. Другой возможный ответ автора:
меню действительно содержит только управления, а действие выбирается иным способом.
Такой отдельный способ в исследованном фрагменте не задан.

Обе модели сохраняют различие между выбором действия, сообщённым человеком
результатом и отдельным выбором сохранения. Молчание не изменяет состояние;
сохранение до сообщения результата и явного подтверждения отвергается.
Токен обратимой пробы абстрактен: её реальный механизм/эффект не моделировались.
Остальной документ сохранён в raw-снимке, а не объявлен полностью формализованным.

Разрешение работать с архивом получено от пользователя. Авторская оценка именно
этого разбора пока NO_REVIEW. Для неё нужно сопоставить этот текст с указанным
хешем исходника и решить: RECOGNIZED, PARTIAL или REJECTED. Никакого verified
или разрешения на исполнение из этой локальной проверки не следует.
'''
