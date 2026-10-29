@echo off
setlocal enabledelayedexpansion

echo ========================================
echo   R-32 CPU - Automated Test Suite
echo ========================================
echo.


python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)


set TEST_DIR=examples
set MAIN_SCRIPT=src\main.py

:: Liste des programmes de test (sans l'extension .r32)
set TESTS=test_all fibonacci bubble_sort eratosthenes guess test_v11 test_movl test_trap test_irq

:: Compteur de succès/échecs
set SUCCESS=0
set FAILED=0

:: Boucle sur chaque test
for %%T in (%TESTS%) do (
    echo [RUNNING] %%T.r32 ...
    
    
    python -c "import sys; sys.path.insert(0, 'src'); from main import run_test; sys.exit(0 if run_test('%%T') else 1)" < nul >nul 2>&1
    
    if !errorlevel! equ 0 (
        echo    [PASS] %%T
        set /a SUCCESS+=1
    ) else (
        echo    [FAIL] %%T
        set /a FAILED+=1
    )
    echo.
)

echo ========================================
echo   Results: !SUCCESS! passed, !FAILED! failed
echo ========================================

if !FAILED! neq 0 (
    echo.
    echo [WARNING] Some tests failed. Check the output above.
    pause
    exit /b 1
) else (
    echo.
    echo [SUCCESS] All tests passed!
    pause
    exit /b 0
)