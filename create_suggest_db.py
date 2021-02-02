import csv
import os
from collections import defaultdict
from hunspell import Hunspell
from redisworks import Root


class SuggestDB:
    _ru = 'йцукенгшщзхъфывапролджэячсмитьбю.'
    _en = 'qwertyuiop[]asdfghjkl;\'zxcvbnm,./'
    pswr = {en_let: ru_let for en_let, ru_let in zip(_en, _ru)}
    pct = ',./;\'[]'

    suggest_db = defaultdict(dict)
    search_words = defaultdict(dict)
    steming = Hunspell('E:\\py\\ru_RU').stem

    def __init__(self, **kwargs):
        self.gm_name: str = self.normalize_word(kwargs['gm_name'])
        if self.gm_name:
            self.count: int = int(kwargs['counts'])
            self.percent: float = float(kwargs.get('percent', 0))
            self.alt_name: str = self.normalize_word(kwargs.get('gm_alt_name', ''))
            self.gm_list = [word for word in self.gm_name.split() + self.alt_name.split()]
            self.gm_list = self.del_duplicate_words(self.gm_list)
            self.ngrams: list = [self.normalize_word(word) for word in kwargs.get('n_grams', '').split(',')]
            self.properties = list()
            [self.properties.extend(ngram.split()) for ngram in self.ngrams]
            [self.properties.remove(val) for val in self.properties
             if not self.is_valid(val) or self.properties.count(val) > 1]
            # pprint(self.__dict__)

    def __call__(self):
        if self.gm_name:
            self.create_gm_suggest_db()
            self.add_properties()

    def normalize_word(self, word):
        return ''.join(let.lower() for let in word if let not in self.pct)

    def punto_switcher(self, word):
        return ''.join(self.pswr.get(let, let) for let in word)

    def del_duplicate_words(self, words_list: list):
        return sorted(set(words_list))

    def is_valid(self, word):
        return word.isalpha() and len(word) > 2

    def get_stem_word(self, word):
        return [word[0] for word in [self.steming(word) or [word]]][0]

    def add_phrase(self, mut_dict, word, pswr_word=''):
        pswr_word = pswr_word if pswr_word else word
        mut_dict[pswr_word] = mut_dict.get(pswr_word,
                                           {
                                               'phrase': word,
                                               'gm_name': [self.gm_name],
                                               'properties': self.properties
                                           }
                                           )
        mut_dict[pswr_word]['gm_name'] += [self.gm_name] if self.gm_name not in mut_dict[pswr_word]['gm_name'] else []
        mut_dict[pswr_word]['properties'] += [prop for prop in self.properties
                                              if prop not in mut_dict[pswr_word]['properties']]

    def create_gm_suggest_db(self):
        for word in self.gm_list:
            first_let = word[0]
            self.add_phrase(mut_dict=self.search_words[first_let], word=word)
            word = self.get_stem_word(word)
            for ix in range(1, 10):
                str_ix = str(ix)
                self.suggest_db[first_let][str_ix] = self.suggest_db[first_let].get(str_ix, dict())

                self.suggest_db[first_let][str_ix][word[:ix]] = self.suggest_db[first_let][str_ix].get(word[:ix],
                                                                                                       list())
                self.suggest_db[first_let][str_ix][word[:ix]] += [word] \
                    if word not in self.suggest_db[first_let][str_ix][word[:ix]] else []

    def add_properties(self):
        for prop in self.properties:
            if prop:
                pswr_prop = self.punto_switcher(prop)
                if self.is_valid(pswr_prop):
                    self.add_phrase(mut_dict=self.search_words[pswr_prop[0]], word=prop, pswr_word=pswr_prop)

PATH_CSV_FILES = f'{os.getcwd()}\\csv_to_suggest\\'


def main(path: str, file_name: str):
    with open(path + file_name, 'r', encoding='utf-8') as csv_file:
        reader = csv.DictReader(csv_file)
        for ix, line in enumerate(reader):
            if not line['gm_name']:
                continue
            db = SuggestDB(**line)
            db()
            # pprint(db.suggest_db)


if __name__ == '__main__':
    root = Root(db=1)
    for file_name in os.listdir(PATH_CSV_FILES):
        print(file_name)
        main(PATH_CSV_FILES, file_name)
    root.suggest_db = SuggestDB.suggest_db.copy()
    root.search_words_db = SuggestDB.search_words.copy()

