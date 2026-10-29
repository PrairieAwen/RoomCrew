# -*- mode: python ; coding: utf-8 -*-
"""Windows 独立目录发行：用户运行 RoomCrew.exe，无需另装 Python。"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

project = Path(SPECPATH).parent
# 1、发行只排除仍用于制作的三维底稿；已废弃资源不保留为另一套运行路径。
ui_root = project / 'desktop/ui'
datas = [(str(path), str(Path('desktop/ui') / path.relative_to(ui_root).parent))
         for path in ui_root.rglob('*') if path.is_file()
         and path.parent != ui_root / 'studio/assets/scene-v2/source']
datas += [(str(project / '.cache/python-runtime'), 'python-runtime')]
datas += [(str(project / 'doc/assets/crew-avatar-example'), 'materials/crew-avatar-example')]
for package in ('deepagents', 'langchain', 'langchain_core', 'langchain_openai',
                'langgraph', 'langgraph_checkpoint', 'langgraph_checkpoint_sqlite',
                'langgraph_prebuilt', 'tiktoken', 'pywebview', 'apscheduler', 'tzdata', 'tzlocal'):
    datas += copy_metadata(package)
datas += collect_data_files('deepagents')
datas += collect_data_files('webview')
datas += collect_data_files('tzdata')
hidden = collect_submodules('langgraph') + collect_submodules('deepagents')
hidden += ['tiktoken_ext.openai_public', 'webview.platforms.edgechromium', 'aiosqlite']
hidden += collect_submodules('langchain_mcp_adapters')
hidden += collect_submodules('tzdata')

analysis = Analysis([str(project / 'packaging/desktop_entry.py')],
    pathex=[str(project / 'backend/src'), str(project / 'desktop/src')], binaries=[], datas=datas,
    hiddenimports=hidden, hookspath=[], runtime_hooks=[],
    excludes=['pytest', 'mypy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
              'webview.platforms.gtk', 'webview.platforms.qt', 'webview.platforms.cocoa',
              'webview.platforms.cef', 'IPython', 'jupyter', 'tkinter'],
    noarchive=False)
archive = PYZ(analysis.pure)
executable = EXE(archive, analysis.scripts, [], exclude_binaries=True,
    name='RoomCrew', debug=False, bootloader_ignore_signals=False, strip=False,
    upx=False, console=False, disable_windowed_traceback=True)
distribution = COLLECT(executable, analysis.binaries, analysis.datas,
    strip=False, upx=False, name='RoomCrew')
