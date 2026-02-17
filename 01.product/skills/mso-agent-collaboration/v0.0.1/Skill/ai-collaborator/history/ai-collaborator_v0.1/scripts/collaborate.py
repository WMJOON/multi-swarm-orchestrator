import subprocess
import argparse
import sys
import os

def run_ai_command(provider, prompt, context_dir=None):
    # Mapping providers to their CLI paths and command patterns
    providers = {
        "codex": {
            "path": "/Users/wmjoon/.bun/bin/codex",
            "cmd": ["exec"],
            "prompt_flag": None  # Codex takes prompt as a positional argument to exec
        },
        "claude": {
            "path": "/opt/homebrew/bin/claude",
            "cmd": [], # Claude Code is often interactive, but let's assume we use it for single shots if possible
            "prompt_flag": None
        },
        "gemini": {
            "path": "/opt/homebrew/bin/gemini",
            "cmd": [],
            "prompt_flag": None
        },
        "grok": {
            "path": "grok", # Placeholder
            "cmd": [],
            "prompt_flag": None
        }
    }

    if provider not in providers:
        return f"Error: Provider {provider} not supported."

    p_config = providers[provider]
    executable = p_config["path"]
    
    # Check if executable exists
    if not os.path.exists(executable) and provider != "grok":
        # Try finding in PATH if absolute path fails
        try:
            subprocess.check_output(["which", provider])
            executable = provider
        except subprocess.CalledProcessError:
            return f"Error: {provider} CLI not found on system."

    # Build the command
    full_cmd = [executable] + p_config["cmd"]
    
    # Provider-specific handling
    if provider == "codex":
        full_cmd.append(prompt)
    elif provider == "claude":
        # Claude Code currently doesn't have a simple 'exec' like Codex in some versions, 
        # but often piped input or 'claude "prompt"' works.
        # Adjusting for standard Claude Code usage.
        full_cmd.append(prompt)
    elif provider == "gemini":
        full_cmd.append(prompt)
    else:
        full_cmd.append(prompt)

    try:
        result = subprocess.run(
            full_cmd,
            cwd=context_dir if context_dir else os.getcwd(),
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Execution failed:\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal AI CLI Collaborator")
    parser.add_argument("--provider", required=True, choices=["codex", "claude", "gemini", "grok"], help="AI Provider CLI")
    parser.add_argument("--message", required=True, help="Prompt message for the AI")
    parser.add_argument("--dir", help="Working directory for the command")

    args = parser.parse_args()
    
    output = run_ai_command(args.provider, args.message, args.dir)
    print(output)
