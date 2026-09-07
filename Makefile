check-deps:
	@! git grep -nE "^(from|import) projects" -- 'packages/chatkit/**/*.py' || (echo "chatkit must not import projects.*" && exit 1)
	@echo "dependency direction OK"

.PHONY: check-deps
