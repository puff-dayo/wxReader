# wxPython Wheel (Testing Only)

wxpython.org distribution is currently unavailable. This project uses a **local pre-built wheel** for testing.

## Setup

The wheel is located at `./wheels/wxpython-4.3.0a16064+246cff28-cp312-cp312-win_amd64.whl`.

### pyproject.toml
```toml
[tool.uv.sources]
wxpython = { path = "wheels/wxpython-4.3.0a16064+246cff28-cp312-cp312-win_amd64.whl" }