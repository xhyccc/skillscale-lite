#!/usr/bin/env python3
import sys
import os
# Add skills/ root to path so llm_utils is importable
# Path: scripts/ -> skill-name/ -> skills/ -> .claude/ -> category/ -> skills/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
sys.path.insert(0, "/app/skills")

import ast
from llm_utils import chat

def analyze_complexity(code_str):
    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        return f"Syntax Error in provided code: {e}"

    class_count = 0
    func_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_count += 1
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            func_count += 1

    prompt = f"""
The following Python code was analyzed.
It contains {class_count} classes and {func_count} functions/methods.

Please provide a brief, professional summary of its code complexity, 
time/space complexity hints if applicable, and suggestions for improvement.

Code:
```python
{code_str}
```
"""

    response = chat(
        system_prompt="You are a senior python engineer answering a request to analyze code complexity.",
        user_message=prompt
    )

    return f"===== AST Analysis =====\nClasses: {class_count}\nFunctions: {func_count}\n\n===== LLM Review =====\n{response}"

if __name__ == "__main__":
    input_code = sys.stdin.read().strip()
    if not input_code:
        print("Error: No code provided to analyze.")
        sys.exit(1)
        
    print(analyze_complexity(input_code))
