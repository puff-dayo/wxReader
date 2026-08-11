import abc
import io
import os
import posixpath
import threading

import re

import fitz  # PyMuPDF
import pyvips
import pyzipper
import wx

import py7zr

import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import unquote

from wxReaderString import IMAGE_EXTENSIONS


def _natural_sort_key(s: str):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]


class ContentProvider(abc.ABC):
    def __init__(self, path: str):
        self.path = path
        self.high_quality_render = 0

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

    @abc.abstractmethod
    def render_to_data(self, page_index: int, zoom: float) -> tuple[int, int, bytes] | None:
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

    def set_render_quality(self, high_quality: int):
        self.high_quality_render = high_quality

    def set_memory_profile(self, profile: dict):
        pass


class PdfContentProvider(ContentProvider):
    def __init__(self, path: str):
        super().__init__(path)
        self.doc = fitz.open(path)
        self.render_lock = threading.Lock()

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

    def render_to_data(self, page_index: int, zoom: float) -> tuple[int, int, bytes] | None:
        if not self.is_valid or not (0 <= page_index < self.page_count):
            return None

        with self.render_lock:
            try:
                page = self.doc.load_page(page_index)
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)

                return pix.width, pix.height, bytes(pix.samples)
            except Exception as e:
                print(f"[ERROR] wxReader render error: {e}")
                return None

    def get_toc(self) -> list:
        if not self.is_valid:
            return []

        existing_toc = self.doc.get_toc(simple=True)

        if existing_toc:
            return existing_toc

        fake_toc = []
        total_pages = self.page_count

        step = 10 if total_pages > 500 else 1

        for i in range(0, total_pages, step):
            page_num = i + 1

            entry = [1, f"Page {page_num}", page_num]
            fake_toc.append(entry)

        return fake_toc

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

    def get_thumbnail(self, thumb_width: int, thumb_height: int) -> tuple[int, int, bytes] | None:
        if not self.is_valid or self.page_count == 0:
            return None

        try:
            page = self.doc.load_page(0)
            rect = page.rect
            scale = min(thumb_width / rect.width, thumb_height / rect.height)
            mat = fitz.Matrix(scale, scale)

            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)

            if pix.n == 3:  # RGB
                return pix.width, pix.height, bytes(pix.samples)

        except Exception as e:
            print(f"[ERROR] wxReader failed to get thumbnail for {self.path}: {e}")

        return None


