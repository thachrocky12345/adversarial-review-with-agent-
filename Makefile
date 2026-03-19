# Makefile for Adversarial Review Pipeline

.PHONY: init install run clean help

# Default target
help:
	@echo "Available targets:"
	@echo "  init     - Run post_init hook and prepare for /init in Claude Code"
	@echo "  install  - Install Python dependencies"
	@echo "  run      - Run the demo"
	@echo "  clean    - Remove generated files and caches"
	@echo "  help     - Show this help message"

# Initialize Claude Code context
init:
	@bash .claude/hooks/post_init.sh
	@echo ""
	@echo "Now run /init inside Claude Code to sync AI context"

# Install dependencies
install:
	pip install -r requirements.txt

# Run the demo
run:
	python main.py

# Clean generated files
clean:
	rm -rf __pycache__ *.pyc .pytest_cache .mypy_cache
	rm -f docs/structure.md
	rm -f docs/decisions/.pending_adr_review
