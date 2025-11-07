# 🐶 SmartDog.py: Generalized Process & Log Utility

**SmartDog.py** is a flexible, configuration-driven Python utility designed to watch system processes and log files for specific conditions. Once all required conditions are met within their individual time limits, **SmartDog** executes a predefined sequence of actions, such as safely closing target programs.

It features multi-threading for concurrent watching, individual job timeouts, and robust signal handling to ensure proper cleanup even when interrupted by **Ctrl+C**.

-----

## 🚀 Features

  * **Configuration Driven:** **SmartDog's** behavior is defined entirely via a central JSON file.
  * **Concurrent Watching:** Uses threads to simultaneously watch multiple programs and log files.
  * **Individual Timeouts:** Each watching job (program start, log pattern) can have its own maximum wait time.
  * **Sequential Actions:** Executes a defined list of actions (e.g., closing programs) in a specified order upon successful trigger or timeout failure.
  * **Robust Signal Handling:** Catches **Ctrl+C** (`SIGINT`) to guarantee the cleanup action sequence runs before termination.
  * **Flexible Launch Support:** Can be launched with or without Administrator privileges, depending on the required actions.

-----

## 💻 Setup and Usage

### 1\. Prerequisites

  * **Python 3.x**
  * **Windows OS** (required for `tasklist` and `taskkill` process control, which require Admin access for effective use).

### 2\. Execution

The primary way to launch **SmartDog** is via a Batch file, which allows easy switching between standard and elevated execution.

#### Updated `run_monitor.bat` Example

Save the following code as **`run_monitor.bat`** in the same directory as `smartdog.py`.

```batch
@echo off
set "PYTHON_SCRIPT=smartdog.py"

ECHO.
ECHO =======================================
ECHO 1. Launch SmartDog with Admin Access (Recommended for process control)
ECHO =======================================

set "ADMIN_CONFIG=config_admin.json"
ECHO Launching SmartDog with Admin Access and config: %ADMIN_CONFIG%...

:: This uses PowerShell to elevate the Python process (triggers UAC)
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'py.exe' -ArgumentList '-u', '%PYTHON_SCRIPT%', '%ADMIN_CONFIG%' -Verb RunAs -Wait"

ECHO.
ECHO =======================================
ECHO 2. Launch SmartDog WITHOUT Admin Access
ECHO (For reading logs/files only)
ECHO =======================================

set "USER_CONFIG=config_user.json"
ECHO Launching SmartDog WITHOUT Admin Access and config: %USER_CONFIG%...

:: This launches Python directly without elevation.
:: Note: taskkill/tasklist may fail without Admin rights.
py.exe -u "%PYTHON_SCRIPT%" "%USER_CONFIG%"

ECHO.
ECHO ======================================================
ECHO Example 3: Single UAC Prompt, Multiple Concurrent Jobs (ALL Admin)
ECHO ======================================================

set "CONFIG_JOB1=config_job1.json"
set "CONFIG_JOB2=config_job2.json"

ECHO Launching elevated PowerShell session... (UAC Prompt will appear)

REM --- The corrected command uses double-quotes for the outer PowerShell argument and properly escapes
REM --- the entire inner command block, removing the confusing parentheses and caret continuation.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoExit -Command \"Start-Process -FilePath ''py.exe'' -ArgumentList ''-u'',''%PYTHON_SCRIPT%'',''%CONFIG_JOB1%'' -NoNewWindow; Start-Process -FilePath ''py.exe'' -ArgumentList ''-u'',''%PYTHON_SCRIPT%'',''%CONFIG_JOB2%'' -NoNewWindow; Start-Sleep -Seconds 1\"' -Verb RunAs"

ECHO.
ECHO All SmartDog jobs have finished.
```

-----

## ⚙️ Configuration (`config.json` / `config_*.json`)

The configuration file is a single JSON object that defines the entire workflow for **SmartDog**.

### Structure

| Key | Type | Description |
| :--- | :--- | :--- |
| **`initial_run`** | `string` | **Optional.** The full path to the program to launch first. |
| **`watch`** | `array` | **Required.** A list of conditions that must all be met to trigger the action sequence. |
| **`action`** | `array` | **Required.** A list of actions **SmartDog** must perform sequentially after all watch conditions are met or a watchdog job fails. |

### Watch Job Details

| Field | Type | Required? | Description |
| :--- | :--- | :--- | :--- |
| **`type`** | `string` | Yes | Either `"program"` or `"log"`. |
| **`name`** | `string` | Yes | **Program:** The executable name (e.g., `notepad.exe`). **Log:** The full path to the log file. |
| **`timeout_seconds`** | `number` | Yes | Maximum time (in seconds) the **SmartDog** thread will wait for this specific condition. |
| **`pattern`** | `string` | Log Only | The exact string to search for in new log lines. |
| **`encoding`** | `string` | Log Only | The file encoding (e.g., `"utf-8"`, `"latin-1"`). Defaults to `"utf-8"`. |

### Action Job Details

| Field | Type | Required? | Description |
| :--- | :--- | :--- | :--- |
| **`action`** | `string` | Yes | Currently only `"close"` is supported. |
| **`type`** | `string` | Yes | Currently only `"program"` is supported. |
| **`name`** | `string` | Yes | The executable name to terminate (e.g., `ProgramC.exe`). **Note:** This requires Admin access. |

-----

## 🛑 Interruption and Error Handling

**SmartDog** is designed to ensure a safe exit, regardless of the trigger:

| Event | Action | Outcome |
| :--- | :--- | :--- |
| **Success Trigger** | All `watch` conditions met. | Executes the `action` sequence immediately and exits successfully. |
| **Job Timeout/Failure** | Any single watch job fails or exceeds its `timeout_seconds`. | Triggers cleanup with a **failure reason**, executes the `action` sequence, and exits. |
| **User Interrupt** | **Ctrl+C** is pressed in the console. | The Python signal handler catches the event, executes the **entire `action` sequence**, and exits. |