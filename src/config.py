"""Local defaults; private files stay outside the publishable project."""
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    project_root: Path
    private_dir: Path
    host: str
    model: str
    embedding_model: str

    @property
    def database_path(self):
        return self.private_dir / 'fitness.db'

    @property
    def cache_dir(self):
        return self.private_dir / 'index'


def load_settings(project_root=None):
    root = Path(project_root or Path(__file__).resolve().parents[1]).resolve()
    private = Path(os.environ.get('FITNESS_PRIVATE_DIR', root.parent / (root.name + '-private'))).resolve()
    if private == root or private.is_relative_to(root):
        raise ValueError('Keep private records outside the public repository.')
    host = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')
    parsed = urlparse(host)
    if parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'} or parsed.username or parsed.password or parsed.path not in {'', '/'}:
        raise ValueError('V1 requires a local loopback Ollama endpoint.')
    return Settings(root, private, host, os.environ.get('OLLAMA_MODEL', 'qwen3.5:4b-q4_K_M'),
                    os.environ.get('EMBEDDING_MODEL', 'nomic-embed-text:v1.5'))
