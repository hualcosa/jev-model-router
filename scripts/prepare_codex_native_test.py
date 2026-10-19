#!/usr/bin/env python3
"""Prepare a disabled disposable Codex test package; never install or trust it."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from router_core.packaging import Bindings, build_codex_package


def _write(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(text)


def prepare(*, python, binary, key_file):
    """Only writes fresh private temporary paths; never reads credential bytes."""
    if subprocess.check_output([binary, "--version"], stderr=subprocess.DEVNULL, timeout=3).strip() != b"codex-cli 0.163.0":
        raise ValueError("unmeasured_runtime")
    # Import isolation matches the production worker; do not read an API key or
    # issue a provider request to validate this interpreter's dependency setup.
    check = subprocess.run([python, "-I", "-c",
        "import importlib.metadata,typesafe_sdk; assert importlib.metadata.version('typesafe-sdk')=='0.7.5'"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
    if check.returncode:
        raise ValueError("pinned_sdk_interpreter_required")
    root = Path(tempfile.mkdtemp(prefix="router-codex-native-handoff-"))
    project, private = root/"project", root/"private"
    project.mkdir(mode=0o700); private.mkdir(mode=0o700)
    config, profile, state = private/"config.json", private/"profile.json", private/"state"
    _write(config, json.dumps({"schema_version": 1, "mode": "disabled"}, indent=2)+"\n")
    bindings = Bindings(str(project), python, binary, str(config), str(state), str(profile), key_file)
    result = build_codex_package(root/"marketplace", bindings)
    selector = result["plugin"]+"@"+result["marketplace"]
    def command(*args):
        return shlex.join(("rtk", binary, *map(str, args)))
    commands = {
        "install_marketplace": command("plugin", "marketplace", "add", root/"marketplace", "--json"),
        "install_plugin": command("plugin", "add", selector, "--json")+" > "+shlex.quote(str(private/"install-result.json")),
        "list": command("plugin", "list", "--marketplace", result["marketplace"], "--json"),
        "open_native_review": command("-C", project),
        "remove_plugin": command("plugin", "remove", selector),
        "remove_marketplace": command("plugin", "marketplace", "remove", result["marketplace"]),
    }
    receipt = {**result, "handoff_root": str(root), "project": str(project), "config": str(config),
        "profile": str(profile), "state": str(state), "selector": selector,
        "commands": commands, "installed": False, "trust_granted": False,
        "provider_calls": 0, "credential_bytes_read": False,
        "notice": "Disposable test artifact, not a durable installation. No native configuration was changed."}
    _write(root/"HANDOFF.json", json.dumps(receipt, indent=2)+"\n")
    _write(root/"LEIA-ME.md", f'''# Etapa manual Codex: instalação/confiança, sem ativar roteamento

Este pacote é novo e está **desativado**. Nada foi instalado no Codex principal.
O interpretador e a pasta são temporários: isto não é uma instalação durável.
A chave não foi lida, copiada ou colocada em comandos. Código real não será
enviado ao Jev; nesta primeira etapa nem tarefas sintéticas são enviadas.

## Só execute os próximos comandos se quiser autorizar a instalação temporária

Eles alteram o Codex selecionado pelo seu ambiente, registrando este marketplace
e plugin. Os hooks/MCP serão registrados, mas o router permanece desativado.
Depois de validar confiança/execução, a intenção é removê-los pelo fluxo nativo.

```sh
{commands['install_marketplace']}
{commands['install_plugin']}
{commands['list']}
{commands['open_native_review']}
```

Na sessão aberta, aceite a pasta descartável se concordar. Abra `/hooks` e
revise **somente** os oito eventos do plugin `{selector}`: SessionStart,
UserPromptSubmit, PreToolUse, PostToolUse, SubagentStart, SubagentStop,
PostCompact, SessionEnd. Confie apenas nas definições esperadas. Não altere
permissões/sandbox, não escolha trust bypass e não conceda confiança aos outros
plugins. Se a interface não corresponder, pare e envie o que apareceu.

Não é necessário repetir testes de modelo agora. Ao terminar a revisão,
informe “instalado e hooks confiáveis”. O resultado da instalação, incluindo
`installedPath`, fica em `{private/'install-result.json'}`. A próxima etapa será
diagnóstico a partir da cópia instalada e teste sintético estritamente nesta
pasta. Perfil, modo ativo e prova de execução **ainda não existem**.

## Remover imediatamente, se desejar

```sh
{commands['remove_plugin']}
{commands['remove_marketplace']}
```

Verifique que o plugin/marketplace não aparecem mais na listagem nativa. Não
remova o interpretador, sua chave externa ou configuração de outros projetos.
As pastas privadas descartáveis são mantidas para diagnóstico, não apagadas.
''')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True)
    parser.add_argument("--runtime-binary", required=True)
    parser.add_argument("--key-file", required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare(python=args.python, binary=args.runtime_binary, key_file=args.key_file)
        print(json.dumps({"status": "prepared_not_installed", "instructions": result["handoff_root"]+"/LEIA-ME.md",
            "selector": result["selector"], "version": result["version"], "provider_calls": 0}))
        return 0
    except Exception:
        print('{"status":"error","reason_code":"native_handoff_unavailable"}')
        return 2


if __name__ == "__main__":
    sys.exit(main())
