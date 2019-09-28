import os
from urllib.request import urlretrieve

from tqdm import tqdm

import tensorflow as tf
import pickle
import sentencepiece

class DataLoader:
    DIR = None
    PATHS = {}
    BPE_VOCAB_SIZE=0
    dictionary = {
        'source': {
            'token2idx':None,
            'idx2token':None,
        },
        'target': {
            'token2idx':None,
            'idx2token':None,
        }
    }
    CONFIG = {
        'wmt14/en-de': {
            'source_lang': 'en',
            'target_lang': 'de',
            'base_url': 'https://nlp.stanford.edu/projects/nmt/data/wmt14.en-de/',
            'train_files': ['train.en', 'train.de'],
            'vocab_files': ['vocab.50K.en', 'vocab.50K.de'],
            'dictionary_files': ['dict.en-de'],
            'test_files': [
                'newstest2012.en', 'newstest2012.de',
                'newstest2013.en', 'newstest2013.de',
                'newstest2014.en', 'newstest2014.de',
                'newstest2015.en', 'newstest2015.de',
            ]
        }
    }
    BPE_MODEL_SUFFIX= '.model'
    BPE_VOCAB_SUFFIX= '.vocab'
    BPE_RESULT_SUFFIX= '.sequences'

    def __init__(self, dataset_name, data_dir, bpe_vocab_size=32000):
        if dataset_name is None or data_dir is None:
            raise ValueError('dataset_name and data_dir must be defined')
        self.DIR = data_dir
        self.DATASET = dataset_name
        self.BPE_VOCAB_SIZE = bpe_vocab_size

        self.PATHS['source_data'] = os.path.join(self.DIR, self.CONFIG[self.DATASET]['train_files'][0])
        self.PATHS['source_bpe_prefix'] = self.PATHS['source_data'] + '.segmented'

        self.PATHS['target_data'] = os.path.join(self.DIR, self.CONFIG[self.DATASET]['train_files'][1])
        self.PATHS['target_bpe_prefix'] = self.PATHS['target_data'] + '.segmented'

    def load(self):
        pickle_data_path = os.path.join(self.DIR, 'data.pickle')
        print('#1 download data')
        self.download_dataset()

        print('#2 parse data')
        source_data = self.parse_data_and_save(self.PATHS['source_data'])
        target_data = self.parse_data_and_save(self.PATHS['target_data'])
        
        print('#3 train bpe')
        
        self.train_bpe(self.PATHS['source_data'], self.PATHS['source_bpe_prefix'])
        self.train_bpe(self.PATHS['target_data'], self.PATHS['target_bpe_prefix'])

        print('#4 load bpe vocab')

        self.dictionary['source']['token2idx'], self.dictionary['source']['idx2token'] =  self.load_bpe_vocab(self.PATHS['source_bpe_prefix'] + self.BPE_VOCAB_SUFFIX)
        self.dictionary['target']['token2idx'], self.dictionary['target']['idx2token'] =  self.load_bpe_vocab(self.PATHS['target_bpe_prefix'] + self.BPE_VOCAB_SUFFIX)

        print('#5 encode data with bpe')
        source_sequences = self.texts_to_sequences(
            self.sentence_piece(
                source_data,
                self.PATHS['source_bpe_prefix'] + self.BPE_MODEL_SUFFIX,
                self.PATHS['source_bpe_prefix'] + self.BPE_RESULT_SUFFIX
            ),
            mode="source"
        )
        target_sequences = self.texts_to_sequences(
            self.sentence_piece(
                target_data,
                self.PATHS['target_bpe_prefix'] + self.BPE_MODEL_SUFFIX,
                self.PATHS['target_bpe_prefix'] + self.BPE_RESULT_SUFFIX
            ),
            mode="target"
        )

        print('source sequence example:', source_sequences[0])
        print('target sequence example:', target_sequences[0])

        return source_sequences, target_sequences

    def download_dataset(self):
        for file in (self.CONFIG[self.DATASET]['train_files']
                     + self.CONFIG[self.DATASET]['vocab_files']
                     + self.CONFIG[self.DATASET]['dictionary_files']
                     + self.CONFIG[self.DATASET]['test_files']):
            self._download(f"{self.CONFIG[self.DATASET]['base_url']}{file}")

    def _download(self, url):
        path = os.path.join(self.DIR, url.split('/')[-1])
        if not os.path.exists(path):
            with TqdmCustom(unit='B', unit_scale=True, unit_divisor=1024, miniters=1, desc=url) as t:
                urlretrieve(url, path, t.update_to)
    
    def parse_data_and_save(self, path):
        print(f'load data from {path}')
        with open(path, encoding='utf-8') as f:
            lines = f.read().strip().split('\n')

        if lines is None:
            raise ValueError('Vocab file is invalid')
            
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return lines
    
    def train_bpe(self, data_path, model_prefix):
        model_path = model_prefix + self.BPE_MODEL_SUFFIX
        vocab_path = model_prefix + self.BPE_VOCAB_SUFFIX

        if not(os.path.exists(model_path) and os.path.exists(vocab_path)):
            print('bpe model does not exist. train bpe. model path:', model_path, ' vocab path:', vocab_path)
            train_source_params = "--input={} \
                --pad_id=0 \
                --unk_id=1 \
                --bos_id=2 \
                --eos_id=3 \
                --model_prefix={} \
                --vocab_size={} \
                --model_type=bpe ".format(
                data_path,
                model_prefix,
                self.BPE_VOCAB_SIZE
            )
            sentencepiece.SentencePieceTrainer.Train(train_source_params)
        else:
            print('bpe model exist. load bpe. model path:', model_path, ' vocab path:', vocab_path)

    def sentence_piece(self, source_data, source_bpe_model_path, result_data_path):
        sp = sentencepiece.SentencePieceProcessor()
        sp.load(source_bpe_model_path)
        
        if os.path.exists(result_data_path):
            print('encoded data exist. load data. path:', result_data_path)
            with open(result_data_path, 'r', encoding='utf-8') as f:
                 sequences = f.read().strip().split('\n')
                 return sequences

        print('encoded data does not exist. encode data. path:', result_data_path)
        sequences = []
        with open(result_data_path, 'w') as f:
            for sentence in tqdm(source_data):
                pieces = sp.EncodeAsPieces(sentence)
                sequence = " ".join(pieces)
                sequences.append(sequence)
                f.write(sequence + "\n")
        return sequences
    
    def load_bpe_vocab(self, bpe_vocab_path):
        vocab = [line.split()[0] for line in open(bpe_vocab_path, 'r').read().splitlines()]
        token2idx = {}
        idx2token = {}

        for idx, token in enumerate(vocab):
            token2idx[token] = idx
            idx2token[idx] = token
        return token2idx, idx2token
    
    def texts_to_sequences(self, texts, mode='source'):
        if mode != 'source' and mode != 'target':
            ValueError('not allowed mode.')
            
        sequences = []
        for text in texts:
            text_list = ["<s>"] + text.split() + ["</s>"]
            sequence = [
                        self.dictionary[mode]['token2idx'].get(
                            token, self.dictionary[mode]['token2idx']["<unk>"]
                        )
                        for token in text_list
            ]
            sequences.append(sequence)
        return sequences

    def sequences_to_texts(self, sequences, mode='source'):
        if mode != 'source' and mode != 'target':
            ValueError('not allowed mode.')
            
        texts = []
        for sequence in sequences:
            text = [
                    self.dictionary[mode]['idx2token'].get(
                        idx,
                        self.dictionary[mode]['idx2token'][1]
                    )
                    for idx in sequence
            ]
            texts.append(text)
        return texts

class TqdmCustom(tqdm):

    def update_to(self, b=1, bsize=1, tsize=None):
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)
