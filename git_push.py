#!/usr/bin/env python3
"""
AI批改系统 - 一键Git同步
用法: python3 git_push.py "提交说明"
"""

import os
import sys
import subprocess
from datetime import datetime

PROJECT_DIR = r"E:\WorkBuddy\2026-06-20-10-51-42\ai-grading-system"

def git_push(commit_msg=None):
    """执行 git add + commit + push"""
    os.chdir(PROJECT_DIR)
    
    # 检查是否有变化
    result = subprocess.run(['git', 'status', '--porcelain'], 
                          capture_output=True, text=True)
    if not result.stdout.strip():
        print("✅ 没有变化，无需同步")
        return True
    
    # 提交说明
    if not commit_msg:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        commit_msg = f"Auto-sync: {timestamp}"
        # Git add + commit + push
    try:
        subprocess.run(['git', 'add', '.'], check=True)
        subprocess.run(['git', 'commit', '-m', commit_msg], check=True)
        push = subprocess.run(['git', 'push', 'origin', 'main'], 
                            capture_output=True, text=True)
        if push.returncode == 0:
            print(f"✅ 已推送到GitHub: {commit_msg}")
            return True
        else:
            print(f"❌ 推送失败: {push.stderr}")
            return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Git操作失败: {e}")
        return False

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else None
    git_push(msg)
