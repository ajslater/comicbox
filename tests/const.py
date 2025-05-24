"""Constants and paths for tests."""

from argparse import Namespace
from datetime import datetime
from pathlib import Path

from ruamel.yaml.timestamp import TimeStamp

from comicbox.version import PACKAGE_NAME, VERSION

# DIRS
TEST_FILES_DIR = Path("tests/files")
TEST_METADATA_DIR = TEST_FILES_DIR / "metadata"
TEST_EXPORT_DIR = TEST_FILES_DIR / "export"
TEST_CS_DIR = TEST_FILES_DIR / "Captain Science 001"
TMP_ROOT_DIR = Path("/tmp")  # noqa: S108
SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"

# SOURCE PATHS
EMPTY_FN = "empty.cbz"
EMPTY_CBZ_SOURCE_PATH = TEST_FILES_DIR / EMPTY_FN
CBI_CBR_FN = "Captain Science #001-cbi.cbr"
CBI_CBR_SOURCE_PATH = TEST_FILES_DIR / CBI_CBR_FN
CIX_CBI_CBR_FN = "Captain Science #001-cix-cbi.cbr"
CIX_CBI_CBR_SOURCE_PATH = TEST_FILES_DIR / CIX_CBI_CBR_FN
CIX_CBT_FN = "Captain Science #001-cix.cbt"
CIX_CBT_SOURCE_PATH = TEST_FILES_DIR / CIX_CBT_FN
CIX_CBZ_FN = "Captain Science #001-cix.cbz"
CIX_CBZ_SOURCE_PATH = TEST_FILES_DIR / CIX_CBZ_FN
CB7_FN = "Captain Science #001.cb7"
CB7_SOURCE_PATH = TEST_FILES_DIR / CB7_FN
METRON_CBZ_FN = "Captain Science #001-metron.cbz"
EXPORT_FN = "export.cbz"
EXPORT_SOURCE_PATH = TEST_FILES_DIR / EXPORT_FN
COVER_FN = "CaptainScience#1_01.jpg"
CBZ_MULTI_FN = "Captain Science #001 (1950) The Beginning - multi.cbz"
CBZ_MULTI_SOURCE_PATH = TEST_FILES_DIR / CBZ_MULTI_FN
PDF_FN = "test_pdf.pdf"
PDF_SOURCE_PATH = TEST_FILES_DIR / PDF_FN


# CONFIGS
READ_CONFIG_EMPTY = Namespace(comicbox=Namespace())

TEST_DTTM_STR = "1970-01-01T00:00:00Z"
_D_TUPLE = (1970, 1, 1)
TEST_DATETIME = datetime(*_D_TUPLE)  # noqa: DTZ001
_IDENT = 145269
TEST_READ_NOTES = (
    f"Tagged with {PACKAGE_NAME} {VERSION} on {TEST_DTTM_STR} "
    f"[Issue ID {_IDENT}] [CVDB{_IDENT}]"
)
TEST_WRITE_NOTES = (
    f"Tagged with {PACKAGE_NAME} {VERSION} on {TEST_DTTM_STR} "
    f"[Issue ID {_IDENT}] urn:comicvine:4000-145269"
)

TEST_TIMESTAMP = TimeStamp(*_D_TUPLE)
