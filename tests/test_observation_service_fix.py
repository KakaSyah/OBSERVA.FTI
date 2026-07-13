import inspect
import builtins
import types
from types import SimpleNamespace

import pytest

from backend.services import observation_service
from backend.services import email_service
from backend.models.email_log import EmailLog


def test_single_definition_count():
    # Ensure there is only one definition for the key functions
    source = open(observation_service.__file__, 'r', encoding='utf-8').read()
    assert source.count('def approve_by_head_of_program') == 1, 'approve_by_head_of_program defined more than once'
    assert source.count('def reject_by_head_of_program') == 1, 'reject_by_head_of_program defined more than once'


class DummyCursor:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount


def test_upload_final_pdf_sends_email(monkeypatch):
    called = {}

    cloudinary_result = {
        'public_id': 'surat-resmi/observation-request-42',
        'secure_url': 'https://cloudinary.test/surat.pdf',
        'resource_type': 'raw',
    }

    def fake_record(cloudinary_payload, request_id):
        called['record_called'] = True
        assert cloudinary_payload == cloudinary_result
        assert request_id == 42
        return {'file_id': 'file-xyz', **cloudinary_result}

    monkeypatch.setattr(observation_service.cloudinary_service, 'record_official_letter_pdf', fake_record)
    monkeypatch.setattr(observation_service.cloudinary_service, 'fetch_uploaded_bytes', lambda secure_url, max_bytes: b'PDFBYTES')

    # fake db.execute to return cursor with rowcount 1
    def fake_execute(sql, params):
        called['execute'] = (sql, params)
        return DummyCursor(rowcount=1)

    monkeypatch.setattr(observation_service.db, 'execute', fake_execute)
    monkeypatch.setattr(observation_service.db, 'commit', lambda: None)
    monkeypatch.setattr(observation_service.db, 'rollback', lambda: None)

    # fake db.fetchone to return nomor_dokumen
    monkeypatch.setattr(observation_service.db, 'fetchone', lambda sql, params: {'nomor_dokumen': '0001/OBS'} )

    # capture insertions
    inserted = []
    monkeypatch.setattr(observation_service, '_insert_instance', lambda inst: inserted.append(inst) or 1)

    # spy email_service.notify_official_letter_issued
    def fake_notify(obs, pdf_bytes):
        called['notify_called'] = True
        assert getattr(obs.student.user, 'email') == 'applicant@example.com'
        assert pdf_bytes == b'PDFBYTES'
        return EmailLog(observation_request_id=obs.id, recipient_email=obs.student.user.email, subject='s', status=EmailLog.STATUS_SENT)

    monkeypatch.setattr(observation_service.email_service, 'notify_official_letter_issued', fake_notify)

    obs = SimpleNamespace(id=42, status_kaprodi='Disetujui', student=SimpleNamespace(user=SimpleNamespace(email='applicant@example.com')))

    result = observation_service.upload_final_pdf(obs, cloudinary_result)
    assert result['file_id'] == 'file-xyz'
    assert called.get('record_called')
    assert called.get('notify_called')
    # ensure an EmailLog instance was inserted
    assert any(isinstance(x, EmailLog) for x in inserted)


def test_upload_final_pdf_email_failure_does_not_fail(monkeypatch):
    # Make notify raise an exception and ensure upload still succeeds and failure is recorded
    cloudinary_result = {
        'public_id': 'surat-resmi/observation-request-99',
        'secure_url': 'https://cloudinary.test/surat.pdf',
        'resource_type': 'raw',
    }
    monkeypatch.setattr(observation_service.cloudinary_service, 'record_official_letter_pdf', lambda payload, request_id: {'file_id': 'file-abc', **payload})
    monkeypatch.setattr(observation_service.cloudinary_service, 'fetch_uploaded_bytes', lambda secure_url, max_bytes: b'PDF')
    monkeypatch.setattr(observation_service.db, 'execute', lambda sql, params: DummyCursor(rowcount=1))
    monkeypatch.setattr(observation_service.db, 'commit', lambda: None)
    monkeypatch.setattr(observation_service.db, 'rollback', lambda: None)
    monkeypatch.setattr(observation_service.db, 'fetchone', lambda sql, params: {'nomor_dokumen': '0002/OBS'})

    inserted = []
    monkeypatch.setattr(observation_service, '_insert_instance', lambda inst: inserted.append(inst) or 1)

    def raise_notify(obs, pdf_bytes):
        raise Exception('resend-down')

    monkeypatch.setattr(observation_service.email_service, 'notify_official_letter_issued', raise_notify)

    obs = SimpleNamespace(id=99, status_kaprodi='Disetujui', student=SimpleNamespace(user=SimpleNamespace(email='applicant2@example.com')))

    result = observation_service.upload_final_pdf(obs, cloudinary_result)
    assert result['file_id'] == 'file-abc'
    # even though notify raised, we should have created a failed EmailLog record
    assert any(isinstance(x, EmailLog) and x.status == EmailLog.STATUS_FAILED for x in inserted)


def test_record_official_letter_pdf_rejects_mismatched_public_id(monkeypatch):
    monkeypatch.setattr(observation_service.cloudinary_service, '_ensure_configured', lambda: None)

    def fake_resource(public_id, resource_type='raw'):
        return {'public_id': public_id, 'resource_type': resource_type}

    monkeypatch.setattr(observation_service.cloudinary_service.cloudinary, 'api', SimpleNamespace(resource=fake_resource), raising=False)

    def fake_insert(sql, params):
        raise AssertionError('DB insert should not be called for mismatched public_id')

    monkeypatch.setattr(observation_service.cloudinary_service.db, 'insert', fake_insert)

    with pytest.raises(observation_service.cloudinary_service.CloudinaryServiceError):
        observation_service.cloudinary_service.record_official_letter_pdf(
            {'public_id': 'surat-resmi/observation-request-7', 'secure_url': 'https://cloudinary.test/file', 'resource_type': 'raw'},
            8,
        )