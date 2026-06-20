#!/usr/bin/env python3
"""
AI批改系统 - 自动Git同步脚本
监控项目文件变化，自动 commit + push 到 GitHub
"""

import os
import time
import subprocess
import hashlib
from datetime import datetime

PROJECT_DIR = r"E:\WorkBuddy\2026-06-20-10-51-42\ai-grading-system"
WATCH_FILES = ["index.html", "obfuscation_map.json"]
CHECK_INTERVAL = 10  # 秒

def get_file_hash(filepath):
    """计算文件MD5哈希"""
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def git_sync(changed_files):
    """执行 git add + commit + push"""
    try:
        os.chdir(PROJECT_DIR)
        
        # 检查是否有变化
        result = subprocess.run(['git', 'status', '--porcelain'], 
                              capture_output=True, text=True)
        if not result.stdout.strip():
            return False  # 没有变化
        
        # Git add
        subprocess.run(['git', 'add', '.'])
        
        # Git commit
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        commit_msg = f"Auto-sync: {timestamp} | {', '.join(changed_files)}"
        subprocess.run(['git', 'commit', '-m', commit_msg])
        
        # Git push
        push_result = subprocess.run(
            ['git', 'push', 'origin', 'main'],
            capture_output=True, text=True
        )
        
        if push_result.returncode == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 已同步: {', '.join(changed_files)}")
            return True
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 推送失败: {push_result.stderr}")
            return False
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 错误: {e}")
        return False

def main():
    print("🔄 AI批改系统 - 自动Git同步已启动")
    print(f"📂 监控目录: {PROJECT_DIR}")
    print(f"📄 监控文件: {', '.join(WATCH_FILES)}")
    print(f"⏱️  检查间隔: {CHECK_INTERVAL}秒")
    print("-" * 50)
    
    # 初始哈希
    file_hashes = {}
    for fname in WATCH_FILES:
        fpath = os.path.join(PROJECT_DIR, fname)
        file_hashes[fname] = get_file_hash(fpath)
    
    while True:
        try:
            changed = []
            for fname in WATCH_FILES:
                fpath = os.path.join(PROJECT_DIR, fname)
                current_hash = get_file_hash(fpath)
                
                if fname not in file_hashes or file_hashes[fname] != current_hash:
                    if file_hashes.get(fname) is not None:  # 不是首次运行
                        changed.append(fname)
                    file_hashes[fname] = current_hash
            
            if changed:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 📝 检测到变化: {', '.join(changed)}")
                git_sync(changed)
            else:
                # 每60秒打印一次心跳
                if int(time.time()) % 60 == 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 💓 监控中...")
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n🛑 停止监控")
            break

if __name__ == "__main__":
    main()
