@echo off
setlocal
where pythonw >nul 2>nul && (start "" pythonw "%~dp0..\scripts\gui_panel.py" %*) || (start "" python "%~dp0..\scripts\gui_panel.py" %*)
