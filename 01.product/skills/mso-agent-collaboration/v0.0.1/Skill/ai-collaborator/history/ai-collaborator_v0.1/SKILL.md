---
name: ai-collaborator
description: Unified interface for collaborating with multiple AI provider CLIs (Codex, Claude Code, Gemini, Grok). Use this skill when you need a "second opinion," alternative perspectives, or specialized validation from other AI models via their local CLI tools.
---

# Universal AI CLI Collaborator Skill

This skill provides a unified gateway to multiple AI CLI tools installed on your system. It simplifies the process of consulting different models by providing a consistent execution pattern.

## 1. Supported Providers

- **Codex**: Best for overall AX/AI strategy and general-purpose reasoning.
- **Claude Code**: High-performance coding assistant and logical analyzer.
- **Gemini CLI**: Strong in Google Ecosystem integration and localized context.
- **Grok CLI**: Placeholder for X.AI's model (if available).

## 2. When to Use

- **Cross-Verification**: Compare how different models (e.g., Claude vs. Gemini) critique a single plan.
- **Specialized Advice**: Use Gemini for Google-specific tasks and Claude for complex code refactoring.
- **Red Team Analysis**: Run multiple "Senior Critics" simultaneously on a PRD or design doc.

## 3. How to Use (Workflow)

You can call the unified `collaborate.py` script to reach any provider.

### Execution Command
```bash
python3 "/Users/wmjoon/Library/Mobile Documents/iCloud~md~obsidian/Documents/wmjoon/skills/skills/ai-collaborator/scripts/collaborate.py" --provider [codex|claude|gemini|grok] --message "[Your Prompt]"
```

### Pattern: The "Council of Elders"
When a decision is critical, consult multiple providers:
1. `python3 collaborate.py --provider codex --message "Critique this PRD: [Content]"`
2. `python3 collaborate.py --provider gemini --message "How does this PRD align with Google AI standards? [Content]"`
3. Consolidate the findings and present them to the user.

## 4. Operational Principles

- **Persona**: Always instruct the target CLI AI to act as a "Senior Specialist" or "Red Team Critic."
- **Context**: Provide relevant file paths or content snippets in the `--message`.
- **Triangulation**: If two models disagree, use a third model to break the tie or ask the user for clarification.
