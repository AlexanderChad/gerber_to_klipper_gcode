import math
import re
import sys
from scanf import scanf
import os.path
import DTM_log
import time

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
dr_dopusk = 0.3  # допуск в мм для отверстий
#####################################################

# файлы с данными
Drill_files_path = ["files/Drill_NPTH_Through.DRL", "files/Drill_PTH_Through.DRL",
                    "files/Drill_PTH_Through_Via.DRL", "files/Gerber_BoardOutlineLayer.GKO"]
# точки (действия), извлеченные из файлов
Drill_files_Points = []
Box_Points = []

# стартовый код
Start_GCode = """
G21
G90
M3 S{0}
G0 Z{1} F{2}
G0 X{3} Y{4} F{2}
"""

# завершающий код
End_GCode = """
M5
M84 X Y E
"""


# проверяем, что необходимые файлы присутствуют
def check_files(files):
    DTM_log.printLog("Check files")
    for file in files:
        if os.path.isfile(file):
            DTM_log.printLog(f"Check file: {file} exists.")
        else:
            DTM_log.printLog(f"Check file: {file} does not exist.")
            return False
    return True


# конвертирование в точки (действия)
def convert_to_points(points_str_lines):
    global Drill_files_Points  # сюда будем складывать все точки
    metric_flag = False  # флаг, что данные в файле метрические
    delim_num = 1  # масштаб, если 1000, а в файле 12560, то это значит 12.56 мм
    tools = {}  # инструменты
    active_tool = 0  # активный инструмент
    points = []  # точки
    # перебираем строки
    for psl in points_str_lines:
        # metric flag
        if psl[:6] == "METRIC":
            metric_flag = True
            # запоминаем масштаб
            delim_num = 10**len(psl.split(',')[2].split('.')[1])
        # ignore
        # if psl == "M48" or psl == "G05" or psl == "G90" or psl == "M30":
        #    continue
        # tool
        elif psl[0] == 'T':  # инструмент
            # запоминаем номер активного
            active_tool = int(scanf("T%2d", psl)[0])
            if not scanf("C%f", psl) == None:  # если это установка параметров инструмента
                # запоминаем диаметр фрезы
                tools[active_tool] = float(scanf("C%f", psl)[0])
        # points
        elif psl[0] == 'X':
            # мы в действии, определяем, точка или линия
            if "G85" in psl:
                # линия
                X0, Y0, X1, Y1 = scanf("X%6dY%6dG85X%6dY%6d", psl)
                # запоминаем в формате [X0, Y0, X1, Y1, D_Frezy]
                points.append([X0/delim_num, Y0/delim_num, X1 /
                              delim_num, Y1/delim_num, tools[active_tool]])
            else:
                # точка
                X0, Y0 = scanf("X%6dY%6d", psl)
                # запоминаем в формате [X0, Y0, D_Frezy]
                points.append([X0/delim_num, Y0/delim_num, tools[active_tool]])
    # если флаг метрических данных не был установлен, то это плохо
    if not metric_flag:
        # обойдемся предупреждением
        DTM_log.printLog(f"Warning! NON-METRIC.")
    # запоминаем полученные точки
    Drill_files_Points += points


# конвертируем в контур платы
def convert_to_box(points_str_lines):
    global Box_Points  # сюда будем складывать все точки контура
    tools = {}  # инструменты
    active_tool = 0  # активный инструмент
    metric_flag = False  # флаг, что данные в файле метрические
    points = []  # точки
    # масштаб, если 1000, а в файле 12560, то это значит 12.56 мм
    delim_num_x = 1
    delim_num_y = 1
    # перебираем строки
    for psl in points_str_lines:
        if "G04" in psl[:3]:
            continue
        elif "%FSLAX" in psl:
            delim_num_x, delim_num_y = scanf("%FSLAX%2dY%2d*%", psl)
            delim_num_x = 10**(delim_num_x % 10)
            delim_num_y = 10**(delim_num_y % 10)
        # metric flag
        elif "%MOMM*%" in psl:
            metric_flag = True
        elif "%ADD" in psl:
            num_tool, tool_param = scanf("%ADD%2dC,%f*%", psl)
            # запоминаем
            tools[num_tool] = tool_param
        elif psl[0] == 'D':
            active_tool = scanf("D%2d*", psl)[0]
        elif "D02*" == psl[-4:]:
            x0, y0 = scanf("X%dY%dD02*", psl)
            x0 /= delim_num_x
            y0 /= delim_num_y
        elif "D01*" == psl[-4:]:
            ss = re.split('X|Y|D', psl)
            x = int(ss[1])
            y = int(ss[2])
            points.append([x/delim_num_x, y/delim_num_y, tools[active_tool]])
    # если флаг метрических данных не был установлен, то это плохо
    if not metric_flag:
        # обойдемся предупреждением
        DTM_log.printLog(f"Warning! NON-METRIC.")
    # запоминаем полученные точки
    Box_Points += points


