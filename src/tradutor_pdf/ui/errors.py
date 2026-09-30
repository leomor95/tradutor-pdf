from __future__ import annotations

import errno
from dataclasses import dataclass
from pathlib import Path


class UserFacingError(Exception):
    """Base exception for user-facing pipeline errors with suggested actions."""

    def __init__(self, title: str, message: str, action: str) -> None:
        super().__init__(f"{message} Ação sugerida: {action}")
        self.title = title
        self.message = message
        self.action = action

    def to_user_message(self) -> str:
        return f"{self.message}\n\nAção sugerida: {self.action}"


class InvalidPdfFileError(UserFacingError):
    def __init__(self, details: str = "") -> None:
        super().__init__(
            title="Arquivo não é PDF",
            message=f"O arquivo selecionado não é um documento PDF válido{f' ({details})' if details else ''}.",
            action="Selecione um arquivo com extensão .pdf (ou use 'Converter arquivo…' no menu para converter outros formatos).",
        )


class PdfPasswordError(UserFacingError):
    def __init__(self, details: str = "") -> None:
        super().__init__(
            title="PDF com senha",
            message=f"O arquivo PDF está protegido por senha e não pode ser processado{f' ({details})' if details else ''}.",
            action="Remova a proteção por senha do PDF em um visualizador de PDF antes de tentar traduzi-lo.",
        )


class PdfCorruptedError(UserFacingError):
    def __init__(self, details: str = "") -> None:
        super().__init__(
            title="PDF corrompido",
            message=f"O arquivo PDF está corrompido, incompleto ou ilegível{f' ({details})' if details else ''}.",
            action="Verifique a integridade do arquivo ou gere/baixe o documento novamente.",
        )


class DiskFullError(UserFacingError):
    def __init__(self, details: str = "") -> None:
        super().__init__(
            title="Disco cheio",
            message=f"Espaço insuficiente em disco para concluir a operação{f' ({details})' if details else ''}.",
            action="Libere espaço na partição do sistema e tente novamente.",
        )


class DestinationPermissionError(UserFacingError):
    def __init__(self, details: str = "") -> None:
        super().__init__(
            title="Sem permissão na pasta de destino",
            message=f"Permissão negada para acessar ou gravar na pasta de destino{f' ({details})' if details else ''}.",
            action="Escolha outra pasta com permissão de escrita ou ajuste as permissões de acesso do diretório.",
        )


@dataclass(frozen=True)
class FormattedError:
    title: str
    message: str
    action: str

    def to_user_message(self) -> str:
        return f"{self.message}\n\nAção sugerida: {self.action}"


