/**
 * AI作业批改系统 - 教师管理端 JavaScript
 */

let currentTeacherTab = 'exams';

// ============================================
// 初始化
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    loadExams();
    loadExamSelects();
    loadTeacherResults();
});

// ============================================
// 选项卡切换
// ============================================

function switchTeacherTab(tab) {
    currentTeacherTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('[id^="teacher-tab-"]').forEach(c => c.classList.remove('active'));

    // 找到对应的按钮和内容
    const buttons = document.querySelectorAll('.tab-btn');
    const tabs = ['exams', 'questions', 'results'];
    const idx = tabs.indexOf(tab);
    if (idx >= 0) {
        buttons[idx].classList.add('active');
        document.getElementById(`teacher-tab-${tab}`).classList.add('active');
    }

    if (tab === 'exams') loadExams();
    if (tab === 'results') loadTeacherResults();
}

// ============================================
// 试卷管理
// ============================================

async function loadExams() {
    try {
        const resp = await fetch('/api/exams');
        const exams = await resp.json();
        const tbody = document.getElementById('examTableBody');

        if (exams.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-secondary);">暂无试卷，点击"新建试卷"创建</td></tr>';
            return;
        }

        tbody.innerHTML = exams.map(e => `
            <tr>
                <td><strong>${e.name}</strong></td>
                <td>${e.total_score}分</td>
                <td><span class="badge badge-info">加载中...</span></td>
                <td>${e.created_at}</td>
                <td>
                    <button class="btn btn-outline" style="padding:4px 12px;font-size:12px;" onclick="editExamQuestions('${e.id}')">配置题目</button>
                    <button class="btn btn-danger" style="padding:4px 12px;font-size:12px;" onclick="deleteExam('${e.id}')">删除</button>
                </td>
            </tr>
        `).join('');

        // 加载每份试卷的题目数
        for (const e of exams) {
            try {
                const qResp = await fetch(`/api/exams/${e.id}/questions`);
                const questions = await qResp.json();
                const rows = tbody.querySelectorAll('tr');
                for (const row of rows) {
                    const nameCell = row.querySelector('td:first-child strong');
                    if (nameCell && nameCell.textContent === e.name) {
                        const badge = row.querySelector('.badge');
                        if (badge) {
                            badge.textContent = `${questions.length}题`;
                            badge.className = `badge ${questions.length > 0 ? 'badge-success' : 'badge-warning'}`;
                        }
                    }
                }
            } catch (err) {
                console.error('加载题目数失败:', err);
            }
        }
    } catch (err) {
        console.error('加载试卷列表失败:', err);
    }
}

function showCreateExamModal() {
    document.getElementById('examModal').classList.add('active');
    document.getElementById('examName').value = '';
    document.getElementById('examTotalScore').value = '100';
}

function closeExamModal() {
    document.getElementById('examModal').classList.remove('active');
}

async function createExam() {
    const name = document.getElementById('examName').value.trim();
    const total = parseFloat(document.getElementById('examTotalScore').value) || 100;

    if (!name) {
        alert('请输入试卷名称');
        return;
    }

    try {
        const resp = await fetch('/api/exams', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, total_score: total })
        });
        const data = await resp.json();
        if (data.success) {
            closeExamModal();
            loadExams();
            loadExamSelects();
            alert('试卷创建成功！请切换到"题目配置"标签添加题目。');
        }
    } catch (err) {
        console.error('创建试卷失败:', err);
        alert('创建失败，请重试');
    }
}

async function deleteExam(examId) {
    if (!confirm('确定删除该试卷及其所有题目吗？此操作不可恢复。')) return;
    try {
        await fetch(`/api/exams/${examId}`, { method: 'DELETE' });
        loadExams();
        loadExamSelects();
    } catch (err) {
        console.error('删除试卷失败:', err);
    }
}

function editExamQuestions(examId) {
    document.getElementById('questionExamSelect').value = examId;
    switchTeacherTab('questions');
    loadQuestions();
}

// ============================================
// 题目配置
// ============================================

