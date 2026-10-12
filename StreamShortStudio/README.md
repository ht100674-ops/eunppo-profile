# StreamShort Studio — Windows Portable 자동 빌드 프로젝트

**이 ZIP은 Windows 배포를 자동으로 만드는 수정 프로젝트입니다. 아직 EXE를 생성한 Portable ZIP 자체는 아닙니다.**
현재 환경은 Linux이고, 연결된 Windows 러너 또는 GitHub 저장소 권한이 없어 Windows 빌드는 실행하지 않았습니다.
Windows EXE를 만든 뒤 사용자가 Python을 설치하거나 명령어를 입력할 필요가 없도록 기존 프로젝트의 배포 구성을 수정했습니다.

## 사용자가 받게 될 실행 방식

빌드 성공 시 생성되는 `StreamShortStudio-Windows-x64-Portable.zip`을 압축 해제한 뒤
`StreamShortStudio/StreamShortStudio.exe`를 더블클릭합니다.
Python 실행 환경, Qt 라이브러리, FFmpeg/FFprobe, 한글 폰트가 `_internal/`에 함께 들어갑니다.
외부 Python/pip/FFmpeg 설치, 인터넷 접속, 관리자 권한 요청은 없습니다.
원본 편집 UI와 컷/배치/자막/BGM/저장/미리보기/출력 기능은 유지합니다.

단일 EXE 대신 안정성과 Qt DLL 교체 가능성을 고려해 Portable 폴더+ZIP을 사용합니다.
EXE만 폴더 밖으로 옮기지 말고 전체 폴더를 유지하세요. 바탕화면에는 바로가기를 만드세요.
자세한 사용법은 `USER_GUIDE.md`에 있습니다.

## 개발 도구 설치 없이 Windows 배포 ZIP 받기 — GitHub 웹 UI

GitHub 계정과 본인이 관리할 저장소가 필요합니다. 프로그램 자체의 로그인 요구가 아닙니다.
이 프로젝트를 새 저장소에 올리면 **GitHub의 Windows 2022 러너**가 빌드합니다.
사용자 PC에 Python이나 빌드 도구를 설치하지 않습니다. 아래는 웹에서 클릭하는 절차입니다.

1. GitHub에서 새 저장소를 만듭니다. 공개/비공개는 본인이 선택합니다.
2. 이 ZIP을 압축 해제합니다.
3. 저장소의 **Add file → Upload files**를 누릅니다.
4. 압축을 푼 `StreamShortStudio` 폴더 **안의 파일과 하위 폴더들**을 올립니다.
   `.github/workflows/windows-portable.yml`이 저장소 루트 기준으로 있어야 합니다.
   `StreamShortStudio/.github/...`처럼 상위 폴더로 한 겹 감싸 올리면 Actions가 인식하지 않습니다.
5. **Commit changes**를 누릅니다. 업로드 push에 의해 자동 빌드가 시작됩니다.
6. **Actions → Build Windows Portable**을 엽니다. 필요하면 **Run workflow**로 재실행합니다.
7. 성공한 실행의 **Artifacts → StreamShortStudio-Windows-x64-Portable**을 다운로드합니다.
8. GitHub 아티팩트 ZIP 안의 `StreamShortStudio-Windows-x64-Portable.zip`도 압축 해제합니다.
9. 그 안의 `StreamShortStudio.exe`를 더블클릭합니다.

실패한 실행에서는 Portable ZIP을 올리지 않습니다. `Windows-build-test-reports`에서 진단 결과를 받습니다.
기본 Actions 권한은 `contents: read`입니다. 자동 공개 배포/Release 생성/결제/계정 변경은 하지 않습니다.
저장소에 Actions 사용 권한과 사용량 여유가 필요합니다. 유료 러너나 추가 과금 작업은 이 환경에서 실행하지 않았습니다.

## 자동 빌드가 하는 일

1. Windows 러너에 빌드용 Python 3.11.9와 고정된 PySide6/PyInstaller/pytest를 설치합니다.
2. 고정된 FFmpeg Windows x64 GPL 정적 빌드를 다운로드하고 SHA-256을 확인합니다.
3. FFmpeg의 libx264/AAC/subtitles/amix 등의 필수 기능과 nonfree 여부를 확인합니다.
4. 소스 자동 테스트를 실행합니다.
5. PyInstaller로 Python·Qt·FFmpeg가 포함된 독립 EXE 폴더를 만듭니다.
6. Python DLL, Qt Multimedia DLL/플러그인, Qt FFmpeg DLL, C++ runtime, 폰트와 미디어 도구를 검사합니다.
7. 실제 생성된 EXE를 **소스 폴더 밖에서 실행**합니다. PATH에는 Windows 시스템 경로만 남깁니다.
   PYTHONPATH/PYTHONHOME/QT_PLUGIN_PATH를 제거하여 설치된 개발 도구에 의존하지 않는지 검사합니다.
