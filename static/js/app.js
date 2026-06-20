/**
 * AI作业批改系统 - 学生端 JavaScript
 */

let currentMode = 'upload';
let selectedFile = null;
let cameraStream = null;
let currentResult = null;

// ============================================
// 初始化
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    loadExams();
    setupDragDrop();

    // 上传预览
    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        fileInput.addEventListener('change', (e) => handleFileSelect(e));
    }
});

// ============================================
// 试卷列表
// ============================================

async function loadExams() {
    try {
        const resp = await fetch('/api/exams');
        const exams = await resp.json();
        const select = document.getElementById('examSelect');
        select.innerHTML = '';
        exams.forEach(e => {
            const opt = document.createElement('option');
            opt.value = e.id;
            opt.textContent = `${e.name} (${e.total_score}分)`;
            select.appendChild(opt);
        });
        if (exams.length === 0) {
            const opt = document.createElement('option');
            opt.value = 'default';
            opt.textContent = '通用试卷（无预设答案）';
            select.appendChild(opt);
        }
    } catch (err) {
        console.error('加载试卷失败:', err);
    }
}

// ============================================
// 模式切换
// ============================================

function switchMode(mode) {
    currentMode = mode;
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.upload-section').forEach(s => s.style.display = 'none');

    if (mode === 'upload') {
        document.querySelector('.mode-btn:first-child').classList.add('active');
        document.getElementById('mode-upload').style.display = 'block';
        stopCamera();
    } else {
        document.querySelector('.mode-btn:last-child').classList.add('active');
        document.getElementById('mode-camera').style.display = 'block';
        startCamera();
    }
}

function switchTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    if (tab === 'grade') {
        document.querySelector('.tab-btn:first-child').classList.add('active');
        document.getElementById('tab-grade').classList.add('active');
    } else {
        document.querySelector('.tab-btn:last-child').classList.add('active');
        document.getElementById('tab-history').classList.add('active');
        loadHistory();
    }
}

// ============================================
// 拖拽上传
// ============================================

function setupDragDrop() {
    const zone = document.getElementById('uploadZone');
    if (!zone) return;

    ['dragenter', 'dragover'].forEach(event => {
        zone.addEventListener(event, (e) => {
            e.preventDefault();
            zone.classList.add('drag-over');
        });
    });

    ['dragleave', 'drop'].forEach(event => {
        zone.addEventListener(event, (e) => {
            e.preventDefault();
            zone.classList.remove('drag-over');
        });
    });

    zone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    });
}

// ============================================
// 文件处理
// ============================================

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) handleFile(file);
}

function handleFile(file) {
    if (!file.type.startsWith('image/')) {
        alert('请选择图片文件（JPG、PNG等）');
        return;
    }
    selectedFile = file;

    const reader = new FileReader();
    reader.onload = (e) => {
        document.getElementById('previewImage').src = e.target.result;
        document.getElementById('previewSection').style.display = 'block';
        document.getElementById('resultPanel').classList.remove('active');
    };
    reader.readAsDataURL(file);
}

function resetUpload() {
    selectedFile = null;
    document.getElementById('previewSection').style.display = 'none';
    document.getElementById('resultPanel').classList.remove('active');
    document.getElementById('previewImage').src = '';
    document.getElementById('fileInput').value = '';
}

// ============================================
// 摄像头
// ============================================

async function startCamera() {
    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } }
        });
        const video = document.getElementById('cameraVideo');
        video.srcObject = cameraStream;
    } catch (err) {
        console.error('摄像头启动失败:', err);
        alert('无法访问摄像头，请检查权限设置。您可以使用上传模式。');
        switchMode('upload');
    }
}

function stopCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(t => t.stop());
        cameraStream = null;
    }
}

function capturePhoto() {
    const video = document.getElementById('cameraVideo');
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);

    canvas.toBlob((blob) => {
        const file = new File([blob], `camera_${Date.now()}.jpg`, { type: 'image/jpeg' });
        handleFile(file);
    }, 'image/jpeg', 0.95);
}

// ============================================
// AI 批改
// ============================================

async function startGrading() {
    if (!selectedFile) {
        alert('请先选择或拍摄试卷图片');
        return;
    }

    showProcessing(true);
    updateProcessing('正在上传图片...', '上传中');

    const formData = new FormData();
    formData.append('image', selectedFile);
    formData.append('exam_id', document.getElementById('examSelect').value);
    formData.append('student_name', document.getElementById('studentName').value || '');

    try {
        updateProcessing('正在AI识别文字...', 'OCR文字提取');
        const resp = await fetch('/api/grade', { method: 'POST', body: formData });
        const data = await resp.json();

        if (data.error) {
            alert('批改失败: ' + data.error);
            showProcessing(false);
            return;
        }

        updateProcessing('正在对比答案并打分...', '智能批改');
        await sleep(500);

        currentResult = data;
        renderResult(data);
        showProcessing(false);

    } catch (err) {
        console.error('批改失败:', err);
        alert('批改失败，请检查网络连接后重试');
        showProcessing(false);
    }
}

