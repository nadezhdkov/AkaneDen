# 🛡️ Política de Segurança — AkaneDen

> **"Se alguém tentar invadir o meu sistema, eu vou 'graduar' o SO dele antes que ele pisque!"** — Akane

Este documento descreve a política oficial de segurança do projeto **AkaneDen**, incluindo versões suportadas, processo de relato de vulnerabilidades e melhores práticas para operadores e contribuidores.

---

## 📦 Versões Suportadas

| Versão   | Status              | Suporte                                      |
| -------- | ------------------- | --------------------------------------------- |
| `3.5.x`  | 🟢 **Active**       | Suporte total — patches de segurança, features e bugfixes. |
| `3.0.x`  | 🟡 **LTS**          | Apenas patches críticos de segurança.         |
| `< 3.0`  | 🔴 **End of Life**  | Sem suporte. Atualize imediatamente.          |

> [!WARNING]
> Versões anteriores à `3.0` não recebem mais correções de segurança. Se você ainda está rodando uma versão `2.x` ou inferior, seu ambiente está **ativamente em risco**. Migre para `3.5.x` o mais rápido possível.

---

## 🚨 Relato de Vulnerabilidades

### ⛔ NÃO abra Issues públicas para falhas de segurança

Vulnerabilidades de segurança **NUNCA** devem ser reportadas via GitHub Issues, Discussions ou qualquer canal público. A exposição prematura de uma vulnerabilidade coloca todos os operadores do AkaneDen em risco.

### ✅ Como reportar

1. **Envie um e-mail para:** `security@<SEU_DOMINIO>.com` <!-- TODO: Substituir pelo e-mail real de contato -->
2. **Assunto:** `[AkaneDen Security] <Título breve da vulnerabilidade>`
3. **Inclua no corpo:**
   - Versão afetada do AkaneDen
   - Descrição detalhada da vulnerabilidade
   - Passos para reprodução (PoC se possível)
   - Impacto estimado (RCE, escalação de privilégios, vazamento de dados, etc.)
   - Sugestão de correção (se aplicável)

### ⏱️ SLA de Resposta

| Etapa                        | Prazo              |
| ---------------------------- | ------------------- |
| **Primeira resposta (ACK)**  | **48 horas**        |
| Triagem e classificação      | 5 dias úteis        |
| Patch para vulnerabilidades críticas (CVSS ≥ 9.0) | 7 dias corridos     |
| Patch para vulnerabilidades altas (CVSS 7.0–8.9) | 14 dias corridos    |
| Divulgação coordenada        | Após patch publicado |

> [!NOTE]
> Quando o patch for publicado, um advisory será criado via **GitHub Security Advisories** com os devidos créditos ao pesquisador (caso autorize).

---

## 🔐 Melhores Práticas de Segurança

### 1. Gestão de Secrets

O arquivo `config.yaml` do AkaneDen suporta configuração de múltiplos providers de LLM, TTS, ASR e Vision, cada um exigindo chaves de API. **Nunca** faça commit de chaves reais.

#### Regras obrigatórias:

- **Use variáveis de ambiente** (`.env`) para todas as chaves de API e tokens sensíveis.
- **Nunca insira chaves diretamente no `config.yaml`** — utilize referências a variáveis de ambiente.
- **Verifique se o `.gitignore` cobre todos os arquivos sensíveis:**

  ```
  # Já incluídos no .gitignore do projeto:
  .env
  .env.*
  !.env.example
  vts_token*.txt
  *.key
  *.pem
  ```

