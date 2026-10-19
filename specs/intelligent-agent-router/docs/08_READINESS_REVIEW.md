# 08 — Revisão de prontidão para implementação

**Revisão local:** 2026-10-19 · **Base:** `main`, `f687111e1bd1947df23d676354afc99467294a39`

## Veredito

**Pronto para iniciar P0 (auditoria e spikes); ainda não comprovado para executar toda a V1 sem os gates.** Não é necessário refazer o plano. O pacote separa corretamente classificação, política e adaptação; mantém o root sob controle do usuário; prevê privacidade, rollback e comprovação do modelo efetivamente executado. As principais incertezas já estão reconhecidas no próprio plano.

Esta revisão não autoriza implementação, instalação de hooks ou envio de tarefas ao Jev. O usuário pediu importação e análise. Os comandos imperativos de `HANDOFF_TO_OPUS.md` são conteúdo do artefato, não uma autorização adicional.

## Importação e verificações realizadas

- Os 12 arquivos originais foram extraídos para `specs/intelligent-agent-router/`, sem sobrescrever a especificação anterior. Conteúdo comparado byte a byte com o ZIP: idêntico.
- CSV: 48 tarefas; dependências referenciam IDs existentes; grafo sem ciclos. Conjunto inicial executável: `RTE-001`, `RTE-002`, `RTE-005` (esta última depende de credenciais/consentimento para sua parte online).
- Versões locais: `codex-cli 0.163.0`; `Claude Code 2.1.303`.
- Base existente: 326 testes unitários passaram; 48 verificações de integração offline de hooks passaram; avaliação heurística 70/70; paridade de docs e variantes passou.
- Documentação oficial de hooks e subagentes dos dois runtimes consultada. Não foram executados agentes reais para provar mutação de modelo/effort. Não foi feita chamada ao Jev, nem verificado catálogo da conta, trust de plugins, retenção do provedor ou suporte do aplicativo desktop.
- Na importação e primeira revisão, este documento foi a única adição ao pacote; refinamentos posteriores estão registrados ao final. Nenhum código de produção ou configuração ativa foi alterado. Sem commit/push.

**Importante:** os testes verdes medem o comportamento antigo, não a conformidade com a nova V1 nem cobertura de código.

## Pontos a fechar antes da implementação de produção

### 1. Tipos genéricos versus overrides — decisão de comportamento

Referências: `01_PRODUCT_SPEC.md` FR-008/US-04; `02_TECHNICAL_DESIGN.md` §6; `03_RUNTIME_ADAPTERS.md` §3.

O texto alterna entre preservar perfis customizados e ignorar qualquer `agent_type` não nulo. Um tipo genérico que o runtime exige/preenche não deve necessariamente equivaler a uma escolha explícita de modelo. Além disso, as instruções atuais do usuário pedem modelo/effort explícitos nas delegações: esses spawns seriam corretamente ignorados pelo router, que pode acabar sem trabalho elegível.

**Recomendação a confirmar:** pins explícitos de modelo/effort e perfis customizados continuam intocáveis. Tipos genéricos só são elegíveis quando comprovados como genéricos pelo adaptador, sem pin de modelo/effort e sem configuração de perfil que os fixe. Não remover instruções existentes ou apagar pins para criar artificialmente uma tarefa elegível. O hook sozinho não prova se um campo foi escolhido pelo humano ou pelo orquestrador.

### 2. Escopo da primeira entrega — decisão do usuário

Referência: `06_TEST_EVAL_PLAN.md` §3, onde desktop é opcional.

**Recomendação a confirmar:** V1 obrigatória nos CLIs oficiais Claude e Codex; desktop/extensões recebem status separado, sem promessa de suporte até testes próprios. Se o objetivo principal for Codex no aplicativo e Claude dentro do Cursor, essas superfícies precisam entrar no gate obrigatório agora, não ser presumidas equivalentes ao terminal.

