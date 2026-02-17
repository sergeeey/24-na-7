#!/usr/bin/env python3
"""
Test Hook Event — имитация событий для проверки реакции хуков.
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Импортируем через путь
hooks_path = Path(__file__).parent.parent / ".cursor" / "hooks" / "on_event.py"
import importlib.util
spec = importlib.util.spec_from_file_location("on_event", hooks_path)
on_event_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(on_event_module)
handle_event = on_event_module.handle_event


def main():
    """Основная функция."""
    parser = argparse.ArgumentParser(description="Test hook event")
    parser.add_argument("event", help="Event name (e.g., low_confidence_detected)")
    parser.add_argument("payload", nargs="?", default="", help="Event payload")
    
    args = parser.parse_args()
    
    print(f"Testing hook event: {args.event}")
    print(f"Payload: {args.payload}")
    print()
    
    result = handle_event(args.event, args.payload)
    
    if result.get("handled"):
        print(f"✅ Event handled: {result.get('hook')}")
        if result.get("action"):
            print(f"   Action: {result['action']}")
    else:
        print(f"⚠️  Event not handled (no hook configured or disabled)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
