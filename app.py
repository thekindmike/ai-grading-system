"""
AI作业批改打分系统 - 后端服务
支持学生拍照上传、OCR识别、答案对比、自动打分、错题标注、结果存储
"""
import os
import re
import json
import sqlite3
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from functools import wraps
from io import BytesIO

from flask import (
    Flask, render_template, request, jsonify, send_from_directory,
    g, redirect, url_for
)
from PIL import Image, ImageDraw, ImageFont
import pytesseract

# ============================================================
# 配置
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'output')
DATA_FOLDER = os.path.join(BASE_DIR, 'data')

# Tesseract 配置
TESSERACT_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# 检查可用的语言包
TESSDATA_DIR = os.path.join(os.path.dirname(TESSERACT_PATH), 'tessdata')
HAS_CHI_SIM = os.path.exists(os.path.join(TESSDATA_DIR, 'chi_sim.traineddata'))
OCR_LANG = 'chi_sim+eng' if HAS_CHI_SIM else 'eng'
print(f"[INFO] OCR 语言: {OCR_LANG} (chi_sim={'可用' if HAS_CHI_SIM else '不可用，请将 chi_sim.traineddata 放入 tessdata 目录'})")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# 确保目录存在
for d in [UPLOAD_FOLDER, OUTPUT_FOLDER, DATA_FOLDER]:
    os.makedirs(d, exist_ok=True)

# ============================================================
# 数据库
# ============================================================
DB_PATH = os.path.join(DATA_FOLDER, 'grading.db')


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript('''
        CREATE TABLE IF NOT EXISTS exams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            total_score REAL DEFAULT 100,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id TEXT NOT NULL,
            question_number INTEGER NOT NULL,
            question_type TEXT DEFAULT 'short_answer',
            question_text TEXT,
            reference_answer TEXT NOT NULL,
            score REAL DEFAULT 10,
            keywords TEXT,
            FOREIGN KEY (exam_id) REFERENCES exams(id)
        );

        CREATE TABLE IF NOT EXISTS grading_results (
            id TEXT PRIMARY KEY,
            exam_id TEXT,
            student_name TEXT DEFAULT '',
            original_image TEXT NOT NULL,
            annotated_image TEXT,
            ocr_text TEXT,
            score REAL DEFAULT 0,
            total_score REAL DEFAULT 100,
            details TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (exam_id) REFERENCES exams(id)
        );
    ''')
    db.commit()
    db.close()


init_db()

# ============================================================
# 辅助函数
# ============================================================


def text_similarity(a, b):
    """计算两段文本的相似度 (0-1)"""
    if not a or not b:
        return 0.0
    a = a.strip().lower()
    b = b.strip().lower()
    return SequenceMatcher(None, a, b).ratio()


def extract_text_from_image(image_path):
    """从图片中提取文字"""
    try:
        img = Image.open(image_path)
        # 预处理：转灰度、增强对比度
        img = img.convert('L')
        # OCR 识别
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(img, lang=OCR_LANG, config=custom_config)
        return text.strip()
    except Exception as e:
        app.logger.error(f"OCR 错误: {e}")
        return ""


def extract_answer_regions(text):
    """从OCR文本中解析出各题答案区域"""
    lines = text.strip().split('\n')
    answers = {}
    current_q = None
    current_answer = []

    patterns = [
        r'^(\d+)[\.、)\s]+',
        r'^第?\s*(\d+)\s*题',
        r'^Q(?:uestion)?\s*(\d+)',
        r'^(\d+)\s*[\.、]\s*',
    ]

    for line in lines:
        line = line.strip()
        if not line:
            continue

        matched = False
        for pat in patterns:
            m = re.match(pat, line, re.IGNORECASE)
            if m:
                if current_q and current_answer:
                    answers[current_q] = '\n'.join(current_answer)
                current_q = int(m.group(1))
                current_answer = [re.sub(pat, '', line, 1, re.IGNORECASE).strip()]
                matched = True
                break

        if not matched and current_q:
            current_answer.append(line)

    if current_q and current_answer:
        answers[current_q] = '\n'.join(current_answer)

    return answers


