import abc
import io
import os

import fitz  # PyMuPDF
import pyzipper
import wx
from PIL import Image


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

    @abc.abstractmethod
    def get_thumbnail(self, thumb_width: int, thumb_height: int) -> bytes | None:
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

    def get_thumbnail(self, thumb_width: int, thumb_height: int) -> bytes | None:
        if not self.is_valid or self.page_count == 0:
            return None

        try:
            page = self.doc.load_page(0)
            rect = page.rect
            scale = min(thumb_width / rect.width, thumb_height / rect.height)
            mat = fitz.Matrix(scale, scale)

            pix = page.get_pixmap(matrix=mat, alpha=False)

            if pix.n == 3:  # RGB
                return bytes(pix.samples)
        except Exception as e:
            print(f"[ERROR] wxReader failed to get thumbnail for {self.path}: {e}")

        return None


class ArchiveContentProvider(ContentProvider):
    def __init__(self, path: str):
        super().__init__(path)

        self.zip_file = pyzipper.AESZipFile(self.path, 'r')

        try:
            all_files = self.zip_file.namelist()
        except Exception:
            all_files = []

        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        self.image_list = sorted([
            f for f in all_files
            if not f.startswith('__MACOSX') and os.path.splitext(f)[1].lower() in image_extensions
        ])

        if self.image_list:
            test_file = self.image_list[0]
            try:
                self.zip_file.read(test_file)
            except (RuntimeError, pyzipper.BadZipFile):
                if os.path.exists('./pswd.txt'):
                    try:
                        with open('./pswd.txt', 'r', encoding='utf-8') as f:
                            for line in f:
                                pwd = line.strip().encode('utf-8')
                                if not pwd:
                                    continue
                                try:
                                    self.zip_file.setpassword(pwd)
                                    self.zip_file.read(test_file)
                                    break
                                except (RuntimeError, pyzipper.BadZipFile):
                                    continue
                    except Exception as e:
                        print(f"[ERROR] pyzipper failed to process password file: {e}")

        self._size_cache = {}
        self._img_cache: dict[int, wx.Image] = {}
        self._img_cache_limit = 32

    def _data_to_wx_image(self, data: bytes) -> wx.Image | None:
        try:
            pil_img = Image.open(io.BytesIO(data))

            if pil_img.mode == 'P' and 'transparency' in pil_img.info:
                pil_img = pil_img.convert('RGBA')

            if pil_img.mode == 'RGBA':
                background = Image.new('RGB', pil_img.size, (255, 255, 255))
                background.paste(pil_img, mask=pil_img.split()[3])
                pil_img = background

            elif pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')

            width, height = pil_img.size

            img = wx.Image(width, height, pil_img.tobytes())
            return img

        except Exception as e:
            print(f"[ERROR] PIL transcode failed: {e}")
            return None

    def _load_original_image(self, page_index: int) -> wx.Image | None:
        if page_index in self._img_cache:
            return self._img_cache[page_index]

        if not (0 <= page_index < self.page_count):
            return None

        image_name = self.image_list[page_index]
        try:
            image_data = self.zip_file.read(image_name)

            img = self._data_to_wx_image(image_data)

            if img is None or not img.IsOk():
                return None

            if len(self._img_cache) >= self._img_cache_limit:
                first_key = next(iter(self._img_cache.keys()))
                del self._img_cache[first_key]

            self._img_cache[page_index] = img
            return img
        except Exception as e:
            print(f"[ERROR] wxReader Failed to load image {image_name}: {e}")
            return None

    @property
    def is_valid(self) -> bool:
        return self.zip_file is not None

    def close(self):
        self._img_cache.clear()
        self._size_cache.clear()
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

        try:
            image_name = self.image_list[page_index]
            image_data = self.zip_file.read(image_name)

            with Image.open(io.BytesIO(image_data)) as pil_img:
                size = pil_img.size

            self._size_cache[page_index] = size
            return size
        except Exception:
            return (1, 1)

    def get_page_images(self, page_index: int) -> list[dict]:
        if not self.is_valid or not (0 <= page_index < self.page_count):
            return []

        try:
            image_name = self.image_list[page_index]
            image_data = self.zip_file.read(image_name)

            width, height = 0, 0
            try:
                with Image.open(io.BytesIO(image_data)) as pil_img:
                    width, height = pil_img.size
            except Exception as e:
                print(f"[ERROR] failed to read image data: {e}")

            return [{
                "bytes": image_data,
                "ext": os.path.splitext(image_name)[1].lstrip('.'),
                "width": width,
                "height": height
            }]
        except Exception as e:
            print(f"[ERROR] failed to read page: {e}")
            return []

    def render_page_to_bitmap(self, page_index: int, zoom: float) -> wx.Bitmap:
        src = self._load_original_image(page_index)
        if not src:
            return wx.Bitmap(1, 1)

        w, h = src.GetWidth(), src.GetHeight()
        new_w = max(1, int(round(w * zoom)))
        new_h = max(1, int(round(h * zoom)))

        if new_w == w and new_h == h:
            img = src.Copy()
        else:
            img = src.Copy().Scale(new_w, new_h, wx.IMAGE_QUALITY_HIGH)

        return wx.Bitmap(img)

    def get_thumbnail(self, thumb_width: int, thumb_height: int) -> bytes | None:
        if not self.is_valid or self.page_count == 0:
            return None

        try:
            first_image_name = self.image_list[0]
            image_data = self.zip_file.read(first_image_name)

            img = self._data_to_wx_image(image_data)
            if not img or not img.IsOk():
                return None

            img.Rescale(thumb_width, thumb_height, wx.IMAGE_QUALITY_HIGH)

            return img.GetData()

        except Exception as e:
            print(f"[ERROR] wxReader failed to get thumbnail for {self.path}: {e}")

        return None
