# Intelligent Agent Router — Engineering Handoff Package

**Version:** 1.0-spec | **Prepared:** 2026-10-17 | **Status:** implementation specification, NOT an implemented plugin

Este pacote contém a revisão de arquitetura e uma especificação executável para desenvolver um **router inteligente de modelos e reasoning effort em Claude Code e Codex**. É documentação para entregar ao Opus 5.5 dentro de um fork do `claude-model-router-hook`; não é o plugin instalado nem contém alterações no seu repositório.

## Ordem recomendada de leitura

1. [`docs/00_REVISED_PLAN.md`](docs/00_REVISED_PLAN.md) — decisões, fases, marcos e gates.
2. [`docs/01_PRODUCT_SPEC.md`](docs/01_PRODUCT_SPEC.md) — comportamentos, casos de uso e critérios de aceite.
3. [`docs/02_TECHNICAL_DESIGN.md`](docs/02_TECHNICAL_DESIGN.md) — arquitetura, contratos, máquina de estados, algoritmos e segurança.
4. [`docs/03_RUNTIME_ADAPTERS.md`](docs/03_RUNTIME_ADAPTERS.md) — integração nativa e limitações Claude Code/Codex.
5. [`docs/04_ROUTING_POLICY_AA.md`](docs/04_ROUTING_POLICY_AA.md) — matriz inicial de modelos/effort baseada na pesquisa anterior, com incertezas explicitadas.
6. [`docs/05_TASK_BACKLOG.md`](docs/05_TASK_BACKLOG.md) — tarefas concretas `RTE-001...`, dependências, evidências e testes.
7. [`tracking/tasks.csv`](tracking/tasks.csv) — backlog importável no GitHub Projects, Linear, Notion etc.
8. [`docs/06_TEST_EVAL_PLAN.md`](docs/06_TEST_EVAL_PLAN.md) — fixtures, smoke tests reais, métricas e critérios de rollout.
9. [`docs/07_ADRS_RISKS_SOURCES.md`](docs/07_ADRS_RISKS_SOURCES.md) — trade-offs, fontes oficiais, decisões e riscos.
10. [`HANDOFF_TO_OPUS.md`](HANDOFF_TO_OPUS.md) — prompt pronto para colar no Claude Code.
11. [`examples/routing.example.yaml`](examples/routing.example.yaml) — exemplo conceitual de configuração; NÃO é um schema implementado.

## Resultado desejado

- **Root/orchestrator:** continua com o modelo e effort já ativos na sessão; o router nunca troca automaticamente.
- **Novo task block:** verifica necessidade de classificação, recomenda upgrades ao root como **warning advisory** e suprime chamadas para continuidades.
- **Subagent novo:** Jev classifica apenas tarefas elegíveis sem override, e uma política versionada escolhe `model + effort` entre opções suportadas.
- **Dois adaptadores na primeira entrega:** Claude Code e Codex, ambos usando instalações oficiais e o mesmo core.
- **Sem inferência proxy por padrão**, sem fork de binários nem uso implícito de chaves de API dos modelos.

## Decisões confirmadas pelo usuário — 2026-10-19

- **Superfícies obrigatórias:** CLI e aplicativo desktop, para Claude Code e Codex em sessões locais de código. Compartilhar harness permite reutilizar implementação, mas cada superfície exige smoke de carregamento/trust, credenciais, aviso visível, modelo/effort efetivos e permissões. Extensões IDE, chat comum, cloud e execução remota não são implicitamente incluídos.
- **Delegação genérica:** o principal fornece a tarefa sem preencher modelo/effort; o router escolhe ambos quando suportados. Exigências explícitas do usuário e perfis customizados continuam protegidos. Qualquer pin já presente é respeitado, pois o hook não pode adivinhar sua origem.
- **Catálogo:** assumir disponibilidade dos modelos-alvo por instrução do usuário (`availability_source: user_assumption`), sem exigir descoberta prévia de entitlement. Ainda validar IDs/versões, campos suportados, efforts e execução real; não registrar disponibilidade presumida como verificada. Rejeição real do runtime é uma falha a tratar com segurança, não razão para trocar geração silenciosamente.
- **Sem mudanças globais agora:** atualizar documentação de delegação do produto; não editar automaticamente AGENTS.md global nem configurar hooks ativos. Root continua sempre sob controle do usuário.