# загрузка файла
def load_file(fpath):
    DTM_log.printLog(f"Load file: {fpath}")
    f_p = open(fpath, 'r')  # получим объект файла
    p_s = f_p.readlines()  # считываем все строки
    p_l = []  # сюда будем складывать строки
    for p_line in p_s:  # перебираем строки
        pls = p_line.rstrip()  # убираем лишнее
        if len(pls) == 0:  # пропускаем пустые
            continue
        if pls[0] == ';':  # комментарии сразу отбрасываем
            continue
        # складываем команды без переноса в конце
        p_l.append(p_line.replace('\n', ''))
    f_p.close  # закрываем файл
    DTM_log.printLog("Collect data")
    if ".GKO" in fpath:
        convert_to_box(p_l)
    else:
        convert_to_points(p_l)  # конвертируем в точки (действия)


# загружаем файлы
def load_files(files):
    DTM_log.printLog("load_files")
    for file in files:
        load_file(file)


def gen_line_gcode(point):
    gc = "; No implementation\n"
    if abs(point[-1]-d_frezy) <= dr_dopusk:
        gc = f"G1 X{point[0]} Y{point[1]} F{g1_speed}\n"
        zp = safe_Z-WpTn_Z-Null_Z
        while (zp > Null_Z):
            gc += f"G1 Z{zp} F{g1_tool_speed}\n"
            gc += f"G1 X{point[2]} Y{point[3]} F{g1_speed}\n"
            zp = round(zp-plunge_height, 3)
            gc += f"G1 Z{zp} F{g1_tool_speed}\n"
            gc += f"G1 X{point[0]} Y{point[1]} F{g1_speed}\n"
    elif point[-1] >= d_frezy:  # если диаметр фрезы меньше диаметра отверстия
        gc = ""
        # запоминаем рабочий радиус с учетом диаметра фрезы
        new_r = (point[-1]-d_frezy)/2
        # отводим инструмент к точке врезания
        # gc = f"G1 X{point[0]+new_r} Y{point[1]} F{g1_speed}\n"
        start_angle = math.atan2(
            point[1]-point[3], point[0]-point[2])-(math.pi/2)
        end_angle = math.pi + start_angle
        # точка начала контура
        start_x = 0
        start_y = 0
        # мы на этой высоте (начало всегда с нее)
        zp = safe_Z-WpTn_Z-Null_Z
        # повторяем резку пока не достигнем высоты конца
        while (zp > Null_Z):
            # опускаемся на следующий слой
            zp = round(zp-plunge_height, 3)
            gc += f"G1 Z{zp} F{g1_tool_speed}\n"
            # обрабатываем концы
            for ia, next_angle in enumerate([start_angle, end_angle]):
                # преобразуем круг в многоугольник
                for i in range(7):
                    # считаем кординаты следующей точки по х
                    next_x = round(
                        new_r*math.cos(i*math.pi/6+next_angle)+point[ia*2], 3)
                    # считаем кординаты следующей точки по у
                    next_y = round(
                        new_r*math.sin(i*math.pi/6+next_angle)+point[ia*2+1], 3)
                    if (i == 0):  # если первый заход
                        # задаем скорость резки
                        gc += f"G1 X{next_x} Y{next_y} F{g1_speed}\n"
                        # если сторона начала
                        if ia == 0:
                            # запоминаем точку начала контура
                            start_x = next_x
                            start_y = next_y
                    else:
                        gc += f"G1 X{next_x} Y{next_y}\n"  # режем по контуру
            # дорезаем до начала контура
            gc += f"G1 X{start_x} Y{start_y}\n"
        gc += "; tested\n"  # пока это тестовая функция
    else:
        gc += "; No implementation. Very small line.\n"
        DTM_log.printLog(f"Warning! No implementation. Very small line.")
    return gc


