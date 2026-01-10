import matplotlib.pyplot as plt
from statistics import mean, stdev

def AnalyzeGame():
    ''' Assume config file format remains the same. '''
    with open('config.py', 'r') as f:
        while True:
            line = f.readline()
            if 'GAME_LOG_FILENAME' in line:
                log_file_name = line.split('"')[-2] + '.txt'
            if 'PLAYER_1_NAME' in line:
                P1 = line.split('"')[-2]
            if 'PLAYER_2_NAME' in line:
                P2 = line.split('"')[-2]
            if line == '':
                break
    
    with open(log_file_name, 'r') as f:
        log = f.read()
        
    log_game, log_final = log.split('Final')[0], log.split('Final')[1]
    log_rounds = log_game.split('#')[1:]
    
    P1_bankroll, P1_PnL = [0], []
    P2_bankroll, P2_PnL = [0], []
    
    for round_x in log_rounds:
        for line_x in round_x.split('\n'):
            if 'awarded' in line_x:
                if P1 in line_x:
                    p1_pnl = int(line_x.split('awarded ')[-1])
                if P2 in line_x:
                    p2_pnl = int(line_x.split('awarded ')[-1])
        
        P1_bankroll.append(P1_bankroll[-1] + p1_pnl)
        P1_PnL.append(p1_pnl)
        
        P2_bankroll.append(P2_bankroll[-1] + p2_pnl)
        P2_PnL.append(p2_pnl)
        
    
    mean_win_p1 = mean(P1_PnL)
    std_win_p1 = stdev(P1_PnL)
    sr1 = mean_win_p1/std_win_p1
    
    print(f'\n---- {P1} ----')
    print(f'Mean PnL per Round: {mean_win_p1:.3f}')
    print(f'Std PnL per Round: {std_win_p1:.3f}')
    print(f'PnL Sharpe Ratio: {sr1:.3f}')
    
    mean_win_p2 = mean(P2_PnL)
    std_win_p2 = stdev(P2_PnL)
    sr2 = mean_win_p2/std_win_p2
    
    print(f'\n---- {P2} ----')
    print(f'Mean PnL per Round: {mean_win_p2:.3f}')
    print(f'Std PnL per Round: {std_win_p2:.3f}')
    print(f'PnL Sharpe Ratio: {sr2:.3f}')
    
    fig1 = plt.figure(figsize=(16, 9))
    plt.plot(P1_bankroll)
    plt.title(f'{P1} Bankroll')
    plt.grid()
    plt.show()
    plt.close()
    
    fig2 = plt.figure(figsize=(16, 9))
    plt.plot(P2_bankroll)
    plt.title(f'{P2} Bankroll')
    plt.grid()
    plt.show()
    plt.close()
    
    print('\n----------------')
    
    return P1_bankroll, P1_PnL, P2_bankroll, P2_PnL
    