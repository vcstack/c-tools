```bat
@echo off
title YouTube Audio Downloader

echo ========================================
echo       YouTube Audio Downloader
echo ========================================
echo.

set /p "URL=Nhap URL YouTube: "

if "%URL%"=="" (
    echo.
    echo Chua nhap URL!
    pause
    exit /b
)

echo.
echo Dang tai audio...
echo.

yt-dlp -f "bestaudio[ext=m4a]/bestaudio" -o "%%(title)s.%%(ext)s" "%URL%"

echo.
echo ========================================
echo Download xong!
echo ========================================
pause
```
