from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
import sqlite3
import pandas as pd
import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import fonts
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import letter
from datetime import datetime

def read_excel_dynamic_skiprows(file_path):
    """ Проверяет первую строку и определяет, нужно ли skiprows=5 на основе количества Unnamed столбцов. """
    first_row = pd.read_excel(file_path, nrows=1)  # Читаем первую строку
    unnamed_columns = sum(col.startswith("Unnamed") for col in first_row.columns)  # Считаем "Unnamed" столбцы
    
    if unnamed_columns > len(first_row.columns) / 2:  # Если более половины столбцов "Unnamed"
        return pd.read_excel(file_path, skiprows=5)  # Пропускаем 5 строк
    else:
        return pd.read_excel(file_path)



app = Flask(__name__)
app.secret_key = os.urandom(24)  # Секретный ключ для сессий

# Настройка папки для загрузок
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- База данных ---
def init_db():
    """
    Инициализирует базу данных и создает таблицу пользователей, если она не существует.
    """
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    # Создаем таблицу пользователей, если она не существует
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def add_user(username, password):
    
    """
    Добавляет нового пользователя в базу данных.
    """
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
        conn.commit()
    except sqlite3.IntegrityError:
        print(f"Пользователь {username} уже существует.")
    finally:
        conn.close()

def validate_user(username, password):
    """
    Проверяет, существует ли пользователь с заданными учетными данными.
    """
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
    user = cursor.fetchone()
    conn.close()
    return user

# --- Роуты ---
@app.route('/')
def login():
    """
    Отображает страницу входа.
    """
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login_user():
    """
    Обрабатывает вход пользователя.
    """
    username = request.form['username']
    password = request.form['password']
    if validate_user(username, password):
        session['username'] = username
        flash('Вы успешно вошли в систему.', 'success')
        return redirect(url_for('upload_files'))
    else:
        flash('Неверное имя пользователя или пароль. Попробуйте снова.', 'danger')
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    """
    Обрабатывает выход пользователя из системы.
    """
    session.pop('username', None)
    flash('Вы успешно вышли из системы.', 'success')
    return redirect(url_for('login'))



