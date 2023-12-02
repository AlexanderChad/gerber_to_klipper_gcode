import sys
from scanf import scanf
import re
import os.path
import DTM_log
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from urllib import parse
import DTM_log

#####################################################
spindle_speed = 20000  # обороты шпинделя
d_frezy = 0.8  # диаметр фрезы
start_point = [0, 0]  # начальная точка
g0_speed = 1000  # скорость свободного перемещения
g1_speed = 300  # рабочая скорость
g1_tool_speed = 60  # скорость врезания
plunge_height = 0.1  # высота слоя врезания
safe_Z = 5  # безопасная высота
Null_Z = 0.5  # конечная высота сверловки
WpTn_Z = 2.0  # высота (толщина) заготовки
dr_dopusk = 0.8  # допуск в мм для отверстий
#####################################################

Drill_files_path = ["files/Drill_NPTH_Through.DRL",
                    "files/Drill_PTH_Through.DRL", "files/Drill_PTH_Through_Via.DRL"]
Drill_files_Points = []

Start_GCode = """
G21
G90
M3 S{0}
G0 Z{1} F{2}
G0 X{3} Y{4} F{2}
"""

End_GCode = """
M5
M84 X Y E
"""


def check_files(files):
    DTM_log.printLog("Check files")
    for file in files:
        if os.path.isfile(file):
            DTM_log.printLog(f"Check file: {file} exists.")
        else:
            DTM_log.printLog(f"Check file: {file} does not exist.")
            return False
    return True


def convert_to_points(points_str_lines):
    metric_flag = False
    delim_num = 1
    tools = {}
    active_tool = 0
    points = []
    for psl in points_str_lines:
        # metric flag
        if psl[:6] == "METRIC":
            metric_flag = True
            delim_num = 10**len(psl.split(',')[2].split('.')[1])
        # ignore
        # if psl == "M48" or psl == "G05" or psl == "G90" or psl == "M30":
        #    continue
        # tool
        if psl[0] == 'T':
            active_tool = int(scanf("T%2d", psl)[0])
            if not scanf("C%f", psl) == None:
                tools[active_tool] = float(scanf("C%f", psl)[0])
        # points
        if psl[0] == 'X':
            # мы в действии, определяем, точка или линия
            if "G85" in psl:
                # линия
                X0, Y0, X1, Y1 = scanf("X%6dY%6dG85X%6dY%6d", psl)
                points.append([X0/delim_num, Y0/delim_num, X1 /
                              delim_num, Y1/delim_num, tools[active_tool]])
            else:
                # точка
                X0, Y0 = scanf("X%6dY%6d", psl)
                points.append([X0/delim_num, Y0/delim_num, tools[active_tool]])
    if not metric_flag:
        DTM_log.printLog(f"Warning! NON-METRIC.")
    Drill_files_Points.append(points)


def load_file(fpath):
    DTM_log.printLog(f"Load file: {fpath}")
    f_p = open(fpath, 'r')  # получим объект файла
    p_s = f_p.readlines()  # считываем все строки
    # очищаем от переносов и разбиваем
    p_l = []
    for p_line in p_s:
        pls = p_line.rstrip()
        if pls[0] == ';' or pls[0] == '%':
            continue
        p_l.append(p_line.replace('\n', ''))
    f_p.close
    DTM_log.printLog("Collect data")
    convert_to_points(p_l)


def load_files(files):
    DTM_log.printLog("load_files")
    for file in files:
        load_file(file)


def gen_line_gcode(point):
    gc = f"G1 X{point[0]} Y{point[1]} F{g1_speed}\n"
    if abs(point[-1]-d_frezy) <= dr_dopusk:
        zp = safe_Z-WpTn_Z-Null_Z
        while (zp > Null_Z):
            gc += f"G1 Z{zp} F{g1_tool_speed}\n"
            gc += f"G1 X{point[2]} Y{point[3]}\n"
            zp = round(zp-plunge_height, 3)
            gc += f"G1 Z{zp} F{g1_tool_speed}\n"
            gc += f"G1 X{point[0]} Y{point[1]}\n"
    else:
        gc = "; No implementation\n"
        DTM_log.printLog(f"Warning! No implementation.")
    return gc


def gen_circle_gcode(point):
    gc = f"G1 X{point[0]} Y{point[1]} F{g1_speed}\n"
    if abs(point[-1]-d_frezy) <= dr_dopusk:
        return f"G1 Z{Null_Z} F{g1_tool_speed}\n"
    else:
        gc = "; No implementation\n"
        DTM_log.printLog(f"Warning! No implementation.")
    return gc


def convert_to_gcode():
    DTM_log.printLog("Start convert to gcode")
    GCode = Start_GCode.format(
        spindle_speed, safe_Z, g0_speed, start_point[0], start_point[1])+'\n'
    for dfp in Drill_files_Points:
        gc = ""
        for p in dfp:
            gc += f"G0 X{p[0]} Y{p[1]} F{g0_speed}\n"
            gc += f"G1 Z{safe_Z-WpTn_Z-Null_Z} F{g1_speed}\n"
            if len(p) == 5:
                # это линия
                gc += "; line\n"
                gc += gen_line_gcode(p)
            else:
                gc += "; circle\n"
                gc += gen_circle_gcode(p)
            gc += f"G1 Z{safe_Z-WpTn_Z-Null_Z} F{g1_speed}\n"
            gc += f"G0 Z{safe_Z}\n"
            gc += "; next\n"
        GCode += gc
    GCode += End_GCode
    return GCode


def save_gcode(gcode):
    DTM_log.printLog("Save gcode")
    f_db = open('gcode.txt', 'w', encoding='utf-8')  # получим объект файла
    f_db.write(gcode)
    f_db.close


if __name__ == "__main__":
    DTM_log.printLog("Starting...")

    if (check_files(Drill_files_path)):
        DTM_log.printLog("Check files: OK.")
    else:
        DTM_log.printLog("Check files: ERR.")
        sys.exit()  # завершаем программу

    load_files(Drill_files_path)

    GCode = convert_to_gcode()

    save_gcode(GCode)

    DTM_log.printLog("Exit")
