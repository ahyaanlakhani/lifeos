@echo off
REM Windows entry point for demo mode.
REM
REM A .cmd wrapper rather than calling demo.ps1 directly: PowerShell scripts are
REM blocked by the default execution policy, batch files never are. The
REM -ExecutionPolicy flag below applies to this one process only and changes no
REM system setting.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0demo.ps1" %*
