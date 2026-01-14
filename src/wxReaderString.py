APP_NAME = "wxReader"
APP_VERSION = "1.3.6"
SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".mobi", ".fb2", ".txt", ".zip", ".cbz"}
SUPPORTED_EXTENSIONS_STRING = ";".join("*" + ext for ext in SUPPORTED_EXTENSIONS)
SUPPORTED_WILDCARDS = f"Supported files ({SUPPORTED_EXTENSIONS_STRING})|{SUPPORTED_EXTENSIONS_STRING}|All files (*.*)|*.*"
GITHUB_REPO_OWNER = "puff-dayo"
GITHUB_REPO_NAME = "wxReader"