class ArchiveContentProvider(ContentProvider):
    _cached_passwords = None

    def __init__(self, path: str):
        super().__init__(path)

        self.zip_file = pyzipper.AESZipFile(self.path, 'r')
        try:
            all_files = self.zip_file.namelist()
        except Exception:
            all_files = []

        self.image_list = sorted([
            f for f in all_files
            if not f.startswith('__MACOSX') and os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
        ], key=_natural_sort_key)

        if self.image_list:
            test_file = self.image_list[0]
            try:
                self.zip_file.read(test_file)
            except (RuntimeError, pyzipper.BadZipFile):
                if ArchiveContentProvider._cached_passwords is None:
                    ArchiveContentProvider._cached_passwords = []
                    if os.path.exists('./pswd.txt'):
                        try:
                            with open('./pswd.txt', 'r', encoding='utf-8') as f:
                                for line in f:
                                    pwd = line.strip().encode('utf-8')
                                    if pwd:
                                        ArchiveContentProvider._cached_passwords.append(pwd)
                        except Exception as e:
                            print(f"[ERROR] failed to load password file: {e}")

                for pwd in ArchiveContentProvider._cached_passwords:
                    try:
                        self.zip_file.setpassword(pwd)
                        self.zip_file.read(test_file)
                        break
                    except (RuntimeError, pyzipper.BadZipFile):
                        continue

        self._size_cache = {}
        self._img_cache: dict[int, pyvips.Image] = {}
        self._img_cache_limit = 32

        self.high_quality_render = 0

    def get_toc(self) -> list:
        if not self.is_valid:
            return []
        toc = [[1, f.replace("\\", "/").split("/")[-1], i + 1] for i, f in enumerate(self.image_list)]
        return toc

    def _data_to_vips_image(self, data: bytes) -> pyvips.Image | None:
        try:
            image = pyvips.Image.new_from_buffer(data, "")

            if image.hasalpha():
                image = image.flatten(background=[255, 255, 255])

            if image.interpretation != 'srgb':
                image = image.colourspace('srgb')

            return image
        except pyvips.Error as e:
            print(f"[ERROR] pyvips decode failed: {e}")
            return None

    def render_to_data(self, page_index: int, zoom: float) -> tuple[int, int, bytes] | None:
        src_vips = self._load_original_image(page_index)
        if not src_vips:
            return None

        w, h = src_vips.width, src_vips.height
        target_w = max(1, int(round(w * zoom)))
        target_h = max(1, int(round(h * zoom)))

        if target_w == w and target_h == h:
            final_vips = src_vips
        else:
            if self.high_quality_render == 2:
                if zoom < 1.0:
                    blur_sigma = (1.0 / zoom) * 0.45
                    final_vips = src_vips.gaussblur(blur_sigma).resize(zoom, kernel='linear')
                else:
                    final_vips = src_vips.resize(zoom, kernel='lanczos3')
            elif self.high_quality_render == 1:
                final_vips = src_vips.resize(zoom, kernel='lanczos3')
            else:
                final_vips = src_vips.resize(zoom, kernel='linear')

        try:
            memory_buffer = final_vips.write_to_memory()
            return final_vips.width, final_vips.height, memory_buffer
        except Exception as e:
            print(f"pyvips render error: {e}")
            return None

    def _load_original_image(self, page_index: int) -> pyvips.Image | None:
        if page_index in self._img_cache:
            return self._img_cache[page_index]

        if not (0 <= page_index < self.page_count):
            return None

        image_name = self.image_list[page_index]
        try:
            image_data = self.zip_file.read(image_name)
            img = self._data_to_vips_image(image_data)

            if img is None:
                return None

            if len(self._img_cache) >= self._img_cache_limit:
                first_key = next(iter(self._img_cache.keys()))
                del self._img_cache[first_key]

            self._img_cache[page_index] = img
            return img
        except Exception as e:
            print(f"[ERROR] Failed to load image {image_name}: {e}")
            return None

    @property
    def is_valid(self) -> bool:
        return self.zip_file is not None

    def set_memory_profile(self, profile: dict):
        self._img_cache_limit = int(profile.get("source_image_cache_pages", 32))

        while len(self._img_cache) > self._img_cache_limit:
            first_key = next(iter(self._img_cache.keys()))
            del self._img_cache[first_key]

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
            with pyvips.Image.new_from_buffer(image_data, "") as vips_img:
                size = (vips_img.width, vips_img.height)

            self._size_cache[page_index] = size
            return size
        except Exception as e:
            print(f"[ERROR] pyvips failed to get page size: {e}")
            return (1, 1)

    def get_page_images(self, page_index: int) -> list[dict]:
        if not self.is_valid or not (0 <= page_index < self.page_count):
            return []

        try:
            image_name = self.image_list[page_index]
            image_data = self.zip_file.read(image_name)

            width, height = 0, 0
            try:
                with pyvips.Image.new_from_buffer(image_data, "") as vips_img:
                    width, height = vips_img.width, vips_img.height
            except Exception as e:
                print(f"[ERROR] pyvips failed to read image data for metadata: {e}")

            return [{
                "bytes": image_data,
                "ext": os.path.splitext(image_name)[1].lstrip('.'),
                "width": width, "height": height
            }]
        except Exception as e:
            print(f"[ERROR] failed to read page: {e}")
            return []

    def render_page_to_bitmap(self, page_index: int, zoom: float) -> wx.Bitmap:
        src_vips = self._load_original_image(page_index)
        if not src_vips:
            return wx.Bitmap(1, 1)

        w, h = src_vips.width, src_vips.height
        target_w = max(1, int(round(w * zoom)))
        target_h = max(1, int(round(h * zoom)))

        if target_w == w and target_h == h:
            final_vips = src_vips
        else:
            if self.high_quality_render == 2:
                if zoom < 1.0:
                    blur_sigma = (1.0 / zoom) * 0.45
                    final_vips = src_vips.gaussblur(blur_sigma).resize(zoom, kernel='linear')
                    # print(f"[DEBUG] pyvips demoire trigger, sigma: {blur_sigma}")
                else:
                    final_vips = src_vips.resize(zoom, kernel='lanczos3')
            elif self.high_quality_render == 1:
                final_vips = src_vips.resize(zoom, kernel='lanczos3')
            else:  # high_quality_render == 0 or fallback
                final_vips = src_vips.resize(zoom, kernel='linear')

        try:
            memory_buffer = final_vips.write_to_memory()
            return wx.Bitmap.FromBuffer(final_vips.width, final_vips.height, memory_buffer)

        except Exception as e:
            print(f"pyvips conversion to wx.Bitmap error: {e}")
            return wx.Bitmap(1, 1)

    def get_thumbnail(self, thumb_width: int, thumb_height: int) -> tuple[int, int, bytes] | None:
        if not self.is_valid or self.page_count == 0:
            return None

        try:
            first_image_name = self.image_list[0]
            image_data = self.zip_file.read(first_image_name)

            vips_img = self._data_to_vips_image(image_data)
            if not vips_img:
                return None

            thumb = vips_img.thumbnail_image(thumb_width, height=thumb_height, crop='centre')

            return thumb.width, thumb.height, thumb.write_to_memory()

        except Exception as e:
            print(f"[ERROR] pyvips failed to get thumbnail for {self.path}: {e}")
            return None


