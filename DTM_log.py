import time


def printLog(str_log):  # лог в формате: время и информация
    FStr = time.strftime("%d-%m-%Y %H:%M:%S\t", time.localtime()) + str_log
    print(FStr)
    with open('DTM_log.txt', 'a') as f:
        f.write(f'{FStr}\n')
