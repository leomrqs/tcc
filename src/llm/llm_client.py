"""
Cliente para o LLM via Ollama.

Encapsula a comunicação HTTP com o servidor Ollama local,
oferecendo métodos para enviar prompts e parsear respostas.

O Ollama serve modelos GGUF localmente via API REST em
http://localhost:11434 por padrão.

Uso:
    client = OllamaClient(model="hf.co/fdtn-ai/Foundation-Sec-8B-Instruct")
    response = client.generate(prompt="...", system="...")
"""

import json
import os
import re
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from src.utils.logger import get_logger

load_dotenv(Path(__file__).parent.parent.parent / ".env")

logger = get_logger(__name__)

# Endereço padrão do Ollama
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Modelo padrão. Pode ser sobrescrito via .env ou parâmetro.
# Se ainda não houver build oficial Foundation-Sec-8B-Instruct no Ollama Hub,
# vocês podem usar um modelo de cibersegurança disponível ou converter o GGUF.
DEFAULT_MODEL = os.environ.get(
    "OLLAMA_MODEL",
    "hf.co/fdtn-ai/Foundation-Sec-8B-Instruct",
)

# Timeout generoso para inferência local (8B model pode levar dezenas de segundos)
DEFAULT_TIMEOUT = 180


class OllamaClient:
    """Cliente HTTP para o servidor Ollama local."""

    def __init__(
        self,
        host: str = None,
        model: str = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.host = host or DEFAULT_OLLAMA_HOST
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout
        logger.info(f"OllamaClient configurado: {self.host}, modelo: {self.model}")

    def health_check(self) -> bool:
        """Verifica se o servidor Ollama está respondendo."""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            r.raise_for_status()
            return True
        except (requests.RequestException, requests.Timeout):
            return False

    def list_models(self) -> list[str]:
        """Lista modelos disponíveis no servidor Ollama."""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            r.raise_for_status()
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        except requests.RequestException as e:
            logger.error(f"Erro ao listar modelos: {e}")
            return []

    def model_available(self) -> bool:
        """Verifica se o modelo configurado está disponível."""
        models = self.list_models()
        # Comparação flexível (Ollama adiciona ':latest' às vezes)
        return any(self.model in m or m in self.model for m in models)

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        structured_output: bool = True,
    ) -> str:
        """
        Envia um prompt ao modelo via /api/chat (aplica template Llama 3
        corretamente, garantindo que o system prompt seja respeitado).

        Args:
            structured_output: se True (default) força JSON Schema da triagem.
                Se False, retorna texto livre (usado pelo Stage 1 binário).
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 8192,
            },
        }

        if structured_output:
            payload["format"] = {
                "type": "object",
                "properties": {
                    "attack_type": {
                        "type": "string",
                        "enum": [
                            "Benign", "DoS", "DDoS", "Brute Force", "Botnet",
                            "Reconnaissance", "Web Attack", "Exploits", "Fuzzers",
                            "Backdoor", "Generic", "Analysis", "Shellcode",
                            "Worms", "Infiltration",
                        ],
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["informational", "low", "medium", "high", "critical"],
                    },
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "mitre_techniques": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "explanation": {"type": "string", "minLength": 20},
                    "recommendations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["attack_type", "severity", "confidence", "mitre_techniques", "explanation", "recommendations"],
            }

        try:
            r = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            response = data.get("message", {}).get("content", "")

            duration = data.get("total_duration", 0) / 1e9
            tokens = data.get("eval_count", 0)
            if tokens > 0:
                logger.debug(
                    f"  Geração: {tokens} tokens em {duration:.1f}s "
                    f"({tokens / duration:.1f} tok/s)"
                )

            return response

        except requests.Timeout:
            raise RuntimeError(
                f"Timeout após {self.timeout}s. "
                f"O modelo pode estar muito lento ou travado."
            )
        except requests.RequestException as e:
            raise RuntimeError(f"Erro na requisição ao Ollama: {e}")


def parse_json_response(response: str) -> Optional[dict]:
    """
    Extrai o primeiro objeto JSON válido de uma resposta do LLM.

    LLMs às vezes incluem texto explicativo antes/depois do JSON.
    Esta função busca o primeiro {...} válido e tenta parseá-lo.

    Returns:
        Dict com o JSON parseado, ou None se não conseguir.
    """
    if not response:
        return None

    # Tentar parsear a resposta inteira primeiro (caso o modelo seja bem comportado)
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass

    # Buscar o primeiro bloco {...} balanceado
    match = _find_json_block(response)
    if match:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            # Tentar limpar problemas comuns (vírgulas trailing, aspas simples)
            cleaned = _clean_json(match)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

    return None


def _find_json_block(text: str) -> Optional[str]:
    """Encontra o primeiro bloco JSON balanceado no texto."""
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


def _clean_json(s: str) -> str:
    """Limpa erros comuns de JSON gerado por LLMs."""
    # Remover vírgulas trailing antes de } ou ]
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s