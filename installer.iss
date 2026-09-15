; ============================================================
; 政务工单脱敏系统 - Inno Setup 安装包脚本
; 使用方法：用 Inno Setup 编译器打开本文件，编译生成 setup.exe
; 前置条件：已运行 build_exe.bat 完成 PyInstaller 打包
; ============================================================

#define MyAppName "政务工单脱敏系统"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "政务数据处理工具"
#define MyAppExeName "GovDataProcessor.exe"

[Setup]
AppId={{B7E3A9D2-4F1A-4E8C-9B2D-6A5F3C8E1D70}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\GovDataProcessor
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=政务工单脱敏系统_v{#MyAppVersion}_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}
AppCopyright=Copyright (C) 2026

; 注：当前 Inno Setup 未安装中文语言包，使用默认英文向导界面。
; 如需中文界面，将 ChineseSimplified.isl 放入 Inno Setup\Languages\ 目录后，
; 取消下方 [Languages] 段的注释即可。

;[Languages]
;Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: unchecked

[Files]
; 打包产物全部复制到安装目录
Source: "dist\GovDataProcessor\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
; 开始菜单
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载{#MyAppName}"; Filename: "{uninstallexe}"
; 桌面快捷方式（由任务控制，默认勾选）
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; 安装完成后可选启动程序
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动{#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载时清理用户数据目录（%APPDATA%\GovDataProcessor）
Type: filesandordirs; Name: "{userappdata}\GovDataProcessor"
