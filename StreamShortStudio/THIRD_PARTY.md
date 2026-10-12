# 의존성과 배포

이 소스 ZIP에는 Windows FFmpeg/FFprobe, Python, Qt DLL을 포함하지 않습니다.
새로 작성한 앱 코드는 MIT입니다. 의존성에는 각자의 라이선스가 적용됩니다.

| 구성 | 적용 라이선스 / 확인 사항 |
|---|---|
| Python | PSF License, 배포한 버전의 고지 유지 |
| PySide6 / Shiboken / 사용한 Qt 모듈 | LGPLv3 / 해당 모듈별 고지. Qt의 추가 제3자 라이선스도 유지 |
| FFmpeg / FFprobe | 빌드 구성에 따라 LGPL 또는 GPL. libx264 사용 빌드는 GPL 의무 확인 |
| Noto Sans KR | SIL Open Font License 1.1. `fonts/OFL.txt` 포함 |
| PyInstaller | GPL 라이선스 + bootloader 배포 예외. 배포한 버전의 고지 확인 |
| pytest | MIT, 개발/테스트 전용 |

## Windows 배포를 만들 때

1. `ffmpeg.exe`, `ffprobe.exe`를 `bin`에 넣습니다. subtitles/libass, libx264, AAC가 필요합니다.
2. `--enable-nonfree`가 있는 빌드는 재배포 대상으로 사용하지 않습니다. doctor가 거부합니다.
3. 선택한 FFmpeg 빌드의 LICENSE/COPYING, 외부 라이브러리 고지, **정확한 바이너리에 대응하는 소스와 빌드 스크립트**를 확보하고 배포와 함께 제공해야 합니다. 최신 FFmpeg 소스 URL만 적는 것은 대응 소스 제공을 대신하지 않습니다. `ffmpeg-build-info.json`은 소스 제공 자체가 아닙니다.
4. 선택한 Qt/PySide6 버전의 라이선스 원문과 제3자 고지를 배포에 포함하고, 필요한 대응 소스 접근을 제공합니다. LGPL 조건에 따라 수정 라이브러리와 재결합할 수 있어야 합니다. 앱 소스와 빌드 스크립트도 함께 배포하고 Qt DLL을 교체 가능한 디렉터리 형태로 둡니다. LGPL이 허용하는 수정/디버깅을 배포 약관으로 제한하지 않습니다.
5. spec은 교체 가능한 DLL을 가진 **onedir** 빌드입니다. EXE 하나만 복사하면 작동하지 않습니다. 설치파일/코드 서명은 이번 버전에 포함하지 않습니다.
6. `licenses/`에 선정한 바이너리의 라이선스/고지를 추가한 후 빌드하세요. 정확한 배포 크기는 빌드 후 측정해야 합니다.

공식 참고:
- https://ffmpeg.org/legal.html
- https://ffmpeg.org/doxygen/trunk/md_LICENSE.html
- https://www.qt.io/development/open-source-lgpl-obligations
- https://www.qt.io/faq/qt-open-source-licensing
- https://pyinstaller.org/en/stable/license.html
- https://www.python.org/psf/license/

이 프로젝트는 라이선스 의무를 자동으로 모두 충족했다고 주장하지 않습니다.
Windows 의존성 바이너리를 선택해 공개 배포하는 단계에서 위 대응 소스와 고지를 함께 제공해야 합니다.

## Portable 자동 빌드 변경 사항

자동 빌드에는 `tools/ffmpeg-lock.json`에 고정한 BtbN GPL 정적 FFmpeg/FFprobe가 동봉됩니다.
SHA-256 검증 후 제공자 아카이브의 bin 외 고지/문서를 `licenses/ffmpeg-provider`에 보존합니다.
버전/원본 URL/해시/FFmpeg 소스 참조를 `ORIGIN.json` 및 `BUILD_INFO.json`에 기록합니다.
이 기록은 GPL 대응 소스 자체가 아닙니다. 정확히 같은 FFmpeg와 포함된 x264/libass 등 의존성 소스 및 빌드 자료는 공개 재배포 전에 별도로 제공해야 합니다.
CI는 다운로드 가능한 빌드 아티팩트를 만들며 자동 공개 Release 게시를 하지 않습니다.
Python LICENSE.txt와 wheel에 제공된 의존성 고지도 수집하고, LGPLv3/GPLv3/OFL 원문을 유지합니다.
Qt DLL/FFmpeg 도구는 교체 가능한 `_internal` 폴더에 둡니다.
PyInstaller가 동봉하는 Microsoft C/C++ 런타임 파일에도 해당 재배포 조건이 적용됩니다.
선택한 DLL의 공급자 고지와 재배포 조건은 공개 배포 감사에 포함해야 합니다.