def get_font(size=24):
    """获取标注字体"""
    font_paths = [
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'simhei.ttf'),
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'msyh.ttc'),
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'simsun.ttc'),
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def annotate_image(image_path, questions_ref, student_answers, details):
    """在图片上标注错误"""
    try:
        img = Image.open(image_path).convert('RGBA')
        overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        font = get_font(20)
        font_small = get_font(16)

        img_w, img_h = img.size
        margin_left = 10
        margin_top = 50
        bar_height = 40

        # 顶部信息栏
        draw.rectangle([(0, 0), (img_w, bar_height)], fill=(0, 0, 0, 160))
        total_score = sum(d['score'] for d in details)
        max_score = sum(d['max_score'] for d in details)
        text = f"总分: {total_score}/{max_score}  |  批改时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        draw.text((10, 8), text, fill=(255, 255, 255, 255), font=font_small)

        # 标注每题
        y_pos = bar_height + 10
        for d in details:
            qn = d['question_number']
            score = d['score']
            max_s = d['max_score']
            is_correct = d.get('is_correct', False)

            color = (0, 200, 60, 200) if is_correct else (255, 60, 60, 200)
            status = "✓" if is_correct else "✗"

            rect_h = 36
            draw.rectangle(
                [(margin_left, y_pos), (margin_left + 280, y_pos + rect_h)],
                fill=(255, 255, 255, 200),
                outline=color[:3] + (220,),
                width=2
            )
            draw.text(
                (margin_left + 8, y_pos + 4),
                f"{status} 第{qn}题: {score}/{max_s}分",
                fill=color[:3],
                font=font
            )
            if not is_correct and d.get('comparison'):
                draw.text(
                    (margin_left + 8, y_pos + 4 + 22),
                    f"预期: {d['comparison'][:40]}...",
                    fill=(100, 100, 100, 255),
                    font=font_small
                )
            y_pos += rect_h + 6

        # 合并图层
        result = Image.alpha_composite(img, overlay)
        output_path = os.path.join(
            OUTPUT_FOLDER,
            f"annotated_{uuid.uuid4().hex[:8]}.png"
        )
        result.convert('RGB').save(output_path, 'PNG')
        return output_path
    except Exception as e:
        app.logger.error(f"图片标注错误: {e}")
        return None


def grade_answers(exam_id, student_answers):
    """对比答案并打分"""
    db = get_db()
    questions = db.execute(
        'SELECT * FROM questions WHERE exam_id=? ORDER BY question_number',
        (exam_id,)
    ).fetchall()

    if not questions:
        # 无配置时尝试智能分区
        return fallback_grade(student_answers)
    
    total_score = 0
    max_total = 0
    details = []

    for q in questions:
        qn = q['question_number']
        ref = q['reference_answer']
        max_s = q['score']
        keywords = q['keywords'] or ''

        student_ans = student_answers.get(qn, '')
        similarity = text_similarity(student_ans, ref)

        # 关键词额外加分
        keyword_bonus = 0
        if keywords and student_ans:
            kw_list = [k.strip() for k in keywords.split(',') if k.strip()]
            if kw_list:
                matched = sum(1 for kw in kw_list if kw.lower() in student_ans.lower())
                keyword_bonus = (matched / len(kw_list)) * 0.2 * max_s

        # 综合评分
        base_score = similarity * max_s * 0.8
        final_score = min(round(base_score + keyword_bonus, 1), max_s)
        is_correct = similarity >= 0.7

        total_score += final_score
        max_total += max_s
        details.append({
            'question_number': qn,
            'question_text': q['question_text'] or '',
            'student_answer': student_ans[:200],
            'reference_answer': ref[:200],
            'score': final_score,
            'max_score': max_s,
            'similarity': round(similarity * 100, 1),
            'is_correct': is_correct,
            'comparison': ref[:100],
        })

    return {
        'total_score': round(total_score, 1),
        'max_total': max_total,
        'details': details,
        'grade': get_grade_level(total_score, max_total),
    }


