@echo off
cd /d "%~dp0"
start "" uv run pythonw -m classnotes.ui.app