async function loadExamSelects() {
    try {
        const resp = await fetch('/api/exams');
        const exams = await resp.json();
        const select = document.getElementById('questionExamSelect');
        const currentVal = select.value;
        select.innerHTML = '<option value="">选择试卷...</option>';
        exams.forEach(e => {
            const opt = document.createElement('option');
            opt.value = e.id;
            opt.textContent = e.name;
            select.appendChild(opt);
        });
        if (currentVal && exams.some(e => e.id === currentVal)) {
            select.value = currentVal;
        }
    } catch (err) {
        console.error('加载试卷选项失败:', err);
    }
}

async function loadQuestions() {
    const examId = document.getElementById('questionExamSelect').value;
    const container = document.getElementById('questionsContainer');

    if (!examId) {
        container.innerHTML = '<div class="empty-state"><div class="empty-icon">📝</div><p>请先选择一份试卷</p></div>';
        return;
    }

    try {
        const resp = await fetch(`/api/exams/${examId}/questions`);
        const questions = await resp.json();

        if (questions.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📝</div>
                    <p>该试卷暂无题目，点击"添加题目"开始配置</p>
                </div>
            `;
            return;
        }

        container.innerHTML = questions.map((q, i) => `
            <div class="card" style="margin-bottom:12px;" data-qid="${q.id}">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                    <strong>第${q.question_number}题 (${q.score}分)</strong>
                    <button class="btn btn-danger" style="padding:4px 10px;font-size:12px;" onclick="deleteQuestion(${q.id})">删除</button>
                </div>
                <div class="form-group">
                    <label class="form-label">题目内容</label>
                    <input type="text" class="input question-text" value="${escapeHtml(q.question_text || '')}" placeholder="例如：巴西的官方语言是什么？">
                </div>
                <div class="form-group">
                    <label class="form-label">参考答案 <span style="color:red;">*</span></label>
                    <textarea class="textarea question-answer" rows="2" placeholder="标准答案">${escapeHtml(q.reference_answer || '')}</textarea>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                    <div class="form-group">
                        <label class="form-label">分值</label>
                        <input type="number" class="input question-score" value="${q.score}" min="1" step="0.5">
                    </div>
                    <div class="form-group">
                        <label class="form-label">关键词（逗号分隔）</label>
                        <input type="text" class="input question-keywords" value="${escapeHtml(q.keywords || '')}" placeholder="例如：南美洲,南美">
                    </div>
                </div>
            </div>
        `).join('');
    } catch (err) {
        console.error('加载题目失败:', err);
        container.innerHTML = '<div class="empty-state"><p style="color:red;">加载失败，请重试</p></div>';
    }
}

function addQuestionRow() {
    const examId = document.getElementById('questionExamSelect').value;
    if (!examId) {
        alert('请先选择一份试卷');
        return;
    }

    const container = document.getElementById('questionsContainer');
    const existingCards = container.querySelectorAll('.card[data-qid]');
    const nextNum = existingCards.length + 1;

    // 移除空状态
    const emptyState = container.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    const card = document.createElement('div');
    card.className = 'card';
    card.style.marginBottom = '12px';
    card.dataset.qid = 'new_' + Date.now();
    card.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <strong>新题目 #${nextNum}</strong>
            <button class="btn btn-danger" style="padding:4px 10px;font-size:12px;" onclick="this.closest('.card').remove()">删除</button>
        </div>
        <div class="form-group">
            <label class="form-label">题目内容</label>
            <input type="text" class="input question-text" placeholder="例如：巴西的官方语言是什么？">
        </div>
        <div class="form-group">
            <label class="form-label">参考答案 <span style="color:red;">*</span></label>
            <textarea class="textarea question-answer" rows="2" placeholder="标准答案"></textarea>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div class="form-group">
                <label class="form-label">分值</label>
                <input type="number" class="input question-score" value="10" min="1" step="0.5">
            </div>
            <div class="form-group">
                <label class="form-label">关键词（逗号分隔）</label>
                <input type="text" class="input question-keywords" placeholder="例如：南美洲,南美">
            </div>
        </div>
    `;
    container.appendChild(card);
    card.scrollIntoView({ behavior: 'smooth' });
}

async function saveAllQuestions() {
    const examId = document.getElementById('questionExamSelect').value;
    if (!examId) {
        alert('请先选择一份试卷');
        return;
    }

    const cards = document.getElementById('questionsContainer').querySelectorAll('.card');
    const questions = [];

    cards.forEach(card => {
        const answer = card.querySelector('.question-answer').value.trim();
        if (!answer) return; // 跳过无答案的

        questions.push({
            text: card.querySelector('.question-text').value.trim(),
            answer: answer,
            score: parseFloat(card.querySelector('.question-score').value) || 10,
            keywords: card.querySelector('.question-keywords').value.trim(),
        });
    });

    if (questions.length === 0) {
        alert('请至少添加一道有参考答案的题目');
        return;
    }

    try {
        const resp = await fetch('/api/questions/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ exam_id: examId, questions })
        });
        const data = await resp.json();
        if (data.success) {
            alert(`保存成功！共 ${data.count} 道题目`);
            loadQuestions();
            loadExams();
        }
    } catch (err) {
        console.error('保存题目失败:', err);
        alert('保存失败，请重试');
    }
}

async function deleteQuestion(questionId) {
    if (!confirm('确定删除这道题目吗？')) return;
    try {
        await fetch(`/api/questions/${questionId}`, { method: 'DELETE' });
        loadQuestions();
        loadExams();
    } catch (err) {
        console.error('删除题目失败:', err);
    }
}

// ============================================
// 批改记录
// ============================================

async function loadTeacherResults() {
    try {
        const resp = await fetch('/api/results');
        const results = await resp.json();
        const tbody = document.getElementById('teacherResultBody');

        if (results.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-secondary);">暂无批改记录</td></tr>';
            return;
        }

        tbody.innerHTML = results.map(r => `
            <tr>
                <td>${r.student_name || '未署名'}</td>
                <td>${r.exam_name || '未知试卷'}</td>
                <td>
                    <strong style="color:${r.total_score >= 60 ? 'var(--success)' : 'var(--danger)'};">
                        ${r.total_score}/${r.total_score}
                    </strong>
                </td>
                <td>${r.created_at}</td>
                <td>
                    <button class="btn btn-outline" style="padding:4px 12px;font-size:12px;" 
                            onclick="viewTeacherDetail('${r.id}')">详情</button>
                    <button class="btn btn-danger" style="padding:4px 12px;font-size:12px;" 
                            onclick="deleteTeacherResult('${r.id}')">删除</button>
                </td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('加载批改记录失败:', err);
    }
}

async function viewTeacherDetail(resultId) {
    try {
        const resp = await fetch(`/api/results/${resultId}`);
        const data = await resp.json();

        let detailsHtml = data.details.map(d => `
            <div class="detail-item ${d.is_correct ? 'correct' : 'incorrect'}">
                <div class="detail-status">${d.is_correct ? '✅' : '❌'}</div>
                <div class="detail-content">
                    <div class="detail-header">
                        <span class="detail-q">第${d.question_number}题</span>
                        <span class="detail-score">${d.score}/${d.max_score}分 (${d.similarity}%)</span>
                    </div>
                    <div class="detail-answer"><strong>学生答案：</strong>${d.student_answer || '（未识别）'}</div>
                    <div class="detail-ref"><strong>参考答案：</strong>${d.reference_answer}</div>
                </div>
            </div>
        `).join('');

        const modal = document.createElement('div');
        modal.className = 'modal-overlay active';
        modal.innerHTML = `
            <div class="modal" style="max-width:640px;">
                <div class="modal-title">📋 批改详情 - ${data.student_name || '未署名'}</div>
                <div class="score-display" style="margin-bottom:16px;">
                    <div class="score-number">${data.total_score}</div>
                    <div class="score-label">/ ${data.total_score} 分</div>
                </div>
                ${data.annotated_image ? `
                    <div style="margin-bottom:16px;">
                        <img src="${data.annotated_image}" style="width:100%;border-radius:8px;" alt="批改结果">
                    </div>
                ` : ''}
                ${detailsHtml}
                <div class="modal-actions">
                    <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">关闭</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });
    } catch (err) {
        console.error('加载详情失败:', err);
    }
}

async function deleteTeacherResult(resultId) {
    if (!confirm('确定删除这条批改记录吗？')) return;
    try {
        await fetch(`/api/results/${resultId}`, { method: 'DELETE' });
        loadTeacherResults();
    } catch (err) {
        console.error('删除失败:', err);
    }
}

// ============================================
// 辅助
// ============================================

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
