from dataclasses import dataclass, field
from pathlib import Path
import yaml

@dataclass(frozen=True)
class DeploymentSettings:
    deployment_id: str = 'standalone'
    profile_path: Path | None = None
    datasource_id: str | None = None
    secret_references: dict[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, path: str | None = None, *, profile_path: str | None = None, datasource_id: str | None = None):
        raw = {}
        base = Path.cwd()
        if path is not None:
            configured = Path(path).resolve()
            base = configured.parent
            try:
                raw = yaml.safe_load(configured.read_text(encoding='utf-8'))
            except (OSError, yaml.YAMLError):
                raise ValueError('deployment configuration cannot be loaded') from None
            if not isinstance(raw, dict):
                raise ValueError('deployment configuration requires a mapping')
        selected = profile_path if profile_path is not None else raw.get('profile_path')
        datasource = datasource_id if datasource_id is not None else raw.get('datasource_id')
        if selected is not None and not isinstance(selected, str):
            raise ValueError('deployment profile_path must be a string')
        if datasource is not None and (not isinstance(datasource, str) or not datasource.strip()):
            raise ValueError('deployment datasource_id must be a nonempty string')
        references = raw.get('secret_references', {})
        if not isinstance(references, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in references.items()):
            raise ValueError('secret_references must map names to references')
        identifier = raw.get('deployment_id', 'standalone')
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError('deployment_id must be a nonempty string')
        return cls(identifier, (base / selected).resolve() if selected else None, datasource, references)