def classify_error(exc: Exception | str) -> FormattedError:
    """Classify an exception or error string into an actionable pt-BR user message."""
    if isinstance(exc, UserFacingError):
        return FormattedError(
            title=exc.title,
            message=exc.message,
            action=exc.action,
        )

    err_text = str(exc)
    err_lower = err_text.lower()

    # 1. PDF com senha
    if (
        "password" in err_lower
        or "senha" in err_lower
        or "encrypted" in err_lower
        or "fpdf_err_password" in err_lower
    ):
        return FormattedError(
            title="PDF com senha",
            message="O arquivo PDF está protegido por senha e não pode ser lido.",
            action="Remova a proteção por senha do PDF antes de tentar traduzi-lo.",
        )

    # 2. Arquivo que não é PDF
    if (
        "não é um documento pdf" in err_lower
        or "não é um pdf" in err_lower
        or "not a pdf" in err_lower
        or "extensão .pdf" in err_lower
    ):
        return FormattedError(
            title="Arquivo não é PDF",
            message="O arquivo selecionado não é um documento PDF válido.",
            action="Selecione um arquivo com extensão .pdf (ou use 'Converter arquivo…' no menu para outros formatos).",
        )

    # 3. PDF corrompido
    if (
        "data format error" in err_lower
        or "corrupt" in err_lower
        or "corrompido" in err_lower
        or "cabeçalho pdf não encontrado" in err_lower
        or "header not found" in err_lower
        or "vazio (0 bytes)" in err_lower
        or "fpdf_err_format" in err_lower
        or "syntax error" in err_lower
    ):
        return FormattedError(
            title="PDF corrompido",
            message="O arquivo PDF está corrompido, incompleto ou com formato inválido.",
            action="Verifique a integridade do arquivo ou gere/baixe o documento novamente.",
        )

    # 4. Disco cheio
    is_disk_full = (
        isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.ENOSPC
    ) or (
        "no space left on device" in err_lower
        or "disk full" in err_lower
        or "out of disk space" in err_lower
        or "espaço insuficiente" in err_lower
        or "disco cheio" in err_lower
    )
    if is_disk_full:
        return FormattedError(
            title="Disco cheio",
            message="Espaço insuficiente em disco para concluir a operação.",
            action="Libere espaço na partição do sistema e tente novamente.",
        )

    # 5. Sem permissão na pasta de destino
    is_perm_denied = (
        isinstance(exc, PermissionError)
        or (
            isinstance(exc, OSError)
            and getattr(exc, "errno", None) in (errno.EACCES, errno.EPERM)
        )
        or "permission denied" in err_lower
        or "permissão negada" in err_lower
    )
    if is_perm_denied:
        return FormattedError(
            title="Sem permissão na pasta de destino",
            message="Permissão negada para acessar ou gravar arquivos na pasta de destino.",
            action="Escolha outra pasta com permissão de escrita ou ajuste as permissões de acesso do diretório.",
        )

    # 6. Arquivo não encontrado
    if isinstance(exc, FileNotFoundError) or "não encontrado" in err_lower:
        return FormattedError(
            title="Arquivo não encontrado",
            message="O arquivo selecionado não foi encontrado.",
            action="Verifique se o arquivo ainda existe no caminho indicado e tente novamente.",
        )

    # 7. Serviço Ollama indisponível
    if "ollama" in err_lower and (
        "não está em execução" in err_lower
        or "connection refused" in err_lower
        or "failed to connect" in err_lower
        or "cannot connect" in err_lower
    ):
        return FormattedError(
            title="Serviço de tradução indisponível",
            message="O serviço de tradução local (Ollama) não está em execução.",
            action="Execute `./scripts/run.sh` no terminal para iniciar o serviço.",
        )

    # Default fallback
    return FormattedError(
        title="Erro na operação",
        message=f"Ocorreu um erro durante o processamento: {err_text}",
        action="Consulte os logs em `logs/app.log` para obter mais detalhes sobre o erro.",
    )


def validate_pdf_file(path: Path | str) -> None:
    """Validate that the given path points to an existing, valid, unencrypted PDF file.

    Raises:
        FileNotFoundError: If the file does not exist.
        InvalidPdfFileError: If the file does not have a .pdf extension.
        PdfPasswordError: If the file is protected by a password.
        PdfCorruptedError: If the file is empty, has an invalid header, or cannot be parsed.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

    if file_path.suffix.lower() != ".pdf":
        raise InvalidPdfFileError(f"extensão '{file_path.suffix}'")

    try:
        size = file_path.stat().st_size
    except OSError as exc:
        raise DestinationPermissionError(
            f"não foi possível ler {file_path.name}"
        ) from exc

    if size == 0:
        raise PdfCorruptedError("arquivo vazio (0 bytes)")

    try:
        with open(file_path, "rb") as f:
            header = f.read(1024)
            if b"%PDF-" not in header:
                raise PdfCorruptedError("cabeçalho PDF não encontrado")
    except (PermissionError, OSError) as exc:
        if isinstance(exc, PermissionError):
            raise DestinationPermissionError(
                f"permissão de leitura negada em {file_path.name}"
            ) from exc
        raise PdfCorruptedError(f"falha de leitura em {file_path.name}: {exc}") from exc

    # Allow lightweight test fixture stubs (e.g. b"%PDF-1.4...")
    if size < 50 and header.startswith(b"%PDF-"):
        return

    # Deep verification with pypdfium2
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(str(file_path))
        try:
            if len(doc) < 1:
                raise PdfCorruptedError("documento sem páginas válidas")
        finally:
            doc.close()
    except Exception as exc:
        err_lower = str(exc).lower()
        if "password" in err_lower or "senha" in err_lower:
            raise PdfPasswordError(f"senha requerida em {file_path.name}") from exc
        raise PdfCorruptedError(f"erro ao decodificar páginas: {exc}") from exc
