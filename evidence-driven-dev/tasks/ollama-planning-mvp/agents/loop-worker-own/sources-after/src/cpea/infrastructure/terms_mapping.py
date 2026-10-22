"""One-process JSON repository. Never hold this lock across LLM/user/DB work."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from threading import RLock

from cpea.application.ports.term_mappings import (
    MappingConflict, MappingScope, MappingSnapshot, MappingStoreError, TermMapping,
)


class JsonTermMappingRepository:
    def __init__(self, path: str | Path, scope: MappingScope):
        self.path = Path(path)
        self.scope = scope
        self.lock = RLock()

    def read(self) -> MappingSnapshot:
        with self.lock:
            try:
                if not self.path.exists():
                    return MappingSnapshot(scope=self.scope)
                data = self.path.read_bytes()
                if data.startswith(b'\xef\xbb\xbf'):
                    raise ValueError('BOM is not supported')
                snapshot = MappingSnapshot.model_validate(json.loads(data.decode('utf-8')))
                if snapshot.scope != self.scope:
                    raise ValueError('scope mismatch')
                return snapshot
            except (OSError, ValueError) as exc:
                raise MappingStoreError('terms_mapping_store_invalid') from exc

    def commit(self, proposals: list[TermMapping], *, used: list[TermMapping],
               replacements: dict[tuple[str, str], str]) -> list[TermMapping]:
        # Re-read -> validate authorizations -> merge -> one atomic replacement.
        with self.lock:
            snapshot = self.read()
            active = snapshot.active()
            conflicts = []
            for record in used:
                current = active.get(record.key)
                if current != record:
                    conflicts.append(record)
            for record in proposals:
                current = active.get(record.key)
                if current and current.column != record.column:
                    if replacements.get(record.key) != current.id:
                        conflicts.append(record)
                elif record.key in replacements and (not current or replacements[record.key] != current.id):
                    conflicts.append(record)
            if conflicts:
                raise MappingConflict(list({m.key: m for m in conflicts}.values()))
            result = []
            records = list(snapshot.mappings)
            changed = False
            for record in proposals:
                current = active.get(record.key)
                if current and current.column == record.column and current.view_contract_fingerprint == record.view_contract_fingerprint:
                    result.append(current)
                    continue
                if current:
                    records = [m.model_copy(update={'status': 'revoked'}) if m.id == current.id else m for m in records]
                records.append(record)
                active[record.key] = record
                result.append(record)
                changed = True
            if changed:
                payload = MappingSnapshot(scope=self.scope, revision=snapshot.revision + 1, mappings=records)
                self._write(payload)
            return result

    def _write(self, snapshot: MappingSnapshot):
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            newline = '\r\n' if self.path.exists() and b'\r\n' in self.path.read_bytes() else '\n'
            text = snapshot.model_dump_json(indent=2) + '\n'
            text = text.replace('\n', newline)
            descriptor, temporary = tempfile.mkstemp(prefix='.' + self.path.name + '-', dir=self.path.parent)
            with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except (OSError, ValueError) as exc:
            raise MappingStoreError('terms_mapping_save_failed') from exc
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