# генерируем код отверстия
def gen_circle_gcode(point):
    gc = "; No implementation\n"
    # если не сильно отличается диаметр отверстия от фрезы
    if abs(point[-1]-d_frezy) <= dr_dopusk:
        return f"G1 Z{Null_Z} F{g1_tool_speed}\n"  # просто сверлим по центру
    elif point[-1] >= d_frezy:  # если диаметр фрезы меньше диаметра отверстия
        # запоминаем рабочий радиус с учетом диаметра фрезы
        new_r = (point[-1]-d_frezy)/2
        # отводим инструмент к точке врезания
        gc = f"G1 X{point[0]+new_r} Y{point[1]} F{g1_speed}\n"
        # gc += f"G1 X{point[0]+new_r} Y{point[1]}\n"#
        zp = safe_Z-WpTn_Z-Null_Z  # мы на этой высоте (начало всегда с нее)
        while (zp >= Null_Z):  # повторяем резку пока не достигнем высоты конца
            gc += f"G1 Z{zp} F{g1_tool_speed}\n"  # врезаемся
            # высчитываем следующую высоту прохода
            zp = round(zp-plunge_height, 3)
            for i in range(12):  # преобразуем круг в многоугольник
                # считаем кординаты следующей точки по х
                next_x = round(new_r*math.cos((i+1)*math.pi/6)+point[0], 3)
                # считаем кординаты следующей точки по у
                next_y = round(new_r*math.sin((i+1)*math.pi/6)+point[1], 3)
                if (i == 0):  # если первый заход
                    # задаем скорость резки
                    gc += f"G1 X{next_x} Y{next_y} F{g1_speed}\n"
                else:
                    gc += f"G1 X{next_x} Y{next_y}\n"  # режем по контуру
        gc += "; tested\n"  # пока это тестовая функция
    else:  # если отверстие сильно меньше фрезы
        # на всякий случай оставляем без изменений
        gc = "; No implementation. Very small hole.\n"
        DTM_log.printLog(f"Warning! No implementation. Very small hole.")
    return gc  # возвращаем gcode


