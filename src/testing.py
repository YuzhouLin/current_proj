import argparse
import os
import torch
import numpy as np
import pandas as pd
import utils
import pickle
from helps import load_data_cnn, load_data_test_cnn, get_device
import optuna
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner

parser = argparse.ArgumentParser()
parser.add_argument('-edl','--edl_used',help = 'if used edl?',action = 'store_true')
args = parser.parse_args()


DEVICE = get_device()
EPOCHS = 20
TRIAL_LIST = list(range(1,7))
DATA_PATH = '/data/NinaproDB5/raw/'

def retrain(params):
    ## load_data
    train_trial_list = [x for x in TRIAL_LIST if x not in params['test_trial_list']]

    sb_n = params['sb_n']

    train_loader = load_data_cnn(DATA_PATH,sb_n,train_trial_list,params['batch_size'])

    model = utils.Model()
    model.to(DEVICE)
    optimizer = getattr(torch.optim, params['optimizer_name'])(model.parameters(), lr=params['lr'])
    eng = utils.Engine(model,optimizer,device = DEVICE)

    edl_flag = params['edl']
    loss_params = {'edl':edl_flag}
    
    if edl_flag:
        edl_loss_params = ['kl','annealing_step','edl_fun','evi_fun','class_n']
        loss_params.update({item:params.get(item) for item in edl_loss_params})
        loss_params['device'] = DEVICE  
    
    for epoch in range(1,EPOCHS+1):
        if edl_flag:
            loss_params['epoch_num'] = epoch
        train_loss = eng.re_train(train_loader,loss_params) 
        print(f"epoch:{epoch}, train_loss:{train_loss}")
    
    model_name = f"models/ecnn/sb{sb_n}.pt" if edl_flag else f"models/cnn/sb{sb_n}.pt"
    torch.save(model.state_dict(), model_name)

    return

def test(params):
    ## load_data
    device = torch.device('cpu')
    test_trial_list = params['test_trial_list']

    sb_n = params['sb_n']

    # Load testing Data
    inputs, targets = load_data_test_cnn(DATA_PATH, params['sb_n'], params['test_trial_list'])

    # Load trained model 
    model = utils.Model()
    model.load_state_dict(torch.load(params['model_saved'], map_location=device))
    model.eval()
    
    # Get Results
    outputs = test_net(inputs)

    # Analyse results
    scores_in, pred_labels = get_scores(outputs,uncertainty_types,params['evi_fun'])
    pred_results = pred_labels== targets

    ## Update acc
    df_acc = update_result_acc(df_acc, temp_data_acc, pred_results,targets)

    ## Update mis

    # Get label  pos: wrong predictions; neg: right predictions
    labels = np.logical_not(pred_results)
    print(labels)
    n_in = len(labels)
    temp_data_mis['skew'] = np.count_nonzero(labels)/n_in
    #print(labels.shape)
    df_mis = update_result_un(df_mis,temp_data_mis,labels,scores_in)


    # print results directly
    print('-'*20)
    print('ovarall test acc')
    print(df_acc['recall'].mean())
    print('Acc for each class')
    print(df_acc['recall'].to_string(index=False))
    print('-'*20)
    df = df_mis.groupby(['uncertainty_type'])['AP_nor'].mean()
    print('mis detection results')
    print(df)
    print(df.to_string(index=False))


    edl_flag = params['edl']
    loss_params = {'edl':edl_flag}

    if edl_flag:
        edl_loss_params = ['kl','annealing_step','edl_fun','evi_fun','class_n']
        loss_params.update({item:params.get(item) for item in edl_loss_params})
        loss_params['device'] = DEVICE

    for epoch in range(1,EPOCHS+1):
        if edl_flag:
            loss_params['epoch_num'] = epoch
        train_loss = eng.re_train(train_loader,loss_params)
        print(f"epoch:{epoch}, train_loss:{train_loss}")

    torch.save(model.state_dict(), params['saved_model'])

    return


if __name__ == "__main__":
    
    retrain_required = False

    test_trial_list = [5]
    
    edl_used = args.edl_used

    params = {
        #'sb_n': sb_n,
        'test_trial_list': test_trial_list,
        'class_n': 12,
        'batch_size': 128,
        'optimizer_name': 'Adam',
        'lr': 1e-3,
        'edl': edl_used
    }
    
    if edl_used:
        params['edl_fun'] = 'mse'
        params['annealing_step'] = 10
        params['kl'] = 0
        params['evi_fun'] = 'relu'
    
    sb_n = 1
    params['sb_n'] = sb_n
    
    core_path = f'study/ecnn/sb{sb_n}' if edl_used else f'study/cnn/sb{sb_n}'
    study_path = "sqlite:///"+core_path+"/temp.db"
    loaded_study = optuna.load_study(study_name="STUDY", storage=study_path)
    temp_best_trial = loaded_study.best_trial
    # Update for the optimal hyperparameters
    for key, value in temp_best_trial.params.items():
        params[key] = value

    model_name = f"models/ecnn/sb{sb_n}.pt" if edl_flag else f"models/cnn/sb{sb_n}.pt"
    params['saved_model'] = model_name
    
    if retrain_required:
        retrain(params)

    test(params)
    
    '''
    for sb_n in range(1,11):
        params['sb_n'] = sb_n
        study_path = f'study/ecnn/sb{sb_n}' if edl_used else f'study/cnn/sb{sb_n}'
    
        if not os.path.exists(study_path):
            os.makedirs(study_path)

        sampler = TPESampler()
        study = optuna.create_study(
            direction="minimize",  # maximaze or minimaze our objective
            sampler=sampler,  # parametrs sampling strategy
            pruner=MedianPruner(
                n_startup_trials=15,
                n_warmup_steps=5,  # let's say num epochs
                interval_steps=2,
            ),
            study_name='STUDY',
            storage="sqlite:///"+study_path+"/temp.db",  # storing study results, other storages are available too, see documentation.
            load_if_exists=True
        )
        
        study.optimize(lambda trial: objective(trial,params), n_trials=25)
        
        print("Number of finished trials: ", len(study.trials))

        print("Best trial:")
        trial = study.best_trial

        print("  Value: ", trial.value)

        print("  Params: ")
        for key, value in trial.params.items():
            print("    {}: {}".format(key, value))
    '''
