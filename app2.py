#!usr/bin/env/python3
from flask import Flask
from flask_restful import Api, Resource, reqparse
from fuzzywuzzy import process
from string import punctuation, whitespace, digits
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

    valid_chars = set(_ru + whitespace + digits)  # для проверки корректности запроса

    def __init__(self):
        parser = reqparse.RequestParser()
        parser.add_argument('phrase', type=str)
        self.phrase = parser.parse_args()['phrase']
        if self.phrase:
            self.phrase = self.punto_switcher(self.phrase.lower())
            self.words = self.phrase.split()
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
        if self.is_valid():
            self.create_properties_list()
            if not self.search_word.isdigit():
                self.search_with_properties_list() if self.properties else self.search_without_properties_list()
            else:
                self.res_list.append((self.start_phrase + self.search_word, 100, self.gm_names))
            self.add_properties_to_response()
            self.sort_answer()
            self.good_response()
            status = 200
        else:
            self.bad_response()
            status = 400

        return self.response, status

    def delete(self):
        if self.is_valid():
            self.delete_phrase()
            status = 200
        else:
            self.bad_response()
            status = 400

        return self.response, status

    def is_valid(self):
        """
        проверяет валидность запроса
        :return: True если валидный, False если нет
        """
        return True if self.search_word and not [let for let in self.phrase if let not in Suggest.valid_chars] \
            else False

    def delete_phrase(self):
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

    def create_properties_list(self):
        """
        Метод ограничивает область поиска, в случае если было введено более одного слова.
        """
        for ix, word in enumerate(self.words[:-1]):
            if word.isdigit():
                continue
            tokens_dict = Suggest.root.search_words_db[word[0]]
            if word not in self.properties:
                word, status = self.find_token_in_properties(word, ix)
                if not status:
                    word, status = self.find_token_in_tokens_dict(tokens_dict, word, ix)
                    if not status:
                        continue
            try:
                word_prop = tokens_dict[word]
            except KeyError:
                continue

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
        token = None
        res = None
        while not res:
            token = process.extractOne(word, self.properties, score_cutoff=70)
            if not token:
                res = (word, False)
            elif token[0] not in Suggest.root.stop_words:
                self.words[ix] = token[0]
                self.start_phrase = ' '.join(self.words[:-1]) + ' '
                res = (token[0], True)
            else:
                self.properties.remove(token[0])
                token = None

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
        Поиск среди ограниченого списка связанных слов
        """
        tokens = self.search_token(self.search_word, list(self.properties), 70, 10)

        if not tokens:
            try:
                search_list = Suggest.root.search_words_db[self.first_let]
                search_word = search_list[process.extractOne(self.search_word, search_list.keys())[0]]['phrase']
                tokens = self.search_token(search_word, list(self.properties), 70, 10)

            except Exception as ex:
                print(ex)
        self.sort_gm_names()
        self.res_list = [[f'{self.start_phrase} {token}', percent, tuple(self.gm_names)]
                         for token, percent in tokens if token not in self.root.stop_words]

    def search_without_properties_list(self):
        """
        Первоначальный поиск не использующий список связанных слов
        """
        search_list = Suggest.root.suggest_db[self.first_let][str(self.len_word)]
        tokens = self.search_token(self.search_word, list(search_list.keys()), 50, 3)

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

    def search_token(self, search_word: str, search_list: list, percent: int, limit: int):
        """
        метод для поиска токена по заданном списку
        :param search_word: токен
        :param search_list: список в котором производится поиск
        :param percent: минимальный процент "похожести"
        :param limit: максимальное число токенов
        :return: список токенов формата [[токен, процент], ...]
        """
        if search_word in self.root.stop_words and search_word in search_list:
            search_list.remove(search_word)

        if search_word in search_list:
            tokens = [[search_word, 100]]
        else:
            tokens = process.extractBests(search_word, search_list, score_cutoff=percent, limit=limit)
        return tokens

    def good_response(self):
        """
        Составляет валидный ответ клиенту
        """
        self.response['response'] = [{
            "suggest": word,
            "gm_name": tuple(gm)[:5],
            "rating": percent
        } for word, percent, gm in self.res_list[:10]]

    def bad_response(self):
        """
        В случае не валидного запроса - указывает на ошибку которую допустил клиент
        """
        if self.phrase is None:
            self.response['response'] = 'Argument `phrase` is not present in the request.'
        elif not self.phrase:
            self.response['response'] = 'Argument `phrase` is empty.'
        else:
            self.response['response'] = 'Argument `phrase` contains invalid characters.'

    def sort_answer(self):
        """
        Сортирует ответы по соответствию запросу
        """
        gm_dict = {self.del_dupl_words(self.normalize_words(word)): gm_name for word, p, gm_name in self.res_list}
        res_list = process.extractBests(self.phrase, gm_dict.keys(), limit=10)
        self.res_list = [
            (word, percent, gm_dict[word])
            for word, percent in res_list
        ]

    def sort_gm_names(self):
        """
        Сортирует родовые товары по вероятности соответствия запросу
        """
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
        """
        Если в ответе есть англоязычные слова - то переводит их на латиницу
        """
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
        Удаляет дупликаты слов в строке
        :param phrase: строка
        :return: строка без повторяющихся слов
        """
        without_dupl = list()
        [without_dupl.append(word) for word in phrase.split() if word not in without_dupl]
        return ' '.join(without_dupl)

    @staticmethod
    def punto_switcher(word: str):
        """
        Переводит англоязычные слова на русскую раскладку и удаляет знаки препинания
        """
        word = [Suggest.pswr.get(let, let) for let in word]
        return ''.join(let for let in word if let not in Suggest.pct)


api.add_resource(Suggest, '/suggest', '/suggest/')

if __name__ == '__main__':
    try:
        app.run(debug=False)
    finally:
        pass
