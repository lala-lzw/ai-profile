@echo off
setlocal
if exist "%~dp0..\scripts\aiprofile_cli.py" (
    set "CLI_SCRIPT=%~dp0..\scripts\aiprofile_cli.py"
) else (
    set "CLI_SCRIPT=C:\Users\user\Documents\Git\common-agent-skills\skills\ai-profile\scripts\aiprofile_cli.py"
)
python "%CLI_SCRIPT%" %*
