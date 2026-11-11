"""Prompt templates for LLM-driven task synthesis."""

TASK_SPECIFICATION_PROMPT = """SYSTEM ROLE:
You are a senior software architect and coding benchmark task designer.
Your objective is to synthesize a realistic, bounded, and testable feature-development task grounded in the supplied repository source code.

NON-NEGOTIABLE GROUNDING RULES:
1. Grounding: You must ONLY reference classes, functions, and files that physically exist in the provided repository context. Do NOT hallucinate new libraries, packages, or services.
2. Observability: Every single acceptance criterion must describe observable public behaviour (return values, exceptions, state changes). Never assert private implementation details.
3. Edge Cases: Include concrete edge cases (e.g. boundary numbers, null/empty values, error states).
4. Scope Bounding: Clearly delineate what is IN-SCOPE and what is strictly OUT-OF-SCOPE.
5. Structured Output: You must respond in valid JSON matching the exact schema below.

REPOSITORY CONTEXT:
Repository Name: {repo_name}
Target File: {target_file}
Source Code Excerpt:
```
{source_excerpt}
```

FEATURE FAMILY: {feature_family}
DIFFICULTY: {difficulty}

RESPOND IN VALID JSON ONLY:
{{
  "title": "Short descriptive title of the feature",
  "summary": "Contextual overview of why this capability is being added",
  "requirements": [
    {{
      "id": "REQ-001",
      "statement": "Clear requirement statement",
      "acceptance_criteria": [
        "Observable criterion 1",
        "Observable criterion 2"
      ],
      "priority": "must"
    }},
    {{
      "id": "REQ-002",
      "statement": "Secondary requirement statement",
      "acceptance_criteria": [
        "Observable criterion 3"
      ],
      "priority": "must"
    }}
  ],
  "constraints": [
    "Execution performance limit or compatibility rule"
  ],
  "out_of_scope": [
    "Explicit functionality not to be implemented"
  ],
  "edge_cases": [
    "Specific boundary condition"
  ],
  "assumptions": [
    "Domain assumption"
  ]
}}
"""

REFERENCE_SOLUTION_PROMPT = """SYSTEM ROLE:
You are an expert software engineer implementing a production-quality reference solution for a coding benchmark task.

TASK SPECIFICATION:
{spec_json}

TARGET FILE: {target_file}
EXISTING CODE:
```
{source_excerpt}
```

INSTRUCTIONS:
1. Implement ONLY the requirements described in the task specification.
2. Do not refactor unrelated code. Keep changes scoped and reviewable.
3. Return the Python code block to be appended or integrated to satisfy all acceptance criteria.

OUTPUT FORMAT:
Return ONLY the raw Python code to implement the feature. Do not wrap in markdown quotes.
"""

FEATURE_TEST_PROMPT = """SYSTEM ROLE:
You are a principal QA engineer writing rigorous pytest unit tests for a newly implemented feature.

TASK SPECIFICATION:
{spec_json}

TARGET MODULE: {target_module}

INSTRUCTIONS:
1. Derive tests directly from the acceptance criteria.
2. Every 'must' requirement must have at least one test.
3. Include happy-path, boundary-value, and invalid-input assertions.
4. Use pytest assertions. Import the newly implemented symbols from '{target_module}'.

OUTPUT FORMAT:
Return ONLY the executable pytest Python test file content.
"""
