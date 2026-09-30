from unittest.mock import patch

from tradutor_pdf import main


def test_main_execution() -> None:
    with (
        patch(
            "tradutor_pdf.translation.ollama_client.OllamaClient.detect_device",
            return_value="CUDA",
        ) as mock_detect,
    ):
        main()
        mock_detect.assert_called_once_with(log_result=True)
