#!/usr/bin/env python3
import sys
import os
# Add skills/ root to path so llm_utils is importable
# Path: scripts/ -> skill-name/ -> skills/ -> .claude/ -> category/ -> skills/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
sys.path.insert(0, "/app/skills")

import ast
from llm_utils import chat

class ImportScanner(ast.NodeVisitor):
    def __init__(self):
        self.imports = set()

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            self.imports.add(alias.asname or alias.name)
        self.generic_visit(node)

def analyze_dead_code(code_str):
    try:
        tree = ast.parse(code_str)
    except Exception as e:
        return f"Could not parse code: {e}"

    # Minimal AST heuristics 
    scanner = ImportScanner()
    scanner.visit(tree)
    imports_found = list(scanner.imports)

    prompt = f"""
You are an expert Python developer tasked with identifying "dead code" (unused imports, unused variables, unreachable branches, and redundant paths).

Analyze the following snippet. Note any code that can be safely deleted without changing program behavior.

Code chunk:
```python
{code_str}
```

Please structure your response:
1. Identified Dead Code: List the specific lines/variables/imports.
2. Refactored Code: Provide the clean version of the code snippet.
"""

    llm_review = chat(
        system_prompt="You are a code optimization expert.",
        user_message=prompt
    )

    return f"===== AST Analysis =====\nImports Detected: {imports_found}\n\n===== LLM Review =====\n{llm_review}"

if __name__ == "__main__":
    input_code = sys.stdin.read().strip()
    if not input_code:
        print("Error: No code provided to analyze.")
        sys.exit(1)
        
    print(analyze_dead_code(input_code))