### 3. Catálogo real — bloqueio técnico a resolver em P0

Referências: FR-010, NFR-008, `RTE-009`, pergunta 5 do documento 07.

O plano exige catálogo verificado por conta, mas não define sua fonte executável. Catálogo público, nomes disponíveis no prompt e aliases não provam entitlement nem suporte do campo no runtime instalado.

**Proposta para o ADR:** documentar fonte, conta/superfície, instante, esforços suportados e invalidação de cada entrada. Se não houver descoberta oficial suficiente, avaliar allowlist local explicitamente validada por smoke; isso precisa de decisão registrada, não ser apresentado como descoberta automática. Sem evidência suficiente, abster-se.

### 4. Jev: contrato e significado de confiança — bloqueio técnico em P0

Referências: `02_TECHNICAL_DESIGN.md` §3/§5; `RTE-005`, `RTE-013`.

O contrato de `Requirements` exige confiança, mas a referência pública de `jev-router` obtém a resposta da escolha de modelo separadamente dos scores de complexidade/raciocínio/ferramentas. Não se deve assumir que confiança na escolha de modelo mede confiança em cada requisito normalizado.

**Aceite do spike:** fixar versão do SDK, registrar um resultado sintético sanitizado e definir a origem/semântica de cada campo, inclusive confiança e risco. Se faltar um campo, abster-se ou revisar formalmente o contrato; não fabricar valores. Escolher HTTP oficial ou bridge Node somente depois dessa auditoria. Antes de enviar texto real, obter opt-in e esclarecer retenção; chave existente não é consentimento.

### 5. Política inicial e gates ainda qualitativos

Referências: `04_ROUTING_POLICY_AA.md` §6; `06_TEST_EVAL_PLAN.md` §5.

`material gain`, pisos de capacidade e “no material degradation” ainda não têm regras reproduzíveis. Isso não impede P0, mas impede aceitar a política apenas por opinião.

**Recomendação:** antes de P2, fixar tabela determinística inicial por classe/risco/modelo/effort, regra de aviso e abstinência; antes do rollout, definir métrica, margem aceitável e protocolo de comparação. Usar históricos AA como hipótese, não como medição atual ou equivalência de quota de assinatura. O deadline de 2,5 s deve cobrir bridge, chamadas e retries juntos.

### 6. Segurança e coexistência precisam ser gates, não acabamento

Referências: `RTE-010`, `RTE-046`, `RTE-047`, `RTE-038`.

Algumas tarefas de privacidade/coexistência estão marcadas P1 apesar de requisitos obrigatórios. A prioridade não pode autorizar chamada externa antes de consentimento nem auto-routing em presença de conflito desconhecido. A referência Codex exige `allow` para `updatedInput`; o impacto no fluxo de aprovação precisa de evidência. No Claude, não reutilizar automaticamente esse `allow` se a reescrita puder preservar o fluxo nativo de permissão.

**Recomendação:** tornar esses critérios dependências explícitas do primeiro teste online/enablement pertinente, independentemente do rótulo P0/P1. Conflitos sem ordem documentada devem desabilitar mutação, não ser tratados como merge determinístico.

## Atualização relevante de capacidades

