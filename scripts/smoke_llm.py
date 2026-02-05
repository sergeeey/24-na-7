#!/usr/bin/env python3
"""Smoke test для LLM провайдеров."""
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm.providers import get_llm_client


def main():
    """Запускает smoke test."""
    print("=" * 70)
    print("LLM Provider Smoke Test")
    print("=" * 70)
    
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "actor": {},
        "critic": {},
        "summary": {
            "all_passed": True
        }
    }
    
    # Тест Actor
    print("\n[1] Testing Actor client...")
    actor_client = get_llm_client(role="actor")
    
    if actor_client:
        test_prompt = "Say 'Hello, Reflexio!' in one sentence."
        response = actor_client.call(prompt=test_prompt, max_tokens=50)
        
        results["actor"] = {
            "initialized": True,
            "provider": actor_client.provider.value,
            "model": actor_client.model,
            "response_received": bool(response.get("text")),
            "has_error": bool(response.get("error")),
            "tokens_used": response.get("tokens_used", 0),
            "latency_ms": response.get("latency_ms", 0),
            "error": response.get("error"),
        }
        
        if response.get("error"):
            print(f"  ❌ Actor failed: {response['error']}")
            results["summary"]["all_passed"] = False
        elif response.get("text"):
            print(f"  ✅ Actor OK: {response['text'][:50]}...")
            print(f"     Tokens: {response['tokens_used']}, Latency: {response['latency_ms']}ms")
        else:
            print("  ⚠️  Actor: No response")
            results["summary"]["all_passed"] = False
    else:
        print("  ⚠️  Actor: Client not initialized (missing API key?)")
        results["actor"] = {"initialized": False}
        results["summary"]["all_passed"] = False
    
    # Тест Critic
    print("\n[2] Testing Critic client...")
    critic_client = get_llm_client(role="critic")
    
    if critic_client:
        test_prompt = "Verify: 'Python is a programming language.' Supported by source: 'Python is a high-level programming language.'"
        response = critic_client.call(prompt=test_prompt, max_tokens=100)
        
        results["critic"] = {
            "initialized": True,
            "provider": critic_client.provider.value,
            "model": critic_client.model,
            "response_received": bool(response.get("text")),
            "has_error": bool(response.get("error")),
            "tokens_used": response.get("tokens_used", 0),
            "latency_ms": response.get("latency_ms", 0),
            "error": response.get("error"),
        }
        
        if response.get("error"):
            print(f"  ❌ Critic failed: {response['error']}")
            results["summary"]["all_passed"] = False
        elif response.get("text"):
            print(f"  ✅ Critic OK: {response['text'][:50]}...")
            print(f"     Tokens: {response['tokens_used']}, Latency: {response['latency_ms']}ms")
        else:
            print("  ⚠️  Critic: No response")
            results["summary"]["all_passed"] = False
    else:
        print("  ⚠️  Critic: Client not initialized (missing API key?)")
        results["critic"] = {"initialized": False}
        results["summary"]["all_passed"] = False
    
    # Сохраняем отчёт
    output_path = Path(".cursor/audit/llm_smoke.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 70)
    print(f"Summary: {'✅ PASSED' if results['summary']['all_passed'] else '❌ FAILED'}")
    print(f"Report saved: {output_path}")
    print("=" * 70)
    
    return 0 if results["summary"]["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())