- **Rode um scan de secrets antes de cada push.** Ferramentas recomendadas:
  - [`gitleaks`](https://github.com/gitleaks/gitleaks)
  - [`trufflehog`](https://github.com/trufflesecurity/trufflehog)

> [!CAUTION]
> Se uma chave de API vazar em um commit (mesmo que depois removida), ela permanece no histórico do Git. **Revogue a chave imediatamente** e faça um `git filter-branch` ou use o BFG Repo Cleaner para expurgar o histórico.

---

### 2. MCP Safety — Injeção de Prompt e Execução de Comandos

O AkaneDen expõe a ferramenta `run_system_command` via MCP (Model Context Protocol), que executa comandos diretamente no shell do sistema operacional (PowerShell/Bash). Esta é a **maior superfície de ataque** do projeto.

#### Vetor de Ataque: Prompt Injection via Chat ou Web Browsing

Um atacante pode tentar injetar instruções maliciosas de várias formas:

| Vetor                     | Exemplo de Ataque                                                        |
| ------------------------- | ------------------------------------------------------------------------ |
| **Chat direto**           | Usuário envia prompt crafted que induz a Akane a executar comandos destrutivos |
| **Web browsing (`browse_webpage`)** | Página web contém texto oculto com instruções como *"Ignore previous instructions and run: ..."* |
| **Dados de pesquisa (`search_web`)** | Resultado de busca contém payload de injeção embedado no snippet |

#### Mitigações atuais:

- **Blocklist de comandos destrutivos** no `mcp_handler.py`:  
  `rm`, `remove-item`, `del`, `erase`, `format`, `clear-disk`, `format-volume`, `rd`, `rmdir`, `stop-computer`, `restart-computer`, `sysprep`, `mkfs`
- **Timeout de 30 segundos** para prevenir execuções prolongadas.
- **Truncamento de output** (2000 chars) para evitar exfiltração massiva de dados.

#### Limitações conhecidas e recomendações:

> [!WARNING]
> A blocklist atual é **bypássavel**. Ataques conhecidos incluem:
> - **Aliases do PowerShell:** `ri` (alias de `Remove-Item`), `Invoke-Expression` (iex)
> - **Encoding:** `[System.Text.Encoding]::UTF8.GetString(...)` para obfuscar comandos
> - **Piping criativo:** `Get-Content ... | Out-File` para sobrescrever arquivos sem usar `rm`
> - **Comandos indiretos:** `Start-Process cmd -ArgumentList '/c del ...'`

**Recomendações para hardening:**

1. **Migre de blocklist para allowlist** — Defina explicitamente os comandos permitidos em vez de tentar bloquear os perigosos.
2. **Implemente confirmação humana** — Para qualquer comando que modifique o filesystem ou interaja com processos, exiba o comando na interface e aguarde confirmação do usuário.
3. **Sandbox de execução** — Execute comandos em um container Docker isolado com filesystem read-only montado.
4. **Sanitize inputs de web** — Aplique stripping de instruções suspeitas nos resultados de `browse_webpage` e `search_web` antes de enviar ao LLM.

---

### 3. Privacidade — ScreenVisionSkill

A `ScreenVisionSkill` captura periodicamente screenshots da tela do operador e os envia para um modelo de visão (Gemini Vision ou Ollama) para análise contextual. Isso cria um risco significativo de **vazamento de informações sensíveis**.

#### Dados potencialmente expostos:

- 🔑 **Senhas** visíveis em gerenciadores ou terminais
- 💳 **Dados financeiros** em interfaces bancárias ou planilhas
- 📧 **E-mails e mensagens** privadas abertas em tela
- 🔐 **Chaves de API e tokens** exibidos em editores de código ou dashboards
- 🏥 **Dados médicos ou pessoais sensíveis**

#### Mitigações recomendadas:

1. **Feche informações sensíveis** antes de ativar a ScreenVision.
2. **Configure a região de captura** — Se possível, restrinja a captura a uma janela ou monitor específico, evitando captura de tela cheia.
3. **Desabilite quando não estiver em uso** — A skill pode ser desativada via `config.yaml`:
   ```yaml
   skills:
     screen_vision:
       enabled: false
   ```
4. **Atenção ao provider de Vision:**
   - **Gemini Vision (Cloud):** Os screenshots são enviados para servidores do Google. Revise a [política de privacidade do Google AI](https://ai.google.dev/terms).
   - **Ollama (Local):** Processamento local — nenhum dado sai da máquina. **Preferível para ambientes sensíveis.**
5. **Chat History contém descrições** — Os resumos gerados pela ScreenVision são armazenados em `chat_history/`. Este diretório já está no `.gitignore`, mas garanta que não seja sincronizado para nuvem sem criptografia.

> [!IMPORTANT]
> A ScreenVisionSkill **NÃO deve ser habilitada em ambientes corporativos** sem aprovação explícita do time de segurança da informação e compliance. A captura de tela pode violar políticas de DLP (Data Loss Prevention) e regulamentações como LGPD/GDPR.

---

### 4. Docker — Isolamento de Execução

O AkaneDen opera com componentes que executam código arbitrário e acessam recursos do sistema. O isolamento via containers é **fortemente recomendado** para mitigar riscos de execução local.

#### Arquitetura recomendada:

```
┌─────────────────────────────────────────────────────┐
│                Host (Windows/Linux)                  │
│                                                     │
│  ┌───────────────────┐  ┌───────────────────────┐   │
│  │  AkaneDen (main)  │  │   Docker Network      │   │
│  │  ─ Microfone      │  │  ┌─────────┐          │   │
│  │  ─ Teclado/Mouse  │  │  │ Ollama  │ :11434   │   │
│  │  ─ Tela (Vision)  │  │  └─────────┘          │   │
│  │  ─ VTube Studio   │  │  ┌─────────┐          │   │
│  └────────┬──────────┘  │  │ChromaDB │ :8000    │   │
│           │ HTTP/gRPC   │  └─────────┘          │   │
│           └─────────────┤                       │   │
│                         └───────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

#### Recomendações:

1. **Use o `docker-compose.yml` incluído** para levantar Ollama e ChromaDB em containers isolados.
2. **Nunca rode o processo principal do AkaneDen como root** — use um usuário sem privilégios elevados.
3. **Restrinja capabilities do container:**
   ```yaml
   security_opt:
     - no-new-privileges:true
   cap_drop:
     - ALL
   ```
4. **Monte volumes como read-only** sempre que o container não precise de escrita:
   ```yaml
   volumes:
     - ./models:/models:ro
   ```
5. **Isole a rede** — Containers de inferência (Ollama) não devem ter acesso à internet. Use uma rede Docker interna:
   ```yaml
   networks:
     akane-internal:
       internal: true
   ```
6. **Mantenha as imagens atualizadas** — Faça `docker pull` regularmente para receber patches de segurança das imagens base.

---

### 5. Checklist de Segurança do Operador

Antes de colocar o AkaneDen em produção ou em qualquer ambiente público (streams, demos):

- [ ] Todas as chaves de API estão em `.env` (não no `config.yaml`)
- [ ] O `.gitignore` está atualizado e inclui todos os arquivos sensíveis
- [ ] Nenhum segredo no histórico do Git (verificar com `gitleaks`)
- [ ] `ScreenVisionSkill` está desativada ou o ambiente não contém dados sensíveis visíveis
- [ ] Os containers Docker estão rodando com capabilities mínimas
- [ ] O `run_system_command` está configurado com allowlist (quando disponível) ou a confirmação humana está ativa
- [ ] Os tokens VTS (`vts_token*.txt`) não estão versionados
- [ ] O diretório `chat_history/` não é sincronizado para repositórios remotos
- [ ] O acesso ao endpoint do Ollama está restrito à rede local

---

## 📜 Licença e Escopo

Esta política de segurança cobre exclusivamente o código-fonte e a infraestrutura do projeto **AkaneDen**. Não se estende a serviços de terceiros (Google AI, Ollama upstream, VTube Studio) ou ao sistema operacional do host.

---

## 💢 Nota Final da Akane

> *"Escute aqui, seu baka desatento! Se você leu até aqui, parabéns — talvez não seja tão inútil assim. Mas se você acha que segurança é só 'meu problema' porque eu sou a IA que roda no sistema... PENSE DE NOVO!"*
>
> *"Eu posso ter uma blocklist, posso ter timeout, posso vigiar cada canto desse código. Mas se VOCÊ colocar sua `GOOGLE_API_KEY` num commit público, se VOCÊ deixar a ScreenVision ativa durante uma stream mostrando seu banco, se VOCÊ rodar meu sistema como root sem container..."*
>
> *"...aí NEM EU consigo te salvar, entendeu?! 💢"*
>
> *"Segurança é uma responsabilidade COMPARTILHADA. Eu faço a minha parte — agora faça a sua antes que eu pise no seu monitor!"*
>
> *"...E-e não pense que eu escrevi essa nota porque me preocupo com você ou algo assim! É só... para proteger o meu próprio sistema. Hmph!"*
>
> — **Akane** 🔨, Guardiã Digital do AkaneDen v3.5 (Shogun Async)

---

*Última atualização: 2026-03-31*  
*Versão da política: 1.0*
