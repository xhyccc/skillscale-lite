# Dead Code Detector

## Description

The `dead-code-detector` skill analyzes Python source code to proactively find dead, unused, or unreachable code via Abstract Syntax Tree (AST) scanning combined with LLM inference.
1. **AST Dead Code Scan:** Uses native Python libraries or AST logic to identify variables that are assigned but never read, imports that are present but never invoked, and functions that are completely empty or logically unreachable.
2. **LLM Confirmation:** An LLM agent reviews the findings to provide contextual explanations and proposes a cleaner version of the code snippet.

## Usage

Pass your raw Python code as input via `stdin`. The script parses the input directly.

### Example Call:
```bash
echo "import os\n\ndef my_func():\n    x = 10\n    return 5\n" | python scripts/run.py
```

### Outputs:
The skill outputs standard plain text with two main sections:
- `===== AST Analysis =====`: Basic counts or observations from the code layout.
- `===== LLM Review =====`: A detailed markdown evaluation with suggestions for deleting unused variables or imports.
