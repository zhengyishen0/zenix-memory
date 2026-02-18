#!/usr/bin/env python3
"""
Minimal cache test following Anthropic docs exactly.

Usage: ANTHROPIC_TOKEN=$(claude setup-token) python test_cache_minimal.py
"""

import os
import requests
import time

TOKEN = os.environ.get("ANTHROPIC_TOKEN", "")

# Large text to ensure we hit 1024+ tokens (roughly 4 chars per token)
LARGE_TEXT = """
This is a comprehensive guide to software development best practices.

Chapter 1: Code Organization
Good code organization is essential for maintainable software. Here are the key principles:
- Single Responsibility Principle: Each module should have one reason to change
- Open/Closed Principle: Open for extension, closed for modification
- Liskov Substitution Principle: Subtypes must be substitutable for their base types
- Interface Segregation Principle: Many specific interfaces are better than one general
- Dependency Inversion Principle: Depend on abstractions, not concretions

Chapter 2: Testing Strategies
Testing is crucial for software quality. Consider these approaches:
- Unit Testing: Test individual components in isolation
- Integration Testing: Test how components work together
- End-to-End Testing: Test complete user workflows
- Performance Testing: Ensure the system meets performance requirements
- Security Testing: Identify vulnerabilities before they're exploited

Chapter 3: Version Control
Git is the standard for version control. Key practices include:
- Write meaningful commit messages
- Use feature branches for new development
- Review code before merging
- Keep commits focused and atomic
- Use tags for releases

Chapter 4: Documentation
Good documentation helps users and developers:
- README files explain project setup
- API documentation describes interfaces
- Code comments explain the why, not the what
- Architecture documents capture design decisions
- User guides help end users get started

Chapter 5: Deployment
Modern deployment practices include:
- Continuous Integration: Automatically build and test
- Continuous Deployment: Automatically deploy passed builds
- Infrastructure as Code: Define infrastructure in version control
- Containerization: Package applications with dependencies
- Orchestration: Manage containers at scale with Kubernetes

Chapter 6: Monitoring
Production systems need visibility:
- Logging: Capture events for debugging
- Metrics: Track system performance
- Alerting: Notify on-call when issues occur
- Tracing: Follow requests through distributed systems
- Dashboards: Visualize system health

Chapter 7: Security
Security is everyone's responsibility:
- Authentication: Verify user identity
- Authorization: Control access to resources
- Encryption: Protect data in transit and at rest
- Input Validation: Prevent injection attacks
- Regular Audits: Review security posture

Chapter 8: Performance
Fast systems keep users happy:
- Caching: Store frequently accessed data
- CDN: Serve static assets from edge locations
- Database Optimization: Use indexes and query analysis
- Load Balancing: Distribute traffic across servers
- Async Processing: Handle slow operations in background

This guide provides a foundation for building quality software.
""" * 2  # Repeat to ensure 1024+ tokens

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
            "max_tokens": 50,
            "system": [
                {
                    "type": "text",
                    "text": LARGE_TEXT,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            "messages": [
                {"role": "user", "content": "Summarize chapter 1 in one sentence."}
            ],
        }
    )

    print(f"Status: {response.status_code}")

    if response.ok:
        data = response.json()
        usage = data.get('usage', {})
        print(f"Response: {data.get('content', [{}])[0].get('text', '')[:80]}...")
        print(f"input_tokens: {usage.get('input_tokens', 0)}")
        print(f"cache_creation: {usage.get('cache_creation_input_tokens', 0)}")
        print(f"cache_read: {usage.get('cache_read_input_tokens', 0)}")
        return usage
    else:
        print(f"Error: {response.text}")
        return None


def main():
    if not TOKEN:
        print("Error: ANTHROPIC_TOKEN not set")
        print("Run: ANTHROPIC_TOKEN=$(claude setup-token) python test_cache_minimal.py")
        return

    print("Minimal cache test")
    print("=" * 50)

    usage1 = make_request(1)
    if not usage1:
        return

    print("\nWaiting 2 seconds...")
    time.sleep(2)

    usage2 = make_request(2)
    if not usage2:
        return

    print("\n" + "=" * 50)
    if usage2.get('cache_read_input_tokens', 0) > 0:
        print(f"✓ CACHE HIT! Read {usage2['cache_read_input_tokens']} cached tokens")
    elif usage1.get('cache_creation_input_tokens', 0) > 0:
        print("Cache created on call 1, but not hit on call 2")
    else:
        print("⚠ No caching occurred")


if __name__ == "__main__":
    main()