@app.route('/upload', methods=['GET', 'POST'])
def upload_files():
    """
    Обрабатывает загрузку файлов.
    """
    if 'username' not in session:
        flash('Пожалуйста, войдите в систему.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Проверка наличия файлов в форме
        if 'file1' not in request.files or 'file2' not in request.files:
            flash('Оба файла обязательны для загрузки.', 'danger')
            return redirect(request.url)

        file1 = request.files['file1']
        file2 = request.files['file2']

        # Проверка, выбраны ли файлы
        if file1.filename == '' or file2.filename == '':
            flash('Пожалуйста, выберите оба файла для загрузки.', 'danger')
            return redirect(request.url)

        # Сохранение файлов
        file1.save(os.path.join(app.config['UPLOAD_FOLDER'], 'file1.xlsx'))
        file2.save(os.path.join(app.config['UPLOAD_FOLDER'], 'file2.xlsx'))

        flash('Файлы успешно загружены.', 'success')
        return redirect(url_for('process_files'))

    return render_template('upload.html')

@app.route('/process')
def process_files():
    """
    Обрабатывает загруженные файлы, сравнивает данные и генерирует отчеты.
    """
    if 'username' not in session:
        flash('Пожалуйста, войдите в систему.', 'warning')
        return redirect(url_for('login'))

    file1_path = os.path.join(app.config['UPLOAD_FOLDER'], 'file1.xlsx')
    file2_path = os.path.join(app.config['UPLOAD_FOLDER'], 'file2.xlsx')

    # Проверка наличия загруженных файлов
    if not os.path.exists(file1_path) or not os.path.exists(file2_path):
        flash('Оба файла должны быть загружены перед обработкой.', 'danger')
        return redirect(url_for('upload_files'))

    # Чтение Excel файлов, пропуская первые 5 строк
    try:
        data1 = pd.read_excel(file1_path, skiprows=5)
        data2 = pd.read_excel(file2_path, skiprows=5)
    except Exception as e:
        flash(f'Ошибка при чтении Excel файлов: {e}', 'danger')
        return redirect(url_for('upload_files'))

    id_column = "Идентификатор обучающегося"

    # Проверка наличия необходимых столбцов
    required_columns = [id_column, "ИИК", "БИК", "ИИН", "Приказ о назначении стипендии", "Квота","Сирота", "Имеет инвалидность по слуху", "Вид стипендии"]
    for col in required_columns:
        if col not in data1.columns or col not in data2.columns:
            flash(f'Отсутствует обязательный столбец: {col}', 'danger')
            return redirect(url_for('upload_files'))

    # Приведение идентификаторов к строковому типу
    data1[id_column] = data1[id_column].astype(str)
    data2[id_column] = data2[id_column].astype(str)

    # Нахождение общих идентификаторов
    common_ids = set(data1[id_column]) & set(data2[id_column])

    # Инициализация списков для различий
    iik_diff = []
    bik_diff = []
    iin_diff = []
    date_diff = []
    sirota_diff=[]
    kvota_diff=[]
    hear_diff=[]
    step_diff=[]
    vision_diff=[]
    period_diff=[]

    # Определение столбцов для сравнения
    columns_to_compare = {
        'iik': "ИИК",
        'bik': "БИК",
        'iin': "ИИН",
        'date': "Приказ о назначении стипендии",
        'sirota': "Сирота",
        'kvota': "Квота",
        'hear':"Имеет инвалидность по слуху",
        'vision': "Имеет инвалидность по зрению",
        'period': "Unnamed: 26"
        
    }
    reports={}

    # Итерация по общим идентификаторам и поиск различий
    for student_id in common_ids:
        row1 = data1[data1[id_column] == student_id].iloc[0]
        row2 = data2[data2[id_column] == student_id].iloc[0]

        # Сравнение ИИК
        if row1[columns_to_compare['iik']] != row2[columns_to_compare['iik']]:
            iik_diff.append({
                "ID": student_id,
                "File1_ИИК": row1[columns_to_compare['iik']],
                "File2_ИИК": row2[columns_to_compare['iik']]
            })
        if iik_diff:
            reports['iik']='reports_iik.txt'

        # Сравнение БИК
        if row1[columns_to_compare['bik']] != row2[columns_to_compare['bik']]:
            bik_diff.append({
                "ID": student_id,
                "File1_БИК": row1[columns_to_compare['bik']],
                "File2_БИК": row2[columns_to_compare['bik']]
            })
        if bik_diff:
            reports['bik']='reports_bil.txt'

        # Сравнение ИИН
        if row1[columns_to_compare['iin']] != row2[columns_to_compare['iin']]:
            iin_diff.append({
                "ID": student_id,
                "File1_IIN": row1[columns_to_compare['iin']],
                "File2_IIN": row2[columns_to_compare['iin']]
            })
        if iin_diff:
            reports['iin']='reports_iin.txt'

        # Сравнение периодов
        if row1[columns_to_compare['period']] != row2[columns_to_compare['period']]:
            period_diff.append({
                "ID": student_id,
                "File1_Period": row1[columns_to_compare['period']],
                "File2_Period": row2[columns_to_compare['period']]
            })
        if period_diff:
            reports['period']='reports_period.txt'

        # Сравнение даты приказа
        if row1[columns_to_compare['date']] != row2[columns_to_compare['date']]:
            date_diff.append({
                "ID": student_id,
                "File1_Date": row1[columns_to_compare['date']],
                "File2_Date": row2[columns_to_compare['date']]
            })
            if date_diff:
                reports['date']='reports_date.txt'
        #sirota
        if row1[columns_to_compare['sirota']] != row2[columns_to_compare['sirota']] :
            sirota_diff.append({
                "ID": student_id,
                "File1_SIROTA": row1[columns_to_compare['sirota']],
                "File2_SIROTA": row2[columns_to_compare['sirota']]
            })
        if sirota_diff:
            reports['sirota']='reports_sirota.txt'
        

        
        # Названия столбцов
        scholarship_column = "Вид стипендии"  # Проверяем наличие данных
        performance_column = "Общая успеваемость"  # Проверяем, входит ли в [0, 1, 3]

# Проверяем, если есть данные в "Вид стипендий" и "Общая успеваемость" равна 0, 1 или 3
        if pd.notna(row1[scholarship_column]) and row1[performance_column] in [0, 1, 3]:
            step_diff.append({
        "ID": student_id,
        "File1_Вид_стипендий": row1[scholarship_column],
        "File1_Общая_успеваемость": row1[performance_column]
    })

        if pd.notna(row2[scholarship_column]) and row2[performance_column] in [0, 1, 3]:
            step_diff.append({
        "ID": student_id,
        "File2_Вид_стипендий": row2[scholarship_column],
        "File2_Общая_успеваемость": row2[performance_column]
    })

        #kvota
        if row1[columns_to_compare['kvota']] != row2[columns_to_compare['kvota']]:
            kvota_diff.append({
                "ID": student_id,
                "File1_Kvota":row1[columns_to_compare['kvota']],
                "File2_Kvota":row2[columns_to_compare['kvota']]
            })
        if kvota_diff:
            reports['kvota']='reports_kvota.txt'
        #invalid_hear

        today=datetime.today().date()
        
        start_row = 8  # Начинать проверку с этой строки
        date_column = "Дата окончания инвалидности"  # Название столбца с датами   
        date_col_index = 41

        if row1[columns_to_compare['hear']]!=row2[columns_to_compare['hear']]:
            date1 = pd.to_datetime(row1[date_column], errors='coerce').date() if pd.notna(row1[date_column]) else None
            date2 = pd.to_datetime(row2[date_column], errors='coerce').date() if pd.notna(row2[date_column]) else None
    
    # Проверяем, если дата существует и она меньше сегодняшней
    is_expired1 = date1 is not None and date1 < today
    is_expired2 = pd.notna(date2) and date2.date() < today

    hear_diff.append({
        "ID": student_id,
        "File1_Hear": row1[columns_to_compare['hear']],
        "File2_Hear": row2[columns_to_compare['hear']],
        "File1_Date": date1,
        "File2_Date": date2,
        "Expired_File1": "Да" if is_expired1 else "Нет",
        "Expired_File2": "Да" if is_expired2 else "Нет"
    })
    if hear_diff:
            reports['hear'] = 'report_hear.txt'


    # Словарь для отслеживания доступных отчетов
    reports = {}

     #invalid_vision

        
    start_row = 8  # Начинать проверку с этой строки
    date_column = "Дата окончания инвалидности"  # Название столбца с датами   
    date_col_index = 44

    if row1[columns_to_compare['vision']]!=row2[columns_to_compare['vision']]:
            date1 = pd.to_datetime(row1[date_column], errors='coerce').date() if pd.notna(row1[date_column]) else None
            date2 = pd.to_datetime(row2[date_column], errors='coerce').date() if pd.notna(row2[date_column]) else None
    
    # Проверяем, если дата существует и она меньше сегодняшней
    is_expired1 = date1 is not None and date1 < today
    is_expired2 = pd.notna(date2) and date2.date() < today

    vision_diff.append({
        "ID": student_id,
        "File1_vision": row1[columns_to_compare['hear']],
        "File2_vision": row2[columns_to_compare['hear']],
        "File1_Date": date1,
        "File2_Date": date2,
        "Expired_File1": "Да" if is_expired1 else "Нет",
        "Expired_File2": "Да" if is_expired2 else "Нет"
    })
    if vision_diff:
            reports['vision'] = 'report_vision.txt'


    # Словарь для отслеживания доступных отчетов
    reports = {}
    

    # Функция для генерации и сохранения отчета, если есть различия
    def generate_report(diff_list, report_key, report_title, headers):
        if diff_list:
            report_content = f"Изменения по {report_title}:\n"
            report_content += ", ".join(headers) + "\n"
            for diff in diff_list:
                report_content += ", ".join([f"{key}: {value}" for key, value in diff.items()]) + "\n"
            report_filename = f'report_{report_key}.txt'
            report_path = os.path.join(app.config['UPLOAD_FOLDER'], report_filename)
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            reports[report_key] = report_filename

    # Генерация отдельных отчетов
    generate_report(iik_diff, 'iik', 'ИИК', ["ID", "File1_ИИК", "File2_ИИК"])
    generate_report(bik_diff, 'bik', 'БИК', ["ID", "File1_БИК", "File2_БИК"])
    generate_report(iin_diff, 'iin', 'ИИН', ["ID", "File1_IIN", "File2_IIN"])
    generate_report(date_diff, 'date', 'датам приказов', ["ID", "File1_Date", "File2_Date"])
    generate_report(sirota_diff, 'sirota', 'сиротам', ["ID", "File1_SIROTA", "File2_SIROTA"])
    generate_report(kvota_diff, 'kvota', 'квоте', ["ID", "File1_kvota", "File2_kvota"])
    generate_report(hear_diff,'hear','слуху', ["ID", "File1_Hear", "File2_Hear"])
    generate_report(step_diff, scholarship_column, 'стипендий', ["ID", "File1_Вид_стипендий", "File1_Общая_успеваемость"])
    generate_report(vision_diff, 'vision', 'зрению', ["ID", "File1_vision", "File2_vision"])
    generate_report(period_diff, 'period', 'периоду', ["ID", "File1_Period", "File2_Period"] )
    



    pdfmetrics.registerFont(TTFont('Times New Roman', 'C:/Users/админ/AppData/Local/Microsoft/Windows/Fonts/Times New Roman.ttf'))  # Укажите путь к своему шрифту
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], 'report_all.pdf')
    c = canvas.Canvas(pdf_path, pagesize=A4)
