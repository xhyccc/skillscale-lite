# Code Complexity Analyzer

## Description

The `code-complexity` skill is designed to evaluate Python source code for complexity. It performs a two-pass analysis:
1. **AST Parsing Validation:** It parses the input Python code into an Abstract Syntax Tree (AST). It counts the number of classes and functions/methods to get a baseline metric of size and complexity.
2. **LLM Code Review:** It packages the source code and AST metrics, then uses the `llm_utils` tool to request a professional, senior software engineer level review from an LLM model. This review estimates time and space complexity and provides actionable refactoring suggestions.

## Usage

This skill expects actual Python source code to be passed via standard input (`stdin`). You can send strings of code and wait for the response.

### Example Call:
```bash
echo "def process_data(data):\n    return [x for x in data if x > 10]" | python scripts/run.py
```

### Outputs:
The skill outputs standard plain text with two main sections:
- `===== AST Analysis =====`: Hard counts of classes and functions.
- `===== LLM Review =====`: The AI's evaluation of the complexity bounds and recommendations.