def fallback_grade(student_answers):
    """无参考答案配置时的智能评分（基于答案长度和格式）"""
    if not student_answers:
        return {
            'total_score': 0,
            'max_total': 100,
            'details': [],
            'grade': '未检测到答案',
        }
    
    details = []
    total_score = 0
    per_q = 100 / len(student_answers)
    
    for qn, ans in student_answers.items():
        # 基于答案长度的简单评分
        length_score = min(len(ans) / 50, 1.0) * 0.5
        has_numbers = bool(re.search(r'\d', ans))
        has_keywords = len(ans.split()) >= 2
        smart_score = length_score + (0.25 if has_numbers else 0) + (0.25 if has_keywords else 0)
        final = round(smart_score * per_q, 1)
        total_score += final
        details.append({
            'question_number': qn,
            'student_answer': ans[:200],
            'reference_answer': '（待教师配置参考答案）',
            'score': min(final, per_q),
            'max_score': round(per_q, 1),
            'similarity': round(smart_score * 100, 1),
            'is_correct': smart_score >= 0.6,
            'comparison': '请教师在管理端配置参考答案以获得精准批改',
        })
    
    return {
        'total_score': round(min(total_score, 100), 1),
        'max_total': 100,
        'details': details,
        'grade': get_grade_level(total_score, 100),
    }


def get_grade_level(score, total):
    """等级评定"""
    if total == 0:
        return 'N/A'
    pct = score / total * 100
    if pct >= 90:
        return 'A (优秀)'
    elif pct >= 80:
        return 'B (良好)'
    elif pct >= 70:
        return 'C (中等)'
    elif pct >= 60:
        return 'D (及格)'
    else:
        return 'F (不及格)'


# ============================================================
# 路由 - 页面
# ============================================================


@app.route('/')
def index():
    """学生端主页"""
    return render_template('index.html', page='student')


@app.route('/teacher')
def teacher():
    """教师管理端"""
    return render_template('teacher.html', page='teacher')


# ============================================================
# API - 学生端
# ============================================================


@app.route('/api/exams', methods=['GET'])
def api_get_exams():
    """获取所有试卷列表"""
    db = get_db()
    exams = db.execute(
        'SELECT * FROM exams ORDER BY created_at DESC'
    ).fetchall()
    return jsonify([dict(e) for e in exams])