class _EpubHtmlImageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.image_refs: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        local_name = tag.rsplit(":", 1)[-1].lower()
        attrs_dict = {
            str(key).lower(): value
            for key, value in attrs
            if key and value
        }

        if local_name == "img":
            src = attrs_dict.get("src")
        elif local_name == "image":
            src = attrs_dict.get("href") or attrs_dict.get("xlink:href")
        else:
            src = None

        if src:
            self.image_refs.append(src)


class EpubComicContentProvider(ArchiveContentProvider):
    _XHTML_MEDIA_TYPES = {
        "application/xhtml+xml",
        "text/html",
    }

    _MARKUP_EXTENSIONS = {
        ".xhtml",
        ".html",
        ".htm",
        ".xml",
        ".svg",
    }

    def __init__(self, path: str):
        ContentProvider.__init__(self, path)

        self.zip_file = None
        self.image_list: list[str] = []
        self._size_cache = {}
        self._img_cache: dict[int, pyvips.Image] = {}
        self._img_cache_limit = 32
        self.high_quality_render = 0

        try:
            self.zip_file = pyzipper.AESZipFile(self.path, "r")
            self._zip_names = set(self.zip_file.namelist())
            self.image_list = self._build_image_list()
        except Exception as e:
            print(f"[ERROR] failed to open EPUB comic {self.path}: {e}")
            if self.zip_file:
                try:
                    self.zip_file.close()
                except Exception:
                    print(Exception)
            self.zip_file = None
            self._zip_names = set()
            self.image_list = []

    @staticmethod
    def _local_name(tag: str) -> str:
        if "}" in tag:
            tag = tag.rsplit("}", 1)[-1]
        if ":" in tag:
            tag = tag.rsplit(":", 1)[-1]
        return tag.lower()

    @staticmethod
    def _clean_href(href: str) -> str:
        href = href.strip().replace("\\", "/")
        href = href.split("#", 1)[0]
        href = href.split("?", 1)[0]
        return unquote(href)

    def _resolve_href(self, owner_path: str, href: str) -> str | None:
        href = self._clean_href(href)
        if not href: return None

        lowered = href.lower()
        if lowered.startswith(("data:", "http://", "https://", "file://")):
            return None

        if href.startswith("/"):
            resolved = posixpath.normpath(href.lstrip("/"))
        else:
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(owner_path), href))

        if resolved == ".." or resolved.startswith("../"):
            return None

        return resolved

    def _read_xml(self, path: str) -> ET.Element:
        return ET.fromstring(self.zip_file.read(path))

    def _find_opf_path(self) -> str:
        container_root = self._read_xml("META-INF/container.xml")

        for element in container_root.iter():
            if self._local_name(element.tag) != "rootfile":
                continue

            full_path = element.attrib.get("full-path")
            if not full_path:
                continue

            full_path = self._clean_href(full_path).lstrip("/")
            if full_path in self._zip_names:
                return full_path

        raise ValueError("EPUB container does not contain a valid OPF")

    def _extract_image_refs(self, document_path: str) -> list[str]:
        data = self.zip_file.read(document_path)
        image_refs: list[str] = []
        try:
            root = ET.fromstring(data)
            for element in root.iter():
                local_name = self._local_name(element.tag)
                if local_name == "img":
                    src = element.attrib.get("src")
                elif local_name == "image":
                    src = (
                            element.attrib.get("href")
                            or element.attrib.get("{http://www.w3.org/1999/xlink}href")
                            or element.attrib.get("xlink:href")
                    )
                else:
                    src = None
                if src:
                    image_refs.append(src)
            return image_refs
        except ET.ParseError:
            parser = _EpubHtmlImageParser()
            parser.feed(data.decode("utf-8-sig", errors="replace"))
            return parser.image_refs

    def _build_image_list(self) -> list[str]:
        opf_path = self._find_opf_path()
        package_root = self._read_xml(opf_path)
        manifest: dict[str, tuple[str, str]] = {}
        spine = None

        for element in package_root.iter():
            local_name = self._local_name(element.tag)
            if local_name == "item":
                item_id = element.attrib.get("id")
                href = element.attrib.get("href")
                media_type = element.attrib.get("media-type", "")
                if not item_id or not href:
                    continue
                resolved = self._resolve_href(opf_path, href)
                if resolved:
                    manifest[item_id] = (
                        resolved,
                        media_type.lower(),
                    )
            elif local_name == "spine" and spine is None:
                spine = element

        if spine is None:
            raise ValueError("EPUB package does not contain a spine")

        image_list: list[str] = []

        for itemref in spine:
            if self._local_name(itemref.tag) != "itemref":
                continue
            idref = itemref.attrib.get("idref")
            if not idref or idref not in manifest:
                continue
            document_path, media_type = manifest[idref]
            if media_type.startswith("image/") and media_type != "image/svg+xml":
                if document_path in self._zip_names:
                    image_list.append(document_path)
                continue
            extension = posixpath.splitext(document_path)[1].lower()
            is_markup = (
                    media_type in self._XHTML_MEDIA_TYPES
                    or media_type == "image/svg+xml"
                    or extension in self._MARKUP_EXTENSIONS
            )
            if not is_markup or document_path not in self._zip_names:
                continue
            for image_ref in self._extract_image_refs(document_path):
                image_path = self._resolve_href(
                    document_path,
                    image_ref,
                )
                if not image_path:
                    continue
                if image_path not in self._zip_names:
                    print(f"[WARN] EPUB comic image not found: {image_ref} -> {image_path}")
                    continue
                if posixpath.splitext(image_path)[1].lower() not in IMAGE_EXTENSIONS:
                    continue
                image_list.append(image_path)
        if not image_list:
            raise ValueError("no comic page images found in EPUB spine")
        return image_list

    @property
    def is_valid(self) -> bool:
        return self.zip_file is not None and bool(self.image_list)


