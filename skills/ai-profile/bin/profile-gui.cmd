@echo off
setlocal
if exist "%~dp0..\scripts\gui_panel.py" (
    set "GUI_SCRIPT=%~dp0..\scripts\gui_panel.py"
) else (
    set "GUI_SCRIPT=C:\Users\user\Documents\Git\common-agent-skills\skills\ai-profile\scripts\gui_panel.py"
)
start "" python "%GUI_SCRIPT%" %*