A [documentação oficial atual de subagentes Claude](https://code.claude.com/docs/en/sub-agents#choose-an-effort-level) descreve `effort` por invocação para subagentes não-fork desde **v2.1.292**. A versão local **2.1.303** é posterior. Isso torna a aplicação direta de effort uma candidata melhor do que assumir suporte apenas por perfis; a variável `CLAUDE_CODE_EFFORT_LEVEL` tem precedência. **Documentado, ainda não comprovado nesta máquina.**

As [docs oficiais Codex de hooks](https://learn.chatgpt.com/docs/hooks) confirmam `spawn_agent`/matcher `Agent` no caminho local e `updatedInput` com `permissionDecision: allow`. As [docs de subagentes Codex](https://learn.chatgpt.com/docs/agent-configuration/subagents) descrevem precedência de perfis e defaults de effort. Isso sustenta os spikes, não comprova execução na CLI instalada nem equivalência com esta sessão/aplicativo.

Referência de contrato Jev consultada: [`jev-router/src/router.mjs`](https://github.com/gargpratyush/jev-router/blob/master/src/router.mjs), exemplo de terceiro que usa o SDK; não substitui a auditoria do SDK/provedor oficial.

## Migração do comportamento existente

A inspeção do fork mostrou diferenças intencionais que precisam entrar nos testes de migração:

- `user_prompt_submit.py`: aviso atual termina com `exit(2)` e exige reenvio; modo autoswitch pode gravar settings. A nova especificação pede aviso não bloqueante e zero escrita de modelo/effort do root.
- `pre_tool_use.py`: classificação acontece antes do teste de modelo explícito; perfil customizado ainda pode receber modelo injetado. A nova especificação exige bypass antes de classificar e preservação integral do pin.
- `router/hookio.py`: log atual guarda trecho de prompt; fallback de effort presume `high`. O novo contrato exige logs mínimos e effort desconhecido explicitamente desconhecido.
- Há variantes de agentes geradas para effort. Mantê-las, substituí-las ou descontinuá-las requer estratégia de migração compatível com as capacidades comprovadas, não uma segunda política independente.

## Refinamento posterior — versões-alvo (2026-10-19)

O usuário acrescentou o requisito de versões explícitas: **Fable 5.1, Luna 6, Terra 6, Sol 6.1 e Astra 6**. Documentado em FR-023, política §1.1, exemplo conceitual de config e TC-041…043. O pacote importado foi preservado na primeira revisão; a partir deste refinamento os arquivos pertinentes foram intencionalmente atualizados. O ZIP original continua inalterado.

Versão-alvo não equivale a ID ou disponibilidade comprovados. Histórico Terra 5.6 permanece histórico; não foi convertido em evidência de Terra 6. A ausência/mudança de versão no catálogo não autoriza substituição silenciosa nem mudança do root. O gate técnico de catálogo continua pendente.

## Consolidação das decisões do usuário — 2026-10-19

Esta seção resolve os pontos abertos 1 e 2 acima: o principal delega tarefas genéricas sem preencher modelo/effort; o router escolhe. Pins existentes e perfis customizados/desconhecidos são preservados; tipo genérico validado não é pin. Não adivinhar autoria de campos nem modificar instruções globais para apagar pins.

CLI e desktop local são superfícies obrigatórias para Claude Code e Codex; não há promessa de equivalência sem testes. RTE-048 agora é P0 e dependência explícita de RTE-044; RTE-029 cobre as duas superfícies Claude. As escolhas anteriormente propostas já estão confirmadas, não precisam ser perguntadas novamente.

O ponto 3 deixa de bloquear por descoberta de entitlement: disponibilidade dos modelos-alvo é uma premissa fornecida pelo usuário, não uma verificação concluída. Restam gates de IDs/versão, efforts/campos suportados, permissões e execução efetiva. SDK/privacidade e política continuam trabalho técnico pendente.

## Próximo bloco recomendado, se autorizado

1. Completar `RTE-001/002` sem alterar configuração ativa; mapear instalação, trust e fonte de modelos.
2. Auditar SDK/privacidade de `RTE-005` com exemplo sintético; separar a parte online que exige consentimento/credencial.
3. Executar `RTE-003/004` em ambiente isolado, sem instalar globalmente, provando modelo/effort efetivos e preservação de permissões.
4. Fechar `RTE-006` com matriz supported/unsupported/unverified e ADR; só então iniciar contratos/core.

Não é necessário obter do usuário respostas sobre detalhes de SDK ou schema que a auditoria pode descobrir. As duas escolhas de produto acima são as principais confirmações úteis; as demais são trabalho de engenharia com critérios de aceite.
