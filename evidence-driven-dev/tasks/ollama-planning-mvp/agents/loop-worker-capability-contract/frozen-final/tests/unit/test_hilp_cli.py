import io
import json
from cpea.interfaces.cli.main import main
from tests.hilp_support import QUESTION, runtime_for


def test_noninteractive_pending_exit_four(tmp_path, monkeypatch, capsys):
    runtime = runtime_for(tmp_path)
    monkeypatch.setattr('sys.stdin', io.StringIO(''))
    assert main(['--request', QUESTION], runtime=runtime) == 4
    value = json.loads(capsys.readouterr().out)
    assert value['status'] == 'needs_confirmation' and value['sql'] is None
    assert not (tmp_path / 'terms_mapping.json').exists()
    runtime.close()


def test_interactive_confirmation_same_process(tmp_path, monkeypatch, capsys):
    runtime = runtime_for(tmp_path)
    class TTY(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.setattr('sys.stdin', TTY('1\n'))
    assert main(['--request', QUESTION], runtime=runtime) == 0
    output = capsys.readouterr().out
    assert 'confirmed_this_request' in output and 'term_mapping_reasoning' in output
    assert runtime.llm.calls == 1
    runtime.close()