# Устанавливаем шрифт
    c.setFont("Times New Roman", 12)

    # Генерация общего отчета, если есть хотя бы один индивидуальный отчет
    if reports:
        width, height = A4
    y_position = height - 50  # Начальная позиция текста
   
    c.setFont("Times New Roman", 14)
    c.drawString(50, y_position, "Общий отчет по различиям")
    y_position -= 20  # Отступ вниз

    has_content = False  # Флаг, есть ли изменения хотя бы в одном разделе

    for key in ['iik', 'bik', 'iin', 'date', 'sirota', "kvota", 'hear', scholarship_column, 'vision', 'period']:
        if key in reports:
            report_path = os.path.join(app.config['UPLOAD_FOLDER'], reports[key])
            if os.path.exists(report_path):  
                with open(report_path, 'r', encoding='utf-8') as f:
                    content = f.readlines()

                # **Фильтруем пустые строки и nan**
                filtered_lines = [line for line in content if "nan" not in line.strip()]

                if filtered_lines:  # Если есть хотя бы одна строка с изменением
                    has_content = True
                    y_position -= 20
                    c.setFont("Times New Roman", 12)
                    c.drawString(50, y_position, f"Раздел: {key.upper()}")
                    y_position -= 10

                    c.setFont("Times New Roman", 10)
                    for line in filtered_lines:
                        y_position -= 15
                        if y_position < 50:
                            c.showPage()
                            c.setFont("Times New Roman", 10)
                            y_position = height - 50
                        c.drawString(50, y_position, line.strip())

    if has_content:
        c.save()
        reports['all'] = 'report_all.pdf'
    else:
        os.remove(pdf_path)  # Удаляем пустой PDF, если нет изменений

    # Передача списка доступных отчетов в шаблон
    return render_template('report.html', reports=reports)

