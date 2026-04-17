@echo off
REM Ghidra launcher with Java 17 configured
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot"
set "PATH=%JAVA_HOME%\bin;%PATH%"

echo Launching Ghidra with Java 17...
echo JAVA_HOME=%JAVA_HOME%
echo.
echo After Ghidra opens:
echo   1. File ^> Configure... (first time)
echo   2. Project: Open or create "C:\Users\charl\Programs\NewWorldPrivate\analysis\ghidra_project"
echo   3. File ^> Import File... pick G:\NewWorldArchive\GameClient\Bin64\NewWorld.exe
echo   4. After import, open in CodeBrowser, let auto-analysis run (1-4 hours)
echo   5. Once analysis completes: File ^> Configure ^> Configure ^> check "GhidraMCP"
echo   6. Restart Ghidra to activate the plugin
echo   7. Tools ^> GhidraMCP should show "Running on port 8080"
echo.

start "" "C:\Tools\ghidra\ghidra_11.3_PUBLIC\ghidraRun.bat"
