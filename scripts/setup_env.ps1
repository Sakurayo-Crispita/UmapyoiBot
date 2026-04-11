# Setup Environment Script for UmapyoiBot
# This script creates a virtual environment and installs all dependencies.

Write-Host "🚀 Iniciando configuración del entorno para UmapyoiBot..." -ForegroundColor Cyan

# 1. Crear el entorno virtual si no existe
if (-not (Test-Path ".venv")) {
    Write-Host "📦 Creando entorno virtual (.venv)..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "✅ El entorno virtual .venv ya existe." -ForegroundColor Green
}

# 2. Instalar dependencias
Write-Host "📥 Instalando dependencias desde requirements.txt..." -ForegroundColor Yellow
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\pip.exe" install -r requirements.txt

Write-Host "`n✨ ¡Configuración completada con éxito!" -ForegroundColor Green
Write-Host "Para que VS Code reconozca el entorno:" -ForegroundColor White
Write-Host "1. Presiona Ctrl+Shift+P" -ForegroundColor Gray
Write-Host "2. Escribe 'Python: Select Interpreter'" -ForegroundColor Gray
Write-Host "3. Selecciona el que dice '(.venv)'" -ForegroundColor Gray