function renderResult(data) {
    // 分数展示
    document.getElementById('scoreDisplay').innerHTML = `
        <div class="score-display">
            <div class="score-number">${data.total_score}</div>
            <div class="score-label">/ ${data.max_total} 分</div>
            <div class="score-grade">${data.grade}</div>
        </div>
    `;

    // 批注图
    let annotatedHtml = '';
    if (data.annotated_image) {
        annotatedHtml = `
            <div class="image-compare">
                <div>
                    <img src="${data.original_image}" alt="原图" onerror="this.style.display='none'">
                    <div class="img-label">📄 原始试卷</div>
                </div>
                <div>
                    <img src="${data.annotated_image}" alt="批改结果" onerror="this.style.display='none'">
                    <div class="img-label">✅ 批改结果</div>
                </div>
            </div>
        `;
    }
    document.getElementById('annotatedImage').innerHTML = annotatedHtml;

    // 每题详情
    let detailsHtml = '<div class="card-header" style="margin-top: 12px;"><span class="card-title">📋 逐题分析</span></div>';
    data.details.forEach(d => {
        const isCorrect = d.is_correct;
        detailsHtml += `
            <div class="detail-item ${isCorrect ? 'correct' : 'incorrect'}">
                <div class="detail-status">${isCorrect ? '✅' : '❌'}</div>
                <div class="detail-content">
                    <div class="detail-header">
                        <span class="detail-q">第${d.question_number}题</span>
                        <span class="detail-score">${d.score}/${d.max_score} 分</span>
                    </div>
                    <div class="detail-answer">
                        <strong>学生答案：</strong>${d.student_answer || '（未识别到答案）'}
                    </div>
                    <div class="detail-ref">
                        <strong>参考答案：</strong>${d.reference_answer}
                    </div>
                    ${!isCorrect ? `<div style="margin-top:4px;font-size:12px;color:var(--danger);">
                        相似度：${d.similarity}%，与参考答案有差异
                    </div>` : ''}
                </div>
            </div>
        `;
    });
    document.getElementById('detailsList').innerHTML = detailsHtml;

    // 显示结果
    document.getElementById('resultPanel').classList.add('active');
    document.getElementById('resultPanel').scrollIntoView({ behavior: 'smooth' });
}

// ============================================
// 历史记录
// ============================================

async function loadHistory() {
    try {
        const resp = await fetch('/api/results');
        const results = await resp.json();
        const container = document.getElementById('historyList');

        if (results.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📭</div>
                    <p>暂无批改记录，快去批改第一份试卷吧！</p>
                </div>
            `;
            return;
        }

        container.innerHTML = results.map(r => {
            const pct = r.total_score > 0 ? Math.round(r.total_score / r.total_score * 100) : 0;
            return `
                <div class="history-item" onclick="viewDetail('${r.id}')">
                    <img class="history-thumb" src="${r.original_image}" alt="试卷缩略图" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2280%22 height=%2260%22><rect fill=%22%23e2e8f0%22 width=%2280%22 height=%2260%22/><text x=%2240%22 y=%2234%22 text-anchor=%22middle%22 fill=%22%2394a3b8%22 font-size=%2216%22>📝</text></svg>'">
                    <div class="history-info">
                        <div class="history-name">${r.exam_name || '试卷'} ${r.student_name ? '- ' + r.student_name : ''}</div>
                        <div class="history-meta">批改时间: ${r.created_at}</div>
                    </div>
                    <div class="history-score">${r.total_score}</div>
                    <button class="btn btn-danger" style="font-size:12px;padding:4px 8px;" onclick="event.stopPropagation(); deleteResult('${r.id}')">删除</button>
                </div>
            `;
        }).join('');

    } catch (err) {
        console.error('加载历史失败:', err);
    }
}

async function viewDetail(resultId) {
    try {
        const resp = await fetch(`/api/results/${resultId}`);
        const data = await resp.json();
        const modal = document.getElementById('detailModal');
        const content = document.getElementById('detailModalContent');

        content.innerHTML = `
            <div class="score-display" style="margin-bottom:16px;">
                <div class="score-number">${data.total_score}</div>
                <div class="score-label">/ ${data.total_score} 分</div>
            </div>
            ${data.details.map(d => `
                <div class="detail-item ${d.is_correct ? 'correct' : 'incorrect'}">
                    <div class="detail-status">${d.is_correct ? '✅' : '❌'}</div>
                    <div class="detail-content">
                        <div class="detail-header">
                            <span class="detail-q">第${d.question_number}题</span>
                            <span class="detail-score">${d.score}/${d.max_score}分</span>
                        </div>
                        <div class="detail-answer"><strong>学生答案：</strong>${d.student_answer || '（未识别）'}</div>
                        <div class="detail-ref"><strong>参考答案：</strong>${d.reference_answer}</div>
                    </div>
                </div>
            `).join('')}
        `;
        modal.classList.add('active');
    } catch (err) {
        console.error('加载详情失败:', err);
    }
}

function closeDetailModal() {
    document.getElementById('detailModal').classList.remove('active');
}

async function deleteResult(resultId) {
    if (!confirm('确定删除这条批改记录吗？此操作不可恢复。')) return;
    try {
        await fetch(`/api/results/${resultId}`, { method: 'DELETE' });
        loadHistory();
    } catch (err) {
        console.error('删除失败:', err);
    }
}

// ============================================
// 辅助函数
// ============================================

function showProcessing(show) {
    document.getElementById('processingOverlay').classList.toggle('active', show);
}

function updateProcessing(text, step) {
    document.getElementById('processingText').textContent = text;
    document.getElementById('processingStep').textContent = step || '';
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
