"""Build strictly labeled QA transcriptions; not a certified literary edition.
No network, no model, no dependencies other than Python stdlib.
"""
from pathlib import Path
import hashlib
import json

BASE=Path(__file__).resolve().parent
records=[
 {
 "id":"blok_night_1960",
 "author":"Александр Блок",
 "title":"Ночь, улица, фонарь, аптека",
 "declared_edition":"Собрание сочинений в 8 томах, т. 3, 1960, с. 37",
 "declared_source_url":"https://ru.wikisource.org/wiki/Ночь,_улица,_фонарь,_аптека_(Блок)/1960_(СО)",
 "lines":["Ночь, улица, фонарь, аптека,","Бессмысленный и тусклый свет.","Живи еще хоть четверть века —","Всё будет так. Исхода нет.","Умрешь — начнешь опять сначала,","И повторится всё, как встарь:","Ночь, ледяная рябь канала,","Аптека, улица, фонарь."]},
 {
 "id":"pushkin_anchar_1956",
 "author":"Александр Пушкин",
 "title":"Анчар",
 "declared_edition":"РВБ, издание 1956 (версия, использованная в предыдущем пилоте, требует сверки)",
 "declared_source_url":"https://ru.wikisource.org/wiki/Анчар_(Пушкин)",
 "lines":["В пустыне чахлой и скупой,","На почве, зноем раскаленной,","Анчар, как грозный часовой,","Стоит — один во всей вселенной.","Природа жаждущих степей","Его в день гнева породила,","И зелень мертвую ветвей","И корни ядом напоила.","Яд каплет сквозь его кору,","К полудню растопясь от зною,","И застывает ввечеру","Густой прозрачною смолою.","К нему и птица не летит,","И тигр нейдет: лишь вихорь черный","На древо смерти набежит —","И мчится прочь, уже тлетворный.","И если туча оросит,","Блуждая, лист его дремучий,","С его ветвей, уж ядовит,","Стекает дождь в песок горючий.","Но человека человек","Послал к анчару властным взглядом,","И тот послушно в путь потек","И к утру возвратился с ядом.","Принес он смертную смолу","Да ветвь с увядшими листами,","И пот по бледному челу","Струился хладными ручьями;","Принес — и ослабел и лег","Под сводом шалаша на лыки,","И умер бедный раб у ног","Непобедимого владыки.","А царь тем ядом напитал","Свои послушливые стрелы","И с ними гибель разослал","К соседям в чуждые пределы."]},
 {
 "id":"pushkin_loved_1948",
 "author":"Александр Пушкин",
 "title":"Я вас любил: любовь ещё, быть может",
 "declared_edition":"ФЭБ (1948), версия Викитеки; требуется сверка",
 "declared_source_url":"https://ru.wikisource.org/wiki/Я_вас_любил:_любовь_ещё,_быть_может..._(Пушкин)",
 "lines":["Я вас любил: любовь ещё, быть может,","В душе моей угасла не совсем;","Но пусть она вас больше не тревожит;","Я не хочу печалить вас ничем.","Я вас любил безмолвно, безнадежно,","То робостью, то ревностью томим;","Я вас любил так искренно, так нежно,","Как дай вам Бог любимой быть другим."]}
]
for obj in records:
 # Intentionally distinguish exact transcribed text bytes from container JSON bytes.
 txt='\n'.join(obj.pop('lines'))
 obj['raw_text_utf8']=txt
 obj['raw_text_sha256']=hashlib.sha256(txt.encode('utf-8')).hexdigest()
 obj['byte_length']=len(txt.encode('utf-8'))
 obj['edition_status']='WORKING_TRANSCRIPTION_REQUIRES_PRE_FREEZE_EDITION_VERIFICATION'
 obj['legal_status']='AUTHOR_PUBLIC_DOMAIN; DIGITAL_EDITORIAL_RIGHTS_NOT_INDEPENDENTLY_AUDITED'
 bundle={'schema':'lm-suti.semantic-fixtures/1','status':'QA_ONLY_UNVERIFIED_EDITION', 'source_records':records}
 file=BASE/'POETRY_QA_FIXTURES.json'
 file.write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('wrote',file)