# оптимизируем расположение точек (действий)
def optim_points():
    global Drill_files_Points
    # получаем элементы х и у, а так же их экстремумы
    x_elem = [elem[0] for elem in Drill_files_Points]
    y_elem = [elem[1] for elem in Drill_files_Points]
    x_min = min(x_elem)
    x_max = max(x_elem)
    y_min = min(y_elem)
    y_max = max(y_elem)
    # сюда будем складывать точки по секторам
    dp_sec = {}
    # размер сетки для разбиения
    x_delim = 10
    y_delim = 10
    # инициализируем массив
    for i in range(x_delim*y_delim):
        dp_sec[i] = []
    # считаем длину разделителей
    x_d = math.ceil((x_max-x_min)/x_delim)
    y_d = math.ceil((y_max-y_min)/y_delim)
    # раскладываем точки по клеткам
    for elem in Drill_files_Points:
        ix = (elem[0]-x_min)//x_d  # вычисляем клетку по х
        iy = (elem[1]-y_min)//y_d  # вычисляем клетку по у
        index = ix+x_delim * iy  # вычисляем координаты клетки (х, у)
        dp_sec[index].append(elem)  # кладем точку в соответствующую клетку
    # задаем порядок обработки точек в каждой клетке с учетом того, что обход будет вертикальный (по Оу)
    for i in range(x_delim*y_delim):
        if i//x_delim % 2:  # определяем, что это столбец с направлением вверх или вниз
            k = 0.3
        else:
            k = 0.7
        # k = 0.5
        # ищем точку центра сектора и тут же задаем смещение в зависимости от направления
        cx = x_min+(x_d/2)+(x_d*(i % x_delim))
        cy = y_min+(y_d*k)+(y_d*(i//x_delim))
        # сортируем по удаленности от точки центра приоритета сектора
        dp_sec[i].sort(key=lambda p: ((p[0] - cx)**2 + (p[1] - cy)**2))

    Drill_files_Points = []  # откуда брали, туда же и будем складывать
    # перебирем секторы
    for i in range(x_delim):
        ri = range(y_delim)
        if i % 2:  # определяем направление столбца
            ri = reversed(ri)  # меняем движение снизу вверх на обратное
        for j in ri:
            # записываем действия в соответствии с их приоритетом
            Drill_files_Points += dp_sec[i+j*x_delim]


# генерируем рез контура платы
def gen_box_gcode():
    # перемещаемся к точке начала
    gc = f"G0 X{Box_Points[0][0]} Y{Box_Points[0][1]} F{g0_speed}\n"
    # опускаемся с безопасной высоты на рабочую
    gc += f"G1 Z{safe_Z-WpTn_Z-Null_Z} F{g1_speed}\n"
    zp = safe_Z-WpTn_Z-Null_Z  # мы на этой высоте (начало всегда с нее)
    while (zp >= Null_Z):  # повторяем резку пока не достигнем высоты конца
        gc += f"G1 Z{zp} F{g1_tool_speed}\n"  # врезаемся
        # высчитываем следующую высоту прохода
        zp = round(zp-plunge_height, 3)
        for i, bp in enumerate(Box_Points):
            if (i == 0):  # если первый заход
                # задаем скорость резки
                gc += f"G1 X{bp[0]} Y{bp[1]} F{g1_speed}\n"
            else:
                gc += f"G1 X{bp[0]} Y{bp[1]}\n"  # режем по контуру
        gc += f"G1 X{Box_Points[0][0]} Y{Box_Points[0][1]}\n"
    # поднимаем инструмент над рабочей поверхностью
    gc += f"G1 Z{safe_Z-WpTn_Z-Null_Z} F{g1_speed}\n"
    # поднимаем на безопасную для перемещения высоту
    gc += f"G0 Z{safe_Z} F{g0_speed}\n"
    gc += "; tested\n"  # пока это тестовая функция
    return gc


# конвертируем в gcode
def convert_to_gcode():
    DTM_log.printLog("Start convert to gcode")
    # добавляем стартовый gcode
    GCode = Start_GCode.format(
        spindle_speed, safe_Z, g0_speed, start_point[0], start_point[1])+'\n'
    optim_points()  # сортировка точек по приоритетности обработки
    # создаем gcode для каждой точки
    for p in Drill_files_Points:
        # перемещаемся к точке
        GCode += f"G0 X{p[0]} Y{p[1]} F{g0_speed}\n"
        # опускаемся с безопасной высоты на рабочую
        GCode += f"G1 Z{safe_Z-WpTn_Z-Null_Z} F{g1_speed}\n"
        # определяем тип точки
        if len(p) == 5:
            # это линия
            GCode += "; line\n"
            # генерируем код линии
            GCode += gen_line_gcode(p)
        else:
            # это отверстие
            GCode += "; circle\n"
            # генерируем код отвертстия
            GCode += gen_circle_gcode(p)
        # поднимаем инструмент над рабочей поверхностью
        GCode += f"G1 Z{safe_Z-WpTn_Z-Null_Z} F{g1_speed}\n"
        # поднимаем на безопасную для перемещения высоту
        GCode += f"G0 Z{safe_Z} F{g0_speed}\n"
        # переходим к следующей точке
        GCode += "; next\n"
    # генерируем рез контура платы
    GCode += gen_box_gcode()
    # добавляем завершающий gcode
    GCode += End_GCode
    # возвращаем сгенерированный
    return GCode


# сохраняем gcode в файл
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