# 🔹 Страница выбора столбцов для сравнения
# 🔹 Выбор столбцов
@app.route('/select_columns', methods=['GET', 'POST'])
def select_columns():
    file1_path = os.path.join(app.config['UPLOAD_FOLDER'], 'file1.xlsx')
    file2_path = os.path.join(app.config['UPLOAD_FOLDER'], 'file2.xlsx')

    # Если загружаем файлы
    if request.method == 'POST' and 'file1' in request.files and 'file2' in request.files:
        file1 = request.files['file1']
        file2 = request.files['file2']

        if not file1 or not file2:
            flash("Пожалуйста, загрузите оба файла!", "danger")
            return redirect(request.url)

        file1.save(file1_path)
        file2.save(file2_path)
        flash("Файлы успешно загружены!", "success")
        return redirect(url_for('select_columns'))  # Перезагрузка страницы

    # Проверяем, загружены ли файлы
    if not os.path.exists(file1_path) or not os.path.exists(file2_path):
        flash("Сначала загрузите файлы!", "danger")
        return redirect(url_for('upload_files'))

    try:
        # Читаем файлы с заголовками с 6-й строки
        df1 = pd.read_excel(file1_path)
        df2 = pd.read_excel(file2_path)

        # Передаем столбцы как списки
        columns1 = df1.columns.tolist()
        columns2 = df2.columns.tolist()

        return render_template('select_columns.html', columns1=columns1, columns2=columns2)

    except Exception as e:
        flash(f"Ошибка при чтении файлов: {e}", "danger")
        return redirect(url_for('upload_files'))


