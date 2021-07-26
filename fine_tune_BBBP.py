import os
os.environ['CUDA_VISIBLE_DEVICES']='0'

import pandas as pd
import torch
from transformers import RobertaForMaskedLM
from torch.utils.data import Dataset, DataLoader
import pickle
from tqdm import tqdm
from Tokenizer.MFBERT_Tokenizer import MFBERTTokenizer
import numpy as np
from sklearn.model_selection import train_test_split
assert torch.cuda.device_count() == 1


MAX_LEN = 514
TRAIN_BATCH_SIZE = 16
VALID_BATCH_SIZE = 8
EPOCHS = 10
LEARNING_RATE = 1e-05
TOKENIZER_DIR = 'Tokenizer/'
df = pd.read_csv('Datasets/BBBP.csv')
train, test = train_test_split(df, test_size=0.2)


class BBBPDataset(Dataset):
    def __init__(self, training=True):
        examples = []
        if training:
            for _, row in train.iterrows():
                examples.append((row['smiles'], row['p_np']))
        else:
            for _, row in test.iterrows():
                examples.append((row['smiles'], row['p_np']))           

        self.data = examples
        self.tokenizer = MFBERTTokenizer.from_pretrained(TOKENIZER_DIR+'Model/',
                                                dict_file = TOKENIZER_DIR+'Model/dict.txt')
        self.max_len = 514
        
    def __getitem__(self, idx):
        example = self.data[idx]
        smiles = example[0]
        target = example[1]
        inputs = self.tokenizer.encode_plus(
            smiles,
            None,
            add_special_tokens=True,
            max_length=self.max_len,
            pad_to_max_length=True,
            return_token_type_ids=True,
            truncation=True
        )
        ids = inputs['input_ids']
        mask = inputs['attention_mask']
        
        return {'input_ids':torch.tensor(ids, dtype=torch.long), 
                             'attention_mask':torch.tensor(mask, dtype=torch.long), 
                             'label':torch.tensor(target, dtype=torch.long)}
    
    def __len__(self):
        return len(self.data)
    
class MFBERTForBBBP(torch.nn.Module):
    def __init__(self):
        super(MFBERTForBBBP, self).__init__()
        self.l1 = list(RobertaForMaskedLM.from_pretrained('Model/pre-trained').children())[0]
        self.l2 = torch.nn.Dropout(0.2)
        self.l3 = torch.nn.Linear(768, 1)
    
    def forward(self, ids, mask):
        output_1 = self.l1(ids, mask)
        output_2 = self.l2(torch.mean(output_1[0], dim=1))
        output = self.l3(output_2)
        return output
    
trainds = BBBPDataset()

model = MFBERTForBBBP().cuda()
train_params = {'batch_size': TRAIN_BATCH_SIZE,
                'shuffle': True,
                'num_workers': 0
                }

test_params = {'batch_size': VALID_BATCH_SIZE,
                'shuffle': True,
                'num_workers': 0
                }

training_loader = DataLoader(trainds, **train_params)

# Creating the loss function and optimizer
loss_function = torch.nn.BCEWithLogitsLoss()
optimizer = torch.optim.Adam(params =  model.parameters(), lr=LEARNING_RATE)

curminloss = 1

def train(epoch):
    model.train()

    for _ , data in tqdm(enumerate(training_loader, 0), desc='ITERATION', total=len(training_loader)):
        ids = data['input_ids'].cuda()
        mask = data['attention_mask'].cuda()
        targets = data['label'].float().cuda()
        global curminloss
        outputs = model(ids, mask).squeeze()
        optimizer.zero_grad()
        
        loss = loss_function(outputs, targets)
        
        if _%100==0:
            print(f'Epoch: {epoch}, Loss:  {loss.item()}')
            # save best model
            if loss.item()<curminloss:
                torch.save(model, f'fine-tuned/BBBP_model_best_{loss.item()}.bin')
                curminloss = loss.item()
                print('saving best...')

        loss.backward()
        optimizer.step()
        
for epoch in tqdm(range(EPOCHS), desc='EPOCHS'):
    train(epoch)


torch.save(model, 'fine-tuned/BBBP_model_last.bin')