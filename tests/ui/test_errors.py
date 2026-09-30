import errno
from pathlib import Path

import pytest
from fpdf import FPDF

from tradutor_pdf.ui.errors import (
    DestinationPermissionError,
    DiskFullError,
    InvalidPdfFileError,
    PdfCorruptedError,
    PdfPasswordError,
    classify_error,
    validate_pdf_file,
)


def test_classify_password_error():
    err1 = PdfPasswordError()
    res1 = classify_error(err1)
    assert res1.title == "PDF com senha"
    assert "senha" in res1.message.lower()
    assert "remova a proteção" in res1.action.lower()

    res2 = classify_error("Failed to load document (PDFium: Incorrect password error).")
    assert res2.title == "PDF com senha"
    assert "remova a proteção" in res2.action.lower()


def test_classify_corrupted_pdf_error():
    err1 = PdfCorruptedError()
    res1 = classify_error(err1)
    assert res1.title == "PDF corrompido"
    assert "integridade" in res1.action.lower()

    res2 = classify_error("PDFium: Data format error")
    assert res2.title == "PDF corrompido"
    assert "integridade" in res2.action.lower()


def test_classify_disk_full_error():
    err1 = DiskFullError()
    res1 = classify_error(err1)
    assert res1.title == "Disco cheio"
    assert "libere espaço" in res1.action.lower()

    os_err = OSError(errno.ENOSPC, "No space left on device")
    res2 = classify_error(os_err)
    assert res2.title == "Disco cheio"
    assert "libere espaço" in res2.action.lower()


def test_classify_permission_error():
    err1 = DestinationPermissionError()
    res1 = classify_error(err1)
    assert res1.title == "Sem permissão na pasta de destino"
    assert "permissão de escrita" in res1.action.lower()

    perm_err = PermissionError("Permission denied")
    res2 = classify_error(perm_err)
    assert res2.title == "Sem permissão na pasta de destino"
    assert "permissão de escrita" in res2.action.lower()


def test_classify_not_a_pdf_error():
    err1 = InvalidPdfFileError()
    res1 = classify_error(err1)
    assert res1.title == "Arquivo não é PDF"
    assert ".pdf" in res1.action.lower()

    res2 = classify_error("Arquivo não é um documento PDF válido")
    assert res2.title == "Arquivo não é PDF"
    assert ".pdf" in res2.action.lower()


def test_validate_pdf_not_found(tmp_path: Path):
    missing = tmp_path / "missing.pdf"
    with pytest.raises(FileNotFoundError):
        validate_pdf_file(missing)


def test_validate_pdf_wrong_extension(tmp_path: Path):
    txt_file = tmp_path / "doc.txt"
    txt_file.write_text("Hello", encoding="utf-8")
    with pytest.raises(InvalidPdfFileError):
        validate_pdf_file(txt_file)


def test_validate_pdf_empty_corrupted(tmp_path: Path):
    empty_file = tmp_path / "empty.pdf"
    empty_file.write_bytes(b"")
    with pytest.raises(PdfCorruptedError):
        validate_pdf_file(empty_file)


def test_validate_pdf_invalid_header(tmp_path: Path):
    junk_file = tmp_path / "junk.pdf"
    junk_file.write_bytes(b"This is just plain text masquerading as pdf.")
    with pytest.raises(PdfCorruptedError):
        validate_pdf_file(junk_file)


def test_validate_pdf_password_protected(tmp_path: Path):
    enc_file = tmp_path / "secret.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.cell(text="Top secret")
    pdf.set_encryption(owner_password="admin", user_password="pass")
    pdf.output(str(enc_file))

    with pytest.raises(PdfPasswordError):
        validate_pdf_file(enc_file)


def test_validate_pdf_valid(tmp_path: Path):
    valid_file = tmp_path / "valid.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.cell(text="Hello world")
    pdf.output(str(valid_file))

    # Should not raise any error
    validate_pdf_file(valid_file)
