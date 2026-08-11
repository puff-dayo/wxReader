APP_NAME = "wxReader"
APP_VERSION = "1.6.4"
SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".mobi", ".fb2", ".txt", ".zip", ".cbz", "7z"}
SUPPORTED_EXTENSIONS_STRING = ";".join("*" + ext for ext in SUPPORTED_EXTENSIONS)
SUPPORTED_WILDCARDS = f"Supported files ({SUPPORTED_EXTENSIONS_STRING})|{SUPPORTED_EXTENSIONS_STRING}|All files (*.*)|*.*"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
GITHUB_REPO_OWNER = "puff-dayo"
GITHUB_REPO_NAME = "wxReader"
