#!usr/bin/env/python3
from flask import Flask
from flask_restful import Api, Resource, reqparse
from fuzzywuzzy import process
from string import punctuation
from flask_cors import CORS
# from pprint import pprint
from redisworks import Root

app = Flask(__name__)
api = Api(app)
api.app.config['RESTFUL_JSON'] = {
    'ensure_ascii': False
}
cors = CORS(api.app, resources={r"/suggest*": {"origins": "*"}})


class Suggest(Resource):
    root = Root(db=1)

    pct = set(punctuation)  # для работы функции punto_switcher
    _en = "qwertyuiop[]asdfghjkl;'zxcvbnm,."
    _ru = "йцукенгшщзхъфывапролджэячсмитьбю"
    pswr = {en_let: ru_let for en_let, ru_let in zip(_en, _ru)}

    def __init__(self):
        parser = reqparse.RequestParser()
        parser.add_argument('phrase', type=str)
        self.phrase = self.punto_switcher(parser.parse_args()['phrase'].lower())
        self.words = self.phrase.split()
        if self.words:
            self.search_word = self.words[-1]
            self.first_let = self.search_word[0]
            self.len_word = min(len(self.search_word), 9)
            self.start_phrase = ' '.join(self.words[:-1]) + ' ' if self.words[:-1] else ''
            self.properties = set()
            self.gm_names = set()
        else:
            self.search_word = ''

        self.res_list = list()
        self.response = dict()

    def get(self):
        if self.search_word:
            self.create_properties_list()
            self.search_with_properties_list() if self.properties else self.search_without_properties_list()
            self.add_properties_to_response()
            self.sort_answer()

        self.good_response()
        return self.response, 200

    def delete(self):
        """
        удаляет слово из словарей "search_words_db" и "suggest_db",
        добавляет данные слова в словарь стоп-слов
        """
        br_dict = Suggest.root.search_words_db[self.first_let]
        try:
            br_dict.pop(self.phrase)
            Suggest.root.search_words_db[self.first_let] = br_dict
            res = 'CORRECT'
        except KeyError:
            res = 'NOT CORRECT'
        else:
            Suggest.root.stop_words |= {self.phrase}
        self.response['search_words'] = res

        br_dict = Suggest.root.suggest_db[self.first_let]
        for ix in range(1, 10):
            str_ix = str(ix)
            try:
                br_dict[str_ix][self.phrase[:ix]].pop(self.phrase)
                if not br_dict[str_ix][self.phrase[:ix]]:
                    br_dict[str_ix].pop(self.phrase[:ix])
                res = 'CORRECT'
            except KeyError:
                res = 'NOT CORRECT'
            self.response[f'suggest_db_{ix}'] = res

        Suggest.root.suggest_db[self.first_let] = br_dict
        return self.response, 200

    def create_properties_list(self):
        """
        метод ограничивает область поиска, в случае если было введено более одного слова.
        """
        for ix, word in enumerate(self.words[:-1]):
            tokens_dict = Suggest.root.search_words_db[word[0]]
            if word not in self.properties:
                word, status = self.find_token_in_properties(word, ix)
                if not status:
                    word, status = self.find_token_in_tokens_dict(tokens_dict, word, ix)
                    if not status:
                        continue
            word_prop = tokens_dict[word]

            if self.properties:
                self.properties.intersection_update(word_prop['properties'])
                self.gm_names.intersection_update(word_prop['gm_name'])
            else:
                self.properties.update(word_prop['properties'])
                self.gm_names.update(word_prop['gm_name'])

    def find_token_in_properties(self, word, ix):
        """
        производит поиск слова среди списка связанных слов
        :param word: поисковое слово
        :param ix: индекс позиции слова в запросе
        :return: найденое слово в списке и статус True,
        либо, если не найдено, возвращает слово обратно и статус False
        """
        token = process.extractOne(word, list(self.properties), score_cutoff=70)
        if token:
            self.words[ix] = token[0]
            self.start_phrase = ' '.join(self.words[:-1]) + ' '
            res = (token[0], True)
        else:
            res = (word, False)
        return res

    def find_token_in_tokens_dict(self, tokens_dict, word, ix):
        """
        Производит поиск слова в общем списке всех слов хранящихся в саджесте
        :param tokens_dict: словарь слов в котором проводится поиск
        :param word: слово для поиска
        :param ix: индекс позиции слова в запросе
        :return: найденое слово в списке и статус True,
        либо, если не найдено, возвращает слово обратно и статус False
        """
        res = ()
        token = [word, 100] if word in tokens_dict \
            else process.extractOne(word, list(tokens_dict.keys()), score_cutoff=70)
        if token:
            new_token = tokens_dict[token[0]]['phrase']
            if new_token in self.properties or (not self.properties and new_token):
                self.words[ix] = new_token
                self.start_phrase = ' '.join(self.words[:-1]) + ' '
                res = (token[0], True)
        return res if res else (word, False)

    def search_with_properties_list(self):
        """
        поиск среди ограниченого списка связанных слов
        """
        tokens = process.extractBests(self.search_word, self.properties, limit=10, score_cutoff=70)
        if not tokens:
            try:
                search_list = Suggest.root.search_words_db[self.first_let]
                search_word = search_list[process.extractOne(self.search_word, search_list.keys())[0]]['phrase']
                tokens = process.extractBests(
                    search_word,
                    self.properties,
                    limit=10,
                    score_cutoff=70
                )
            except Exception as ex:
                print(ex)
        self.sort_gm_names()
        self.res_list = [[f'{self.start_phrase} {token}', percent, tuple(self.gm_names)]
                         for token, percent in tokens if token not in self.root.stop_words]

    def search_without_properties_list(self):
        """
        первоначальный поиск не использующий список связанных слов
        """
        try:
            search_list = Suggest.root.suggest_db[self.first_let][str(self.len_word)]
        except KeyError:
            return
        tokens = process.extractBests(self.search_word, search_list.keys(), score_cutoff=50, limit=3)

        for token, percent in tokens:
            tokens_list = search_list[token[:self.len_word]]
            token = process.extractBests(self.search_word, tokens_list.keys(), limit=3, score_cutoff=50)

            for t in token:
                t_list = tokens_list[t[0]]
                self.res_list += [
                    (self.start_phrase + t_list[w]['phrase'],
                     percent,
                     tuple(t_list[w]['gm_name']))
                    for w in t_list.keys() if w not in Suggest.root.stop_words
                ]

    def good_response(self):
        self.response['response'] = [{
            "suggest": word,
            "gm_name": tuple(gm)[:5],
            "rating": percent
        } for word, percent, gm in self.res_list[:10]]

    def sort_answer(self):
        gm_dict = {self.del_dupl_words(self.normalize_words(word)): gm_name for word, p, gm_name in self.res_list}
        res_list = process.extractBests(self.phrase, gm_dict.keys(), limit=10)
        self.res_list = [
            (word, percent, gm_dict[word])
            for word, percent in res_list
        ]

    def sort_gm_names(self):
        self.gm_names = [gm_name[0] for gm_name in process.extractBests(
            self.phrase,
            self.gm_names,
            limit=5,
            score_cutoff=50
        )]

    def add_properties_to_response(self):
        """
        Если ответов меньше 10, добавляет возможные варианты уточнения
        """
        for phrase, percent, gm_name in self.res_list:
            word = phrase.split()[-1]
            properties = set(Suggest.root.search_words_db[self.first_let].get(word, dict()).get('properties', set()))
            properties = properties & self.properties if self.properties and properties \
                else properties | self.properties

            [self.res_list.append(
                (
                    f'{phrase} {prop}',
                    percent,
                    gm_name
                )
            ) for prop in properties if prop not in Suggest.root.stop_words]

            if len(self.res_list) > 9:
                self.res_list = self.res_list[:10]
                return

    @staticmethod
    def normalize_words(phrase):
        phrase = phrase.split()
        for ix, word in enumerate(phrase):
            try:
                word = Suggest.root.search_words_db[word[0]][word]['phrase']
                phrase[ix] = word
            except KeyError:
                continue
        return ' '.join(phrase)

    @staticmethod
    def del_dupl_words(phrase: str):
        """
        функция удаляет дупликаты слов в строке
        :param phrase: строка
        :return: строка без повторяющихся слов
        """
        without_dupl = list()
        [without_dupl.append(word) for word in phrase.split() if word not in without_dupl]
        return ' '.join(without_dupl)

    @staticmethod
    def punto_switcher(word: str):
        word = [Suggest.pswr.get(let, let) for let in word]
        return ''.join(let for let in word if let not in Suggest.pct)


api.add_resource(Suggest, '/suggest')

if __name__ == '__main__':
    try:
        app.run(debug=False)
    finally:
        pass