8. EXE 안의 self-test로 영상 생성/불러오기/IN·OUT/분할/삭제/순서 변경/저장·복원,
   한글 자막 픽셀 변화, 원음 음소거+BGM 신호, 세로 1080p 출력/전 구간 디코드, Qt 미리보기 프레임을 확인합니다.
9. self-test가 통과할 때만 실제 배포 ZIP과 SHA-256, 테스트 기록을 업로드합니다.

PATH 격리는 의미 있는 배포 검사지만, Python이 미설치된 실제 클린 PC 시험은 아닙니다.
러너 자체에는 빌드용 Python이 있으며 그 사실을 테스트 결과에 숨기지 않습니다.
클린 PC 검증은 아래 선택적 Sandbox 방법으로 수행할 수 있습니다.

## Windows 클린 환경 검증 구성

생성된 Portable 폴더의 `Validate-Clean-Windows.cmd`는 **개발 검증용**입니다.
Windows Sandbox가 이미 활성화된 지원 에디션에서만 실행 가능합니다. 일반 앱 실행에는 필요 없습니다.
Sandbox 네트워크를 끄고 앱 폴더를 읽기 전용으로 연결합니다.
Python/pip/FFmpeg를 Sandbox에 설치하지 않은 상태에서 EXE self-test를 실행하고
`SandboxResults/clean-windows-self-test.json`에 결과를 기록합니다.
현재 환경에서 이 검증은 실행하지 않았습니다. JSON의 `status: passed`를 실제로 확인하기 전까지 미검증입니다.
설치되지 않은 Windows Sandbox를 자동 설치하거나 관리자 권한을 요청하지 않습니다.

## Portable 데이터 저장

`portable.ini`를 동봉하면 EXE 옆 `Data/`에 캐시/자동 저장/최근 프로젝트/오류 로그를 둡니다.
그 폴더에 쓸 수 없으면 현재 사용자 AppData로 전환합니다. 관리자 권한은 요구하지 않습니다.
프로젝트에는 원본 경로와 편집 데이터만 저장합니다. 이동한 원본은 재연결해야 합니다.
설치된 FFmpeg가 있어도 frozen EXE는 동봉 파일만 사용합니다. 배포 파일이 누락되면 재압축 해제를 안내합니다.

## 빌드 대상과 미검증 사항

- Windows 10 **22H2** / Windows 11 **64비트** 대상. 선택한 FFmpeg 제공자의 최소 지원 목표에 맞춥니다.
- Windows 32비트/ARM64, 이전 Windows 10 버전은 이번 배포 목표가 아닙니다.
- 8GB/16GB 노트북, GPU 드라이버, 실제 Windows 기기에서의 성능/호환성은 미검증입니다.
- 코드 서명과 설치 마법사, 단일 EXE는 포함하지 않습니다.
- 현재 파일은 자동 빌드 프로젝트이며 Windows EXE가 들어 있지 않습니다.
- EXE를 생성했다고 주장하지 않습니다. 워크플로 자체의 Windows 실행도 이 환경에서 하지 않았습니다.
- `TEST_RESULTS.md`에 실제 실행한 검사와 아직 실행하지 않은 검사를 구분합니다.

## 개발자용 로컬 Windows 빌드

이 절차는 개발자용이며 일반 사용자에게 요구하지 않습니다.
빌드 PC에만 Python 3.11 x64가 필요합니다.

```powershell
.\build-windows.ps1 -Python python
```

도구 다운로드/검사/EXE 생성/실제 frozen self-test/ZIP 생성까지 자동으로 진행합니다.
사용자의 앱 실행에는 이 Python 설치가 필요 없습니다.
수동으로 FFmpeg를 공급할 경우 `-SkipFetch`를 사용할 수 있지만 공식 CI는 checksum이 고정된 다운로드를 사용합니다.

## 라이선스

앱 소스 MIT, Noto Sans KR OFL, Qt/PySide6 LGPL 및 모듈별 조건, 선택한 FFmpeg는 GPL입니다.
빌드가 제공자 아카이브의 고지/문서를 보존하고 Python 라이선스, Qt/GPL 라이선스, 배포 메타데이터를 포함합니다.
그것만으로 모든 대응 소스 제공 의무가 충족됐다는 주장은 하지 않습니다.
공개 재배포 시 **각 바이너리에 정확히 대응하는 소스/빌드 지침 및 추가 고지**를 함께 준비해야 합니다.
공개 Release 자동 게시를 하지 않는 이유도 이 공개 배포 준비를 분리하기 위해서입니다.
`THIRD_PARTY.md`를 확인하세요.
