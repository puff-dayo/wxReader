import abc
import io
import os

import fitz  # PyMuPDF
import pyzipper
import wx


class ContentProvider(abc.ABC):
    def __init__(self, path: str):
        self.path = path

    @abc.abstractmethod
    def close(self):
        pass

    @property
    @abc.abstractmethod
    def page_count(self) -> int:
        pass

    @property
    @abc.abstractmethod
    def is_reflowable(self) -> bool:
        pass

    @abc.abstractmethod
    def get_page_size(self, page_index: int) -> tuple[float, float]:
        pass

    @abc.abstractmethod
    def render_page_to_bitmap(self, page_index: int, zoom: float) -> wx.Bitmap:
        pass

    def get_toc(self) -> list:
        return []

    def get_links(self, page_index: int) -> list:
        return []

    def get_page_text(self, page_index: int) -> str:
        return ""

    def get_page_images(self, page_index: int) -> list[dict]:
        return []

    @property
    @abc.abstractmethod
    def is_valid(self) -> bool:
        pass


class PdfContentProvider(ContentProvider):
    def __init__(self, path: str):
        super().__init__(path)
        self.doc = fitz.open(path)

    @property
    def is_valid(self) -> bool:
        return self.doc and not self.doc.is_closed

    def close(self):
        if self.doc:
            self.doc.close()
        self.doc = None

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    @property
    def is_reflowable(self) -> bool:
        return self.doc.is_reflowable

    def get_page_size(self, page_index: int) -> tuple[float, float]:
        try:
            p_idx = max(0, min(page_index, self.page_count - 1))
            page = self.doc.load_page(p_idx)
            r = page.rect
            return r.width, r.height
        except Exception:
            return 595.0, 842.0  # Fallback A4

    def render_page_to_bitmap(self, page_index: int, zoom: float) -> wx.Bitmap:
        if not (0 <= page_index < self.page_count):
            return wx.Bitmap(1, 1)

        page = self.doc.load_page(page_index)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        img = wx.Image(pix.width, pix.height, pix.samples)
        return wx.Bitmap(img)

    def get_toc(self) -> list:
        return self.doc.get_toc(simple=True)

    def get_links(self, page_index: int) -> list:
        if 0 <= page_index < self.page_count:
            return self.doc.load_page(page_index).get_links()
        return []

    def get_page_text(self, page_index: int) -> str:
        if not self.is_valid or not (0 <= page_index < self.page_count):
            return ""
        return self.doc.load_page(page_index).get_text()

    def get_page_images(self, page_index: int) -> list[dict]:
        if not self.is_valid or not (0 <= page_index < self.page_count):
            return []

        found_images = []
        page = self.doc.load_page(page_index)

        if self.is_reflowable:
            blocks = page.get_text("dict").get("blocks", [])
            image_blocks = [b for b in blocks if b.get("type") == 1]
            for block in image_blocks:
                found_images.append({
                    "bytes": block.get("image", b''),
                    "ext": block.get("ext", "png"),
                    "width": block.get("width", 0),
                    "height": block.get("height", 0)
                })
        else:
            img_info_list = page.get_images(full=True)
            for img_info in img_info_list:
                xref = img_info[0]
                base_image = self.doc.extract_image(xref)
                if base_image:
                    found_images.append({
                        "bytes": base_image.get("image", b''),
                        "ext": base_image.get("ext", "png"),
                        "width": base_image.get("width", 0),
                        "height": base_image.get("height", 0)
                    })
        return found_images


class ArchiveContentProvider(ContentProvider):
    def __init__(self, path: str):
        super().__init__(path)
        # todo: handle encrypted files
        self.zip_file = pyzipper.ZipFile(self.path, 'r')

        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        self.image_list = sorted([
            f for f in self.zip_file.namelist()
            if not f.startswith('__MACOSX') and os.path.splitext(f)[1].lower() in image_extensions
        ])

        self._size_cache = {}

    @property
    def is_valid(self) -> bool:
        return self.zip_file is not None

    def close(self):
        if self.zip_file:
            self.zip_file.close()
        self.zip_file = None

    @property
    def page_count(self) -> int:
        return len(self.image_list)

    @property
    def is_reflowable(self) -> bool:
        return False

    def get_page_size(self, page_index: int) -> tuple[float, float]:
        if page_index in self._size_cache:
            return self._size_cache[page_index]

        if not (0 <= page_index < self.page_count):
            return (1, 1)

        image_name = self.image_list[page_index]
        image_data = self.zip_file.read(image_name)
        stream = io.BytesIO(image_data)

        img = wx.Image(stream)
        if not img.IsOk():
            return (1, 1)

        size = (img.GetWidth(), img.GetHeight())
        self._size_cache[page_index] = size
        return size

    def get_page_images(self, page_index: int) -> list[dict]:
        if not self.is_valid or not (0 <= page_index < self.page_count):
            return []

        try:
            image_name = self.image_list[page_index]
            image_data = self.zip_file.read(image_name)

            stream = io.BytesIO(image_data)
            img = wx.Image(stream)

            return [{
                "bytes": image_data,
                "ext": os.path.splitext(image_name)[1].lstrip('.'),
                "width": img.GetWidth() if img.IsOk() else 0,
                "height": img.GetHeight() if img.IsOk() else 0
            }]
        except Exception:
            return []

    def render_page_to_bitmap(self, page_index: int, zoom: float) -> wx.Bitmap:
        if not (0 <= page_index < self.page_count):
            return wx.Bitmap(1, 1)

        image_name = self.image_list[page_index]
        image_data = self.zip_file.read(image_name)
        stream = io.BytesIO(image_data)

        img = wx.Image(stream)
        if not img.IsOk():
            return wx.Bitmap(100, 100)

        w, h = img.GetWidth(), img.GetHeight()
        new_w, new_h = int(w * zoom), int(h * zoom)

        if new_w > 0 and new_h > 0:
            img.Rescale(new_w, new_h, wx.IMAGE_QUALITY_HIGH)

        return wx.Bitmap(img)
