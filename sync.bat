@echo off
chcp 65001 >nul
echo ===============================
echo  AI批改系统 - Git自动同步
echo ===============================
echo.

cd /d "E:\WorkBuddy\2026-06-20-10-51-42\ai-grading-system"

"C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe" git_push.py %1

echo.
pause
