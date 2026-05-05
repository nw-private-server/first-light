@echo off
setlocal

if not exist build mkdir build

cl /nologo /std:c++17 /EHsc /O2 /LD ^
  d3d11_proxy.cpp ^
  /link /DEF:d3d11_proxy.def /OUT:build\d3d11.dll

if errorlevel 1 exit /b %errorlevel%

echo Built build\d3d11.dll
