@echo off
chcp 65001 > nul
echo ========================================================
echo   crypto-alert 안드로이드 APK 빌드 스크립트
echo ========================================================
echo.

where flutter >nul 2>nul
if %errorlevel% neq 0 (
    echo [경고] Flutter가 시스템 PATH에 설치되어 있지 않습니다.
    echo Flutter SDK(https://docs.flutter.dev/get-started/install/windows)를 설치하거나
    echo GitHub Actions 워크플로우를 통해 클라우드에서 자동 빌드할 수 있습니다.
    echo.
    pause
    exit /b 1
)

echo [1/3] 의존성 패키지 다운로드 중...
call flutter pub get
if %errorlevel% neq 0 (
    echo [오류] 의존성 패키지 설치 실패
    pause
    exit /b 1
)

echo [2/3] Android Release APK 빌드 중...
call flutter build apk --release
if %errorlevel% neq 0 (
    echo [오류] APK 빌드 실패
    pause
    exit /b 1
)

echo.
echo [3/3] 빌드 완료!
echo 생성된 APK 경로: build\app\outputs\flutter-apk\app-release.apk
echo ========================================================
pause
