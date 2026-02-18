#!/usr/bin/env python3
"""
Test cache with tool_use/tool_result messages.
Verifies tool messages don't break caching.

Usage: ANTHROPIC_TOKEN=$(claude setup-token) python test_cache_tools.py
"""

import os
import requests
import time

TOKEN = os.environ.get("ANTHROPIC_TOKEN", "")

# Large system prompt (1024+ tokens required for caching)
SYSTEM_TEXT = """
You are a helpful coding assistant with access to file system tools.

Comprehensive Guide to Software Development:

Chapter 1: Code Organization - SOLID Principles
- Single Responsibility: Each module has one reason to change
- Open/Closed: Open for extension, closed for modification
- Liskov Substitution: Subtypes substitutable for base types
- Interface Segregation: Many specific interfaces better than one general
- Dependency Inversion: Depend on abstractions, not concretions

Chapter 2: Testing Strategies
- Unit Testing: Test components in isolation
- Integration Testing: Test component interactions
- E2E Testing: Test complete workflows
- Performance Testing: Verify performance requirements
- Security Testing: Identify vulnerabilities

Chapter 3: Version Control with Git
- Meaningful commit messages
- Feature branches for development
- Code review before merging
- Atomic, focused commits
- Tags for releases

Chapter 4: Documentation Standards
- README for project setup
- API docs for interfaces
- Comments explain why, not what
- Architecture decision records
- User guides for end users

Chapter 5: Modern Deployment
- CI/CD pipelines
- Infrastructure as Code
- Container orchestration
- Blue-green deployments
- Canary releases

Chapter 6: Observability
- Structured logging
- Metrics collection
- Distributed tracing
- Alerting systems
- Health dashboards

Chapter 7: Security Best Practices
- Authentication & authorization
- Encryption at rest and in transit
- Input validation
- Security audits
- Dependency scanning

Chapter 8: Performance Optimization
- Caching strategies
- CDN for static assets
- Database optimization
- Load balancing
- Async processing
""" * 4  # Ensure 1024+ tokens for caching

# Conversation WITH tool_use and tool_result
MESSAGES = [
    {
        "role": "user",
        "content": "Find all Python files in the project."
    },
    {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "I'll search for Python files."},
            {
                "type": "tool_use",
                "id": "toolu_glob_001",
                "name": "Glob",
                "input": {"pattern": "**/*.py"}
            }
        ]
    },
    {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_glob_001",
                "content": "src/main.py\nsrc/utils.py\nsrc/config.py\ntests/test_main.py\ntests/test_utils.py"
            }
        ]
    },
    {
        "role": "assistant",
        "content": "Found 5 Python files: 3 in src/ and 2 test files."
    },
    {
        "role": "user",
        "content": "What testing framework should I use based on the guide?"
    }
]

def make_request(call_num):
    """Make API request."""
    print(f"\n=== Call {call_num} ===")

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "anthropic-beta": "oauth-2025-04-20,prompt-caching-2024-07-31",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 100,
            "system": [
                {
                    "type": "text",
                    "text": SYSTEM_TEXT,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            "messages": MESSAGES,
        }
    )

    print(f"Status: {response.status_code}")

    if response.ok:
        data = response.json()
        usage = data.get('usage', {})
        text = data.get('content', [{}])[0].get('text', '')
        print(f"Response: {text[:100]}...")
        print(f"input_tokens: {usage.get('input_tokens', 0)}")
        print(f"cache_creation: {usage.get('cache_creation_input_tokens', 0)}")
        print(f"cache_read: {usage.get('cache_read_input_tokens', 0)}")
        return usage
    else:
        print(f"Error: {response.text[:500]}")
        return None


def main():
    if not TOKEN:
        print("Error: ANTHROPIC_TOKEN not set")
        print("Run: ANTHROPIC_TOKEN=$(claude setup-token) python test_cache_tools.py")
        return

    print("Testing cache WITH tool_use/tool_result messages")
    print("=" * 55)

    usage1 = make_request(1)
    if not usage1:
        return

    print("\nWaiting 2 seconds...")
    time.sleep(2)

    usage2 = make_request(2)
    if not usage2:
        return

    print("\n" + "=" * 55)
    if usage2.get('cache_read_input_tokens', 0) > 0:
        print("✓ CACHE HIT! Tool messages preserve cache compatibility.")
        print(f"  Cached: {usage2['cache_read_input_tokens']} tokens")
    elif usage1.get('cache_creation_input_tokens', 0) > 0:
        created = usage1['cache_creation_input_tokens']
        print(f"Cache created ({created} tokens) but not hit on call 2")
    else:
        print("⚠ No caching occurred")


if __name__ == "__main__":
    main()