class SevenZipContentProvider(ContentProvider):
    _cached_passwords = None

    def __init__(self, path: str):
        super().__init__(path)

        self.sz_file = None
        self._password = None

        def _open_with_password(pwd: str | None):
            if pwd is None:
                return py7zr.SevenZipFile(self.path, mode='r')
            return py7zr.SevenZipFile(self.path, mode='r', password=pwd)

        try:
            self.sz_file = _open_with_password(None)
        except Exception as e:
            print(f"[ERROR] 7z open failed: {e}")
            self.sz_file = None

        all_files = []
        if self.sz_file:
            try:
                all_files = self.sz_file.getnames()
            except Exception as e:
                print(f"[ERROR] 7z getnames failed: {e}")
                all_files = []

        self.image_list = sorted([
            f for f in all_files
            if not f.startswith('__MACOSX') and os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
        ], key=_natural_sort_key)

        if self.sz_file and self.image_list:
            test_file = self.image_list[0]
            try:
                self._read_file(test_file)
            except Exception as e:
                print(f"[ERROR] 7z read test file failed: {e}")

                try:
                    self.sz_file.close()
                except Exception:
                    pass
                self.sz_file = None

                if SevenZipContentProvider._cached_passwords is None:
                    SevenZipContentProvider._cached_passwords = []
                    if os.path.exists('./pswd.txt'):
                        try:
                            with open('./pswd.txt', 'r', encoding='utf-8') as f:
                                for line in f:
                                    pwd = line.strip()
                                    if pwd:
                                        SevenZipContentProvider._cached_passwords.append(pwd)
                        except Exception as e:
                            print(f"[ERROR] failed to load password file: {e}")

                for pwd in SevenZipContentProvider._cached_passwords:
                    try:
                        self.sz_file = _open_with_password(pwd)
                        self._read_file(test_file)
                        self._password = pwd
                        break
                    except Exception as e:
                        print(f"[ERROR] 7z password failed ({pwd}): {e}")
                        try:
                            if self.sz_file:
                                self.sz_file.close()
                        except Exception:
                            pass
                        self.sz_file = None

        self._size_cache = {}
        self._img_cache: dict[int, pyvips.Image] = {}
        self._img_cache_limit = 32

        self.high_quality_render = 0

    def _read_file(self, name: str) -> bytes:
        if not self.sz_file:
            raise RuntimeError("7z not opened")

        if hasattr(self.sz_file, "read"):
            data_map = self.sz_file.read([name])
            v = data_map.get(name)
            if v is None:
                raise RuntimeError(f"missing entry: {name}")
            return v.read()

        import py7zr.io

        class _MemIO(py7zr.io.Py7zIO):
            def __init__(self):
                self.buf = io.BytesIO()
                self.length = 0
                self.lock = threading.Lock()

            def write(self, data):
                with self.lock:
                    self.buf.write(data)
                    self.length += len(data)

            def read(self, size=None):
                with self.lock:
                    return self.buf.getvalue() if size is None else self.buf.getvalue()[:size]

            def seek(self, offset, whence=0):
                with self.lock:
                    return self.buf.seek(offset, whence)

            def flush(self):
                return

            def size(self):
                return self.length

            def getvalue(self):
                with self.lock:
                    return self.buf.getvalue()

        class _MemFactory(py7zr.io.WriterFactory):
            def __init__(self):
                self.products = {}

            def create(self, filename: str):
                product = _MemIO()
                self.products[filename] = product
                return product

        try:
            if hasattr(self.sz_file, "reset"):
                self.sz_file.reset()
        except Exception:
            pass

        factory = _MemFactory()
        self.sz_file.extract(targets=[name], factory=factory)

        io_obj = factory.products.get(name)
        if not io_obj:
            raise RuntimeError(f"missing entry: {name}")

        return io_obj.getvalue()

    def get_toc(self) -> list:
        if not self.is_valid:
            return []
        toc = [[1, f.replace("\\", "/").split("/")[-1], i + 1] for i, f in enumerate(self.image_list)]
        return toc

    def _data_to_vips_image(self, data: bytes) -> pyvips.Image | None:
        try:
            image = pyvips.Image.new_from_buffer(data, "")

            if image.hasalpha():
                image = image.flatten(background=[255, 255, 255])

            if image.bands == 1:
                image = image.bandjoin([image, image])

            if image.interpretation != 'srgb':
                image = image.colourspace('srgb')

            if image.format != 'uchar':
                image = image.cast('uchar')

            return image
        except pyvips.Error as e:
            print(f"[ERROR] pyvips decode failed: {e}")
            return None

    def _load_original_image(self, page_index: int) -> pyvips.Image | None:
        if page_index in self._img_cache:
            return self._img_cache[page_index]

        if not (0 <= page_index < self.page_count):
            return None

        image_name = self.image_list[page_index]
        try:
            image_data = self._read_file(image_name)
            img = self._data_to_vips_image(image_data)

            if img is None:
                return None

            if len(self._img_cache) >= self._img_cache_limit:
                first_key = next(iter(self._img_cache.keys()))
                del self._img_cache[first_key]

            self._img_cache[page_index] = img
            return img
        except Exception as e:
            print(f"[ERROR] Failed to load image {image_name}: {e}")
            return None

    def render_to_data(self, page_index: int, zoom: float) -> tuple[int, int, bytes] | None:
        src_vips = self._load_original_image(page_index)
        if not src_vips:
            return None

        w, h = src_vips.width, src_vips.height
        target_w = max(1, int(round(w * zoom)))
        target_h = max(1, int(round(h * zoom)))

        if target_w == w and target_h == h:
            final_vips = src_vips
        else:
            if self.high_quality_render == 2:
                if zoom < 1.0:
                    blur_sigma = (1.0 / zoom) * 0.45
                    final_vips = src_vips.gaussblur(blur_sigma).resize(zoom, kernel='linear')
                else:
                    final_vips = src_vips.resize(zoom, kernel='lanczos3')
            elif self.high_quality_render == 1:
                final_vips = src_vips.resize(zoom, kernel='lanczos3')
            else:
                final_vips = src_vips.resize(zoom, kernel='linear')

        try:
            memory_buffer = final_vips.write_to_memory()
            return final_vips.width, final_vips.height, memory_buffer
        except Exception as e:
            print(f"pyvips render error: {e}")
            return None

    def render_page_to_bitmap(self, page_index: int, zoom: float) -> wx.Bitmap:
        src_vips = self._load_original_image(page_index)
        if not src_vips:
            return wx.Bitmap(1, 1)

        w, h = src_vips.width, src_vips.height
        target_w = max(1, int(round(w * zoom)))
        target_h = max(1, int(round(h * zoom)))

        if target_w == w and target_h == h:
            final_vips = src_vips
        else:
            if self.high_quality_render == 2:
                if zoom < 1.0:
                    blur_sigma = (1.0 / zoom) * 0.45
                    final_vips = src_vips.gaussblur(blur_sigma).resize(zoom, kernel='linear')
                else:
                    final_vips = src_vips.resize(zoom, kernel='lanczos3')
            elif self.high_quality_render == 1:
                final_vips = src_vips.resize(zoom, kernel='lanczos3')
            else:
                final_vips = src_vips.resize(zoom, kernel='linear')

        try:
            memory_buffer = final_vips.write_to_memory()
            return wx.Bitmap.FromBuffer(final_vips.width, final_vips.height, memory_buffer)
        except Exception as e:
            print(f"pyvips conversion to wx.Bitmap error: {e}")
            return wx.Bitmap(1, 1)

    @property
    def is_valid(self) -> bool:
        return self.sz_file is not None

    def set_memory_profile(self, profile: dict):
        self._img_cache_limit = int(profile.get("source_image_cache_pages", 32))

        while len(self._img_cache) > self._img_cache_limit:
            first_key = next(iter(self._img_cache.keys()))
            del self._img_cache[first_key]

    def close(self):
        self._img_cache.clear()
        self._size_cache.clear()
        if self.sz_file:
            try:
                self.sz_file.close()
            except Exception:
                pass
        self.sz_file = None

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
            image_data = self._read_file(image_name)
            with pyvips.Image.new_from_buffer(image_data, "") as vips_img:
                size = (vips_img.width, vips_img.height)

            self._size_cache[page_index] = size
            return size
        except Exception as e:
            print(f"[ERROR] pyvips failed to get page size: {e}")
            return (1, 1)

    def get_page_images(self, page_index: int) -> list[dict]:
        if not self.is_valid or not (0 <= page_index < self.page_count):
            return []

        try:
            image_name = self.image_list[page_index]
            image_data = self._read_file(image_name)

            width, height = 0, 0
            try:
                with pyvips.Image.new_from_buffer(image_data, "") as vips_img:
                    width, height = vips_img.width, vips_img.height
            except Exception as e:
                print(f"[ERROR] pyvips failed to read image data for metadata: {e}")

            return [{
                "bytes": image_data,
                "ext": os.path.splitext(image_name)[1].lstrip('.'),
                "width": width, "height": height
            }]
        except Exception as e:
            print(f"[ERROR] failed to read page: {e}")
            return []

    def get_thumbnail(self, thumb_width: int, thumb_height: int) -> tuple[int, int, bytes] | None:
        if not self.is_valid or self.page_count == 0:
            return None

        try:
            first_image_name = self.image_list[0]
            image_data = self._read_file(first_image_name)

            vips_img = self._data_to_vips_image(image_data)
            if not vips_img:
                return None

            thumb = vips_img.thumbnail_image(thumb_width, height=thumb_height, crop='centre')

            return thumb.width, thumb.height, thumb.write_to_memory()

        except Exception as e:
            print(f"[ERROR] pyvips failed to get thumbnail for {self.path}: {e}")
            return None
