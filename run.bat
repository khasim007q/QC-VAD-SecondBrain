@echo off
cd /d "%~dp0"
uv run --no-dev pythonw -m classnotes.ui.app
