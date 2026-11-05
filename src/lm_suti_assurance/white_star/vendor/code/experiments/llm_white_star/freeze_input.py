"""Materialize the current assistant's encoding before running the search.

The integer coordinates are an explicit LLM hypothesis, not measurements and
not an output of division by zero. No complete interpretation is encoded here.
"""
from pathlib import Path
import argparse
import hashlib
import json

HERE = Path(__file__).resolve().parent

# label, exact evidence [(one-based line, substring)], coordinates, rationale
ATOMS = [
    ("night", "ночь", [(1, "Ночь"), (7, "Ночь")], [-3, -3],
     "Возвращающийся фон сцены; неподвижность — выбранный акцент, не свойство всякой ночи."),
    ("street", "улица", [(1, "улица"), (8, "улица")], [-1, -4],
     "Предметное пространство; повторяется, но допускает движение по нему."),
    ("lamp", "фонарь", [(1, "фонарь"), (8, "фонарь")], [-2, -4],
     "Повторяющийся предмет. Связь именно с описанным светом правдоподобна, но не доказана грамматически."),
    ("pharmacy", "аптека", [(1, "аптека"), (8, "Аптека")], [1, -3],
     "Предметное место; возможность лечения — культурная ассоциация LLM, не событие стихотворения."),
    ("light", "бессмысленный и тусклый свет", [(2, "Бессмысленный и тусклый свет")], [-3, -2],
     "В этом описании освещение не даёт ясности или изменения; это трактовка признаков света."),
    ("duration", "жить ещё четверть века", [(3, "Живи еще хоть четверть века")], [-2, 3],
     "Продолжающееся действие во времени, связанное говорящим с сохранением положения."),
    ("same", "всё будет так", [(4, "Всё будет так")], [-4, 1],
     "Утверждение будущей неизменности; неизвестен домен слова «всё»."),
    ("no_exit", "исхода нет", [(4, "Исхода нет")], [-4, -1],
     "Заявленное говорящим замыкание положения; это не независимый закон мира."),
    ("death", "умрёшь", [(5, "Умрешь")], [4, 3],
     "Предельное изменение участника в условной конструкции; его осуществление не сообщено."),
    ("restart", "начнёшь опять сначала", [(5, "начнешь опять сначала")], [3, 4],
     "Начало как действие и изменение; тождество нового цикла прежнему оставлено открытым."),
    ("repeat", "повторится всё", [(6, "повторится всё")], [-3, 4],
     "Процесс воспроизведения; замыкание и действие сосуществуют."),
    ("past", "как встарь", [(6, "как встарь")], [-4, -2],
     "Ссылка на прежнее как опору сравнения; конкретное прошлое неизвестно."),
    ("ripple", "ледяная рябь", [(7, "ледяная рябь")], [2, 4],
     "Динамика поверхности внутри образа холода; движение — обычное значение ряби."),
    ("canal", "канал", [(7, "канала")], [-1, -3],
     "Предметная граница/русло; течение и отражение возможны как ассоциации, но не утверждены текстом."),
]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_input(source_document, prior_output):
    text = source_document["input"]["raw_text"]
    sha = hashlib.sha256(text.encode()).hexdigest()
    assert sha == source_document["input"]["expected_sha256"]
    lines = text.splitlines(keepends=True)
    offsets, offset = [], 0
    for line in lines:
        offsets.append(offset)
        offset += len(line.encode())
    concepts = []
    for key, label, evidence, vector, rationale in ATOMS:
        citations = []
        for lineno, quote in evidence:
            line = lines[lineno - 1]
            pos = line.index(quote)
            start = offsets[lineno - 1] + len(line[:pos].encode())
            citations.append(dict(line=lineno, byte_start=start,
                                  byte_end=start + len(quote.encode()), quote=quote))
        concepts.append(dict(id=key, label=label, evidence=citations,
                             coordinates=vector, encoding_rationale=rationale))
    return dict(
        schema="llm-white-star-concepts/1",
        source=dict(author="Александр Блок", title="Ночь, улица, фонарь, аптека",
                    text=text, sha256=sha, rights="PUBLIC_DOMAIN"),
        provenance=dict(
            prior_archive="LivingMath_MEANING014_20261101.zip",
            prior_library_id="libfile_15a8a7acc13081918da54094fb66b12d",
            prior_case="K4408", prior_schema=prior_output["version"],
            encoder="current conversation assistant; explicit one-shot annotation",
            remote_model_call=False,
            distinction="Reuse addressed concepts/uncertainties; the coordinate adapter is NEW."),
        axes=[
            dict(id="change", minus="сохранение/возвращение", plus="изменение/начало"),
            dict(id="process", minus="предмет/состояние", plus="действие/процесс"),
        ],
        coordinate_status="SUBJECTIVE_LLM_ENCODING_NOT_INTRINSIC_SEMANTIC_GEOMETRY",
        concepts=concepts,
        source_relations=[
            dict(id="r_duration", concepts=["duration", "same"], kind="SPEAKER_CLAIM",
                 note="Длительность жизни не меняет положения в утверждении голоса."),
            dict(id="r_exit", concepts=["same", "no_exit"], kind="TEXTUAL_NEIGHBORHOOD",
                 note="Два утверждения в одной строке; причинность не задана."),
            dict(id="r_restart", concepts=["death", "restart"], kind="CONDITIONAL_CLAIM",
                 note="Буквальное или риторическое начало после условной смерти."),
            dict(id="r_past", concepts=["repeat", "past"], kind="SPEAKER_COMPARISON",
                 note="Домен «всё» и конкретное прошлое неизвестны."),
            dict(id="r_surface", concepts=["ripple", "canal"], kind="EXPLICIT_ATTACHMENT",
                 note="Рябь канала; её тождество прежнему состоянию не установлено."),
            dict(id="r_light", concepts=["lamp", "light"], kind="PLAUSIBLE_NOT_ENTAILED",
                 note="Не выдавать фонарь за грамматически установленный источник света."),
        ],
        uncertainties=[
            "Говорящий и подразумеваемое «ты» могут не совпадать.",
            "Утверждения голоса не являются независимыми фактами о мире.",
            "Повтор общих названий не устанавливает тождество полных сцен.",
            "Наличие канала только в финальном перечислении не доказывает его прежнего отсутствия.",
            "Буквальный посмертный перезапуск и риторическое повторение остаются разными чтениями.",
        ],
        protocol=dict(seed=42, steps=64, candidates_per_step=3, frame_size=3,
                      decode_first_frames=6, exclude_zero_direction=True,
                      semantic_reranking=False, optimizer_feedback=False,
                      selection="UNCHANGED_NATIVE_STRUCTURAL_NOVELTY",
                      output_selection="FIRST_SIX_CONSECUTIVE_FRAMES_NO_POSTHOC_CURATING",
                      objective="Explore different source-grounded conceptual relations; no global maximum claim"),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prior_case", type=Path)
    args = parser.parse_args()
    source = json.loads((args.prior_case / "source.json").read_text())
    receipt = json.loads((args.prior_case / "A0-receipt.json").read_text())
    dest = HERE / "input"
    dest.mkdir(parents=True, exist_ok=True)
    output = make_input(source, receipt["output"])
    write_json(dest / "concepts.json", output)
    write_json(dest / "prior_A0.json", receipt["output"])
    (dest / "poem.txt").write_text(output["source"]["text"], encoding="utf-8")
    frozen = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(dest.iterdir()) if p.is_file() and p.name != "freeze.json"}
    write_json(dest / "freeze.json", frozen)
    print(json.dumps(frozen, indent=2))


if __name__ == "__main__":
    main()
