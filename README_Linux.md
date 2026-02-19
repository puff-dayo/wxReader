Tested on platform: Linux-6.12.73+deb13-amd64-x86_64-with-glibc2.41

```
sudo apt install libvips42t64 python3-wxgtk4.0
uv venv --python /usr/bin/python3 --system-site-packages
cd src
../.venv/bin/python wxReader.py
```

OR to build:
(run inside repo root)
```
uv --project . run pyinstaller \
  --name wxReader \
  --distpath build \
  --workpath build/pyi-build \
  --specpath build/pyi-spec \
  --onedir \
  --icon "$(pwd)/src/icon.png" \
  --add-data "$(pwd)/src/icon.png:icon.png" \
  --add-data "$(pwd)/src/filters:filters" \
  --add-data "$(pwd)/src/locale:locale" \
  --exclude-module tkinter \
  --exclude-module pillow \
  --collect-submodules OpenGL \
  src/wxReader.py
  ```