# 🔹 Обработка сравнения столбцов
@app.route('/compare', methods=['POST'])
def compare():
    selected_columns1 = request.form.getlist('columns1')
    selected_columns2 = request.form.getlist('columns2')

    if not selected_columns1 or not selected_columns2:
        flash("Выберите хотя бы один столбец из каждого файла!", "danger")
        return redirect(url_for('select_columns'))

    file1_path = os.path.join(app.config['UPLOAD_FOLDER'], 'file1.xlsx')
    file2_path = os.path.join(app.config['UPLOAD_FOLDER'], 'file2.xlsx')

    df1 = pd.read_excel(file1_path, skiprows=5, usecols=selected_columns1)
    df2 = pd.read_excel(file2_path, skiprows=5, usecols=selected_columns2)

    report_lines = []
    common_rows = min(len(df1), len(df2))  # Сравниваем только одинаковые строки

    for i in range(common_rows):
        row_diff = []
        for col1, col2 in zip(selected_columns1, selected_columns2):
            if str(df1.iloc[i][col1]) != str(df2.iloc[i][col2]):  # Исправлено
                row_diff.append(f"{col1}: {df1.iloc[i][col1]} -> {df2.iloc[i][col2]}")

        if row_diff:
            report_lines.append(f"Строка {i + 1}: " + "; ".join(row_diff))

    report_path = os.path.join(app.config['UPLOAD_FOLDER'], 'report.txt')

    if report_lines:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(report_lines))
        return send_file(report_path, as_attachment=True)
    else:
        flash("Нет различий в выбранных столбцах!", "success")
        return redirect(url_for('select_columns'))



@app.route('/download/<report_type>')
def download_report(report_type):
    """
    Обрабатывает скачивание отчета по типу.
    """
    if 'username' not in session:
        flash('Пожалуйста, войдите в систему.', 'warning')
        return redirect(url_for('login'))

    # Сопоставление типов отчетов с именами файлов
    report_files = {
        'iik': 'report_iik.txt',
        'bik': 'report_bik.txt',
        'iin': 'report_iin.txt',
        'date': 'report_date.txt',
        'all': 'report_all.pdf',
        'sirota': 'report_sirota.txt'
    }

    # Проверка валидности типа отчета
    if report_type not in report_files:
        flash('Неверный тип отчета.', 'danger')
        return redirect(url_for('process_files'))

    report_path = os.path.join(app.config['UPLOAD_FOLDER'], report_files[report_type])

    # Проверка существования файла отчета
    if not os.path.exists(report_path):
        flash('Отчет не найден или изменений не обнаружено.', 'warning')
        return redirect(url_for('process_files'))

    return send_file(report_path, as_attachment=True)

# --- Запуск приложения ---
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