@app.route('/api/grade', methods=['POST'])
def api_grade():
    """批改上传的试卷图片"""
    # 获取上传文件
    if 'image' not in request.files:
        return jsonify({'error': '未找到上传文件'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    exam_id = request.form.get('exam_id', 'default')
    student_name = request.form.get('student_name', '')

    # 保存原图
    ext = os.path.splitext(file.filename)[1] or '.jpg'
    save_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_FOLDER, save_name)
    file.save(save_path)

    # OCR 识别
    ocr_text = extract_text_from_image(save_path)
    student_answers = extract_answer_regions(ocr_text)

    # 对比打分
    result = grade_answers(exam_id, student_answers)
    
    # 图片标注
    annotated_path = annotate_image(
        save_path,
        [],
        student_answers,
        result['details']
    )

    # 存储结果
    result_id = uuid.uuid4().hex[:12]
    db = get_db()
    db.execute(
        '''INSERT INTO grading_results 
           (id, exam_id, student_name, original_image, annotated_image, 
            ocr_text, score, total_score, details)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            result_id, exam_id, student_name,
            f'/static/uploads/{save_name}',
            f'/output/{os.path.basename(annotated_path)}' if annotated_path else None,
            ocr_text,
            result['total_score'],
            result['max_total'],
            json.dumps(result['details'], ensure_ascii=False)
        )
    )
    db.commit()

    return jsonify({
        'success': True,
        'result_id': result_id,
        'ocr_text': ocr_text,
        'student_answers': {str(k): v for k, v in student_answers.items()},
        'total_score': result['total_score'],
        'max_total': result['max_total'],
        'grade': result['grade'],
        'details': result['details'],
        'original_image': f'/static/uploads/{save_name}',
        'annotated_image': f'/output/{os.path.basename(annotated_path)}' if annotated_path else None,
    })


@app.route('/api/results', methods=['GET'])
def api_get_results():
    """获取批改历史"""
    db = get_db()
    results = db.execute(
        '''SELECT r.*, e.name as exam_name 
           FROM grading_results r 
           LEFT JOIN exams e ON r.exam_id = e.id
           ORDER BY r.created_at DESC
           LIMIT 50'''
    ).fetchall()
    output = []
    for r in results:
        item = dict(r)
        item['details'] = json.loads(item['details']) if item['details'] else []
        output.append(item)
    return jsonify(output)


@app.route('/api/results/<result_id>', methods=['GET'])
def api_get_result(result_id):
    """获取单次批改详情"""
    db = get_db()
    r = db.execute(
        'SELECT * FROM grading_results WHERE id=?', (result_id,)
    ).fetchone()
    if not r:
        return jsonify({'error': '记录不存在'}), 404
    item = dict(r)
    item['details'] = json.loads(item['details']) if item['details'] else []
    return jsonify(item)


# ============================================================
# API - 教师端
# ============================================================


@app.route('/api/exams', methods=['POST'])
def api_create_exam():
    """创建试卷"""
    data = request.get_json()
    exam_id = uuid.uuid4().hex[:8]
    db = get_db()
    db.execute(
        'INSERT INTO exams (id, name, total_score) VALUES (?, ?, ?)',
        (exam_id, data.get('name', '未命名试卷'), data.get('total_score', 100))
    )
    db.commit()
    return jsonify({'success': True, 'exam_id': exam_id})


@app.route('/api/exams/<exam_id>', methods=['DELETE'])
def api_delete_exam(exam_id):
    """删除试卷及其题目"""
    db = get_db()
    db.execute('DELETE FROM questions WHERE exam_id=?', (exam_id,))
    db.execute('DELETE FROM exams WHERE id=?', (exam_id,))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/exams/<exam_id>/questions', methods=['GET'])
def api_get_questions(exam_id):
    """获取试卷的所有题目"""
    db = get_db()
    questions = db.execute(
        'SELECT * FROM questions WHERE exam_id=? ORDER BY question_number',
        (exam_id,)
    ).fetchall()
    return jsonify([dict(q) for q in questions])


@app.route('/api/questions', methods=['POST'])
def api_add_question():
    """添加题目"""
    data = request.get_json()
    db = get_db()
    # 获取下一个题号
    last = db.execute(
        'SELECT MAX(question_number) as m FROM questions WHERE exam_id=?',
        (data['exam_id'],)
    ).fetchone()
    next_num = (last['m'] or 0) + 1

    db.execute(
        '''INSERT INTO questions (exam_id, question_number, question_type, 
           question_text, reference_answer, score, keywords)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (
            data['exam_id'], next_num,
            data.get('question_type', 'short_answer'),
            data.get('question_text', ''),
            data['reference_answer'],
            data.get('score', 10),
            data.get('keywords', '')
        )
    )
    db.commit()
    return jsonify({'success': True, 'question_number': next_num})


@app.route('/api/questions/batch', methods=['POST'])
def api_batch_add_questions():
    """批量添加题目"""
    data = request.get_json()
    exam_id = data['exam_id']
    questions = data['questions']
    db = get_db()
    
    # 先清空该试卷的题目
    db.execute('DELETE FROM questions WHERE exam_id=?', (exam_id,))
    
    for i, q in enumerate(questions, 1):
        db.execute(
            '''INSERT INTO questions (exam_id, question_number, question_type,
               question_text, reference_answer, score, keywords)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (exam_id, i, q.get('type', 'short_answer'),
             q.get('text', ''), q['answer'], q.get('score', 10),
             q.get('keywords', ''))
        )
    db.commit()
    return jsonify({'success': True, 'count': len(questions)})


@app.route('/api/questions/<int:question_id>', methods=['PUT'])
def api_update_question(question_id):
    """更新题目"""
    data = request.get_json()
    db = get_db()
    db.execute(
        '''UPDATE questions SET question_text=?, reference_answer=?, 
           score=?, keywords=? WHERE id=?''',
        (data.get('question_text', ''), data['reference_answer'],
         data.get('score', 10), data.get('keywords', ''), question_id)
    )
    db.commit()
    return jsonify({'success': True})


@app.route('/api/questions/<int:question_id>', methods=['DELETE'])
def api_delete_question(question_id):
    """删除题目"""
    db = get_db()
    db.execute('DELETE FROM questions WHERE id=?', (question_id,))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/results/<result_id>', methods=['DELETE'])
def api_delete_result(result_id):
    """删除批改记录"""
    db = get_db()
    db.execute('DELETE FROM grading_results WHERE id=?', (result_id,))
    db.commit()
    return jsonify({'success': True})


# ============================================================
# 静态文件
# ============================================================


@app.route('/output/<filename>')
def output_file(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)


@app.route('/api/info')
def api_info():
    """系统信息"""
    db = get_db()
    exam_count = db.execute('SELECT COUNT(*) as c FROM exams').fetchone()['c']
    result_count = db.execute('SELECT COUNT(*) as c FROM grading_results').fetchone()['c']
    return jsonify({
        'ocr_lang': OCR_LANG,
        'has_chi_sim': HAS_CHI_SIM,
        'exam_count': exam_count,
        'result_count': result_count,
    })


# ============================================================
# 初始化演示数据
# ============================================================


def seed_demo_data():
    db = sqlite3.connect(DB_PATH)
    count = db.execute('SELECT COUNT(*) as c FROM exams').fetchone()[0]
    if count == 0:
        import uuid
        exam_id = 'demo_exam_01'
        db.execute(
            "INSERT INTO exams (id, name, total_score) VALUES (?, ?, ?)",
            (exam_id, '七年级地理-巴西章节测试', 100)
        )
        questions = [
            ('巴西位于哪个大洲？', '南美洲', 10, '南美洲,南美'),
            ('巴西的官方语言是什么？', '葡萄牙语', 10, '葡萄牙语,葡萄牙'),
            ('巴西的首都是哪个城市？', '巴西利亚', 10, '巴西利亚'),
            ('世界上流量最大的河流位于巴西，叫什么名字？', '亚马孙河', 10, '亚马孙河,亚马逊'),
            ('巴西最大的城市是哪个？', '圣保罗', 10, '圣保罗'),
            ('巴西的主要地形区分为哪两部分？', '亚马孙平原和巴西高原', 15, '亚马孙平原,巴西高原'),
            ('巴西人口主要分布在哪类地区？', '东南沿海地区', 15, '东南,沿海'),
            ('巴西热带雨林的名称是什么？', '亚马孙热带雨林', 20, '亚马孙,热带雨林,雨林'),
        ]
        for i, (text, answer, score, keywords) in enumerate(questions, 1):
            db.execute(
                '''INSERT INTO questions (exam_id, question_number, question_type,
                   question_text, reference_answer, score, keywords)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (exam_id, i, 'short_answer', text, answer, score, keywords)
            )
        db.commit()
        print("[INFO] 已创建演示试卷: 七年级地理-巴西章节测试 (8题, 100分)")
    db.close()


# ============================================================
# 启动
# ============================================================

if __name__ == '__main__':
    seed_demo_data()
    print(f"\n{'='*60}")
    print(f"  AI作业批改打分系统 已启动")
    print(f"  学生端: http://localhost:5000")
    print(f"  教师端: http://localhost:5000/teacher")
    print(f"  OCR引擎: {OCR_LANG}")
    print(f"{'='*60}\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
