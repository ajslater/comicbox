"""Access PDFS with a ZipFile-like API."""
import math
from logging import getLogger
from pathlib import Path
from zipfile import ZipInfo

try:
    from filetype import guess

    FILETYPE_IMPORTED = True
except ImportError:
    FILETYPE_IMPORTED = False

try:
    from fitz_new import fitz

    FITZ_IMPORTED = True
except ImportError:
    FITZ_IMPORTED = False

LOG = getLogger(__name__)


class FitzNotFoundError(Exception):
    """PyMuPDF not found."""


class PDFFile:
    """ZipFile like API to PDFs."""

    MIME_TYPE = "application/pdf"
    SUFFIX = ".pdf"
    _TMP_SUFFIX = ".comicbox_tmp_pdf"
    _DEFAULT_PAGE_COUNT = 100
    _METADATA_COPY_KEYS = ("format", "encryption", "creationDate", "modDate", "trapped")

    @classmethod
    def check_import(cls):
        """Check if fitz imported."""
        if not FITZ_IMPORTED:
            reason = (
                "Unsupported archive type:"
                " comicbox[pdf] extra dependencies not installed."
            )
            raise FitzNotFoundError(reason)

    @classmethod
    def is_pdffile(cls, path):
        """Is the path a pdf."""
        if Path(path).suffix.lower() == cls.SUFFIX:
            return True
        if not FILETYPE_IMPORTED:
            return False
        kind = guess(path)
        return kind and kind.mime == cls.MIME_TYPE

    def __init__(self, path):
        """Initialize document."""
        self.check_import()
        self._path = path
        self._doc = fitz.Document(self._path)

    def __enter__(self):
        """Context enter."""
        return self

    def __exit__(self, *_args):
        """Context close."""
        self.close()

    def namelist(self):
        """Return sortable zero padded index strings."""
        page_count = self.get_page_count()
        zero_pad = math.floor(math.log10(page_count)) + 1
        return [f"{i:0{zero_pad}}" for i in range(page_count)]

    def infolist(self):
        """Return ZipFile like infolist."""
        infos = []
        for index in self.namelist():
            info = ZipInfo(index)
            infos.append(info)
        return infos

    def read(self, filename, to_pixmap=False):
        """Return a single page pdf doc or pixmap."""
        index = int(filename)

        if to_pixmap:
            pix = self._doc.get_page_pixmap(index)  # type: ignore
            page_bytes = pix.tobytes(output="ppm")
        else:
            page_bytes = self._doc.convert_to_pdf(index, index)
        return page_bytes

    def close(self):
        """Close the fitz doc."""
        if self._doc:
            self._doc.close()

    def get_page_count(self):
        """Get the page count from the doc or the default highnum."""
        try:
            page_count = self._doc.page_count
        except Exception as exc:
            LOG.warning(f"Error reading page count for {self._path}: {exc}")
            page_count = self._DEFAULT_PAGE_COUNT
        return page_count

    def get_metadata(self):
        """Return metadata from the pdf doc."""
        md = self._doc.metadata
        if not md:
            md = {}
        return md

    def _get_preserved_metadata(self):
        """Get preserved metadata."""
        old_metadata = {}
        if self._doc.metadata:
            for key in self._METADATA_COPY_KEYS:
                if value := self._doc.metadata.get(key):
                    old_metadata[key] = value
        return old_metadata

    def save_metadata(self, metadata):
        """Set metadata to the pdf doc."""
        preserved_metadata = self._get_preserved_metadata()
        new_metadata = {
            **preserved_metadata,
            **metadata,
        }
        self._doc.set_metadata(new_metadata)  # type: ignore

        tmp_path = self._path.with_suffix(self._TMP_SUFFIX)
        self._doc.save(
            tmp_path,
            garbage=4,
            deflate=True,
            deflate_images=False,
            deflate_fonts=True,
            encryption=fitz.PDF_ENCRYPT_KEEP,  # type: ignore
            linear=True,
            pretty=True,
            no_new_id=True,
        )
        tmp_path.replace(self._path)
