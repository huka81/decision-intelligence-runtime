@echo off
netstat -ano | find ":11434" >nul
if %errorlevel%==0 (
  echo Ollama already running
) else (
  wsl -d Ubuntu-24.04 -- bash -lc "OLLAMA_HOST=0.0.0.0:11434 exec ollama serve"
)
pause