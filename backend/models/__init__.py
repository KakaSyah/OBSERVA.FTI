"""
backend/models/__init__.py

Mengimpor seluruh model agar semua entitas didaftarkan oleh model layer
sebelum runtime memuat blueprint, sekaligus memudahkan impor singkat dari
modul lain, mis. `from backend.models import User`.

Urutan impor mengikuti urutan dependency FK pada ERD Tahap 1 bagian 7.
"""

from backend.models.role import Role
from backend.models.user import User
from backend.models.study_program import StudyProgram
from backend.models.student import Student
from backend.models.lecturer import Lecturer
from backend.models.head_of_program import HeadOfProgram
from backend.models.cloudinary_file import CloudinaryFile
from backend.models.letter_template import LetterTemplate
from backend.models.system_setting import SystemSetting
from backend.models.observation_request import ObservationRequest
from backend.models.letter_number import LetterNumber
from backend.models.approval_log import ApprovalLog
from backend.models.email_log import EmailLog
from backend.models.activity_log import ActivityLog

__all__ = [
    "Role",
    "User",
    "StudyProgram",
    "Student",
    "Lecturer",
    "HeadOfProgram",
    "CloudinaryFile",
    "LetterTemplate",
    "SystemSetting",
    "ObservationRequest",
    "LetterNumber",
    "ApprovalLog",
    "EmailLog",
    "ActivityLog",
]
