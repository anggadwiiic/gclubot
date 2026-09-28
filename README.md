# LU Automation Engine

LU Automation Engine is a desktop automation workspace for Administrative Services Bureau and Gun Control and Licensing Unit forum operations.

The application is designed to bring four existing automation workflows into one interactive GUI:

- **Valid Checker** - validates and repairs license application threads.
- **Auto Renewal** - identifies expired licenses and starts the renewal workflow.
- **Renewal Check** - checks renewal responses and denies expired renewal requests.
- **CGC Checker** - expires and archives Certificate of Good Conduct threads.

## Key Features

- One desktop GUI with four selectable automation modules.
- One shared Chrome profile for all modules.
- Manual login in Chrome on first use.
- Reusable login session through the local `bot_profile` directory.
- One active module at a time to prevent browser profile conflicts.
- Start, stop, progress, and activity log controls for each module.
- Global signature settings for generated forum messages.
- Optional signature image URL using BBCode.
- Portable Windows executable distribution.

## Implementation Status

The current source contains the shared GUI shell, shared Chrome profile service, global signature builder, and four GUI-independent module adapters. The three renewal/CGC adapters receive the saved configurable signature when they generate forum messages. Valid Checker intentionally keeps its paid response limited to `PAID` and `VALID UNTIL`; it does not use the global signature. Final end-to-end forum testing remains before the first production release.

## Signature Customization

Generated messages can use a shared signature configuration:

- Staff position.
- Staff name.
- Optional signature image URL.

Example output:

```bbcode
[right]Sincerely,
[img]https://imgur.com/ViYn0hy.png[/img]
[b]LU Staff[/b], [i]Firstname Lastname[/i]
[/right]
```

The image URL is optional and is taken from the GUI input. If it is empty, the
`[img]...[/img]` line is omitted:

```bbcode
[right]Sincerely,
[b]LU Staff[/b], [i]Firstname Lastname[/i]
[/right]
```

The configured signature is used by Auto Renewal, Renewal Check, and CGC
Checker. Valid Checker intentionally does not use the global signature.

Default values:

```text
Position: LU Staff
Staff name: empty
Signature image URL: empty
```

## Requirements

- Windows 10 or newer.
- Python 3.10 or newer for running from source.
- Google Chrome.
- A valid forum account.
- Forum permissions required by the selected automation module.

## Installation

Open PowerShell in the project folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run from Source

```powershell
.\.venv\Scripts\python.exe app.py
```

The application opens a dedicated visible Chrome profile for manual login when required. It does not control the page during verification. After you finish verification and login, the application attaches to that same browser session for the selected workflow. The login session is kept in the `bot_profile` folder beside the application.

## Download the Latest Windows Executable

When a GitHub Release is published, download the latest executable here:

[Download LU Automation Engine for Windows](https://github.com/anggadwiiic/gclubot/releases/latest/download/LU-Automation-Engine.exe)

The repository is currently being prepared. The download link will become active after the first release asset is uploaded.

## Build a Standalone Executable

Install PyInstaller:

```powershell
py -3.13 -m pip install pyinstaller
```

Build the executable:

```powershell
py -3.13 -m PyInstaller --clean LU-Automation-Engine.spec
```

The executable is generated in the `dist` directory.

Use the included spec file instead of the shorter command above. The build command intentionally uses the regular Windows Python installation because it contains the Tcl/Tk standard-library package. It explicitly bundles Tkinter, the Tcl/Tk runtime, and the Windows GUI dependencies required by the standalone executable.

If the Python Launcher is unavailable, run the command with the full path to a regular Python installation that includes Tkinter. Do not build this application with a virtual environment whose Python installation does not expose the standard-library `tkinter` package to PyInstaller.

After building, verify that this file exists:

```text
dist\LU-Automation-Engine.exe
```

If source code or message formatting is changed, rebuild the executable before
testing the packaged application. The `.exe` does not update automatically
when a `.py` file is edited.

For GitHub distribution, upload the generated file as a release asset with this exact name:

```text
LU-Automation-Engine.exe
```

## Usage Guide

1. Launch the application.
2. Select one of the four automation modules. The selected module is highlighted in blue in the sidebar.
3. Configure the module-specific inputs.
4. Configure the global signature if the selected workflow sends a message. Valid Checker does not use this setting.
5. Click **Open Login Browser**. A dedicated visible Chrome opens with the shared `bot_profile`.
6. Complete any human-verification prompt manually, wait for the forum page to finish loading, and log in manually.
7. Leave the browser window open, return to the application, and click **Start Automation**. The application attaches to this same Chrome session.
8. Follow the progress and activity log.
9. Stop the process only when necessary and wait for the active browser operation to finish.

Only one automation module can run at a time because all modules use the shared Chrome profile.

## Automation Modules

### Valid Checker

Valid Checker reads license and activity records from the selected data directory. It calculates the expected validity period, checks the related forum thread, repairs incorrect validity dates when needed, and moves the thread to the matching forum.

For cancelled applications, it can mark the thread as denied, publish the denial response, and move the thread to the archive forum. For example, an officer can select a folder containing `licenses*.xlsx` and `log*.xlsx`, enter the issuing officer name, and process all eligible records in one run.

### Auto Renewal

Auto Renewal scans valid-license forums for threads whose validity period has reached its renewal window. It changes the thread to the renewal format, posts the renewal reminder, and moves the thread to the relevant renewal forum.

For example, a truck license that has reached its expiration date can automatically receive an `EXPIRED` notice and a three-day renewal instruction.

### Renewal Check

Renewal Check reviews renewal threads and checks whether the license owner has responded after receiving the renewal reminder. If there is no valid response after three days, the thread is marked as denied and moved to the appropriate archive forum.

For example, a renewal thread that still contains only the reminder and has no completed application response after the grace period becomes an automatic denial candidate.

### CGC Checker

CGC Checker scans Certificate of Good Conduct threads, identifies expired certificates, updates the title, posts the expiration notice, and moves the thread to the CGC archive.

For example, a CGC thread whose `Valid To` date has passed can be marked `[EXPIRED]` and archived without manually checking every page.

## Saved Settings

The staff position, staff name, and optional signature image URL are saved in a local `settings.json` file beside the application. They are loaded automatically the next time the application starts.

This file contains only local application settings. Chrome login/session data remains in `bot_profile`.

## Project Structure

```text
LU Automation Engine/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── core/
├── modules/
├── ui/
└── bot_profile/
```

The `bot_profile` directory is created automatically beside the executable and should not be committed to GitHub.

## Notes

- Do not run two copies of the application at the same time.
- Do not share the `bot_profile` directory because it may contain browser session data.
- Keep the application timing human-like to reduce invalid PHPBB form submissions.
- Always review the activity log and manually inspect failed or pending records.