## Versões-alvo explícitas — refinamento de 2026-10-19

**Fable 5.1, Luna 6, Terra 6, Sol 6.1 e Astra 6** são as versões desejadas para essas famílias. Nomes genéricos nos diagramas/configs são chaves de política, não IDs executáveis. A aplicação depende do catálogo real da conta e da superfície; não substituir silenciosamente por outra versão. Ver regras em [`docs/04_ROUTING_POLICY_AA.md`](docs/04_ROUTING_POLICY_AA.md#11-required-target-versions-user-refinement-2026-10-19).

## Comandos para começar no fork

```bash
# dentro do clone/fork claude-model-router-hook
# copie o conteúdo deste ZIP para docs/spec-router/ ou pasta de sua preferência
cat docs/spec-router/HANDOFF_TO_OPUS.md
# inicie sua sessão Claude Code habitual com o modelo que desejar
claude
```

**Atenção:** não copie `examples/routing.example.yaml` para uma configuração ativa como se o plugin já suportasse essa sintaxe. Os nomes de modelos são exemplos versionáveis, sujeitos ao catálogo real da conta, e as capacidades de hooks devem ser confirmadas em execuções reais.

## Evidências verificadas (pesquisa em 2026-10-17)

- Claude Code: documentação oficial reconhece hooks `UserPromptSubmit`, `PreToolUse`, `TaskCreated`, `SubagentStart`, `PreModelSwitch`, `PostModelSwitch`, e `PreToolUse.hookSpecificOutput.updatedInput`.
- Codex: documentação oficial descreve hooks `PreToolUse` em funções locais, `spawn_agent` (`Agent` matcher), `updatedInput` para reescrita, `model` no contexto de hook, e revisão/trust de hooks de plugins.
- `claude-model-router-hook`: classifica por heurísticas com fallback opcional; intercepta `Agent`/`Task`; mantém autoswitch desativado por padrão; implementação em Python.
- `jev-router`: seu `src/router.mjs` chama `TypeSafeClient.systemOne`, com perguntas de escolha e scores; é uma referência de API, não a arquitetura de execução pretendida.
- `guilhem/codex-subagent-router`: referência concreta de `PreToolUse` + Jev + profiles no Codex; revalidar versões, manutenção e uso no ambiente local.

Veja os links e qualificações de cada evidência em `docs/07_ADRS_RISKS_SOURCES.md`.

## Estado da implementação local

O texto acima é o pacote de planejamento original. A implementação em andamento
fica em `router_core/` e `scripts/`, no checkout local, sem ativação global.

- Backlog atual: **36/48 tarefas concluídas**; ver `tracking/tasks.csv`.
- [Telemetria privada e limites da evidência](docs/20_PRIVACY_SAFE_TELEMETRY.md).
- [Observações Claude e limitação real do advisory inicial](docs/21_CLAUDE_OBSERVATIONS_AND_ROOT_LIMIT.md).
- [Explain offline: decisões, proveniência e catálogo salvo](docs/22_OFFLINE_EXPLAIN.md).
- [Suíte offline e gate SDK obrigatório: validação local, CI remoto pendente](docs/23_OFFLINE_CONTRACT_SUITE.md).
- [Segurança e aprovações: threat model, correções e limites verificados](docs/24_SECURITY_AND_APPROVAL_BOUNDARIES.md).
- [Pacote Claude nativo, instalação isolada e rollback](docs/25_CLAUDE_PACKAGE_AND_ROLLBACK.md).
- [Inventário Claude: candidatos versus autoridade da sessão](docs/26_CLAUDE_HOOK_INVENTORY.md).
- [Latência Jev e overhead local: resultados, regressão corrigida e limites](docs/27_CLASSIFICATION_AND_LOCAL_OVERHEAD.md).
- [Piloto de resultados por tarefa: quatro estratégias e limites da comparação](docs/28_TASK_OUTCOME_PILOT.md).
- [Código gerado e testes independentes em contêiner isolado](docs/29_CODE_OUTCOME_SLICE.md).
- Claude interativo 2.1.303 forneceu `SessionStart.model`: aviso visível e
  continuação sem nova classificação foram verificados (RTE-024). O modo `-p`
  não forneceu o campo e continua degradado; não generalizar esse limite ao TUI.
- CLI/desktop e execução de pacote após confiança ainda têm gates próprios;
  testes unitários verdes não representam liberação completa.
